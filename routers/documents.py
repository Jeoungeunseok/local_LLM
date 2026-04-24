import io
import uuid
import docx
import fitz
from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.http import models as qdrant_models

import models
from database import get_db
from config import QDRANT_COLLECTION
from utils import chunk_text
from services.vector_store import embedder, qdrant

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
