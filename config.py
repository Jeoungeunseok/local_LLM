import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = "company_docs"

EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"

# RAG 검색 설정
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
# 코사인 유사도 임계값: 이 값 미만의 결과는 무관한 것으로 간주
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.3"))

# 업로드 파일 최대 크기 (기본 20MB)
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))

# 원본 파일 저장 경로
STORAGE_DIR = os.getenv("STORAGE_DIR", "/app/storage")
DOCUMENTS_DIR = os.path.join(STORAGE_DIR, "documents")
