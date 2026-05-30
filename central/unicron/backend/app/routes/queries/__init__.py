from fastapi import APIRouter

from . import herald_queries

queries_router = APIRouter(prefix="/queries", tags=["queries"])
queries_router.include_router(herald_queries.router)

routers = [queries_router]
