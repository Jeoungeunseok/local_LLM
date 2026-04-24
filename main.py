import os
from typing import List, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: List[ChatMessage] = Field(default_factory=list)

class ChatResponse(BaseModel):
    answer: str
    model: str

app = FastAPI(
    title="Local Company LLM Server",
    description="로컬 또는 회사 내부망에서 사용하는 LLM API 서버",
    version="1.0.0",
)

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
