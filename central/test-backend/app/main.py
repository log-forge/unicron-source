from fastapi import Depends, FastAPI

from .core.logging import get_logger
from .core.spiffe import require_spiffe_pair

logger = get_logger("main")

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/whoami")
async def whoami(spiffe_pair: tuple[str, str] = Depends(require_spiffe_pair)):
    spiffe_id, common_name = spiffe_pair
    # Enforce trust domain/prefix
    logger.debug("whoami called with SPIFFE ID: %s (CN=%s)", spiffe_id, common_name)
    return {"herald_id": spiffe_id, "common_name": common_name}
