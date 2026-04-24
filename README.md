# Local Company LLM Server

## 1. 프로젝트 개요

로컬 PC 또는 회사 내부 서버에서 동작하는 LLM 기반 업무지원 서버입니다.

외부 클라우드 API를 사용하지 않고, `Ollama + FastAPI + Qdrant` 구조로 내부 문서 기반 질의응답을 수행하는 것을 목표로 합니다.

본 프로젝트는 `Docker Compose`를 기반으로 배포합니다.

현재 개발 기준 사양은 다음과 같습니다.

| 항목 | 사양 |
|---|---|
| CPU | Intel i5-12400 |
| Core | 6 Core / 12 Thread |
| RAM | 16GB |
| GPU | 없음 |
| 용도 | 로컬 LLM 개발 / 내부망 PoC / RAG 테스트 |

---

## 2. 목표

- Docker 기반 로컬 LLM 서버 구성
- FastAPI 기반 API 서버 구축
- Ollama 컨테이너를 이용한 로컬 LLM 실행
- Qdrant Vector DB를 이용한 문서 검색 구조 구현
- 업로드한 문서를 기반으로 질문에 답변하는 RAG 시스템 개발
- 향후 회사 내부 서버 또는 GPU 서버로 확장 가능한 구조 설계

---

## 3. 시스템 구조

```text
사용자
  ↓
FastAPI 컨테이너
  ↓
질문 임베딩 생성
  ↓
Qdrant Vector DB 컨테이너 검색
  ↓
관련 문서 Chunk 추출
  ↓
Ollama 컨테이너의 LLM 호출
  ↓
사용자에게 응답
```

---

## 4. Docker 서비스 구성

| 서비스 | 역할 | 포트 |
|---|---|---|
| api | FastAPI 백엔드 서버 | 8000 |
| ollama | 로컬 LLM 실행 서버 | 11434 |
| qdrant | Vector DB | 6333, 6334 |

---

## 5. 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | FastAPI |
| LLM Runtime | Ollama |
| LLM Model | qwen3:4b / gemma3:4b |
| Vector DB | Qdrant |
| Embedding | sentence-transformers 계열 또는 BGE 계열 |
| File Storage | Local Storage |
| Language | Python |
| Deploy | Docker Compose |
| Server | Uvicorn |

---

## 6. 저장소 역할

| 저장소 | 역할 |
|---|---|
| Qdrant | 문서 Chunk 임베딩 저장 및 의미 기반 검색 |
| Local Storage | 원본 PDF, DOCX, TXT 파일 저장 |
| SQLite/PostgreSQL | 사용자, 문서 메타데이터, 채팅 로그 저장용 |
| Ollama | 로컬 LLM 모델 실행 |

문서 검색의 핵심 DB는 `Qdrant Vector DB`입니다.  
SQLite나 PostgreSQL은 운영 로그와 메타데이터 저장용으로 사용합니다.

---

## 7. 프로젝트 구조

```text
local-llm-server/
├── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── storage/
│   ├── documents/
│   └── temp/
└── README.md
```

향후 확장 시:

```text
local-llm-server/
├── app/
│   ├── api/
│   ├── services/
│   ├── models/
│   └── main.py
├── storage/
├── docker-compose.yml
└── README.md
```

---

## 8. requirements.txt

```txt
fastapi==0.115.12
uvicorn==0.34.2
httpx==0.28.1
pydantic==2.11.3
qdrant-client==1.14.2
sentence-transformers==4.1.0
python-multipart==0.0.20
PyMuPDF==1.25.5
python-docx==1.1.2
```

---

## 9. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY storage /app/storage

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 10. docker-compose.yml

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: local-llm-api
    ports:
      - "8000:8000"
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      OLLAMA_MODEL: qwen3:4b
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
      STORAGE_DIR: /app/storage
    volumes:
      - ./storage:/app/storage
    depends_on:
      - ollama
      - qdrant
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    container_name: local-llm-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    container_name: local-llm-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  ollama_data:
  qdrant_data:
```

---

## 11. .dockerignore

```dockerignore
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.git
.gitignore
README.md
.env
.env.*
storage/temp/*
```

---

## 12. Docker 실행

전체 서비스를 실행합니다.

```bash
docker compose up -d --build
```

컨테이너 상태를 확인합니다.

```bash
docker compose ps
```

로그를 확인합니다.

```bash
docker compose logs -f
```

특정 서비스 로그만 확인하려면 다음 명령을 사용합니다.

```bash
docker compose logs -f api
```

```bash
docker compose logs -f ollama
```

```bash
docker compose logs -f qdrant
```

---

## 13. Ollama 모델 다운로드

Ollama 컨테이너가 처음 실행되면 모델이 아직 없기 때문에 모델을 다운로드해야 합니다.

현재 PC 사양에서는 4B급 모델을 권장합니다.

```bash
docker compose exec ollama ollama pull qwen3:4b
```

또는:

```bash
docker compose exec ollama ollama pull gemma3:4b
```

모델 목록 확인:

```bash
docker compose exec ollama ollama list
```

모델 실행 테스트:

```bash
docker compose exec ollama ollama run qwen3:4b
```

---

## 14. API 문서 접속

FastAPI 서버 실행 후 브라우저에서 접속합니다.

```text
http://localhost:8000/docs
```

Qdrant 접속 확인:

```text
http://localhost:6333
```

Ollama 접속 확인:

```text
http://localhost:11434
```

---

## 15. 주요 API

| API | 설명 |
|---|---|
| GET /health | 서버 상태 확인 |
| POST /chat | LLM 질의응답 |
| POST /documents/upload | 문서 업로드 |
| POST /documents/index | 문서 임베딩 및 Qdrant 저장 |
| POST /rag/ask | 문서 기반 질의응답 |

---

## 16. RAG 처리 흐름

```text
문서 업로드
  ↓
텍스트 추출
  ↓
Chunk 분할
  ↓
임베딩 생성
  ↓
Qdrant 저장
  ↓
사용자 질문 입력
  ↓
질문 임베딩 생성
  ↓
Qdrant 유사 문서 검색
  ↓
검색 결과를 LLM 프롬프트에 삽입
  ↓
Ollama LLM 답변 생성
```

---

## 17. Docker 내부 통신 주의사항

Docker Compose 환경에서는 컨테이너 간 통신 시 `localhost` 또는 `127.0.0.1`을 사용하면 안 됩니다.

FastAPI 컨테이너에서 Ollama와 Qdrant에 접근할 때는 서비스명을 사용합니다.

```text
FastAPI → Ollama: http://ollama:11434
FastAPI → Qdrant: qdrant:6333
```

따라서 `main.py`에서는 환경변수를 사용해 주소를 설정하는 것이 좋습니다.

```python
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
```

---

## 18. 현재 PC 기준 권장 설정

| 항목 | 권장값 |
|---|---|
| 모델 | qwen3:4b |
| Context | 4096 |
| 동시 사용자 | 1~2명 |
| Vector DB | Qdrant |
| 문서 검색 top_k | 3~5 |
| RAM | 16GB 가능, 32GB 권장 |

---

## 19. 내부망 접속

같은 네트워크의 다른 PC에서 접속하려면 현재 PC의 내부 IP를 확인합니다.

Windows CMD:

```bash
ipconfig
```

예를 들어 내부 IP가 `192.168.0.25`라면 다른 PC에서 다음 주소로 접속합니다.

```text
http://192.168.0.25:8000/docs
```

접속이 안 되면 Windows 방화벽에서 8000 포트를 허용해야 합니다.

```powershell
New-NetFirewallRule -DisplayName "Local LLM FastAPI 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## 20. 서버 중지

컨테이너를 중지합니다.

```bash
docker compose down
```

볼륨까지 삭제하려면 다음 명령을 사용합니다.

```bash
docker compose down -v
```

주의: `docker compose down -v`를 실행하면 Ollama 모델 데이터와 Qdrant 데이터가 함께 삭제될 수 있습니다.

---

## 21. 개발 단계

### 1단계

- Docker Compose 구성
- FastAPI 컨테이너 실행
- Ollama 컨테이너 실행
- Qdrant 컨테이너 실행

### 2단계

- qwen3:4b 모델 다운로드
- FastAPI `/chat` API 구현
- FastAPI에서 Ollama 컨테이너 호출

### 3단계

- 문서 업로드 기능 구현
- 문서 Chunk 분할
- 임베딩 생성
- Qdrant에 문서 Chunk 저장

### 4단계

- Qdrant 검색 결과를 LLM 프롬프트에 연결
- `/rag/ask` API 구현
- 문서 기반 질의응답 구현

### 5단계

- 사용자 로그 저장
- 문서 메타데이터 관리
- PostgreSQL 또는 SQLite 추가
- 회사 내부 서버로 이전