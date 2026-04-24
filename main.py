import io
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Literal

import docx
import fitz
import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = "company_docs"
EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"

# Initialize Embedding model
embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

# Initialize Qdrant Client
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: List[ChatMessage] = Field(default_factory=list)

class ChatResponse(BaseModel):
    answer: str
    model: str

@asynccontextmanager
async def lifespan(app: FastAPI):
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

def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다.")
    
    ext = file.filename.split(".")[-1].lower()
    content = await file.read()
    
    text = ""
    if ext == "pdf":
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                text += page.get_text() + "\n"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF 추출 오류: {str(e)}")
    elif ext == "docx":
        try:
            doc = docx.Document(io.BytesIO(content))
            for para in doc.paragraphs:
                text += para.text + "\n"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DOCX 추출 오류: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="지원되지 않는 파일 형식입니다. (pdf, docx만 지원)")
    
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="추출된 텍스트가 없습니다.")
        
    chunks = chunk_text(text)
    
    try:
        embeddings = embedder.encode(chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 생성 오류: {str(e)}")
        
    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        points.append(qdrant_models.PointStruct(
            id=point_id,
            vector=emb.tolist(),
            payload={
                "filename": file.filename,
                "text": chunk,
                "chunk_index": i
            }
        ))
        
    try:
        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant 저장 오류: {str(e)}")
        
    return {
        "status": "success",
        "filename": file.filename,
        "chunks_count": len(chunks),
        "message": f"성공적으로 {len(chunks)}개의 Chunk가 벡터 DB에 저장되었습니다."
    }

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": OLLAMA_MODEL,
        "ollama_base_url": OLLAMA_BASE_URL,
        "qdrant_host": QDRANT_HOST,
        "qdrant_port": QDRANT_PORT,
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 회사 내부에서 사용하는 업무지원 AI입니다. "
                "답변은 한국어로 작성하고, 모르면 추측하지 말고 모른다고 답하세요."
            ),
        }
    ]

    for item in request.history:
        messages.append(
            {
                "role": item.role,
                "content": item.content,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": request.message,
        }
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 4096,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama API 오류: {exc.response.text}",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Ollama 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인하세요.",
        ) from exc

    answer = data.get("message", {}).get("content", "")

    if not answer:
        raise HTTPException(
            status_code=500,
            detail="Ollama 응답에서 답변을 찾을 수 없습니다.",
        )

    return ChatResponse(
        answer=answer,
        model=OLLAMA_MODEL,
    )
