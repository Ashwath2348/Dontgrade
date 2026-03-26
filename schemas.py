from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[int] = None


class TextAnalysisCreate(BaseModel):
    input_text: str


class TextAnalysisOut(BaseModel):
    id: int
    input_text: str
    grade_level: float
    reading_ease: float
    simplified_text: Optional[str]
    clear_text: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class HistoryOut(BaseModel):
    analyses: List[TextAnalysisOut]
