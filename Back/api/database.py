"""
DB 연결 관리 (asyncpg 커넥션 풀)

- DATABASE_URL 환경변수로 접속 정보를 받습니다.
- .env 파일이 있으면 자동으로 읽어옵니다.
- FastAPI 앱이 켜질 때 connect(), 꺼질 때 disconnect() 를 호출합니다.
"""
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()  # .env 파일에서 DATABASE_URL 등을 읽어옴

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/notice_rag",
)

# 전역 커넥션 풀 (앱 전체가 하나의 풀을 공유)
_pool: asyncpg.Pool | None = None


async def connect() -> None:
    """앱 시작 시 커넥션 풀 생성."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)


async def disconnect() -> None:
    """앱 종료 시 커넥션 풀 정리."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    """라우터에서 풀을 꺼내 쓸 때 사용."""
    if _pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았습니다. connect() 를 먼저 호출하세요.")
    return _pool
