"""
더미데이터 시더 : 학교 1개 / 게시판 1개 / 문서(공지) 1개
(chunk 는 제외)

실행:
    python seed.py

UNIQUE 제약 때문에 여러 번 실행해도 에러가 안 나도록 ON CONFLICT(upsert) 사용.
"""
import asyncio
from datetime import date

import database


async def seed() -> None:
    await database.connect()
    db = database.pool()

    # 1) 학교 1개  (school.name 이 UNIQUE → 없으면 추가, 있으면 기존 것 사용)
    school = await db.fetchrow(
        """INSERT INTO school (name) VALUES ($1)
           ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
           RETURNING id, name""",
        "원광대학교",
    )
    print(f"[school]   id={school['id']}  name={school['name']}")

    # 2) 게시판 1개  ((school_id, name) 이 UNIQUE)
    board = await db.fetchrow(
        """INSERT INTO board (school_id, name, is_active) VALUES ($1, $2, TRUE)
           ON CONFLICT (school_id, name) DO UPDATE SET is_active = TRUE
           RETURNING id, school_id, name, is_active""",
        school["id"],
        "공지사항",
    )
    print(f"[board]    id={board['id']}  name={board['name']}")

    # 3) 공지(문서) 1개  (document.url 이 UNIQUE)
    document = await db.fetchrow(
        """INSERT INTO document
             (school_id, board_id, url, title, content,
              post_date, eligibility, deadline, category)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           ON CONFLICT (url) DO UPDATE SET title = EXCLUDED.title
           RETURNING id, title, url""",
        school["id"],
        board["id"],
        "https://www.wku.ac.kr/notice/2026-scholarship-001",
        "2026학년도 1학기 국가장학금 신청 안내",
        (
            "2026학년도 1학기 국가장학금 신청 기간을 안내드립니다. "
            "한국장학재단 홈페이지에서 온라인으로 신청 가능하며, "
            "소득분위에 따라 지원 금액이 차등 지급됩니다. "
            "기한 내에 신청하지 않으면 지원을 받을 수 없으니 유의하시기 바랍니다."
        ),
        date(2026, 2, 3),  # post_date (게시일)
        "재학생 및 신입생 (소득 8구간 이하)",  # eligibility (지원조건)
        date(2026, 3, 15),  # deadline (마감일)
        "장학",  # category (카테고리)
    )
    print(f"[document] id={document['id']}  title={document['title']}")

    await database.disconnect()
    print("\n✅ 더미데이터 시딩 완료!")


if __name__ == "__main__":
    asyncio.run(seed())
