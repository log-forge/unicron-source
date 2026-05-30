#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from typing import Sequence
from urllib.parse import urlparse, urlunparse


REQUIRED_ENV_KEYS = {
    "AGENT_NAME",
    "CENTRAL_WS_URL",
    "CENTRAL_URL",
    "CENTRAL_MTLS_URL",
    "ENROLL_TOKEN",
    "CA_FINGERPRINT",
    "HOST_ID",
    "HERALD_NAME",
    "HERALD_ID",
    "ENVIRONMENT",
}

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _collapse_line_continuations(command_text: str) -> str:
    return re.sub(r"\\\s*\n", " ", command_text).strip()


def _extract_docker_run_segment(command_text: str) -> str:
    normalized = _collapse_line_continuations(command_text)
    if not normalized:
        return ""

    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.search(r"(?:^|;)\s*(docker\s+run(?:\s|$).*)", stripped)
        if match:
            return match.group(1).strip()

    return normalized


def tokenize_generated_command(command_text: str) -> list[str]:
    docker_run_segment = _extract_docker_run_segment(command_text)
    if not docker_run_segment:
        raise ValueError("No docker run command was provided on stdin.")
    try:
        return shlex.split(docker_run_segment, posix=True)
    except ValueError as exc:
        raise ValueError(f"Failed to parse docker command: {exc}") from exc


def _read_env_keys(tokens: Sequence[str]) -> dict[str, str]:
    env_values: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"-e", "--env"}:
            if i + 1 >= len(tokens):
                raise ValueError(f"Missing value after {token}.")
            assignment = tokens[i + 1]
            i += 2
        elif token.startswith("--env="):
            assignment = token.split("=", 1)[1]
            i += 1
        else:
            i += 1
            continue
        key, sep, value = assignment.partition("=")
        if not sep or not key:
            raise ValueError(f"Invalid environment assignment: {assignment!r}")
        env_values[key] = value
    return env_values


def _extract_container_name(tokens: Sequence[str]) -> str:
    for i, token in enumerate(tokens):
        if token == "--name":
            if i + 1 >= len(tokens):
                raise ValueError("Missing container name after --name.")
            return tokens[i + 1]
        if token.startswith("--name="):
            value = token.split("=", 1)[1]
            if not value:
                raise ValueError("Missing container name after --name=.")
            return value
    raise ValueError("Generated command is missing --name.")


def _rewrite_url_host(value: str, *, hostname: str) -> str:
    parsed = urlparse(value)
    current_host = (parsed.hostname or "").strip().lower()
    if not current_host or current_host not in LOOPBACK_HOSTS:
        return value

    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _rewrite_central_env_urls(tokens: list[str], *, hostname: str) -> None:
    i = 0
    while i < len(tokens):
        token = tokens[i]
        assignment_index: int | None = None
        assignment: str | None = None

        if token in {"-e", "--env"}:
            if i + 1 >= len(tokens):
                raise ValueError(f"Missing value after {token}.")
            assignment_index = i + 1
            assignment = tokens[assignment_index]
            i += 2
        elif token.startswith("--env="):
            assignment_index = i
            assignment = token.split("=", 1)[1]
            i += 1
        else:
            i += 1
            continue

        key, sep, value = assignment.partition("=")
        if not sep or key not in {"CENTRAL_WS_URL", "CENTRAL_URL", "CENTRAL_MTLS_URL"}:
            continue

        rewritten = f"{key}={_rewrite_url_host(value, hostname=hostname)}"
        if tokens[assignment_index].startswith("--env="):
            tokens[assignment_index] = f"--env={rewritten}"
        else:
            tokens[assignment_index] = rewritten


def validate_generated_command(tokens: Sequence[str]) -> str:
    if len(tokens) < 3 or tokens[0] != "docker" or tokens[1] != "run":
        raise ValueError("Expected the canonical enroll-generated command to start with `docker run`.")
    if tokens[-1].startswith("-"):
        raise ValueError("Expected the final token in the generated command to be the image reference.")

    env_values = _read_env_keys(tokens)
    missing = sorted(key for key in REQUIRED_ENV_KEYS if key not in env_values)
    if missing:
        raise ValueError(
            "Generated command is missing required enroll fields: " + ", ".join(missing)
        )
    if env_values.get("ENVIRONMENT") != "production":
        raise ValueError("Generated command must preserve `ENVIRONMENT=production`.")

    return _extract_container_name(tokens)


def extract_container_name(command_text: str) -> str:
    tokens = tokenize_generated_command(command_text)
    return validate_generated_command(tokens)


def _upsert_add_host(tokens: list[str], *, hostname: str, resolved_ip: str) -> None:
    add_host_value = f"{hostname}:{resolved_ip}"
    for index, token in enumerate(tokens):
        if token == "--add-host":
            if index + 1 >= len(tokens):
                raise ValueError("Missing value after --add-host.")
            current_host, _, _current_ip = tokens[index + 1].partition(":")
            if current_host == hostname:
                tokens[index + 1] = add_host_value
                return
            continue
        if token.startswith("--add-host="):
            current_value = token.split("=", 1)[1]
            current_host, _, _current_ip = current_value.partition(":")
            if current_host == hostname:
                tokens[index] = f"--add-host={add_host_value}"
                return

    image_index = len(tokens) - 1
    tokens[image_index:image_index] = [f"--add-host={add_host_value}"]


def rewrite_generated_agent_command(
    command_text: str,
    *,
    image_ref: str,
    hostname: str,
    resolved_ip: str,
) -> str:
    tokens = tokenize_generated_command(command_text)
    container_name = validate_generated_command(tokens)
    _rewrite_central_env_urls(tokens, hostname=hostname)
    _upsert_add_host(tokens, hostname=hostname, resolved_ip=resolved_ip)
    tokens[-1] = image_ref
    remove_cmd = f"{shlex.join(['docker', 'rm', '-f', container_name])} 2>/dev/null"
    data_volume_name = f"{container_name}-data"
    remove_data_volume_cmd = f"{shlex.join(['docker', 'volume', 'rm', data_volume_name])} 2>/dev/null || true"
    return f"{remove_cmd}; {remove_data_volume_cmd}; {shlex.join(tokens)}"


def resolve_host_ip(*, dind_container: str, hostname: str) -> str:
    shell_cmd = (
        f"HOSTNAME={shlex.quote(hostname)}; "
        "awk -v host=\"$HOSTNAME\" 'NF >= 2 { for (i = 2; i <= NF; i++) if ($i == host) { print $1; exit } }' /etc/hosts"
    )
    result = subprocess.run(
        ["docker", "exec", dind_container, "sh", "-lc", shell_cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to resolve {hostname!r} from {dind_container}: {result.stderr.strip() or result.stdout.strip()}"
        )
    resolved_ip = result.stdout.strip()
    if not resolved_ip:
        raise RuntimeError(f"Could not find {hostname!r} in {dind_container} /etc/hosts.")
    return resolved_ip.splitlines()[0].strip()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite an enroll-generated docker run command so it can run inside unicron-remote-dind."
    )
    parser.add_argument("--dind-container", default="unicron-remote-dind")
    parser.add_argument("--hostname", default="unicron.central")
    parser.add_argument("--image-ref")
    parser.add_argument("--print-container-name", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        original_command = sys.stdin.read()
        if args.print_container_name:
            print(extract_container_name(original_command))
            return 0
        if not args.image_ref:
            raise ValueError("--image-ref is required unless --print-container-name is used.")
        resolved_ip = resolve_host_ip(dind_container=args.dind_container, hostname=args.hostname)
        rewritten = rewrite_generated_agent_command(
            original_command,
            image_ref=args.image_ref,
            hostname=args.hostname,
            resolved_ip=resolved_ip,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(rewritten)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
