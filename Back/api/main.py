"""
공지사항 RAG 시스템 - CRUD API
====================================================
대상 테이블 : school, board, document   (chunk 는 제외)
스택        : FastAPI + asyncpg (PostgreSQL)

실행:
    uvicorn main:app --reload
문서(자동 생성):
    http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Response

import database
from schemas import (
    BoardCreate,
    BoardOut,
    BoardUpdate,
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    SchoolCreate,
    SchoolOut,
    SchoolUpdate,
)


# 앱 시작/종료 시 DB 풀을 열고 닫음
@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()


app = FastAPI(title="공지사항 RAG CRUD API", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------
#  헬퍼: 부분 수정(PUT)용 SET 절 만들기
#  - 컬럼명은 Pydantic 모델에서 온 고정 값이라 SQL 인젝션 위험 없음
#  - 값은 전부 $1, $2 ... 로 파라미터 바인딩
# ---------------------------------------------------------------
def build_set_clause(data: dict, start: int = 1):
    cols = list(data.keys())
    clause = ", ".join(f"{col} = ${i}" for i, col in enumerate(cols, start=start))
    values = [data[col] for col in cols]
    return clause, values


@app.get("/", tags=["root"])
async def root():
    return {"message": "공지사항 RAG CRUD API", "docs": "/docs"}


# ==================================================================
#  School (학교)
# ==================================================================
@app.post("/schools", response_model=SchoolOut, status_code=201, tags=["school"])
async def create_school(payload: SchoolCreate):
    try:
        row = await database.pool().fetchrow(
            "INSERT INTO school (name) VALUES ($1) RETURNING id, name",
            payload.name,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"이미 존재하는 학교입니다: {payload.name}")
    return dict(row)


@app.get("/schools", response_model=list[SchoolOut], tags=["school"])
async def list_schools(limit: int = 100, offset: int = 0):
    rows = await database.pool().fetch(
        "SELECT id, name FROM school ORDER BY id LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [dict(r) for r in rows]


@app.get("/schools/{school_id}", response_model=SchoolOut, tags=["school"])
async def get_school(school_id: int):
    row = await database.pool().fetchrow(
        "SELECT id, name FROM school WHERE id = $1", school_id
    )
    if row is None:
        raise HTTPException(404, "학교를 찾을 수 없습니다.")
    return dict(row)


@app.put("/schools/{school_id}", response_model=SchoolOut, tags=["school"])
async def update_school(school_id: int, payload: SchoolUpdate):
    try:
        row = await database.pool().fetchrow(
            "UPDATE school SET name = $1 WHERE id = $2 RETURNING id, name",
            payload.name,
            school_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"이미 존재하는 학교 이름입니다: {payload.name}")
    if row is None:
        raise HTTPException(404, "학교를 찾을 수 없습니다.")
    return dict(row)


@app.delete("/schools/{school_id}", status_code=204, tags=["school"])
async def delete_school(school_id: int):
    result = await database.pool().execute(
        "DELETE FROM school WHERE id = $1", school_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "학교를 찾을 수 없습니다.")
    return Response(status_code=204)


# ==================================================================
#  Board (게시판)
# ==================================================================
@app.post("/boards", response_model=BoardOut, status_code=201, tags=["board"])
async def create_board(payload: BoardCreate):
    try:
        row = await database.pool().fetchrow(
            """INSERT INTO board (school_id, name, is_active)
               VALUES ($1, $2, $3)
               RETURNING id, school_id, name, is_active""",
            payload.school_id,
            payload.name,
            payload.is_active,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(400, f"존재하지 않는 school_id 입니다: {payload.school_id}")
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "같은 학교에 동일한 이름의 게시판이 이미 있습니다.")
    return dict(row)


@app.get("/boards", response_model=list[BoardOut], tags=["board"])
async def list_boards(school_id: int | None = None, limit: int = 100, offset: int = 0):
    if school_id is not None:
        rows = await database.pool().fetch(
            """SELECT id, school_id, name, is_active FROM board
               WHERE school_id = $1 ORDER BY id LIMIT $2 OFFSET $3""",
            school_id,
            limit,
            offset,
        )
    else:
        rows = await database.pool().fetch(
            """SELECT id, school_id, name, is_active FROM board
               ORDER BY id LIMIT $1 OFFSET $2""",
            limit,
            offset,
        )
    return [dict(r) for r in rows]


@app.get("/boards/{board_id}", response_model=BoardOut, tags=["board"])
async def get_board(board_id: int):
    row = await database.pool().fetchrow(
        "SELECT id, school_id, name, is_active FROM board WHERE id = $1", board_id
    )
    if row is None:
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    return dict(row)


@app.put("/boards/{board_id}", response_model=BoardOut, tags=["board"])
async def update_board(board_id: int, payload: BoardUpdate):
    data = payload.model_dump(exclude_unset=True)  # 보낸 필드만
    if not data:
        raise HTTPException(400, "수정할 내용이 없습니다.")
    clause, values = build_set_clause(data, start=1)
    try:
        row = await database.pool().fetchrow(
            f"""UPDATE board SET {clause} WHERE id = ${len(values) + 1}
                RETURNING id, school_id, name, is_active""",
            *values,
            board_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "같은 학교에 동일한 이름의 게시판이 이미 있습니다.")
    if row is None:
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    return dict(row)


@app.delete("/boards/{board_id}", status_code=204, tags=["board"])
async def delete_board(board_id: int):
    result = await database.pool().execute(
        "DELETE FROM board WHERE id = $1", board_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    return Response(status_code=204)


# ==================================================================
#  Document (공지사항 원문)
# ==================================================================
# SELECT / RETURNING 에서 공통으로 쓰는 컬럼 목록
DOC_COLS = (
    "id, school_id, board_id, url, title, content, "
    "post_date, eligibility, deadline, delete_date, category, created_at"
)


@app.post("/documents", response_model=DocumentOut, status_code=201, tags=["document"])
async def create_document(payload: DocumentCreate):
    try:
        row = await database.pool().fetchrow(
            f"""INSERT INTO document
                  (school_id, board_id, url, title, content,
                   post_date, eligibility, deadline, delete_date, category)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING {DOC_COLS}""",
            payload.school_id,
            payload.board_id,
            payload.url,
            payload.title,
            payload.content,
            payload.post_date,
            payload.eligibility,
            payload.deadline,
            payload.delete_date,
            payload.category,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(400, "존재하지 않는 school_id 또는 board_id 입니다.")
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"이미 등록된 URL 입니다: {payload.url}")
    return dict(row)


@app.get("/documents", response_model=list[DocumentOut], tags=["document"])
async def list_documents(
    school_id: int | None = None,
    board_id: int | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    # 넘어온 필터만 골라서 WHERE 절을 동적으로 구성
    conditions: list[str] = []
    params: list = []
    if school_id is not None:
        params.append(school_id)
        conditions.append(f"school_id = ${len(params)}")
    if board_id is not None:
        params.append(board_id)
        conditions.append(f"board_id = ${len(params)}")
    if category is not None:
        params.append(category)
        conditions.append(f"category = ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    rows = await database.pool().fetch(
        f"""SELECT {DOC_COLS} FROM document
            {where} ORDER BY id DESC LIMIT ${limit_idx} OFFSET ${offset_idx}""",
        *params,
    )
    return [dict(r) for r in rows]


@app.get("/documents/{document_id}", response_model=DocumentOut, tags=["document"])
async def get_document(document_id: int):
    row = await database.pool().fetchrow(
        f"SELECT {DOC_COLS} FROM document WHERE id = $1", document_id
    )
    if row is None:
        raise HTTPException(404, "공지사항을 찾을 수 없습니다.")
    return dict(row)


@app.put("/documents/{document_id}", response_model=DocumentOut, tags=["document"])
async def update_document(document_id: int, payload: DocumentUpdate):
    data = payload.model_dump(exclude_unset=True)  # 보낸 필드만
    if not data:
        raise HTTPException(400, "수정할 내용이 없습니다.")
    clause, values = build_set_clause(data, start=1)
    try:
        row = await database.pool().fetchrow(
            f"""UPDATE document SET {clause} WHERE id = ${len(values) + 1}
                RETURNING {DOC_COLS}""",
            *values,
            document_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "이미 등록된 URL 입니다.")
    if row is None:
        raise HTTPException(404, "공지사항을 찾을 수 없습니다.")
    return dict(row)


@app.delete("/documents/{document_id}", status_code=204, tags=["document"])
async def delete_document(document_id: int):
    result = await database.pool().execute(
        "DELETE FROM document WHERE id = $1", document_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "공지사항을 찾을 수 없습니다.")
    return Response(status_code=204)
