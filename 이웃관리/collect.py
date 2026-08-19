#!/usr/bin/env python3
"""
블로그 이웃관리 1단계 — 대상 수집기 (읽기 전용).

댓글도 안 달고 서이추도 안 한다. **후보 목록만 만든다.**
이 단계는 네이버에 아무것도 쓰지 않으므로 계정 위험이 0이다.

두 가지 출처:
  ① 검색 상위      — 내 주제 키워드로 상위에 뜨는 블로그 (로그인 불필요)
  ② 내 블로그 방문자 — 내 최근 글에 댓글 단 사람 (로그인 필요, 화면에서 읽음)

사용법:
  python3 collect.py --keywords "부천 맛집,신중동 맛집"   # 내 블로그ID는 내정보.txt에서 읽습니다
  python3 collect.py --visitors --posts 10
  python3 collect.py --keywords "AI 자동화" --visitors

결과:
  work/후보_<blog>_<날짜>.csv   — 사람이 눈으로 보고 고르는 목록
  work/ledger.json              — 지금까지 손댄 블로그 전체 기록(중복 방지, 계정 공용)

⚠️ ledger는 절대 지우지 말 것. 같은 블로그에 두 번 댓글 달거나 서이추를 두 번 신청하면
   그게 바로 봇 티다. 이 파일이 그걸 막는 유일한 장치다.
"""

import argparse

# ── 수강생 배포판: 내 블로그 정보는 내정보.txt 에서 읽는다 ──
# 🔴예전엔 에디님 블로그ID가 코드에 박혀 있었다. 그대로 두면 수강생이 실행할 때
#    남의 블로그로 간다(2026-08-19 배포 직전에 발견).
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "블로그자동"))
import myinfo  # noqa: E402

import csv
import html
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
LEDGER = os.path.join(WORK_DIR, "ledger.json")

# 세션은 체험단 도구가 이미 관리하고 있는 걸 그대로 쓴다(따로 로그인하지 않는다).
# ── 로그인 세션 위치 (수강생 배포판) ──
# 블로그자동에서 네이버 로그인을 하면 그 폴더의 session/ 에 저장된다. 그걸 그대로 쓴다.
_BASE = os.path.dirname(os.path.abspath(__file__))
_CANDS = [
    os.path.join(os.path.dirname(_BASE), "블로그자동", "session"),   # 같은 패키지의 블로그자동
    os.path.join(_BASE, "session"),                                   # 이웃관리 자체
    os.path.expanduser("~/블로그 체험단/session"),                     # 체험단 패키지(있으면)
]
SESSION_DIR = next((p for p in _CANDS if os.path.isdir(p)), _CANDS[0])

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# 내 계정들 — 후보에서 항상 제외한다.
# 🔴수강생 배포판: 내 블로그는 내정보.txt 에서. 내 글에 내가 댓글 다는 걸 막는 용도다.
def MY_BLOGS():
    return {myinfo.blog_id()}

# 결이 아예 다른 글은 걸러낸다. 이웃 수를 빨리 늘리는 것보다 **답방 오는 이웃**이 중요하다.
# (검색 키워드를 넓히면 키즈카페·학원·분양 글이 섞여 들어온다 — 실측)
EXCLUDE_DEFAULT = [
    "키즈", "아이와", "유아", "돌잔치", "산후", "육아",
    "학원", "입시", "과외",
    "분양", "청약", "대출", "보험", "재테크", "코인", "주식",
    "성인", "출장", "제휴문의",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def session_file(blog_id):
    name = f"naver_state_{blog_id}.json"
    return os.path.join(SESSION_DIR, name)


# ───────────────────────── ledger (중복 방지) ─────────────────────────

def load_ledger():
    if not os.path.exists(LEDGER):
        return {}
    try:
        with open(LEDGER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_ledger(led):
    os.makedirs(WORK_DIR, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)  # 중간에 죽어도 원본이 안 깨지게


# ───────────────────────── ① 검색 상위 블로그 ─────────────────────────

def fetch(url, referer=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if referer:
        req.add_header("Referer", referer)
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", "ignore")


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", s).strip()


def search_top_blogs(keyword, limit=15, exclude=None, require=""):
    """블로그 탭 검색 결과를 순위 순서대로. (체험단 도구에서 검증된 방식)

    require: 제목·미리보기에 반드시 있어야 하는 말(보통 지역명).
      ⚠️동명 지역 함정 — "중동 카페"로 검색하면 부천 중동뿐 아니라 **창원 중동**이 섞여 온다(실측).
        지역 키워드를 쓸 땐 이 필터를 켜야 엉뚱한 동네 블로그가 안 들어온다.
    """
    ex = exclude if exclude is not None else EXCLUDE_DEFAULT
    q = urllib.parse.quote(keyword)
    url = f"https://m.search.naver.com/search.naver?ssc=tab.m_blog.all&query={q}"
    try:
        html = fetch(url)
    except Exception as e:
        log(f"  !! 검색 실패({keyword}): {e}")
        return []

    pat = re.compile(
        r'<a[^>]+href="(https://m\.blog\.naver\.com/([A-Za-z0-9_-]+)/(\d{9,}))"[^>]*>(.*?)</a>',
        re.S,
    )
    seen_url, order = {}, []
    for m in pat.finditer(html):
        u, blog_id, _log_no, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        text = strip_tags(inner)
        if len(text) < 6:
            continue
        if u not in seen_url:
            seen_url[u] = {"url": u, "blogId": blog_id, "title": text, "snippet": ""}
            order.append(u)
        elif not seen_url[u]["snippet"]:
            seen_url[u]["snippet"] = text

    out, seen_blog, dropped = [], set(), 0
    for u in order:
        h = seen_url[u]
        if h["blogId"] in MY_BLOGS() or h["blogId"] in seen_blog:
            continue
        hay = f"{h['title']} {h['snippet']}"
        if any(w in hay for w in ex):
            dropped += 1
            continue
        if require and require not in hay:
            dropped += 1
            continue
        seen_blog.add(h["blogId"])
        h["rank"] = len(out) + 1
        out.append(h)
        if len(out) >= limit:
            break
    if dropped:
        log(f"    (결 안 맞아 제외 {dropped}곳)")
    return out


# ───────────────────────── ② 내 글에 댓글 단 사람 ─────────────────────────
# 댓글 API(apis.naver.com/commentBox)는 "서비스 정책에 의해 사용이 제한" 으로 막혀 있다.
# → 로그인 세션으로 글을 열어 화면에 그려진 댓글을 읽는다.

def fetch_my_recent_posts(blog_id, count=10):
    """내 최근 글 목록 (공개 API, 로그인 불필요).

    ⚠️두 가지 함정:
      ① countPerPage를 크게 줘도 **페이지당 5편만** 준다 → 페이지를 넘겨 모은다.
      ② 응답이 JSON처럼 생겼지만 제목 이스케이프가 깨져 있어 json.loads가 터진다 → 정규식으로 뽑는다.
    """
    pat = re.compile(r'"logNo"\s*:\s*"(\d+)"\s*,\s*"title"\s*:\s*"(.*?)"\s*,\s*"categoryNo"', re.S)
    posts, seen = [], set()
    for page in range(1, 12):  # 최대 12페이지(≈60편)까지만
        url = (
            "https://blog.naver.com/PostTitleListAsync.naver"
            f"?blogId={blog_id}&viewdate=&currentPage={page}&categoryNo=0&parentCategoryNo=&countPerPage=30"
        )
        try:
            body = fetch(url)
        except Exception as e:
            log(f"  !! 글 목록 실패(p{page}): {e}")
            break
        found = pat.findall(body)
        if not found:
            break
        for log_no, raw_title in found:
            if log_no in seen:
                continue
            seen.add(log_no)
            title = html.unescape(urllib.parse.unquote(raw_title).replace("+", " "))
            posts.append({"logNo": log_no, "title": title, "date": ""})
            if len(posts) >= count:
                return posts
        time.sleep(random.uniform(0.3, 0.7))
    return posts


def collect_commenters(blog_id, posts, headless=True):
    """Playwright로 내 글을 열어 댓글 작성자를 읽는다. 읽기만 한다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("  !! playwright 미설치 — pip3 install playwright")
        return []

    sess = session_file(blog_id)
    if not os.path.exists(sess):
        log(f"  !! 세션 없음: {sess}")
        return []

    found = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(storage_state=sess, user_agent=UA)
        page = ctx.new_page()
        for i, post in enumerate(posts, 1):
            # ★CommentList.naver 로 열면 댓글 시트(CommentBottomSheet)가 펼쳐진 채로 뜬다.
            #   그냥 글 주소로 열면 댓글이 접혀 있어 아무것도 안 잡힌다.
            url = f"https://m.blog.naver.com/CommentList.naver?blogId={blog_id}&logNo={post['logNo']}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if "nidlogin" in page.url:
                    log("  !! 세션 만료 — 체험단 도구에서 --login 후 다시")
                    break
                page.wait_for_timeout(2200)
                # 댓글 작성자는 trackingCode=blog_comment 링크로만 나온다(가장 확실한 신호).
                rows = page.evaluate(
                    """() => {
                        const out = [];
                        document.querySelectorAll('a[href*="trackingCode=blog_comment"]').forEach(a => {
                            const m = (a.getAttribute('href')||'').match(/blogId=([A-Za-z0-9_-]+)/);
                            if (!m) return;
                            const box = a.closest('li, [class*=comment], [class*=Comment]');
                            const txt = box ? (box.innerText||'').replace(/\\s+/g,' ').trim().slice(0, 90) : '';
                            out.push({ blogId: m[1], name: (a.innerText||'').trim(), text: txt });
                        });
                        return out;
                    }"""
                )
                for r in rows:
                    bid = r.get("blogId", "")
                    if not bid or bid in MY_BLOGS() or bid in found:
                        continue
                    found[bid] = {
                        "blogId": bid,
                        "url": f"https://m.blog.naver.com/{bid}",
                        "title": r.get("name") or bid,
                        "snippet": r.get("text", ""),
                        "rank": 0,
                        "onPost": post["title"][:40],
                    }
                log(f"  ({i}/{len(posts)}) {post['title'][:28]} → 누적 {len(found)}명")
            except Exception as e:
                log(f"  ({i}/{len(posts)}) 실패: {str(e)[:60]}")
            # 사람처럼 — 연속 요청을 붙이지 않는다
            page.wait_for_timeout(random.randint(700, 1600))
        browser.close()
    return list(found.values())


# ───────────────────────── 메인 ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="이웃관리 1단계 — 후보 수집(읽기 전용)")
    ap.add_argument("--blog", default="", help="내 블로그 id (비우면 내정보.txt에서 읽습니다)")
    ap.add_argument("--keywords", default="", help="검색 키워드, 쉼표로 구분")
    ap.add_argument("--areas", default="", help="지역 목록 (--kinds와 곱해 키워드를 만든다)")
    ap.add_argument("--kinds", default="", help="업종 목록 (--areas와 곱해 키워드를 만든다)")
    ap.add_argument("--visitors", action="store_true", help="내 글에 댓글 단 사람도 수집")
    ap.add_argument("--posts", type=int, default=8, help="방문자 수집 시 훑을 내 최근 글 수")
    ap.add_argument("--limit", type=int, default=15, help="키워드당 최대 후보 수")
    ap.add_argument("--exclude", default="", help="추가로 걸러낼 단어, 쉼표로 구분")
    ap.add_argument(
        "--require-any",
        default="",
        help="이 단어들 중 하나는 반드시 있어야 함(쉼표). "
        "★주제 블로그(에디=AI)에 필수 — 방문자 출처는 주제를 안 가려서 결이 다른 사람이 섞인다.",
    )
    ap.add_argument("--show", action="store_true", help="브라우저를 눈에 보이게(디버그)")
    args = ap.parse_args()
    args.blog = args.blog or myinfo.blog_id()   # 비었으면 내정보.txt

    # 1000명 서이추를 하려면 후보가 2,000~3,000곳 필요한데
    # 키워드 하나로는 30곳이 한계다 → 지역 × 업종으로 키워드를 불려서 푼다.
    combo = []
    if args.areas and args.kinds:
        areas = [a.strip() for a in args.areas.split(",") if a.strip()]
        kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
        # 지역명을 require로 달아 보낸다 — 동명 지역(부천 중동 vs 창원 중동)을 막는다.
        combo = [(f"{a} {k}", a) for a in areas for k in kinds]
        log(f"키워드 조합 {len(areas)}지역 × {len(kinds)}업종 = {len(combo)}개")

    if not args.keywords and not combo and not args.visitors:
        ap.error("--keywords / (--areas + --kinds) / --visitors 중 하나는 필요합니다.")

    os.makedirs(WORK_DIR, exist_ok=True)
    ledger = load_ledger()
    cands = {}

    # (키워드, 반드시 포함해야 할 말) 쌍. 직접 준 키워드는 require 없음.
    kws = [(k.strip(), "") for k in args.keywords.split(",") if k.strip()] + combo
    if kws:
        log(f"① 검색 상위 수집 — 키워드 {len(kws)}개")
        extra = [w.strip() for w in args.exclude.split(",") if w.strip()]
        for kw, need in kws:
            hits = search_top_blogs(kw, args.limit, EXCLUDE_DEFAULT + extra, require=need)
            log(f"  '{kw}' → {len(hits)}곳")
            for h in hits:
                c = cands.setdefault(h["blogId"], {**h, "source": "검색", "why": kw})
                if c["source"] == "검색" and c["why"] != kw:
                    c["why"] += f", {kw}"  # 여러 키워드에 걸리면 그만큼 주제가 겹친다
            time.sleep(random.uniform(0.8, 1.6))

    if args.visitors:
        log(f"② 내 글에 댓글 단 사람 수집 — 최근 {args.posts}편")
        posts = fetch_my_recent_posts(args.blog, args.posts)
        if posts:
            for v in collect_commenters(args.blog, posts, headless=not args.show):
                if v["blogId"] in cands:
                    cands[v["blogId"]]["source"] += "+방문"
                else:
                    cands[v["blogId"]] = {**v, "source": "방문", "why": v.get("onPost", "")}

    # ★주제 필터 — 결이 다른 사람은 이웃이 안 남는다.
    #   특히 방문자 출처는 주제를 안 가린다: 에디 블로그는 정체성이 AI인데
    #   최근 글이 연예 글(홈판 조회수용)이라, 댓글 다는 사람은 연예 관심층이지 AI 하는 사람이 아니다.
    #   실측으로 혜화 크로플 카페·안경 후기 블로거가 후보 상위에 올라왔다.
    need_any = [w.strip() for w in args.require_any.split(",") if w.strip()]
    if need_any:
        before = len(cands)
        cands = {
            b: c
            for b, c in cands.items()
            if any(w in f"{c.get('title','')} {c.get('snippet','')} {c.get('why','')}" for w in need_any)
        }
        log(f"주제 필터 '{','.join(need_any[:4])}…' → {before}곳 중 {len(cands)}곳만 남김")

    # ledger 대조 — 이미 손댄 곳은 표시해서 두 번 안 가게
    rows = []
    fresh = 0
    for bid, c in cands.items():
        past = ledger.get(bid, {})
        already = []
        if past.get("commented"):
            already.append(f"댓글 {past['commented']}회")
        if past.get("buddy_requested"):
            already.append("서이추 신청함")
        if not already:
            fresh += 1
        rows.append(
            {
                "blogId": bid,
                "출처": c.get("source", ""),
                "근거": c.get("why", ""),
                "순위": c.get("rank", 0),
                "최근글/이름": c.get("title", "")[:60],
                "미리보기": c.get("snippet", "")[:70],
                "URL": c.get("url", ""),
                "이력": " / ".join(already) or "처음",
            }
        )

    # 정렬: 처음 보는 곳 먼저 → **내 글에 댓글 단 사람 먼저**(답방이라 가장 자연스럽고 성공률 높다) → 검색 순위
    rows.sort(key=lambda r: (r["이력"] != "처음", "방문" not in r["출처"], r["순위"] or 999))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = os.path.join(WORK_DIR, f"후보_{args.blog}_{stamp}.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["blogId"])
        w.writeheader()
        w.writerows(rows)

    # 후보로 '봤다'는 사실만 기록. 댓글·서이추는 아직 아무것도 안 했다.
    for bid in cands:
        e = ledger.setdefault(bid, {})
        e["last_seen"] = stamp
        e.setdefault("first_seen", stamp)
    save_ledger(ledger)

    log(f"완료 — 후보 {len(rows)}곳 (처음 보는 곳 {fresh}곳)")
    log(f"  → {out}")
    if rows:
        print("\n상위 10곳:")
        for r in rows[:10]:
            print(f"  {r['출처']:<6} {r['blogId']:<18} {r['최근글/이름'][:38]:<40} [{r['이력']}]")
    print("\n※ 이 단계는 읽기만 했습니다. 댓글·서이추는 아직 하나도 안 나갔습니다.")


if __name__ == "__main__":
    sys.exit(main())
