import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import cast

from app.core.config import settings
from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from cryptography.x509.oid import NameOID
from fastapi import HTTPException, status

MAX_LEAF_SECONDS = 43200  # 12 hours

_PEM_CERT_BLOCK_RE = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\s*", flags=re.DOTALL)


def coerce_not_after_seconds(value: int | None) -> int:
    try:
        if value is None or value <= 0:
            return MAX_LEAF_SECONDS
        return min(value, MAX_LEAF_SECONDS)
    except Exception:
        return MAX_LEAF_SECONDS


def _extract_pem_blocks(pem: str) -> list[str]:
    return [m.group(0).strip() + "\n" for m in _PEM_CERT_BLOCK_RE.finditer(pem or "")]


def _run_step(cmd: list[str], *, error_prefix: str) -> str:
    """Run a step-cli command and raise HTTPException on failure."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{error_prefix}: {str(exc)}",
        )

    if proc.returncode != 0:
        stderr_snip = proc.stderr.strip() or proc.stdout.strip()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{error_prefix}: {stderr_snip}",
        )

    return (proc.stdout or "").strip()


def _parse_csr_and_validate(csr_pem: str, expected_spiffe_uris: list[str]) -> tuple[str, list[str]]:
    """Return (CSR common name, SAN strings) after validating SPIFFE URI SAN."""
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid CSR PEM")

    try:
        san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSR missing subjectAltName")

    san = cast(x509.SubjectAlternativeName, san_ext.value)
    dns = [str(v) for v in san.get_values_for_type(x509.DNSName)]
    ips = [str(v) for v in san.get_values_for_type(x509.IPAddress)]
    uris = [str(v) for v in san.get_values_for_type(x509.UniformResourceIdentifier)]

    if not expected_spiffe_uris:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No expected SPIFFE URI provided")

    if not any(expected in uris for expected in expected_spiffe_uris):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSR SPIFFE id mismatch")

    cn_values = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    subject_cn = cn_values[0].value.strip() if cn_values else ""
    if not subject_cn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSR missing commonName")

    # Step token SANs must match CSR SANs. Keep deterministic order and remove duplicates.
    sans: list[str] = []
    seen: set[str] = set()
    for value in [*dns, *ips, *uris]:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        sans.append(normalized)

    return subject_cn, sans


def sign_csr(*, csr_pem: str, not_after_seconds: int, expected_spiffe_uris: list[str]) -> tuple[str, str, datetime]:
    """Sign a CSR via internal RA and return (cert_pem, chain_pem, not_after)."""
    subject_cn, san_values = _parse_csr_and_validate(csr_pem, expected_spiffe_uris)

    if not os.path.exists(settings.RA_PROVISIONER_KEY):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RA provisioner key unavailable",
        )
    if not os.path.exists(settings.RA_PROVISIONER_PASSWORD_FILE):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RA provisioner password unavailable",
        )

    csr_path = cert_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as csr_file:
            csr_file.write(csr_pem)
            csr_path = csr_file.name
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as out_file:
            cert_path = out_file.name

        token_cmd = [
            "step",
            "ca",
            "token",
            subject_cn,
            "--ca-url",
            settings.RA_URL,
            "--root",
            settings.ROOT_CA,
            "--provisioner",
            "ra@unicron",
            "--provisioner-password-file",
            settings.RA_PROVISIONER_PASSWORD_FILE,
            "--key",
            settings.RA_PROVISIONER_KEY,
            "--not-after",
            "5m",
        ]
        for san in san_values:
            token_cmd.extend(["--san", san])
        token = _run_step(token_cmd, error_prefix="CSR token generation failed")
        if not token:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CSR token generation failed")

        sign_cmd = [
            "step",
            "ca",
            "sign",
            csr_path,
            cert_path,
            "--force",
            "--token",
            token,
            "--ca-url",
            settings.RA_URL,
            "--root",
            settings.ROOT_CA,
            "--not-after",
            f"{not_after_seconds}s",
        ]
        _run_step(sign_cmd, error_prefix="CSR signing failed")

        with open(cert_path, "r") as f:
            bundled = f.read()
    finally:
        if csr_path:
            try:
                os.unlink(csr_path)
            except Exception:
                pass
        if cert_path:
            try:
                os.unlink(cert_path)
            except Exception:
                pass

    blocks = _extract_pem_blocks(bundled)
    if not blocks:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CSR signing produced no certificate"
        )

    leaf = blocks[0]
    chain = "".join(blocks[1:]).strip() + ("\n" if len(blocks) > 1 else "")
    try:
        cert_obj = x509.load_pem_x509_certificate(leaf.encode())
        not_after = cert_obj.not_valid_after_utc
    except Exception:
        not_after = datetime.now(timezone.utc) + timedelta(seconds=not_after_seconds)

    return leaf, chain, not_after


__all__ = ["sign_csr", "coerce_not_after_seconds"]
