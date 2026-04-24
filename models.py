from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from database import Base

class DocumentMeta(Base):
    __tablename__ = "document_meta"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), index=True)
    chunk_count = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text)
    answer = Column(Text)
    model_used = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
