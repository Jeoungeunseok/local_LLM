import io
import logging
import uuid
import docx
import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.http import models as qdrant_models

import models
from database import get_db
from config import QDRANT_COLLECTION
from utils import chunk_text
from services.vector_store import embedder, qdrant

logger = logging.getLogger("app")
router = APIRouter()

@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
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
        
    # Save to PostgreSQL
    new_doc = models.DocumentMeta(
        filename=file.filename,
        chunk_count=len(chunks)
    )
    db.add(new_doc)
    await db.commit()
        
    return {
        "status": "success",
        "filename": file.filename,
        "chunks_count": len(chunks),
        "message": f"성공적으로 {len(chunks)}개의 Chunk가 벡터 DB에 저장되었습니다."
    }

@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    """업로드된 문서 목록을 반환합니다."""
    result = await db.execute(select(models.DocumentMeta).order_by(models.DocumentMeta.uploaded_at.desc()))
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "chunk_count": d.chunk_count,
                "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None
            }
            for d in docs
        ]
    }

@router.delete("/documents/{filename}")
async def delete_document(filename: str, db: AsyncSession = Depends(get_db)):
    """파일명을 기준으로 Qdrant 벡터 데이터와 PostgreSQL 메타데이터를 모두 삭제합니다."""

    # 1. PostgreSQL에서 해당 파일명 레코드 존재 확인
    result = await db.execute(
        select(models.DocumentMeta).where(models.DocumentMeta.filename == filename)
    )
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"'{filename}' 문서를 찾을 수 없습니다.")

    # 2. Qdrant에서 filename payload 기준으로 벡터 데이터 삭제
    try:
        qdrant.delete(
            collection_name=QDRANT_COLLECTION,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="filename",
                            match=qdrant_models.MatchValue(value=filename)
                        )
                    ]
                )
            )
        )
        logger.info(f"[/documents/delete] Qdrant 삭제 완료: {filename}")
    except Exception as e:
        logger.error(f"[/documents/delete] Qdrant 삭제 실패: {filename} | {e}")
        raise HTTPException(status_code=500, detail=f"Qdrant 삭제 오류: {str(e)}")

    # 3. PostgreSQL에서 해당 파일명의 메타데이터 삭제 (동일 파일명 중복 업로드 포함 전체 삭제)
    await db.execute(
        delete(models.DocumentMeta).where(models.DocumentMeta.filename == filename)
    )
    await db.commit()
    logger.info(f"[/documents/delete] PostgreSQL 삭제 완료: {filename}")

    return {
        "status": "success",
        "filename": filename,
        "message": f"'{filename}' 문서의 벡터 데이터와 메타데이터가 모두 삭제되었습니다."
    }
