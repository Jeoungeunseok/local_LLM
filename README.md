# Local Company LLM Server

## 1. 프로젝트 개요

로컬 PC 또는 회사 내부 서버에서 동작하는 LLM 기반 업무지원 서버입니다.

외부 클라우드 API를 사용하지 않고, `Ollama + FastAPI + Qdrant` 구조로 내부 문서 기반 질의응답을 수행하는 것을 목표로 합니다.

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

- 로컬 PC에서 LLM 모델 실행
- FastAPI 기반 API 서버 구축
- Qdrant Vector DB를 이용한 문서 검색 구조 구현
- 업로드한 문서를 기반으로 질문에 답변하는 RAG 시스템 개발
- 향후 회사 내부 서버 또는 GPU 서버로 확장 가능한 구조 설계

---

## 3. 시스템 구조

```text
사용자
  ↓
FastAPI 서버
  ↓
질문 임베딩 생성
  ↓
Qdrant Vector DB 검색
  ↓
관련 문서 Chunk 추출
  ↓
Ollama LLM 답변 생성
  ↓
사용자에게 응답
```

---

## 4. 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | FastAPI |
| LLM Runtime | Ollama |
| LLM Model | qwen3:4b / gemma3:4b |
| Vector DB | Qdrant |
| Embedding | sentence-transformers 계열 또는 BGE 계열 |
| File Storage | Local Storage |
| Language | Python |
| Server | Uvicorn |

---

## 5. 저장소 역할

| 저장소 | 역할 |
|---|---|
| Qdrant | 문서 Chunk 임베딩 저장 및 의미 기반 검색 |
| Local Storage | 원본 PDF, DOCX, TXT 파일 저장 |
| SQLite/PostgreSQL | 사용자, 문서 메타데이터, 채팅 로그 저장용 |
| Ollama | 로컬 LLM 모델 실행 |

문서 검색의 핵심 DB는 `Qdrant Vector DB`입니다.  
SQLite나 PostgreSQL은 운영 로그와 메타데이터 저장용으로 사용합니다.

---

## 6. 프로젝트 구조

```text
local-llm-server/
├── main.py
├── requirements.txt
├── run.bat
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

## 7. 설치

### Python 가상환경 생성

```bash
python -m venv .venv
```

### 가상환경 실행

Windows CMD:

```bash
.venv\Scripts\activate
```

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 패키지 설치

```bash
pip install -r requirements.txt
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

## 9. Ollama 모델 설치

현재 PC 사양에서는 4B급 모델을 권장합니다.

```bash
ollama pull qwen3:4b
```

또는:

```bash
ollama pull gemma3:4b
```

모델 실행 테스트:

```bash
ollama run qwen3:4b
```

---

## 10. Qdrant 실행

Docker를 사용할 경우:

```bash
docker run -p 6333:6333 -p 6334:6334 ^
  -v qdrant_storage:/qdrant/storage ^
  qdrant/qdrant
```

접속 확인:

```text
http://localhost:6333
```

---

## 11. 서버 실행

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

또는:

```bash
run.bat
```

`run.bat` 예시:

```bat
@echo off
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 12. API 문서

서버 실행 후 접속:

```text
http://localhost:8000/docs
```

---

## 13. 주요 API

| API | 설명 |
|---|---|
| GET /health | 서버 상태 확인 |
| POST /chat | LLM 질의응답 |
| POST /documents/upload | 문서 업로드 |
| POST /documents/index | 문서 임베딩 및 Qdrant 저장 |
| POST /rag/ask | 문서 기반 질의응답 |

---

## 14. RAG 처리 흐름

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
답변 생성
```

---

## 15. 현재 PC 기준 권장 설정

| 항목 | 권장값 |
|---|---|
| 모델 | qwen3:4b |
| Context | 4096 |
| 동시 사용자 | 1~2명 |
| Vector DB | Qdrant |
| 문서 검색 top_k | 3~5 |
| RAM | 16GB 가능, 32GB 권장 |

---

## 16. 내부망 접속

같은 네트워크의 다른 PC에서 접속하려면 현재 PC의 내부 IP를 확인합니다.

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

## 17. 개발 단계

### 1단계

- Ollama 설치
- qwen3:4b 모델 실행
- FastAPI `/chat` API 구현

### 2단계

- Qdrant 실행
- 문서 업로드 기능 구현
- 문서 Chunk 임베딩 저장

### 3단계

- Qdrant 검색 결과를 LLM 프롬프트에 연결
- `/rag/ask` API 구현

### 4단계

- 사용자 로그 저장
- 문서 메타데이터 관리
- PostgreSQL 또는 SQLite 추가

### 5단계

- 회사 내부 서버로 이전
- Docker Compose 구성
- GPU 서버 또는 RAM 32GB 이상 환경으로 확장