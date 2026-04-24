from typing import List, Literal
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: List[ChatMessage] = Field(default_factory=list)

class ChatResponse(BaseModel):
    answer: str
    model: str

class RagRequest(BaseModel):
    question: str = Field(min_length=1)

class RagSource(BaseModel):
    filename: str
    text: str
    score: float

class RagResponse(BaseModel):
    answer: str
    model: str
    sources: List[RagSource]
