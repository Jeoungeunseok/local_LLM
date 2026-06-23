import asyncio
import json
import logging
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import get_db, AsyncSessionLocal
from schemas import RagRequest, RagSource
from config import (
    QDRANT_COLLECTION,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    RAG_TOP_K,
    RAG_SCORE_THRESHOLD,
)
from services.vector_store import embedder, qdrant

NO_CONTEXT_MESSAGE = "제공된 문서에서 답변을 찾을 수 없습니다."

logger = logging.getLogger("app")
router = APIRouter()


@router.post("/rag/ask")
async def rag_ask(request: RagRequest, db: AsyncSession = Depends(get_db)):
    try:
        question_emb = await asyncio.to_thread(embedder.encode, request.question)
    except Exception as e:
        logger.error(f"[/rag/ask] 임베딩 오류: {e}")
        async def emb_err():
            yield f"data: {json.dumps({'error': f'질문 임베딩 오류: {str(e)}'})}\n\n"
        return StreamingResponse(emb_err(), media_type="text/event-stream")

    try:
        search_result = await asyncio.to_thread(
            qdrant.search,
            collection_name=QDRANT_COLLECTION,
            query_vector=question_emb.tolist(),
            limit=RAG_TOP_K,
            score_threshold=RAG_SCORE_THRESHOLD,
        )
    except Exception as e:
        logger.error(f"[/rag/ask] Qdrant 검색 오류: {e}")
        async def qdrant_err():
            yield f"data: {json.dumps({'error': f'Qdrant 검색 오류: {str(e)}'})}\n\n"
        return StreamingResponse(qdrant_err(), media_type="text/event-stream")

    sources: list[RagSource] = []
    contexts: list[str] = []
    for hit in search_result:
        payload = hit.payload or {}
        text = payload.get("text", "")
        filename = payload.get("filename", "unknown")
        sources.append(RagSource(filename=filename, text=text, score=hit.score))
        contexts.append(f"[{filename}] {text}")

    if not sources:
        logger.info(f"[/rag/ask] 임계값({RAG_SCORE_THRESHOLD}) 이상 관련 문서 없음 | question={request.question}")
        async def no_ctx():
            yield f"data: {json.dumps({'done': True, 'model': OLLAMA_MODEL, 'answer': NO_CONTEXT_MESSAGE, 'sources': []})}\n\n"
        return StreamingResponse(no_ctx(), media_type="text/event-stream")

    context_str = "\n\n".join(contexts)
    prompt = (
        "주어진 문서(Context)를 바탕으로 사용자의 질문에 답하세요. "
        "문서에 내용이 없다면 '제공된 문서에서 답변을 찾을 수 없습니다'라고 답하세요.\n\n"
        f"[Context]\n{context_str}\n\n"
        f"[질문]\n{request.question}"
    )

    ollama_payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }

    sources_data = [{"filename": s.filename, "text": s.text, "score": s.score} for s in sources]
    question = request.question

    async def generate():
        yield f"data: {json.dumps({'sources': sources_data})}\n\n"

        full_answer = ""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=ollama_payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {json.dumps({'error': f'Ollama API 오류: {body.decode()}'})}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_answer += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True, 'model': OLLAMA_MODEL})}\n\n"
        except httpx.HTTPStatusError as exc:
            logger.error(f"[/rag/ask] Ollama HTTP 오류 | status={exc.response.status_code}")
            yield f"data: {json.dumps({'error': f'Ollama API 오류: {exc.response.text}'})}\n\n"
            return
        except httpx.RequestError as exc:
            logger.error(f"[/rag/ask] Ollama 연결 실패 | {exc}")
            yield f"data: {json.dumps({'error': 'Ollama 서버에 연결할 수 없습니다.'})}\n\n"
            return

        # 스트리밍 완료 후 새 세션으로 DB 저장
        if full_answer:
            try:
                async with AsyncSessionLocal() as session:
                    session.add(models.ChatHistory(
                        question=question,
                        answer=full_answer,
                        model_used=OLLAMA_MODEL,
                    ))
                    await session.commit()
            except Exception as e:
                logger.error(f"[/rag/ask] DB 저장 실패 | {e}")

    return StreamingResponse(generate(), media_type="text/event-stream")
