package main

import (
	"fmt"
	"os"
	"strings"
)

func renderTraefikConfig(templateBody, hostsCSV string) string {
	rule := hostsRule(hostsCSV)
	return strings.ReplaceAll(templateBody, "{{HOSTS_OR_RULES}}", rule)
}

func hostsRule(hostsCSV string) string {
	hosts := csvFields(hostsCSV)
	if len(hosts) == 0 {
		hosts = []string{"localhost", "127.0.0.1"}
	}
	parts := make([]string, 0, len(hosts))
	for _, host := range hosts {
		escaped := strings.ReplaceAll(host, "`", "\\`")
		parts = append(parts, fmt.Sprintf("Host(`%s`)", escaped))
	}
	return strings.Join(parts, " || ")
}

func renderTraefikFile(cfg RuntimeConfig) error {
	template, err := os.ReadFile(cfg.TraefikTemplateFile)
	if err != nil {
		return err
	}
	rendered := renderTraefikConfig(string(template), cfg.TraefikRouterHosts)
	if err := os.MkdirAll(dirName(cfg.TraefikDynamicConfigFile), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(cfg.TraefikDynamicConfigFile, []byte(rendered), 0o664); err != nil {
		return err
	}
	return os.Chmod(cfg.TraefikDynamicConfigFile, 0o664)
}

func dirName(path string) string {
	idx := strings.LastIndex(path, "/")
	if idx <= 0 {
		return "."
	}
	return path[:idx]
}
