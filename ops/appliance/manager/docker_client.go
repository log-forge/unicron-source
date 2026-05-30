package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type dockerClient struct {
	socket string
	client *http.Client
}

type dockerContainerInspect struct {
	ID              string                `json:"Id"`
	Name            string                `json:"Name"`
	Image           string                `json:"Image"`
	Config          map[string]any        `json:"Config"`
	HostConfig      map[string]any        `json:"HostConfig"`
	Mounts          []map[string]any      `json:"Mounts"`
	NetworkSettings dockerNetworkSettings `json:"NetworkSettings"`
	State           dockerContainerState  `json:"State"`
}

type dockerNetworkSettings struct {
	Networks map[string]map[string]any `json:"Networks"`
}

type dockerContainerState struct {
	Status  string `json:"Status"`
	Running bool   `json:"Running"`
}

type dockerImageInspect struct {
	ID          string   `json:"Id"`
	RepoTags    []string `json:"RepoTags"`
	RepoDigests []string `json:"RepoDigests"`
}

func newDockerClient(socket string) *dockerClient {
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", socket)
		},
	}
	return &dockerClient{
		socket: socket,
		client: &http.Client{Transport: transport, Timeout: 0},
	}
}

func (c *dockerClient) ping(ctx context.Context) error {
	return c.request(ctx, http.MethodGet, "/_ping", nil, nil, nil)
}

func (c *dockerClient) inspectContainer(ctx context.Context, idOrName string) (dockerContainerInspect, error) {
	var inspect dockerContainerInspect
	err := c.request(ctx, http.MethodGet, "/containers/"+url.PathEscape(strings.TrimPrefix(idOrName, "/"))+"/json", nil, nil, &inspect)
	return inspect, err
}

func (c *dockerClient) inspectImage(ctx context.Context, ref string) (dockerImageInspect, error) {
	var inspect dockerImageInspect
	err := c.request(ctx, http.MethodGet, "/images/"+ref+"/json", nil, nil, &inspect)
	return inspect, err
}

func (c *dockerClient) pullImage(ctx context.Context, ref string) error {
	repo, tag := splitImagePullRef(ref)
	query := url.Values{"fromImage": []string{repo}}
	if tag != "" {
		query.Set("tag", tag)
	}
	resp, err := c.rawRequest(ctx, http.MethodPost, "/images/create", query, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		return fmt.Errorf("docker POST /images/create returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	decoder := json.NewDecoder(resp.Body)
	for {
		var event map[string]any
		if err := decoder.Decode(&event); err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}
		if rawErr, ok := event["error"]; ok {
			return fmt.Errorf("%v", rawErr)
		}
	}
}

func (c *dockerClient) createContainer(ctx context.Context, name string, spec map[string]any) (string, error) {
	query := url.Values{"name": []string{name}}
	var response struct {
		ID       string   `json:"Id"`
		Warnings []string `json:"Warnings"`
	}
	if err := c.request(ctx, http.MethodPost, "/containers/create", query, spec, &response); err != nil {
		return "", err
	}
	if response.ID == "" {
		return "", fmt.Errorf("docker create returned an empty container id")
	}
	return response.ID, nil
}

func (c *dockerClient) startContainer(ctx context.Context, idOrName string) error {
	return c.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(strings.TrimPrefix(idOrName, "/"))+"/start", nil, nil, nil)
}

func (c *dockerClient) stopContainer(ctx context.Context, idOrName string, timeoutSeconds int) error {
	query := url.Values{"t": []string{fmt.Sprintf("%d", timeoutSeconds)}}
	return c.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(strings.TrimPrefix(idOrName, "/"))+"/stop", query, nil, nil)
}

func (c *dockerClient) renameContainer(ctx context.Context, idOrName, newName string) error {
	query := url.Values{"name": []string{newName}}
	return c.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(strings.TrimPrefix(idOrName, "/"))+"/rename", query, nil, nil)
}

func (c *dockerClient) removeContainer(ctx context.Context, idOrName string, force bool) error {
	query := url.Values{}
	if force {
		query.Set("force", "1")
	}
	return c.request(ctx, http.MethodDelete, "/containers/"+url.PathEscape(strings.TrimPrefix(idOrName, "/")), query, nil, nil)
}

func (c *dockerClient) request(ctx context.Context, method, path string, query url.Values, body any, out any) error {
	resp, err := c.rawRequest(ctx, method, path, query, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		responseBody, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
		message := strings.TrimSpace(string(responseBody))
		if parsed := dockerErrorMessage(message); parsed != "" {
			message = parsed
		}
		return fmt.Errorf("docker %s %s returned %d: %s", method, path, resp.StatusCode, message)
	}
	if out == nil {
		_, _ = io.Copy(io.Discard, resp.Body)
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (c *dockerClient) rawRequest(ctx context.Context, method, path string, query url.Values, body any) (*http.Response, error) {
	var reader io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = bytes.NewReader(payload)
	}
	requestURL := url.URL{Scheme: "http", Host: "docker", Path: path}
	if len(query) > 0 {
		requestURL.RawQuery = query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, method, requestURL.String(), reader)
	if err != nil {
		return nil, err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return c.client.Do(req)
}

func dockerErrorMessage(body string) string {
	var parsed struct {
		Message string `json:"message"`
		Error   string `json:"error"`
	}
	if err := json.Unmarshal([]byte(body), &parsed); err != nil {
		return ""
	}
	if parsed.Message != "" {
		return parsed.Message
	}
	return parsed.Error
}

func splitImagePullRef(ref string) (string, string) {
	if strings.Contains(ref, "@") {
		return ref, ""
	}
	lastSlash := strings.LastIndex(ref, "/")
	lastColon := strings.LastIndex(ref, ":")
	if lastColon > lastSlash {
		return ref[:lastColon], ref[lastColon+1:]
	}
	return ref, "latest"
}

func dockerSocketExists(socket string) error {
	info, err := os.Stat(socket)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSocket == 0 {
		return fmt.Errorf("%s is not a socket", socket)
	}
	return nil
}

func dockerContext(parent context.Context, timeout time.Duration) (context.Context, context.CancelFunc) {
	if parent == nil {
		parent = context.Background()
	}
	return context.WithTimeout(parent, timeout)
}
