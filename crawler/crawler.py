"""학교 공지사항 크롤러 (단일 파일 버전)

사용법:
  IDE 실행버튼(F5/▶)으로 그냥 실행 → run + url.json으로 자동 동작,
  결과는 같은 폴더의 posts.json에 저장.
  터미널에서 명령을 지정할 수도 있음:
    python crawler.py enrich url.json    # 원시 JSON → 완성 JSON (LLM 사용)
    python crawler.py crawl  url.json    # 크롤링 (모든 게시판·전 페이지 덤프)
    python crawler.py run    url.json    # 둘 다

url.json 원시 형태:
  { "학교": { "메인": {"url": "..."}, "기숙사": {"url": "..."} } }
enrich 후 완성 형태:
  { "학교": { "메인": { "boards": [
      {"name": "...", "url": "...", "fetch": "static", "selectors": {...}} ] } } }

posts.json 출력 형태:
  [ {"post_url": "...", "source_url": "..."}, ... ]

API 설정: 같은 폴더의 .env 파일에 NVIDIA_API_KEY=... 형태로 저장 (enrich에만 사용됨)
  필요시 NVIDIA_BASE_URL, NVIDIA_MODEL 도 .env에서 덮어쓸 수 있음
필요 패키지: pip install requests beautifulsoup4 lxml openai
  (dynamic 게시판 발견 시: pip install playwright && playwright install chromium)
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

# ============================================================ 설정
MAX_PAGES = 60
MAX_SELECTOR_RETRIES = 3

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept-Language": "ko,en;q=0.8"}

PAGE_PARAMS = ["pageIndex", "page", "pageNo", "pageNum", "cpage", "curPage", "pg"]


def log(*a):
    print(*a, file=sys.stderr)


# ============================================================ HTML 가져오기
def fetch_static(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding  # 오래된 학교 사이트 euc-kr 대응
    return r.text


def fetch_dynamic(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright 필요: pip install playwright && playwright install chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, timeout=30_000, wait_until="networkidle")
        html = page.content()
        browser.close()
    return html


def fetch(url: str, mode: str) -> str:
    return fetch_dynamic(url) if mode == "dynamic" else fetch_static(url)


# ============================================================ LLM (NVIDIA NIM)
def _load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(Path(__file__).resolve().parent / ".env")

API_KEY = os.environ.get("NVIDIA_API_KEY", "")
BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL = os.environ.get("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro")


def ask_llm_json(system: str, user: str):
    if not API_KEY:
        raise RuntimeError("NVIDIA_API_KEY 가 설정되지 않았습니다. crawler.py 옆에 .env 파일을 만들고 "
                           "'NVIDIA_API_KEY=nvapi-...' 형태로 저장하세요.")
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.0, max_tokens=2048,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    text = resp.choices[0].message.content.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)  # 마크다운 펜스 제거
    if m:
        text = m.group(1)
    for start in (text.find("{"), text.find("[")):  # 잡담 섞였을 때 방어
        if start != -1:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
    return json.loads(text)


# ============================================================ 날짜/URL 유틸
DATE_FORMATS = ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%y-%m-%d", "%y.%m.%d", "%y/%m/%d",
                "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M"]


def parse_date(text: str):
    t = re.sub(r"[\[\]()]", "", text or "").strip()
    m = re.search(r"\d{2,4}[-./]\d{1,2}[-./]\d{1,2}( \d{1,2}:\d{2})?", t)
    if not m:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(m.group(0), fmt)
        except ValueError:
            continue
    return None


def page_url(board_url: str, page: int) -> str:
    """페이지 파라미터 교체/추가."""
    p = urlparse(board_url)
    params = dict(parse_qsl(p.query, keep_blank_values=True))
    key = next((k for k in params if k in PAGE_PARAMS), None)
    params[key or "pageIndex"] = str(page)
    return urlunparse((p.scheme, p.netloc, p.path, "", urlencode(params), ""))


# ============================================================ enrich: 게시판 발견
def discover_boards(section_url: str) -> list[dict]:
    html = fetch_static(section_url)
    soup = BeautifulSoup(html, "lxml")
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        url = urljoin(section_url, href)
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:60]
        if text and url not in seen:
            seen.add(url)
            links.append({"text": text, "url": url})
    links = links[:300]

    host = urlparse(section_url).netloc
    system = ("너는 한국 대학교 웹사이트 링크 목록에서 '공지사항 게시판 목록 페이지'만 골라내는 도구다. "
              "반드시 JSON 배열만 출력. 설명, 마크다운 금지.")
    user = f"""아래는 {section_url} 에서 추출한 링크들이다.
"게시글 목록이 표시되는 게시판 페이지"만 골라라.
- 포함: 학사공지, 장학공지, 채용정보, 기숙사공지 등 게시판 목록
- 제외: 개별 게시글, 로그인, 사이트맵, 소개, SNS, 호스트가 {host}와 다른 외부 링크
- name은 한국어 라벨
출력: [{{"name":"...","url":"..."}}]

{json.dumps(links, ensure_ascii=False)}"""
    result = ask_llm_json(system, user)
    out, dedup = [], set()
    for b in (result if isinstance(result, list) else []):
        u = b.get("url")
        if u and u not in dedup:
            dedup.add(u)
            out.append({"name": b.get("name") or u, "url": u})
    return out


# ============================================================ enrich: 셀렉터 생성+검증
def _slim_html(html: str, limit=12_000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "meta", "link"]):
        t.decompose()
    node = None
    for sel in ["table tbody", "table", "ul.board-list", "div.board-list", "main", "body"]:
        found = soup.select_one(sel)
        if found and len(found.find_all("a")) >= 3:
            node = found
            break
    return re.sub(r"\s+", " ", str(node or soup.body or soup))[:limit]


def validate_selectors(html: str, base_url: str, sel: dict):
    """(성공여부, 실패사유) — 실제로 적용해서 검사."""
    soup = BeautifulSoup(html, "lxml")
    try:
        rows = soup.select(sel["row"])
    except Exception as e:
        return False, f"row 셀렉터 문법 오류: {e}"
    if not rows:
        return False, f"row '{sel['row']}' 매칭 0건"
    samples, ok_t, ok_d, ok_l = [], 0, 0, 0
    for row in rows[:10]:
        try:
            t, l, d = (row.select_one(sel["title"]), row.select_one(sel["link"]),
                       row.select_one(sel["date"]))
        except Exception as e:
            return False, f"하위 셀렉터 문법 오류: {e}"
        title = t.get_text(" ", strip=True) if t else ""
        ok_t += bool(title)
        ok_l += bool(l and l.has_attr("href"))
        ok_d += bool(parse_date(d.get_text(" ", strip=True) if d else ""))
        samples.append({"title": title[:40],
                        "date": d.get_text(" ", strip=True)[:20] if d else ""})
    n = len(samples)
    if ok_t < max(1, n // 2):
        return False, f"title 대부분 빈 값 ({ok_t}/{n}). 샘플: {samples[:3]}"
    if ok_d < max(1, n // 2):
        return False, f"date 파싱 실패 ({ok_d}/{n}). 샘플: {samples[:3]}"
    if ok_l == 0:
        return False, "link에서 href를 못 얻음"
    return True, ""


def generate_selectors(url: str, html: str) -> dict:
    system = ("너는 한국 대학 공지 게시판 HTML을 파싱할 CSS 셀렉터를 만드는 도구다. "
              "반드시 JSON 객체만 출력. 설명, 마크다운 금지.")
    base = f"""아래 게시판 목록 HTML에서 게시글 파싱용 CSS 셀렉터를 만들어라.
- row: 게시글 한 건의 반복 요소 (보통 tbody tr 또는 li). thead 제외되게.
- title/link/date: row 기준 상대 셀렉터. link는 href 있는 <a>.
출력: {{"row":"...","title":"...","link":"...","date":"..."}}

HTML:
{_slim_html(html)}"""
    fb = None
    for i in range(1, MAX_SELECTOR_RETRIES + 1):
        user = base if not fb else base + f"\n\n이전 시도 실패. 다른 셀렉터를 만들어라.\n이전: {fb[0]}\n사유: {fb[1]}"
        sel = ask_llm_json(system, user)
        if not (isinstance(sel, dict) and all(k in sel for k in ("row", "title", "link", "date"))):
            fb = (sel, "row/title/link/date 4개 키 필수")
            continue
        ok, reason = validate_selectors(html, url, sel)
        if ok:
            return sel
        fb = (sel, reason)
        log(f"    [재시도 {i}/{MAX_SELECTOR_RETRIES}] {reason[:120]}")
    raise RuntimeError(f"셀렉터 생성 실패: {url} — {fb[1][:200]}")


def enrich(config: dict) -> dict:
    """원시 섹션({"url": "..."})만 골라 boards로 채운다. 완성 섹션은 그대로 둠(멱등)."""
    for school, sections in config.items():
        for sec_name, sec in sections.items():
            if "boards" in sec:      # 이미 완성
                continue
            raw = sec.get("url")
            if not raw:
                continue
            log(f"[enrich] {school}/{sec_name} ← {raw}")
            boards = []
            for b in discover_boards(raw):
                log(f"  - {b['name']}")
                try:
                    mode, html = "static", fetch_static(b["url"])
                    try:
                        selectors = generate_selectors(b["url"], html)
                    except RuntimeError:
                        log("    static 실패 → dynamic 재시도")
                        mode, html = "dynamic", fetch_dynamic(b["url"])
                        selectors = generate_selectors(b["url"], html)
                    boards.append({"name": b["name"], "url": b["url"],
                                   "fetch": mode, "selectors": selectors})
                except Exception as e:
                    log(f"    [실패, 건너뜀] {e}")
            sections[sec_name] = {"boards": boards}
    return config


# ============================================================ crawl
def parse_rows(html: str, base_url: str, sel: dict) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for row in soup.select(sel["row"]):
        l = row.select_one(sel["link"])
        if not (l and l.has_attr("href")):
            continue
        href = l["href"].strip()
        if href.startswith("javascript:"):   # onclick형 게시판: 숫자 ID라도 건짐
            m = re.search(r"['\"(](\d{3,})['\")]", href)
            if not m:
                continue
            href = f"{base_url}?extracted_id={m.group(1)}"
        out.append(urljoin(base_url, href))
    return out


def crawl_board(board: dict) -> list[dict]:
    out, prev_urls = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = board["url"] if page == 1 else page_url(board["url"], page)
        try:
            html = fetch(url, board["fetch"])
        except Exception as e:
            log(f"    [fetch 실패 p{page}] {e}")
            break
        urls = parse_rows(html, board["url"], board["selectors"])
        cur = set(urls)
        if not urls or cur == prev_urls:   # 빈 페이지 or 페이지 파라미터 안 먹음
            break
        prev_urls = cur
        for u in urls:
            out.append({"post_url": u, "source_url": board["url"]})
    return out


def crawl(config: dict) -> list[dict]:
    results = []
    for school, sections in config.items():
        for sec_name, sec in sections.items():
            for b in sec.get("boards", []):
                log(f"[crawl] {school}/{sec_name}/{b['name']}")
                posts = crawl_board(b)
                log(f"    {len(posts)}건")
                results.extend(posts)
    return results


# ============================================================ main
DEFAULT_CMD = "run"             # 실행버튼으로 돌릴 때: enrich / crawl / run
DEFAULT_CONFIG = "url.json"     # 설정 파일 (crawler.py와 같은 폴더)
OUTPUT_FILE = "posts.json"      # 크롤링 결과 저장 파일


def main():
    here = Path(__file__).resolve().parent
    # 터미널 인자가 있으면 그걸 쓰고, 없으면(=IDE 실행버튼) 기본값 사용
    if len(sys.argv) == 3 and sys.argv[1] in ("enrich", "crawl", "run"):
        cmd, cfg_path = sys.argv[1], Path(sys.argv[2])
    else:
        cmd, cfg_path = DEFAULT_CMD, here / DEFAULT_CONFIG

    if not cfg_path.exists():
        log(f"설정 파일이 없습니다: {cfg_path}")
        sys.exit(1)
    config = json.loads(cfg_path.read_text(encoding="utf-8"))

    if cmd in ("enrich", "run"):
        config = enrich(config)
        cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"완성 JSON 저장: {cfg_path}")
    if cmd in ("crawl", "run"):
        results = crawl(config)
        out = here / OUTPUT_FILE
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"결과 저장: {out} ({len(results)}건)")


if __name__ == "__main__":
    main()