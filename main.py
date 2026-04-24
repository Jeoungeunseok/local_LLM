from contextlib import asynccontextmanager
from fastapi import FastAPI
from qdrant_client.http import models as qdrant_models

from config import OLLAMA_MODEL, OLLAMA_BASE_URL, QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION
from database import engine
import models
from services.vector_store import qdrant, embedder
from routers import chat, documents, rag

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    # Create Qdrant collection if not exists
    collections = qdrant.get_collections().collections
    collection_names = [c.name for c in collections]
    if QDRANT_COLLECTION not in collection_names:
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=qdrant_models.VectorParams(
                size=embedder.get_sentence_embedding_dimension(),
                distance=qdrant_models.Distance.COSINE,
            ),
        )
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

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "ollama_base_url": OLLAMA_BASE_URL,
        "qdrant_host": QDRANT_HOST,
        "qdrant_port": QDRANT_PORT,
    }
