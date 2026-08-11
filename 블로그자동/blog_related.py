"""내 블로그(ioiykd8599) 글 목록 수집 + 현재 글과 유사한 글 N개 선정."""
from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

import config


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def fetch_my_posts(blog_id: str, limit: int = 30) -> list[dict]:
    """모바일 블로그 목록에서 {logNo, title, url} 수집."""
    posts: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=config.SESSION_FILE)
        pg = ctx.new_page()
        pg.set_default_timeout(20000)
        try:
            pg.goto(f"https://m.blog.naver.com/{blog_id}?tab=1", wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            raw = pg.evaluate("""() => {
                const out=[];
                document.querySelectorAll("a[href*='logNo=']").forEach(a=>{
                    const m=(a.href||'').match(/logNo=(\\d+)/); if(!m) return;
                    let card=a.closest('li, .item, .post, div'); let title='';
                    if(card){ const el=card.querySelector("strong, .tit, .title, .se-title, .se_title"); if(el) title=(el.textContent||'').replace(/\\s+/g,' ').trim(); }
                    if(!title) title=(a.textContent||'').replace(/\\s+/g,' ').trim();
                    if(title && !/사진 개수|더보기|공감|댓글|이웃|카테고리/.test(title))
                        out.push({logNo:m[1], title:title.slice(0,80)});
                });
                return out;
            }""")
        finally:
            b.close()
    seen = set()
    for o in raw:
        if o["logNo"] in seen:
            continue
        seen.add(o["logNo"])
        title = re.sub(r"^제목\s*[:：]\s*", "", o["title"]).strip()
        posts.append({
            "logNo": o["logNo"],
            "title": title,
            "url": f"https://blog.naver.com/{blog_id}/{o['logNo']}",
        })
        if len(posts) >= limit:
            break
    return posts


def pick_related(keywords: list[str], current_title: str, posts: list[dict], n: int = 3) -> list[dict]:
    """키워드(해시태그 등) 겹침으로 유사 글 상위 n개 선정."""
    cur = _norm(current_title)
    # 너무 일반적인 키워드는 매칭력이 약하므로 그대로 두되 길이 가중
    scored = []
    for post in posts:
        if _norm(post["title"]) == cur:
            continue
        t = _norm(post["title"])
        score = 0
        hits = []
        for kw in keywords:
            k = _norm(kw)
            if len(k) >= 2 and k in t:
                score += len(k)  # 긴(구체적) 키워드에 가중
                hits.append(kw)
        if score > 0:
            scored.append((score, post, hits))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"title": p["title"], "url": p["url"], "hits": h} for _, p, h in scored[:n]]
