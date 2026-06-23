#!/bin/bash
# Ollama 서버를 시작하고, 준비되면 지정 모델을 자동으로 pull한다.
MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"

echo "[ollama-init] 서버 시작..."
ollama serve &

echo "[ollama-init] 서버 준비 대기 중..."
until ollama list > /dev/null 2>&1; do
    sleep 2
done
echo "[ollama-init] 서버 준비 완료"

echo "[ollama-init] 모델 확인: ${MODEL}"
ollama pull "${MODEL}"
echo "[ollama-init] 모델 준비 완료: ${MODEL}"

wait
