-- ============================================================
--  공지사항 RAG 시스템 스키마 (PostgreSQL + pgvector)
--  임베딩 모델: BAAI/bge-m3  (1024차원, 최대 8192 토큰)
-- ============================================================

-- pgvector 확장 설치: embedding 컬럼의 vector 타입을 쓰려면 반드시 필요
CREATE EXTENSION IF NOT EXISTS vector;


-- ------------------------------------------------------------
--  school : 학교
-- ------------------------------------------------------------
CREATE TABLE school (
    id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- 자동 증가 PK (SERIAL과 같은 역할)
    name TEXT   NOT NULL,
    UNIQUE (name)          -- name이 유일해야 "없으면 추가(upsert)" 로직이 성립
);


-- ------------------------------------------------------------
--  board : 게시판 (학교마다 여러 개)
-- ------------------------------------------------------------
CREATE TABLE board (
    id        BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    school_id BIGINT  NOT NULL REFERENCES school(id) ON DELETE CASCADE,
    name      TEXT    NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (school_id, name)   -- "공지사항" 게시판은 학교마다 있을 수 있어서
                               -- (학교, 게시판이름) 조합으로 유일하게 잡음
);


-- ------------------------------------------------------------
--  document : 공지사항 원문 (게시글 1개 = 1 row)
-- ------------------------------------------------------------
CREATE TABLE document (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES school(id) ON DELETE CASCADE,
    board_id  BIGINT NOT NULL REFERENCES board(id)  ON DELETE CASCADE,
    url       TEXT   NOT NULL,
    title     TEXT   NOT NULL,
    content   TEXT   NOT NULL,
    post_date DATE,                 -- 게시글에 시각까지 있으면 TIMESTAMPTZ로 바꿔도 됨

    eligibility TEXT,               -- [추가] 지원조건 (없는 공지도 많으니 NULL 허용)
    deadline    DATE,               -- [추가] 마감일
    delete_date DATE,               -- [추가] 삭제일 (예약 삭제/만료 예정일)
    category    TEXT,               -- [추가] 카테고리 (예: 장학, 취업, 학사 ...)

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (url)                    -- 같은 글 중복 저장 방지

);


-- ------------------------------------------------------------
--  chunk : 벡터 검색용 조각 (게시글 1개 = chunk 여러 개)
-- ------------------------------------------------------------
CREATE TABLE chunk (
    id          BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id BIGINT  NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    school_id   BIGINT  NOT NULL REFERENCES school(id)   ON DELETE CASCADE,  -- (비정규화) 검색 필터용
    board_id    BIGINT  NOT NULL REFERENCES board(id)    ON DELETE CASCADE,  -- (비정규화) 검색 필터용
    category    TEXT,                      -- [추가] (비정규화) 검색 필터용, document.category 복사
    seq         INTEGER NOT NULL,          -- 문서 안에서 몇 번째 청크인지 (0,1,2,...)
    content     TEXT    NOT NULL,          -- 실제로 임베딩한 텍스트
    embedding   vector(1024),             -- bge-m3 벡터
    tsv         TSVECTOR,                  -- 키워드(전문) 검색용
    token_count INTEGER,                   -- 이 청크의 토큰 수 (8192 넘지 않게 관리)
    UNIQUE (document_id, seq)
);

-- 참고) tsv를 DB가 자동으로 채우게 하려면 위 tsv 줄 대신 아래처럼 생성 컬럼으로:
--   tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
-- (한국어 형태소 분석은 기본 설정이 약하니, 앱에서 직접 채우는 방법도 고려)


-- ------------------------------------------------------------
--  인덱스 (검색 속도를 위해 필요)
-- ------------------------------------------------------------

-- 벡터 유사도 검색: 코사인 기준 HNSW (pgvector 0.5+)
CREATE INDEX chunk_embedding_hnsw
    ON chunk USING hnsw (embedding vector_cosine_ops);

-- 키워드 검색
CREATE INDEX chunk_tsv_gin
    ON chunk USING gin (tsv);

-- 조인/필터에 자주 쓰는 외래키 컬럼 (PostgreSQL은 FK에 인덱스를 자동 생성하지 않음)
CREATE INDEX board_school_id_idx    ON board(school_id);
CREATE INDEX document_school_id_idx ON document(school_id);
CREATE INDEX document_board_id_idx  ON document(board_id);
CREATE INDEX chunk_document_id_idx  ON chunk(document_id);

CREATE INDEX chunk_school_id_idx ON chunk(school_id);
CREATE INDEX chunk_board_id_idx  ON chunk(board_id);

-- [추가] 카테고리 필터용 인덱스
CREATE INDEX chunk_category_idx ON chunk(category);
