package main

import (
	"os"
	"path/filepath"
	"time"

	"github.com/sirupsen/logrus"
	"github.com/unicron/go-streamer/internal/pki"
)

const defaultAgentCertNotAfterSeconds = 43200

func bootstrapConfigFromRuntime(cfg config) pki.BootstrapConfig {
	return pki.BootstrapConfig{
		EnrollToken:   cfg.enrollToken,
		AgentName:     cfg.agentName,
		CentralURL:    cfg.centralURL,
		CAFingerprint: cfg.caFingerprint,
		CertNotAfter:  defaultAgentCertNotAfterSeconds,
		CertPath:      cfg.certPath,
		KeyPath:       cfg.keyPath,
		CAPath:        cfg.caPath,
	}
}

func renewalConfigFromRuntime(cfg config, renewThreshold time.Duration) pki.RenewalConfig {
	return pki.RenewalConfig{
		CertPath:       cfg.certPath,
		KeyPath:        cfg.keyPath,
		CAPath:         cfg.caPath,
		CentralMTLSURL: cfg.centralMTLSURL + cfg.centralRootPrefix,
		RenewThreshold: renewThreshold,
		CheckInterval:  5 * time.Minute,
	}
}

func startAgentRenewalLoop(cfg pki.RenewalConfig) {
	pki.StartRenewalLoop(cfg)
}

func bootstrapAgentCertificate(cfg config) {
	if err := ensureCertDirs(cfg.certPath, cfg.keyPath, cfg.caPath); err != nil {
		logrus.WithError(err).Fatal("[Bootstrap] Failed to create certificate directory")
	}
	if err := pki.BootstrapAgent(bootstrapConfigFromRuntime(cfg)); err != nil {
		logrus.WithError(err).Fatal("[Bootstrap] Certificate bootstrap failed")
	}
}

func ensureCertDirs(paths ...string) error {
	seen := map[string]struct{}{}
	for _, path := range paths {
		dir := filepath.Dir(path)
		if dir == "." || dir == "" {
			continue
		}
		if _, ok := seen[dir]; ok {
			continue
		}
		seen[dir] = struct{}{}
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
	}
	return nil
}

func prepareAgentCertificate(cfg config, renewThreshold time.Duration) bool {
	inspection := pki.InspectCertificate(cfg.certPath, cfg.keyPath, cfg.caPath, cfg.agentName, renewThreshold)

	switch inspection.Status {
	case pki.CertificateMissing:
		if cfg.enrollToken == "" {
			logrus.WithField("reason", inspection.Reason).Warn("[Bootstrap] Certificate material missing and no enrollment token provided")
			return false
		}
		logrus.WithField("reason", inspection.Reason).Info("[Bootstrap] Certificate material missing, starting bootstrap process")
		bootstrapAgentCertificate(cfg)
		return true

	case pki.CertificateValid:
		logrus.WithFields(logrus.Fields{
			"cert_path":  cfg.certPath,
			"expires_at": inspection.NotAfter.UTC().Format(time.RFC3339),
			"spiffe":     inspection.SPIFFEURI,
		}).Info("[Bootstrap] Using existing valid certificate")
		return true

	case pki.CertificateRenewalRequired:
		logrus.WithFields(logrus.Fields{
			"cert_path":   cfg.certPath,
			"expires_at":  inspection.NotAfter.UTC().Format(time.RFC3339),
			"expires_in":  inspection.TimeRemaining.Round(time.Second).String(),
			"renew_after": renewThreshold.String(),
		}).Warn("[Bootstrap] Existing certificate is near expiry; attempting renewal before registration")
		if err := pki.RenewCertIfNeeded(renewalConfigFromRuntime(cfg, renewThreshold)); err != nil {
			logrus.WithError(err).Warn("[Bootstrap] Pre-registration certificate renewal failed; continuing with still-valid certificate")
		}
		return true

	case pki.CertificateExpired, pki.CertificateInvalid:
		fields := logrus.Fields{
			"cert_path": cfg.certPath,
			"status":    inspection.Status,
			"reason":    inspection.Reason,
		}
		if !inspection.NotAfter.IsZero() {
			fields["expires_at"] = inspection.NotAfter.UTC().Format(time.RFC3339)
		}
		if cfg.enrollToken == "" {
			logrus.WithFields(fields).Fatal("[Bootstrap] Existing certificate material cannot be reused and no enrollment token was provided; generate a new agent install command")
			return false
		}
		logrus.WithFields(fields).Warn("[Bootstrap] Existing certificate material cannot be reused; clearing it and bootstrapping fresh identity")
		if err := pki.RemoveCertificateMaterial(cfg.certPath, cfg.keyPath, cfg.caPath); err != nil {
			logrus.WithError(err).Warn("[Bootstrap] Failed to fully remove stale certificate material before rebootstrap")
		}
		bootstrapAgentCertificate(cfg)
		return true

	default:
		logrus.WithFields(logrus.Fields{
			"cert_path": cfg.certPath,
			"status":    inspection.Status,
			"reason":    inspection.Reason,
		}).Fatal("[Bootstrap] Unknown certificate inspection status")
		return false
	}
}

func registerAgentWithCentral(cfg config, renewThreshold time.Duration, cpuCount int) {
	failureReporter := newRegisterFailureReporter(cfg)
	err := registerHerald(cfg, cpuCount)
	if err == nil {
		failureReporter.Clear()
		return
	}

	if isRegisterRebootstrapRequired(err) {
		rebootstrapAfterRejectedRegister(cfg, renewThreshold, err, cpuCount)
		return
	}

	failureReporter.Report(err)
	if err := retryStep("herald_register", 0, 2*time.Second, func() error {
		err := registerHerald(cfg, cpuCount)
		if err != nil {
			if isRegisterRebootstrapRequired(err) {
				rebootstrapAfterRejectedRegister(cfg, renewThreshold, err, cpuCount)
				return nil
			}
			failureReporter.Report(err)
			return err
		}
		failureReporter.Clear()
		return nil
	}); err != nil {
		logrus.WithError(err).Fatal("[Register] Herald registration failed")
	}
}

func rebootstrapAfterRejectedRegister(
	cfg config,
	renewThreshold time.Duration,
	registerErr error,
	cpuCount int,
) {
	fields := logrus.Fields{
		"cert_path": cfg.certPath,
		"reason":    registerErr.Error(),
	}
	if cfg.enrollToken == "" {
		logrus.WithFields(fields).Fatal("[Register] Central requires certificate rebootstrap, but no enrollment token was provided; generate a new agent install command")
		return
	}

	logrus.WithFields(fields).Warn("[Register] Central requires certificate rebootstrap; clearing local identity and bootstrapping with enrollment token")
	if err := pki.RemoveCertificateMaterial(cfg.certPath, cfg.keyPath, cfg.caPath); err != nil {
		logrus.WithError(err).Warn("[Register] Failed to fully remove rejected certificate material before rebootstrap")
	}
	bootstrapAgentCertificate(cfg)

	failureReporter := newRegisterFailureReporter(cfg)
	if err := retryStep("herald_register_after_rebootstrap", 0, 2*time.Second, func() error {
		err := registerHerald(cfg, cpuCount)
		if err != nil {
			if isRegisterRebootstrapRequired(err) {
				logrus.WithError(err).Fatal("[Register] Freshly bootstrapped certificate was rejected; verify the enrollment token and agent name")
				return nil
			}
			failureReporter.Report(err)
			return err
		}
		failureReporter.Clear()
		return nil
	}); err != nil {
		logrus.WithError(err).Fatal("[Register] Herald registration failed after rebootstrap")
	}

	// The certificate changed. Try to renew only if it landed inside the window.
	inspection := pki.InspectCertificate(cfg.certPath, cfg.keyPath, cfg.caPath, cfg.agentName, renewThreshold)
	if inspection.Status == pki.CertificateRenewalRequired {
		if err := pki.RenewCertIfNeeded(renewalConfigFromRuntime(cfg, renewThreshold)); err != nil {
			logrus.WithError(err).Warn("[Register] Post-rebootstrap renewal check failed")
		}
	}
}
