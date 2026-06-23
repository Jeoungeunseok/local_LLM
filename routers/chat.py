import json
import logging
import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from schemas import ChatRequest
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger("app")
router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
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
        messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": request.message})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.2, "num_ctx": 4096},
    }

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
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
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True, 'model': OLLAMA_MODEL})}\n\n"
        except httpx.HTTPStatusError as exc:
            logger.error(f"[/chat] Ollama HTTP 오류 | status={exc.response.status_code}")
            yield f"data: {json.dumps({'error': f'Ollama API 오류: {exc.response.text}'})}\n\n"
        except httpx.RequestError as exc:
            logger.error(f"[/chat] Ollama 연결 실패 | {exc}")
            yield f"data: {json.dumps({'error': 'Ollama 서버에 연결할 수 없습니다.'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
