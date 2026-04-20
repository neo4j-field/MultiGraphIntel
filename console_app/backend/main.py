"""FastAPI entrypoint for the MultiGraphIntel console backend."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import run_router
from .neo4j_client import close_driver, fetch_subgraph

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("console-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_driver()


app = FastAPI(title="MultiGraphIntel Console Backend", lifespan=lifespan)

# MVP is open to the internet and doesn't yet know the frontend's final
# domain, so CORS accepts everything. When we add auth we narrow this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class SubgraphRequest(BaseModel):
    entity_type: str
    entity_id: str
    depth: int = 1


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    logger.info("chat message: %s", request.message)
    try:
        result = await run_router(request.message)
        return result
    except Exception as exc:
        logger.exception("router failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/subgraph")
def subgraph(entity_type: str, entity_id: str, depth: int = 1) -> dict:
    try:
        return fetch_subgraph(entity_type, entity_id, depth)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("subgraph failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "console_app.backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        log_level="info",
    )
