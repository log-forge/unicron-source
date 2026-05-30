package main

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestDeriveCentralRootPrefixPrefersCentralURLPath(t *testing.T) {
	got := deriveCentralRootPrefix(
		"https://unicron.central/unicron",
		"wss://unicron.central:8443/unicron/api/agent/ws",
	)
	if got != "/unicron" {
		t.Fatalf("expected /unicron, got %q", got)
	}
}

func TestDeriveCentralRootPrefixFallsBackToWebSocketPath(t *testing.T) {
	got := deriveCentralRootPrefix(
		"http://unicron-central:8000",
		"wss://unicron.central:8443/unicron/api/agent/ws",
	)
	if got != "/unicron" {
		t.Fatalf("expected /unicron, got %q", got)
	}
}

func TestBuildRegisterURLUsesDerivedRootPrefix(t *testing.T) {
	got, err := buildRegisterURL(config{
		centralMTLSURL: "https://unicron.central:8443",
		centralURL:     "",
		centralWSURL:   "wss://unicron.central:8443/unicron/api/agent/ws",
	})
	if err != nil {
		t.Fatalf("buildRegisterURL failed: %v", err)
	}
	if got != "https://unicron.central:8443/unicron/api/herald/register" {
		t.Fatalf("unexpected register URL %q", got)
	}
}

func TestNormalizeCentralMTLSBaseURLStripsPath(t *testing.T) {
	got := normalizeCentralMTLSBaseURL("https://unicron.central:8443/unicron/api")
	if got != "https://unicron.central:8443" {
		t.Fatalf("expected host-only origin, got %q", got)
	}
}

func TestBuildRegisterURLNormalizesPathfulCentralMTLSURL(t *testing.T) {
	got, err := buildRegisterURL(config{
		centralMTLSURL: "https://unicron.central:8443/unicron",
		centralURL:     "https://unicron.central/unicron",
		centralWSURL:   "wss://unicron.central:8443/unicron/api/agent/ws",
	})
	if err != nil {
		t.Fatalf("buildRegisterURL failed: %v", err)
	}
	if got != "https://unicron.central:8443/unicron/api/herald/register" {
		t.Fatalf("unexpected normalized register URL %q", got)
	}
}

func TestRegisterFailureReporterReportsReasonChangesOnly(t *testing.T) {
	reporter := newRegisterFailureReporter(config{hostID: "herald", agentName: "herald"})
	var reasons []string
	reporter.send = func(_ config, reason string, _ *registerFailureDetail) error {
		reasons = append(reasons, reason)
		return nil
	}

	reporter.Report(&registerHTTPError{StatusCode: 503, Body: "db unavailable"})
	reporter.Report(&registerHTTPError{StatusCode: 503, Body: "db unavailable"})
	reporter.Report(&registerHTTPError{StatusCode: 503, Body: "reverse proxy unavailable"})
	reporter.Clear()
	reporter.Report(&registerHTTPError{StatusCode: 503, Body: "db unavailable"})

	if len(reasons) != 3 {
		t.Fatalf("expected 3 reported reasons, got %d (%v)", len(reasons), reasons)
	}
	if reasons[0] != "register returned HTTP 503: db unavailable" {
		t.Fatalf("unexpected first reason %q", reasons[0])
	}
	if reasons[1] != "register returned HTTP 503: reverse proxy unavailable" {
		t.Fatalf("unexpected second reason %q", reasons[1])
	}
	if reasons[2] != "register returned HTTP 503: db unavailable" {
		t.Fatalf("unexpected third reason %q", reasons[2])
	}
}

func TestIsRegisterRebootstrapRequiredRequiresStructured401Or403(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "401 with structured rebootstrap detail is rebootstrapable",
			err: &registerHTTPError{
				StatusCode: http.StatusUnauthorized,
				Body:       `{"detail":{"code":"REBOOTSTRAP_REQUIRED","message":"Certificate bootstrap required for fresh enrollment"}}`,
			},
			want: true,
		},
		{
			name: "plain 401 is not rebootstrapable",
			err:  &registerHTTPError{StatusCode: http.StatusUnauthorized, Body: "unknown token"},
			want: false,
		},
		{
			name: "403 with structured rebootstrap detail is rebootstrapable",
			err: &registerHTTPError{
				StatusCode: http.StatusForbidden,
				Body:       `{"detail":{"code":"REBOOTSTRAP_REQUIRED","message":"Certificate bootstrap required for fresh enrollment"}}`,
			},
			want: true,
		},
		{
			name: "plain 403 is not rebootstrapable",
			err:  &registerHTTPError{StatusCode: http.StatusForbidden, Body: "decommissioned"},
			want: false,
		},
		{
			name: "409 registration refusal is not rebootstrapable",
			err: &registerHTTPError{
				StatusCode: http.StatusConflict,
				Body:       `{"detail":{"code":"AGENT_REGISTRATION_REFUSED","message":"Agent registration was refused."}}`,
				Failure:    &registerFailureDetail{Code: "AGENT_REGISTRATION_REFUSED"},
			},
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isRegisterRebootstrapRequired(tt.err); got != tt.want {
				t.Fatalf("expected %v, got %v", tt.want, got)
			}
		})
	}
}

func TestParseRegisterFailureDetailFromStructured409(t *testing.T) {
	body := []byte(`{"detail":{"code":"AGENT_REGISTRATION_REFUSED","message":"Agent registration was refused."}}`)

	detail := parseRegisterFailureDetail(body)
	if detail == nil {
		t.Fatal("expected structured failure detail")
	}
	if detail.Code != "AGENT_REGISTRATION_REFUSED" {
		t.Fatalf("unexpected code %q", detail.Code)
	}
	if detail.Message != "Agent registration was refused." {
		t.Fatalf("unexpected message %q", detail.Message)
	}
}

func TestParseRegisterFailureDetailIgnoresRebootstrapRequired(t *testing.T) {
	body := []byte(`{"detail":{"code":"REBOOTSTRAP_REQUIRED","message":"Certificate bootstrap required for fresh enrollment"}}`)

	if detail := parseRegisterFailureDetail(body); detail != nil {
		t.Fatalf("rebootstrap detail should not be reported as register failure: %#v", detail)
	}
	if recovery := parseRegisterAuthRecoveryDetail(body); recovery == nil || recovery.Code != registerRebootstrapRequiredCode {
		t.Fatalf("expected auth recovery detail, got %#v", recovery)
	}
}

func TestRegisterFailureReporterReportsStructuredFailure(t *testing.T) {
	reporter := newRegisterFailureReporter(config{hostID: "edge-a", agentName: "edge-a"})
	var gotReason string
	var gotFailure *registerFailureDetail
	reporter.send = func(_ config, reason string, failure *registerFailureDetail) error {
		gotReason = reason
		gotFailure = failure
		return nil
	}

	failure := &registerFailureDetail{
		Code:    "AGENT_REGISTRATION_REFUSED",
		Message: "Agent registration was refused.",
	}
	reporter.Report(&registerHTTPError{StatusCode: 409, Body: `{"detail":{"code":"AGENT_REGISTRATION_REFUSED"}}`, Failure: failure})

	if gotReason != failure.Message {
		t.Fatalf("unexpected reason %q", gotReason)
	}
	if gotFailure == nil || gotFailure.Code != "AGENT_REGISTRATION_REFUSED" {
		t.Fatalf("expected structured failure, got %#v", gotFailure)
	}
}

func TestBuildRegisterFailurePayloadIncludesStructuredFailure(t *testing.T) {
	payload, err := buildRegisterFailurePayload(
		config{hostID: "edge-a", agentName: "edge-a"},
		"Agent registration was refused.",
		&registerFailureDetail{Code: "AGENT_REGISTRATION_REFUSED", Message: "Agent registration was refused."},
	)
	if err != nil {
		t.Fatalf("buildRegisterFailurePayload failed: %v", err)
	}

	var decoded registerFailPayload
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("payload was not json: %v", err)
	}
	if decoded.Failure == nil || decoded.Failure.Code != "AGENT_REGISTRATION_REFUSED" {
		t.Fatalf("missing structured failure in payload: %#v", decoded.Failure)
	}
}
