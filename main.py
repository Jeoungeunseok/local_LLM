import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from qdrant_client.http import models as qdrant_models

from logger import setup_logging
from config import OLLAMA_MODEL, OLLAMA_BASE_URL, QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION
from database import engine
import models
from services.vector_store import qdrant, embedder
from routers import chat, documents, rag

# 로깅 시스템 초기화 (가장 먼저 실행)
setup_logging()
logger = logging.getLogger("app")

# 의존 서비스 준비 대기 설정
STARTUP_MAX_RETRIES = int(os.getenv("STARTUP_MAX_RETRIES", "30"))
STARTUP_RETRY_DELAY = float(os.getenv("STARTUP_RETRY_DELAY", "2.0"))


async def _wait_for(name: str, coro_factory):
    """의존 서비스가 준비될 때까지 재시도하며 대기한다."""
    last_err = None
    for attempt in range(1, STARTUP_MAX_RETRIES + 1):
        try:
            await coro_factory()
            logger.info(f"[startup] {name} 준비 완료 (시도 {attempt})")
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(f"[startup] {name} 대기 중... (시도 {attempt}/{STARTUP_MAX_RETRIES}) | {e}")
            await asyncio.sleep(STARTUP_RETRY_DELAY)
    raise RuntimeError(f"[startup] {name} 준비 실패 ({STARTUP_MAX_RETRIES}회 시도): {last_err}")


async def _init_db():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


async def _init_qdrant():
    collections = (await asyncio.to_thread(qdrant.get_collections)).collections
    collection_names = [c.name for c in collections]
    if QDRANT_COLLECTION not in collection_names:
        await asyncio.to_thread(
            qdrant.create_collection,
            collection_name=QDRANT_COLLECTION,
            vectors_config=qdrant_models.VectorParams(
                size=embedder.get_sentence_embedding_dimension(),
                distance=qdrant_models.Distance.COSINE,
            ),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 의존 서비스(db, qdrant)가 아직 준비되지 않았을 수 있으므로 재시도하며 초기화
    await _wait_for("PostgreSQL", _init_db)
    await _wait_for("Qdrant", _init_qdrant)
    yield

app = FastAPI(
    title="Local Company LLM Server",
    description="로컬 또는 회사 내부망에서 사용하는 LLM API 서버",
    version="1.0.0",
    lifespan=lifespan,
)

# Include Routers
app.include_router(chat.router, tags=["Chat"])
app.include_router(documents.router, tags=["Documents"])
app.include_router(rag.router, tags=["RAG"])

# Mount Frontend
os.makedirs("frontend", exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "ollama_base_url": OLLAMA_BASE_URL,
        "qdrant_host": QDRANT_HOST,
        "qdrant_port": QDRANT_PORT,
    }
