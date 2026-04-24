import logging
import httpx
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import get_db
from schemas import RagRequest, RagResponse, RagSource
from config import QDRANT_COLLECTION, OLLAMA_MODEL, OLLAMA_BASE_URL
from services.vector_store import embedder, qdrant

logger = logging.getLogger("app")
router = APIRouter()

@router.post("/rag/ask", response_model=RagResponse)
async def rag_ask(request: RagRequest, db: AsyncSession = Depends(get_db)) -> RagResponse:
    try:
        question_emb = embedder.encode(request.question)
    except Exception as e:
        logger.error(f"[/rag/ask] 임베딩 오류: {e}")
        raise HTTPException(status_code=500, detail=f"질문 임베딩 오류: {str(e)}")

    try:
        search_result = qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=question_emb.tolist(),
            limit=3
        )
    except Exception as e:
        logger.error(f"[/rag/ask] Qdrant 검색 오류: {e}")
        raise HTTPException(status_code=500, detail=f"Qdrant 검색 오류: {str(e)}")

    sources = []
    contexts = []
    for hit in search_result:
        payload = hit.payload or {}
        text = payload.get("text", "")
        filename = payload.get("filename", "unknown")
        
        sources.append(RagSource(
            filename=filename,
            text=text,
            score=hit.score
        ))
        contexts.append(f"[{filename}] {text}")

    context_str = "\n\n".join(contexts)

    prompt = (
        "주어진 문서(Context)를 바탕으로 사용자의 질문에 답하세요. "
        "문서에 내용이 없다면 '제공된 문서에서 답변을 찾을 수 없습니다'라고 답하세요.\n\n"
        f"[Context]\n{context_str}\n\n"
        f"[질문]\n{request.question}"
    )

    messages = [
        {"role": "user", "content": prompt}
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
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
        logger.error(f"[/rag/ask] Ollama HTTP 오류 | status={exc.response.status_code} | body={exc.response.text}")
        raise HTTPException(
            status_code=502,
            detail=f"Ollama API 오류: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        logger.error(f"[/rag/ask] Ollama 연결 실패 | {exc}")
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

    # Save to PostgreSQL
    chat_log = models.ChatHistory(
        question=request.question,
        answer=answer,
        model_used=OLLAMA_MODEL
    )
    db.add(chat_log)
    await db.commit()

    return RagResponse(
        answer=answer,
        model=OLLAMA_MODEL,
        sources=sources
    )
