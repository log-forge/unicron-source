# Security Policy

LogForge Unicron is a local-first appliance that controls container
observation, agent enrollment, telemetry ingest, notifications, and
authenticated operator actions. Please report suspected vulnerabilities
privately before public disclosure.

## Reporting

Use the repository's private vulnerability reporting channel when it is
available. If it is not available yet, open a minimal issue asking maintainers
for a private contact path and do not include exploit details in the public
issue.

Include:

- affected component or path
- impact and attacker prerequisites
- reproduction steps or proof of concept
- relevant versions, commit hashes, or deployment mode
- any suggested mitigation

Do not include secrets, tokens, signing key material, customer data, or
unrelated personal information.

## Supported Scope

Security reports are in scope for current source-available code and deployment
artifacts, including:

- standalone appliance runtime and Compose deployment
- Central backend, frontend, and local auth service
- appliance updater and Docker socket handling
- agent enrollment, mTLS identity, and telemetry ingest
- alert engine and notifier services

## Handling Expectations

Maintainers should acknowledge valid private reports, keep exploit details
private until a fix or mitigation is available, and document any required
operator action in release notes or security advisories.
