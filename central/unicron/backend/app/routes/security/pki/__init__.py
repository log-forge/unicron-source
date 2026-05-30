from fastapi import APIRouter

from .cert_sign import router as cert_sign_router
from .pki import router as pki_router

pki_public = APIRouter(prefix="/pki", tags=["PKI"])
pki_public.include_router(pki_router)

pki_mtls = APIRouter(prefix="/pki", tags=["PKI"])
pki_mtls.include_router(cert_sign_router)

routers = [pki_public, pki_mtls]

__all__ = ["pki_public", "pki_mtls", "routers"]
