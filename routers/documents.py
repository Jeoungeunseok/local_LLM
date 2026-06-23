import asyncio
import io
import logging
import os
import uuid
import docx
import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.http import models as qdrant_models

import models
from database import get_db
from config import QDRANT_COLLECTION, MAX_UPLOAD_SIZE, DOCUMENTS_DIR
from utils import chunk_text
from services.vector_store import embedder, qdrant

logger = logging.getLogger("app")
router = APIRouter()


def _qdrant_delete_filter(filename: str) -> qdrant_models.FilterSelector:
    return qdrant_models.FilterSelector(
        filter=qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="filename",
                    match=qdrant_models.MatchValue(value=filename),
                )
            ]
        )
    )


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다.")

    # Content-Length 헤더가 있으면 읽기 전에 미리 거부
    content_length = file.size
    if content_length is not None and content_length > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB까지 업로드할 수 있습니다.",
        )

    # 청크 단위로 읽으며 한도 초과 즉시 중단
    ext = file.filename.split(".")[-1].lower()
    chunks_read: list[bytes] = []
    total = 0
    async for chunk in file:
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB까지 업로드할 수 있습니다.",
            )
        chunks_read.append(chunk)
    content = b"".join(chunks_read)

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
        embeddings = await asyncio.to_thread(embedder.encode, chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임베딩 생성 오류: {str(e)}")

    # 동일 파일명이 이미 존재하면 Qdrant·PostgreSQL·원본 파일 먼저 삭제
    existing = (await db.execute(
        select(models.DocumentMeta).where(models.DocumentMeta.filename == file.filename)
    )).scalars().first()

    if existing:
        try:
            await asyncio.to_thread(
                qdrant.delete,
                collection_name=QDRANT_COLLECTION,
                points_selector=_qdrant_delete_filter(file.filename),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"기존 벡터 데이터 삭제 오류: {str(e)}")

        if existing.file_path and os.path.exists(existing.file_path):
            os.remove(existing.file_path)

        await db.execute(
            delete(models.DocumentMeta).where(models.DocumentMeta.filename == file.filename)
        )
        await db.flush()
        logger.info(f"[/documents/upload] 기존 데이터 교체: {file.filename}")

    # 원본 파일을 storage/documents/ 에 저장
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    file_path = os.path.join(DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        points.append(qdrant_models.PointStruct(
            id=str(uuid.uuid4()),
            vector=emb.tolist(),
            payload={"filename": file.filename, "text": chunk, "chunk_index": i},
        ))

    try:
        await asyncio.to_thread(
            qdrant.upsert,
            collection_name=QDRANT_COLLECTION,
            points=points,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant 저장 오류: {str(e)}")

    db.add(models.DocumentMeta(
        filename=file.filename,
        file_path=file_path,
        chunk_count=len(chunks),
    ))
    await db.commit()

    return {
        "status": "success",
        "filename": file.filename,
        "chunks_count": len(chunks),
        "message": f"성공적으로 {len(chunks)}개의 Chunk가 벡터 DB에 저장되었습니다.",
    }


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.DocumentMeta).order_by(models.DocumentMeta.uploaded_at.desc()))
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "chunk_count": d.chunk_count,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            }
            for d in docs
        ]
    }


@router.delete("/documents/{filename}")
async def delete_document(filename: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.DocumentMeta).where(models.DocumentMeta.filename == filename)
    )
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"'{filename}' 문서를 찾을 수 없습니다.")

    try:
        await asyncio.to_thread(
            qdrant.delete,
            collection_name=QDRANT_COLLECTION,
            points_selector=_qdrant_delete_filter(filename),
        )
        logger.info(f"[/documents/delete] Qdrant 삭제 완료: {filename}")
    except Exception as e:
        logger.error(f"[/documents/delete] Qdrant 삭제 실패: {filename} | {e}")
        raise HTTPException(status_code=500, detail=f"Qdrant 삭제 오류: {str(e)}")

    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
        logger.info(f"[/documents/delete] 원본 파일 삭제 완료: {doc.file_path}")

    await db.execute(
        delete(models.DocumentMeta).where(models.DocumentMeta.filename == filename)
    )
    await db.commit()
    logger.info(f"[/documents/delete] PostgreSQL 삭제 완료: {filename}")

    return {
        "status": "success",
        "filename": filename,
        "message": f"'{filename}' 문서의 벡터 데이터, 메타데이터, 원본 파일이 모두 삭제되었습니다.",
    }
