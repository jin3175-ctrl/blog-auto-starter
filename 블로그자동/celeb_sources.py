"""연예 글 생성용 실시간 소스 스크래핑.

- 기사(사실 재료): 네이버 연예 랭킹뉴스 목록 + 기사 본문.
- 제목·본문 '공식'(현재 홈판이 밀어주는 여러 연예 블로그): section.blog 스타·연예인(디렉토리12) 피드.
"""
from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

_UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
RANK_URL = "https://m.entertain.naver.com/ranking"
THEME_URL = ("https://section.blog.naver.com/ThemePost.naver"
             "?directoryNo={d}&activeDirectorySeq=1&currentPage={p}")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def fetch_news_ranking(limit: int = 20) -> list[dict]:
    """연예 랭킹뉴스 목록 [{rank,title,snippet,url}]."""
    out: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=_UA_M)
        try:
            pg.goto(RANK_URL, wait_until="domcontentloaded", timeout=40000)
            pg.wait_for_timeout(1800)
            items = pg.eval_on_selector_all(
                "a",
                """els => els.map(e => ({txt:(e.innerText||'').trim(), h:e.href}))
                    .filter(x => x.txt && /\\/ranking\\/article\\//.test(x.h))""")
        finally:
            b.close()
    seen = set()
    for it in items:
        url = it["h"].split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        lines = [l.strip() for l in it["txt"].splitlines() if l.strip()]
        # 첫 줄이 'N위'면 제거
        if lines and re.match(r"^\d+위$", lines[0]):
            lines = lines[1:]
        if not lines:
            continue
        out.append({"rank": len(out) + 1, "title": lines[0],
                    "snippet": _clean(" ".join(lines[1:]))[:120], "url": url})
        if len(out) >= limit:
            break
    return out


_NEWS_SEARCH = "https://m.search.naver.com/search.naver?where=m_news&sort=1&query={q}"


def fetch_news_search(query: str, limit: int = 5) -> list[dict]:
    """네이버 뉴스 검색(최신순)에서 [{title, snippet, body, url}]. 특정 소재(나솔·이혼숙려 등) 능동 확보용.
    ★기사 링크가 최신 DOM에서 불안정해, 검색 스니펫(문단)을 body 소재로 함께 담는다(url='' 가능)."""
    import urllib.parse
    texts: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=_UA_M)
        try:
            pg.goto(_NEWS_SEARCH.format(q=urllib.parse.quote(query)),
                    wait_until="domcontentloaded", timeout=35000)
            pg.wait_for_timeout(2200)
            texts = pg.eval_on_selector_all(
                ".sds-comps-text",
                "els => els.map(e => (e.innerText||'').trim()).filter(t => t.length >= 12)")
        finally:
            b.close()
    texts = [_clean(t) for t in texts]
    # 짧은 줄(제목, ~55자, 문장부호로 안 끝남) 뒤에 오는 긴 줄(스니펫 문단)을 짝짓는다.
    out: list[dict] = []
    seen: set = set()
    i = 0
    while i < len(texts) and len(out) < limit:
        t = texts[i]
        is_title = 12 <= len(t) <= 60
        snip = ""
        if is_title and i + 1 < len(texts) and len(texts[i + 1]) > 60:
            snip = texts[i + 1]
            i += 2
        else:
            i += 1
        # ★관련도: 소재가 '제목'에 있어야 채택(스니펫만 걸치는 오탐 제거).
        qkey = query.replace(" ", "")
        if not is_title or qkey not in t.replace(" ", ""):
            continue
        key = t[:30]
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": t[:90], "snippet": snip[:160],
                    "body": (t + " " + snip)[:1200], "url": ""})
    return out


def fetch_article(url: str) -> dict:
    """기사 본문 {title, body}."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=_UA_M)
        title, body = "", ""
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=40000)
            pg.wait_for_timeout(1500)
            for sel in ["h2.end_tit", ".media_end_head_headline", "h2", "title"]:
                try:
                    title = _clean(pg.locator(sel).first.inner_text(timeout=2500))
                    if title:
                        break
                except Exception:  # noqa: BLE001
                    pass
            for sel in ["#comp_news_article ._article_content", "#dic_area",
                        ".article_body", "#newsEndContents", "article"]:
                try:
                    body = pg.locator(sel).first.inner_text(timeout=3500)
                    if body.strip():
                        break
                except Exception:  # noqa: BLE001
                    pass
        finally:
            b.close()
    body = re.sub(r"원본 이미지 보기", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return {"title": title, "body": body}


def fetch_theme_titles(directory: int = 12, n: int = 40, max_pages: int = 3) -> list[str]:
    """현재 밀어주는 연예 블로그 글 제목(여러 블로그). directory=12: 스타·연예인."""
    titles: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1280, "height": 2400})
        try:
            for pno in range(1, max_pages + 1):
                pg.goto(THEME_URL.format(d=directory, p=pno), wait_until="domcontentloaded", timeout=35000)
                pg.wait_for_timeout(2000)
                loc = pg.locator(".title_post")
                for i in range(loc.count()):
                    t = _clean(loc.nth(i).inner_text())
                    if t and len(t) >= 6 and t not in titles:
                        titles.append(t)
                if len(titles) >= n:
                    break
        finally:
            b.close()
    return titles[:n]


def fetch_theme_posts(directory: int = 12, n: int = 6) -> list[dict]:
    """현재 밀어주는 연예 블로그 글 [{title,url}] (본문 구조 샘플용)."""
    out: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1280, "height": 2400})
        try:
            pg.goto(THEME_URL.format(d=directory, p=1), wait_until="domcontentloaded", timeout=35000)
            pg.wait_for_timeout(2200)
            items = pg.eval_on_selector_all(
                "a",
                """els => els.map(e => ({t:(e.innerText||'').trim(), h:e.href}))
                    .filter(x => x.t && /blog\\.naver\\.com\\/[^/]+\\/\\d+/.test(x.h))""")
        finally:
            b.close()
    seen = set()
    for it in items:
        url = it["h"].split("?")[0]
        if url in seen or len(it["t"]) < 8:
            continue
        seen.add(url)
        out.append({"title": _clean(it["t"])[:60], "url": url})
        if len(out) >= n:
            break
    return out


def fetch_theme_thumbnails(directory: int = 30, n: int = 6, max_pages: int = 2) -> list[str]:
    """현재 밀어주는 글들의 '대표 썸네일 이미지 URL' 목록. 썸네일 공식 추출용(비전 분석).
    directory=30: IT·컴퓨터."""
    urls: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1280, "height": 2400})
        try:
            for pno in range(1, max_pages + 1):
                pg.goto(THEME_URL.format(d=directory, p=pno), wait_until="domcontentloaded", timeout=35000)
                pg.wait_for_timeout(2000)
                imgs = pg.eval_on_selector_all(
                    "img",
                    """els => els.map(e => e.currentSrc || e.src || '')
                        .filter(s => /pstatic\\.net|blogthumb|postfiles/.test(s))""")
                for s in imgs:
                    u = s.split("?")[0]
                    if u and u not in urls:
                        urls.append(u)
                if len(urls) >= n:
                    break
        finally:
            b.close()
    return urls[:n]


def fetch_blog_body(url: str, max_chars: int = 1800) -> str:
    """블로그 글 본문 텍스트(모바일). 구조/톤 샘플용."""
    murl = re.sub(r"^https?://blog\.naver\.com/", "https://m.blog.naver.com/", url)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=_UA_M)
        txt = ""
        try:
            pg.goto(murl, wait_until="domcontentloaded", timeout=40000)
            pg.wait_for_timeout(1500)
            for sel in [".se-main-container", "#postViewArea", ".post_ct"]:
                try:
                    txt = pg.locator(sel).first.inner_text(timeout=4000)
                    if txt.strip():
                        break
                except Exception:  # noqa: BLE001
                    pass
        finally:
            b.close()
    return re.sub(r"\n{3,}", "\n\n", txt).strip()[:max_chars]


if __name__ == "__main__":
    news = fetch_news_ranking(8)
    print(f"[랭킹뉴스 {len(news)}]")
    for a in news:
        print(f"  {a['rank']}. {a['title']}")
    tt = fetch_theme_titles(12, 10)
    print(f"[연예블로그 제목 {len(tt)}]")
    for t in tt:
        print("  -", t)
