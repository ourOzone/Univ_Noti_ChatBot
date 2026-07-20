# 공지사항 RAG - CRUD API

`school`(학교) / `board`(게시판) / `document`(공지사항) 3개 테이블에 대한 CRUD REST API입니다.
**`chunk`(벡터 검색용 조각) 테이블은 요구사항대로 제외**했습니다. (그래서 이 API 자체는 pgvector가 필요 없어요.)

- 스택: **FastAPI + asyncpg (PostgreSQL)**
- 요청받은 최소 범위는 C·R 이지만, U·D도 얼마 안 되어 **풀 CRUD**로 만들었습니다. (C·R만 쓰고 싶으면 나머지 무시하면 됩니다.)

## 파일 구성

| 파일 | 설명 |
|------|------|
| `main.py` | FastAPI 앱 + 모든 CRUD 라우트 |
| `schemas.py` | 요청/응답 데이터 모델 (Pydantic) |
| `database.py` | DB 커넥션 풀 설정 |
| `seed.py` | 더미데이터 시딩 (학교/게시판/문서 각 1개) |
| `requirements.txt` | 의존성 |
| `.env.example` | DB 접속 정보 예시 |

## 실행 방법

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. DB 접속 정보 설정
`.env.example`을 복사해 `.env`를 만들고 본인 DB 정보로 수정하세요.
```bash
cp .env.example .env
# .env 안의 DATABASE_URL 을 본인 환경에 맞게 수정
# 예) postgresql://아이디:비밀번호@localhost:5432/DB이름
```
> 스키마(`schema.sql`)는 이미 DB에 반영해 두셨으니 그대로 사용하면 됩니다.

### 3. 더미데이터 넣기 (선택)
```bash
python seed.py
```
> `ON CONFLICT`(upsert)로 짜여 있어 **여러 번 실행해도 에러 없이** 안전합니다.

### 4. 서버 실행
```bash
uvicorn main:app --reload
```
- 실행 후 **http://localhost:8000/docs** 로 들어가면 Swagger UI에서 바로 테스트할 수 있어요.

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| **School** | | |
| POST | `/schools` | 학교 생성 |
| GET | `/schools` | 학교 목록 (`limit`, `offset`) |
| GET | `/schools/{id}` | 학교 단건 조회 |
| PUT | `/schools/{id}` | 학교 수정 |
| DELETE | `/schools/{id}` | 학교 삭제 |
| **Board** | | |
| POST | `/boards` | 게시판 생성 |
| GET | `/boards` | 게시판 목록 (`school_id` 필터 가능) |
| GET | `/boards/{id}` | 게시판 단건 조회 |
| PUT | `/boards/{id}` | 게시판 수정 (보낸 필드만) |
| DELETE | `/boards/{id}` | 게시판 삭제 |
| **Document** | | |
| POST | `/documents` | 공지 생성 |
| GET | `/documents` | 공지 목록 (`school_id`, `board_id`, `category` 필터 가능) |
| GET | `/documents/{id}` | 공지 단건 조회 |
| PUT | `/documents/{id}` | 공지 수정 (보낸 필드만) |
| DELETE | `/documents/{id}` | 공지 삭제 |

### 요청 예시
```bash
# 학교 생성
curl -X POST localhost:8000/schools \
  -H "Content-Type: application/json" \
  -d '{"name": "원광대학교"}'

# 게시판 생성 (school_id 필요)
curl -X POST localhost:8000/boards \
  -H "Content-Type: application/json" \
  -d '{"school_id": 1, "name": "공지사항"}'

# 공지 생성 (school_id, board_id 필요)
curl -X POST localhost:8000/documents \
  -H "Content-Type: application/json" \
  -d '{"school_id": 1, "board_id": 1, "url": "https://ex.com/1",
       "title": "장학금 안내", "content": "본문", "category": "장학"}'
```

## 참고 사항

- **에러 응답**: 중복(UNIQUE) → `409`, 존재하지 않는 FK(school_id/board_id) → `400`, 없는 id → `404` 로 깔끔하게 내려줍니다.
- **PUT 부분 수정**: 게시판·공지는 body에 **보낸 필드만** 바뀌고 나머지는 유지됩니다.
- **CASCADE 삭제**: 스키마에 `ON DELETE CASCADE`가 걸려 있어, 학교를 지우면 그 학교의 게시판·공지도 함께 삭제됩니다.
- 문서의 소속(school_id/board_id) 변경 기능은 넣지 않았습니다. 필요하면 `DocumentUpdate` 스키마에 두 필드를 추가하면 됩니다.
