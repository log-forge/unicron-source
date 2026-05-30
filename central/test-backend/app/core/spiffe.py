import base64
import re
from functools import lru_cache
from typing import Dict, Optional, Tuple
from urllib.parse import unquote

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID
from fastapi import HTTPException, Request

from .logging import logger  # project logger module

HEADER_PEM = "X-Forwarded-Tls-Client-Cert"

__all__ = [
    "require_spiffe_id",
    "require_spiffe_common_name",
    "require_spiffe_pair",
    "require_spiffe_pair_socket",
    "require_spiffe_id_socket",
    "require_spiffe_common_name_socket",
]

_SPIFFE_PREFIX = "spiffe://unicron/herald/"
_SPIFFE_RE = re.compile(r"^spiffe://unicron/herald/[a-z0-9._-]+$")
_CERT_BLOCK_RE = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL)
_PEM_BEGIN = "-----BEGIN CERTIFICATE-----"
_PEM_END = "-----END CERTIFICATE-----"


def _normalize_header(raw: str) -> str:
    if not raw:
        return ""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    try:
        value = unquote(value)
    except Exception:
        pass
    return value.replace("\\n", "\n")


def _pem_from_der(der: bytes) -> str:
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return f"{_PEM_BEGIN}\n" + "\n".join(lines) + f"\n{_PEM_END}\n"


def _candidate_blocks(header: str) -> Tuple[str, ...]:
    header = _normalize_header(header)
    pem_blocks = _CERT_BLOCK_RE.findall(header)
    if pem_blocks:
        return tuple(block if block.endswith("\n") else f"{block}\n" for block in pem_blocks)

    candidates = {header.strip()} if header.strip() else set()
    candidates.update(part.strip() for part in re.split(r",+", header) if part.strip())

    blocks: list[str] = []
    for candidate in candidates:
        try:
            der = base64.b64decode(candidate, validate=True)
            x509.load_der_x509_certificate(der)
        except Exception:
            continue
        blocks.append(_pem_from_der(der))

    if not blocks:
        preview = header[:600].replace("\n", "\\n")
        logger.debug("SPIFFE no PEM blocks found. Header preview: %s", preview)
    return tuple(blocks)


def _certificates_from_header(header: Optional[str]) -> Tuple[x509.Certificate, ...]:
    if not header:
        return tuple()

    certs: list[x509.Certificate] = []
    for block in _candidate_blocks(header):
        try:
            certs.append(x509.load_pem_x509_certificate(block.encode()))
        except Exception as exc:
            logger.debug("SPIFFE: PEM parse failed: %s", exc)

    logger.debug("SPIFFE cert blocks detected: %s", len(certs))
    return tuple(certs)


@lru_cache(maxsize=256)
def _parse_header(header: Optional[str]) -> Tuple[Tuple[str, ...], Tuple[str, ...], Optional[str]]:
    certs = _certificates_from_header(header)
    segments: list[str] = []
    uris: list[str] = []
    common_name: Optional[str] = None

    for cert in certs:
        if common_name is None:
            try:
                attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                if attrs:
                    value = attrs[0].value
                    common_name = value if isinstance(value, str) else str(value)
            except Exception:
                pass

        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        except x509.ExtensionNotFound:
            continue

        for gn in san_ext.value:  # type: ignore[attr-defined]
            if not isinstance(gn, x509.UniformResourceIdentifier):
                continue
            uri = str(gn.value)
            if uri not in uris:
                uris.append(uri)
            if not uri.startswith("spiffe://"):
                continue
            _validate_spiffe(uri)
            segment = uri[len(_SPIFFE_PREFIX) :]
            if not segment:
                raise HTTPException(status_code=403, detail="Empty SPIFFE workload ID")
            if segment not in segments:
                segments.append(segment)

        if segments and common_name:
            break

    return tuple(segments), tuple(uris), common_name


def _get_header_from_environ(environ: Dict, name: str) -> Optional[str]:
    headers = environ.get("headers")
    if isinstance(headers, (list, tuple)):
        name_lower = name.lower()
        for key, value in headers:
            if isinstance(key, (bytes, bytearray)):
                key = key.decode()
            if str(key).lower() == name_lower:
                return value.decode() if isinstance(value, (bytes, bytearray)) else value

    wsgi_key = "HTTP_" + name.upper().replace("-", "_")
    return environ.get(name) or environ.get(name.lower()) or environ.get(name.title()) or environ.get(wsgi_key)


def require_spiffe_pair_socket(environ: Dict) -> Tuple[str, str]:
    """Socket.IO variant: return (workload_id, common_name).

    Raises ValueError on failures so connect handlers can map to non-herald flows.
    """
    raw = _get_header_from_environ(environ, HEADER_PEM)
    if not raw:
        raise ValueError("Client certificate header missing on handshake")

    segments, _, cn = _parse_header(raw)
    if not segments:
        raise ValueError("SPIFFE ID not found in URI SANs")
    if not cn:
        raise ValueError("Common Name not present in certificate")
    return segments[0], cn


def require_spiffe_id_socket(environ: Dict) -> str:
    return require_spiffe_pair_socket(environ)[0]


def require_spiffe_common_name_socket(environ: Dict) -> str:
    return require_spiffe_pair_socket(environ)[1]


def _validate_spiffe(spiffe_id: str) -> None:
    if not spiffe_id.startswith(_SPIFFE_PREFIX):
        raise HTTPException(status_code=403, detail="Invalid SPIFFE trust domain")
    if not _SPIFFE_RE.match(spiffe_id):
        raise HTTPException(status_code=403, detail="Invalid SPIFFE workload format")


def require_spiffe_pair(request: Request) -> tuple[str, str]:
    """Return a tuple of (workload_id, common_name).

    Currently both values are identical: the segment after the SPIFFE prefix.
    This is future-proofed in case you differentiate an opaque id vs a display name later.
    """
    pem = request.headers.get(HEADER_PEM)
    logger.debug("SPIFFE PEM header present: %s", bool(pem))
    if not pem:
        raise HTTPException(status_code=401, detail="Client certificate header missing")
    segments, uris, cn = _parse_header(pem)
    logger.debug("SPIFFE segments extracted: %s", segments)
    if not segments:
        logger.debug("SPIFFE URI SANs extracted: %s", uris)
        if not uris:
            raise HTTPException(status_code=401, detail="No URI SANs present in client certificate")
        raise HTTPException(status_code=401, detail="SPIFFE ID not found in URI SANs")

    segment = segments[0]
    full_uri = f"{_SPIFFE_PREFIX}{segment}"
    if cn:
        logger.debug("SPIFFE workload accepted: %s (full=%s) CN=%s", segment, full_uri, cn)
        return segment, cn

    logger.debug("SPIFFE workload accepted: %s (full=%s)", segment, full_uri)
    # Fallback: id == common_name
    return segment, segment


def require_spiffe_id(request: Request) -> str:
    return require_spiffe_pair(request)[0]


def require_spiffe_common_name(request: Request) -> str:
    return require_spiffe_pair(request)[1]
