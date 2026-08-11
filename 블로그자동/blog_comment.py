#!/usr/bin/env python3
"""이웃 블로그 댓글 활동 — 대상 수집 + 글을 읽고 쓴 댓글 초안 (2026-08-11 신설).

에디님 요청: 노마케터스 강의(3)의 '댓글 자동화'를 에디 블로그에도.
실측 배경 — 최근 15편에 달린 댓글이 3개뿐이라 '내 글 댓글에 답글'은 실효가 없다.
효과가 있는 건 **같은 주제 블로그에 먼저 댓글을 남겨 답방 유입을 만드는 쪽**이다.

★★안전 원칙 (이게 이 파일의 존재 이유다)
남의 블로그에 자동으로 댓글을 쓰는 건 네이버가 **매크로로 잡는다**. 댓글 작성 제한,
심하면 아이디 이용정지다. 이 계정은 애드포스트 수익 계정이라 정지되면 전부 날아간다.
그래서 이 모듈은 **게시를 하지 않는다.** 대상을 모으고 댓글 초안까지만 만들어
`work/comment_plan_YYYYMMDD.md`로 남긴다. 붙여넣고 올리는 건 에디님이 직접 한다.

댓글 품질 원칙(제재를 부르는 건 '내용 없는 반복 댓글'이다):
- 글을 **실제로 읽고** 그 글에만 있는 사실 하나를 언급한다(템플릿 금지).
- 1~2문장, 광고·링크·내 블로그 홍보 금지. 이모지는 없거나 하나.
- 같은 블로그는 3일 안에 다시 대상으로 삼지 않는다(`work/comment_log.json`).

사용:
  python3 blog_comment.py                  # 오늘 소재 키워드로 12건 초안
  python3 blog_comment.py 이혼숙려캠프 나는솔로   # 키워드 지정
  python3 blog_comment.py --n 20           # 건수 지정
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from claude_cli import run_claude_p
import config

import myinfo  # 수강생 배포판: 내정보.txt에서 읽는다
BLOG_ID = myinfo.blog_id()
LOG_FILE = os.path.join(config.WORK_DIR, "comment_log.json")
_UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
REVISIT_DAYS = 3          # 같은 블로그 재방문 최소 간격
#: 광고·업체 블로그로 보이면 건너뛴다(댓글 달아도 답방이 없다)
_SKIP = re.compile(r"협찬|체험단|제공받|광고|공식\s*블로그|상담문의|카톡문의|DM문의")

DRAFT_PROMPT = """아래는 다른 사람이 쓴 네이버 블로그 글이다. 이 글에 남길 **댓글 한 개**를 써라.

[글 제목] {title}
[글 앞부분] {body}

[규칙 — 이걸 어기면 스팸 댓글이 된다]
- **이 글에만 있는 구체적인 내용 하나를 언급**한다(제목만 보고 쓴 티가 나면 안 된다).
- 1~2문장, 60자 안팎. 존댓말. 담백하게.
- 칭찬 일변도·영혼 없는 감탄("좋은 정보 감사합니다", "잘 보고 갑니다") 금지.
- 내 블로그 홍보·링크·서로이웃 요청 금지. 이모지는 넣지 않거나 딱 하나.
- 글쓴이가 쓴 표현을 그대로 되풀이하지 말고, 읽은 사람의 반응으로 쓴다.

[출력] 댓글 문장만. 설명·따옴표 없이 한 줄.
"""


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA_M})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


def _load_log() -> dict:
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save_log(d: dict) -> None:
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def find_targets(keywords: list[str], want: int = 12, log=print) -> list[dict]:
    """키워드별 블로그 검색(최신순)에서 댓글 달 글을 모은다. 로그인 불필요."""
    hist = _load_log()
    cutoff = time.time() - REVISIT_DAYS * 86400
    recent_blogs = {b for b, ts in hist.items() if ts >= cutoff}
    out, seen = [], set()
    for kw in keywords:
        if len(out) >= want:
            break
        try:
            h = _get("https://m.search.naver.com/search.naver?ssc=tab.m_blog.all"
                     f"&query={urllib.parse.quote(kw)}&sort=date")
        except Exception as e:  # noqa: BLE001
            log(f"  '{kw}' 검색 실패: {str(e)[:40]}")
            continue
        found = 0
        for bid, lg in re.findall(r"blog\.naver\.com/([A-Za-z0-9_-]+)/(\d{9,})", h):
            if len(out) >= want:
                break
            if bid == BLOG_ID or bid in recent_blogs or (bid, lg) in seen:
                continue
            seen.add((bid, lg))
            recent_blogs.add(bid)          # 같은 실행 안에서도 블로그 중복 금지
            out.append({"blog": bid, "logNo": lg, "keyword": kw,
                        "url": f"https://m.blog.naver.com/{bid}/{lg}"})
            found += 1
        log(f"  '{kw}' {found}건")
        time.sleep(0.4)
    return out


def read_post(t: dict) -> dict:
    """대상 글의 제목·본문 앞부분을 읽는다(댓글을 '읽고' 쓰기 위해 필수)."""
    try:
        h = _get(t["url"])
    except Exception as e:  # noqa: BLE001
        t["skip"] = f"본문 읽기 실패({str(e)[:30]})"
        return t
    m = re.search(r'<meta property="og:title" content="([^"]+)"', h)
    t["title"] = html.unescape(m.group(1)) if m else ""
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)))
    i = txt.find("본문 기타 기능")
    body = txt[i + 8:] if i > 0 else txt
    t["body"] = body[:900].strip()
    if _SKIP.search(t["title"] + t["body"][:300]):
        t["skip"] = "협찬·광고성 글로 보임"
    elif len(t["body"]) < 200:
        t["skip"] = "본문이 너무 짧아 읽고 쓸 내용이 없음"
    return t


def draft(t: dict, log=print) -> dict:
    if t.get("skip"):
        return t
    try:
        c = run_claude_p(DRAFT_PROMPT.format(title=t.get("title", ""),
                                             body=t.get("body", "")[:800]), timeout=120)
        c = (c or "").strip().splitlines()
        c = next((l.strip().strip('"').strip("'") for l in c if len(l.strip()) >= 8), "")
        if 8 <= len(c) <= 140:
            t["comment"] = c
        else:
            t["skip"] = "댓글 초안 생성 실패(길이 이상)"
    except Exception as e:  # noqa: BLE001
        t["skip"] = f"댓글 초안 실패({str(e)[:30]})"
    return t


def make_plan(keywords: list[str], want: int = 12, log=print) -> str:
    """대상 수집 → 글 읽기 → 댓글 초안 → work/comment_plan_YYYYMMDD.md 로 저장."""
    log(f"댓글 대상 수집({', '.join(keywords)})")
    targets = find_targets(keywords, want, log)
    log(f"대상 {len(targets)}건 → 글 읽고 초안 작성")
    rows, ok = [], 0
    for i, t in enumerate(targets, 1):
        t = draft(read_post(t), log)
        rows.append(t)
        if t.get("comment"):
            ok += 1
            log(f"  [{i}/{len(targets)}] {t['blog']} — {t['comment'][:34]}")
        else:
            log(f"  [{i}/{len(targets)}] {t['blog']} 건너뜀: {t.get('skip','?')}")
        time.sleep(0.3)

    path = os.path.join(config.WORK_DIR, f"comment_plan_{config.today_str()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 댓글 계획 {config.today_str()} — {ok}건\n\n")
        f.write("> ⚠️ **자동 게시하지 않습니다.** 아래 초안을 보고 직접 다듬어 올리세요.\n"
                "> 한 번에 몰아서 달지 말고 **건당 1~3분 간격**, 하루 20건 이내를 권합니다.\n"
                "> 네이버는 짧은 시간에 반복되는 댓글을 매크로로 판정합니다(댓글 제한·계정 정지).\n\n")
        for t in rows:
            if not t.get("comment"):
                continue
            f.write(f"### {t.get('title','(제목 없음)')[:70]}\n")
            f.write(f"- 키워드: {t['keyword']}  ·  블로그: `{t['blog']}`\n")
            f.write(f"- {t['url']}\n")
            f.write(f"- **댓글**: {t['comment']}\n\n")
        skipped = [t for t in rows if not t.get("comment")]
        if skipped:
            f.write("---\n\n## 건너뛴 글\n")
            for t in skipped:
                f.write(f"- `{t['blog']}` — {t.get('skip','?')}\n")
    # 기록(같은 블로그 3일 내 재방문 금지)
    hist = _load_log()
    for t in rows:
        if t.get("comment"):
            hist[t["blog"]] = time.time()
    _save_log(hist)
    log(f"완료: {ok}건 → {path}")
    return path


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = 12
    if "--n" in sys.argv:
        try:
            n = int(sys.argv[sys.argv.index("--n") + 1])
        except (IndexError, ValueError):
            pass
    kws = args or None
    if not kws:
        # 오늘 우리가 쓴 소재로 잡는다(같은 주제 독자를 만나야 답방이 온다)
        try:
            import gen_celeb_ai
            kws = gen_celeb_ai.PRIORITY_SUBJECTS[:4] + ["AI 부업", "AI 자동화"]
        except Exception:  # noqa: BLE001
            kws = ["나는솔로", "이혼숙려캠프", "AI 부업"]
    make_plan(kws, n)
