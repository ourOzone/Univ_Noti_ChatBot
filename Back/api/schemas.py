"""
요청(입력) / 응답(출력) 데이터 모델 (Pydantic v2)

- ...Create : 새로 만들 때(POST) 받는 body
- ...Update : 수정할 때(PUT) 받는 body (보낸 필드만 부분 수정)
- ...Out    : 클라이언트에게 돌려줄 응답 형태
"""
from datetime import date, datetime

from pydantic import BaseModel


# ---------------------------------------------------------------
#  School (학교)
# ---------------------------------------------------------------
class SchoolCreate(BaseModel):
    name: str


class SchoolUpdate(BaseModel):
    name: str


class SchoolOut(BaseModel):
    id: int
    name: str


# ---------------------------------------------------------------
#  Board (게시판)
# ---------------------------------------------------------------
class BoardCreate(BaseModel):
    school_id: int
    name: str
    is_active: bool = True


class BoardUpdate(BaseModel):
    # 보낸 필드만 수정됨 (안 보낸 필드는 그대로 유지)
    name: str | None = None
    is_active: bool | None = None


class BoardOut(BaseModel):
    id: int
    school_id: int
    name: str
    is_active: bool


# ---------------------------------------------------------------
#  Document (공지사항 원문)
# ---------------------------------------------------------------
class DocumentCreate(BaseModel):
    school_id: int
    board_id: int
    url: str
    title: str
    content: str
    post_date: date | None = None
    eligibility: str | None = None
    deadline: date | None = None
    delete_date: date | None = None
    category: str | None = None


class DocumentUpdate(BaseModel):
    # 보낸 필드만 수정됨
    url: str | None = None
    title: str | None = None
    content: str | None = None
    post_date: date | None = None
    eligibility: str | None = None
    deadline: date | None = None
    delete_date: date | None = None
    category: str | None = None


class DocumentOut(BaseModel):
    id: int
    school_id: int
    board_id: int
    url: str
    title: str
    content: str
    post_date: date | None
    eligibility: str | None
    deadline: date | None
    delete_date: date | None
    category: str | None
    created_at: datetime
