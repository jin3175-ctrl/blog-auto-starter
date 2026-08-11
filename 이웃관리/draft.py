#!/usr/bin/env python3
"""
블로그 이웃관리 2단계 — 댓글·서이추 메시지 초안 생성 (아직 아무것도 올리지 않는다).

1단계(collect.py)가 만든 후보 CSV를 받아,
각 후보의 **글 본문을 실제로 읽고** 그 내용에 대한 댓글 초안을 만든다.

"잘 보고 갑니다 ^^" 같은 건 네이버도 잡고 사람도 안다.
글을 읽고 쓴 댓글이라야 답방이 오고, 그게 이 도구의 유일한 존재 이유다.

사용법:
  python3 draft.py                          # 가장 최근 후보 CSV, 상위 10곳
  python3 draft.py --csv work/후보_xxx.csv --limit 15
  python3 draft.py --blog ioiykd8599        # 내 소개 톤을 에디 블로그로

결과:
  work/초안_<날짜>.csv   — blogId · 글제목 · URL · 댓글초안 · 서이추메시지 · 본문요약

⚠️ 이 단계도 네이버에 쓰지 않는다. 올리는 건 3단계(사람이 최종 확인).
"""

import argparse
import csv
import glob
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# 내가 누구인지 — 서이추 메시지에 "왜 이웃하고 싶은지"를 구체적으로 쓰려면 필요하다.
ME = {
    "hsh-2022": {
        # ⚠️내 사는 지역을 밝히지 않는다(에디님 지시).
        #   후보가 대구·제주·광명 등 전국에 흩어져 있어서 "저희도 부천에서…"는 상대와 상관없는 말이 되고,
        #   내 위치를 굳이 알릴 이유도 없다.
        "name": "가봄사봄",
        "who": "부부가 함께 다녀온 맛집과 체험단 후기를 쓰는 블로그",
        "topic": "맛집·카페·체험단 후기",
    },
    "ioiykd8599": {
        "name": "AI 에디",
        "who": "AI와 자동화를 실제로 써보고 기록하는 블로그",
        "topic": "AI 도구·업무 자동화·클로드 코드",
    },
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ───────────────────────── 글 본문 읽기 ─────────────────────────
# AI글쓰기웹의 fetchPostBody와 같은 방식. 세션 불필요.

def fetch_post_body(url, max_chars=1500):
    if not url:
        return ""
    mobile = url.replace("//blog.naver.com/", "//m.blog.naver.com/")
    try:
        req = urllib.request.Request(mobile, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return ""
    # ⚠️본문 컨테이너의 '여는 태그 >' 다음부터 자른다. 안 그러면 클래스명이 본문에 섞인다.
    i = html.find("se-main-container")
    start = html.find(">", i) + 1 if i > 0 else 0
    seg = html[start : start + 200_000] if start > 0 else html
    seg = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", seg, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", seg)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(a, b)
    text = text.replace("​", "")
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def is_post_url(url):
    """블로그 홈이 아니라 '글' 주소인가(끝이 logNo인가)."""
    return bool(re.search(r"blog\.naver\.com/[A-Za-z0-9_-]+/\d{9,}", url or ""))


def latest_post_url(blog_id):
    """방문자 후보는 글 주소가 없다(블로그 주소만). 최근 글 하나를 찾아온다."""
    url = (
        "https://blog.naver.com/PostTitleListAsync.naver"
        f"?blogId={blog_id}&viewdate=&currentPage=1&categoryNo=0&parentCategoryNo=&countPerPage=5"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read().decode("utf-8", "ignore")
    except Exception:
        return "", ""
    m = re.search(r'"logNo"\s*:\s*"(\d+)"\s*,\s*"title"\s*:\s*"(.*?)"\s*,\s*"categoryNo"', body, re.S)
    if not m:
        return "", ""
    import html as _h
    import urllib.parse as _up

    title = _h.unescape(_up.unquote(m.group(2)).replace("+", " "))
    return f"https://m.blog.naver.com/{blog_id}/{m.group(1)}", title


# ───────────────────────── 초안 생성 ─────────────────────────

PROMPT = """당신은 네이버 블로그 이웃과 교류하는 사람입니다. 아래 '상대방 글'을 읽고 댓글 한 개와 서로이웃 신청 메시지 한 개를 씁니다.

[내가 누구인지]
블로그명: {me_name}
소개: {me_who}
주로 쓰는 주제: {me_topic}

[상대방 글]
블로그: {blog_id}
제목: {title}
본문: {body}

[댓글 규칙 — 이게 전부입니다]
- **글에서 실제로 언급된 구체적인 것 하나를 집어서** 말하세요. 그게 글을 읽었다는 유일한 증거입니다.
  (예: 특정 메뉴 이름, 가격, 웨이팅 시간, 주차 얘기, 글쓴이가 아쉬워한 부분)
- 2~3문장. 짧아야 합니다. 길면 오히려 부담스럽습니다.
- 끝에 **가벼운 질문 하나**를 붙이세요. 답글이 오면 그게 교류의 시작입니다.
- 존댓말. 이모티콘은 쓰더라도 하나까지만.

[절대 금지]
- "잘 보고 갑니다", "좋은 정보 감사합니다", "유익한 글이네요" 같은 아무 글에나 붙는 말
- 내 블로그 홍보·주소·방문 요청 (스팸으로 신고됩니다)
- 글에 없는 내용을 아는 척하기
- 과장된 칭찬, 느낌표 남발

[서로이웃 신청 메시지 규칙]
- 1~2문장. **왜 이웃하고 싶은지 구체적으로** — 쓰는 글의 결이 비슷해서, 이 글이 좋아서 같은 이유를 대세요.
- "서이추 신청합니다", "소통해요" 같은 상투적인 말만 쓰지 마세요.

[★내 지역을 밝히지 마세요 — 댓글·서이추 메시지 둘 다]
- "저희도 ○○에서", "저는 ○○ 사는데" 처럼 **내가 어디 사는지 쓰지 마세요.**
- 상대는 전국 어디에 있을지 모릅니다. 내 지역을 대는 건 상대와 상관없는 말입니다.
- 공통점을 댈 거면 지역 말고 **쓰는 글의 결**로 대세요("저희도 부부가 같이 다녀와서 쓰거든요").

[출력 형식 — 이 두 줄만, 다른 말 없이]
댓글: (여기에 댓글)
서이추: (여기에 신청 메시지)"""


def make_draft(me, blog_id, title, body):
    prompt = PROMPT.format(
        me_name=me["name"],
        me_who=me["who"],
        me_topic=me["topic"],
        blog_id=blog_id,
        title=title or "(제목 없음)",
        body=body[:1400],
    )
    # claude CLI가 간헐적으로 120초를 넘긴다(실측 12건 중 1건) → 한 번 더 시도한다.
    txt = ""
    last = ""
    for attempt in (1, 2):
        try:
            out = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            txt = (out.stdout or "").strip()
            if txt:
                break
            last = "빈 응답"
        except Exception as e:
            last = type(e).__name__
        if attempt == 1:
            time.sleep(3)
    if not txt:
        return "", "", f"생성 실패({last})"

    comment = buddy = ""
    for line in txt.splitlines():
        line = line.strip().lstrip("*-# ").strip()
        if line.startswith("댓글:"):
            comment = line.split("댓글:", 1)[1].strip()
        elif line.startswith("서이추:"):
            buddy = line.split("서이추:", 1)[1].strip()
    if not comment:
        # 형식을 안 지켰으면 첫 문단이라도 건진다
        comment = txt.split("\n")[0][:200]
    return comment, buddy, ""


# ───────────────────────── 검수 ─────────────────────────

BANNED = ["잘 보고 갑니다", "좋은 정보", "유익한", "감사합니다 ^^", "소통해요", "서이추 신청합니다"]


def check(comment, buddy=""):
    """사람이 보기 전에 기계가 먼저 걸러낸다."""
    bad = []
    if not comment:
        return ["빈 초안"]
    # 내 지역 노출 — "저희도 부천에서…"는 대구·제주 블로거한테는 상관없는 말이다.
    if re.search(r"(저희?도?|제가)\s*\S{0,4}(부천|경기|인천|신중동|상동)", f"{comment} {buddy}"):
        bad.append("내 지역 노출")
    if len(comment) < 25:
        bad.append("너무 짧음")
    if len(comment) > 250:
        bad.append("너무 김")
    for w in BANNED:
        if w in comment:
            bad.append(f"상투어 '{w}'")
    if re.search(r"blog\.naver\.com|제 블로그|놀러", comment):
        bad.append("내 블로그 홍보 의심")
    # 글을 못 읽었을 때 나오는 신호 — 이런 댓글은 달 글이 애초에 없다는 뜻이다
    if re.search(r"첫 글|아직 글이|글이 없", comment):
        bad.append("글 없는 블로그 의심")
    if comment.count("!") > 2:
        bad.append("느낌표 과다")
    return bad


# ───────────────────────── 메인 ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="이웃관리 2단계 — 댓글·서이추 초안(올리지 않음)")
    ap.add_argument("--csv", default="", help="후보 CSV 경로 (없으면 가장 최근 것)")
    ap.add_argument("--blog", default="hsh-2022", help="내 블로그 id — 소개 톤이 달라진다")
    ap.add_argument("--limit", type=int, default=10, help="몇 곳까지 초안을 만들지")
    args = ap.parse_args()

    me = ME.get(args.blog)
    if not me:
        ap.error(f"모르는 블로그 id: {args.blog} (hsh-2022 | ioiykd8599)")

    path = args.csv
    if not path:
        found = sorted(glob.glob(os.path.join(WORK_DIR, "후보_*.csv")), key=os.path.getmtime)
        if not found:
            ap.error("후보 CSV가 없습니다. 먼저 collect.py를 돌리세요.")
        path = found[-1]
    log(f"후보 파일: {os.path.basename(path)}")

    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("이력") == "처음"]
    rows = rows[: args.limit]
    log(f"초안 만들 곳: {len(rows)}곳 (처음 보는 곳만)")

    out_rows = []
    for i, r in enumerate(rows, 1):
        bid = r["blogId"]
        url = r.get("URL", "")
        title = r.get("최근글/이름", "")
        # 방문자 후보는 블로그 주소만 있으니 최근 글을 찾아온다
        if not is_post_url(url):
            url2, title2 = latest_post_url(bid)
            if url2:
                url, title = url2, title2

        def skip(reason):
            log(f"  ({i}/{len(rows)}) {bid} — 건너뜀: {reason}")
            out_rows.append(
                {
                    "blogId": bid, "출처": r.get("출처", ""), "글제목": title[:60], "URL": url,
                    "댓글초안": "", "서이추메시지": "", "검수": reason, "본문앞부분": "",
                }
            )

        # 🔴글이 하나도 없는 블로그가 섞여 있다(방문자 중에 흔하다).
        #   이걸 안 막으면 블로그 홈페이지를 본문으로 읽고 "아직 첫 글 전이시네요" 같은 초안이 나온다.
        #   댓글 달 글 자체가 없으므로 초안을 만들 필요도 없다.
        if not is_post_url(url):
            skip("글 없는 블로그")
            continue

        body = fetch_post_body(url)
        if len(body) < 150 or "로그인이 필요합니다" in body[:200]:
            skip("본문 못 읽음(비공개·삭제 가능)")
            continue

        comment, buddy, err = make_draft(me, bid, title, body)
        flags = [err] if err else check(comment, buddy)
        log(f"  ({i}/{len(rows)}) {bid} — {'⚠ ' + ', '.join(flags) if flags else '✅'} {comment[:40]}")
        out_rows.append(
            {
                "blogId": bid, "출처": r.get("출처", ""), "글제목": title[:60], "URL": url,
                "댓글초안": comment, "서이추메시지": buddy,
                "검수": ", ".join(flags) or "통과", "본문앞부분": body[:120],
            }
        )
        time.sleep(random.uniform(0.5, 1.2))

    stamp = time.strftime("%Y%m%d_%H%M")
    out = os.path.join(WORK_DIR, f"초안_{args.blog}_{stamp}.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    ok = sum(1 for r in out_rows if r["검수"] == "통과")
    log(f"완료 — {len(out_rows)}건 중 검수 통과 {ok}건")
    log(f"  → {out}")
    print("\n※ 아직 네이버에 아무것도 올리지 않았습니다. 초안을 읽어보고 고칠 곳을 알려주세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
