#!/usr/bin/env python3
"""
내 글에 달린 댓글에 **답글** 달기 (반자동).

왜 필요한가 — 답글을 안 달면 애써 만든 관계가 거기서 끊긴다.
실측: 내가 댓글 단 8명 중 6명(75%)이 내 블로그로 답방을 왔다. 이게 가장 값진 그룹인데,
`draft.py`/`run.py`는 ledger에 기록이 있으면 제외해서 **이들을 영원히 빠뜨린다.** 그 구멍을 메운다.

★스크립트는 '등록'을 절대 누르지 않는다. 답글창을 열고 초안을 채워놓는 데까지만 한다.

사용법:
  python3 reply.py --blog hsh-2022 --posts 10        # 답글 달 댓글 찾아 초안까지
  python3 reply.py --blog hsh-2022 --dry             # 아무것도 입력 안 하고 점검만

내 블로그에서 하는 일이라 남의 블로그에 다는 것보다 위험이 훨씬 낮다.
그래도 답글 내용은 사람이 보고 누른다.
"""

import argparse
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
LEDGER = os.path.join(WORK_DIR, "ledger.json")
REPLIED = os.path.join(WORK_DIR, "replied.json")  # 같은 댓글에 두 번 답글 다는 것 방지
SESSION_DIR = "/Users/edi/블로그 체험단/session"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

ME = {
    "hsh-2022": {"name": "가봄사봄", "who": "부부가 함께 다녀온 맛집과 체험단 후기를 쓰는 블로그"},
    "ioiykd8599": {"name": "AI 에디", "who": "AI와 자동화를 실제로 써보고 기록하는 블로그"},
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def save_json(p, data):
    os.makedirs(WORK_DIR, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def session_file(blog_id):
    name = "naver_state.json" if blog_id == "hsh-2022" else f"naver_state_{blog_id}.json"
    return os.path.join(SESSION_DIR, name)


def fetch_my_posts(blog_id, count=10):
    """내 최근 글 (페이지당 5편만 주므로 넘겨가며 모은다)."""
    pat = re.compile(r'"logNo"\s*:\s*"(\d+)"\s*,\s*"title"\s*:\s*"(.*?)"\s*,\s*"categoryNo"', re.S)
    posts, seen = [], set()
    for page in range(1, 10):
        url = (
            "https://blog.naver.com/PostTitleListAsync.naver"
            f"?blogId={blog_id}&viewdate=&currentPage={page}&categoryNo=0&parentCategoryNo=&countPerPage=30"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                body = r.read().decode("utf-8", "ignore")
        except Exception:
            break
        found = pat.findall(body)
        if not found:
            break
        for log_no, raw in found:
            if log_no in seen:
                continue
            seen.add(log_no)
            posts.append({"logNo": log_no, "title": html.unescape(urllib.parse.unquote(raw).replace("+", " "))})
            if len(posts) >= count:
                return posts
        time.sleep(random.uniform(0.3, 0.7))
    return posts


PROMPT = """당신은 블로그 주인입니다. 내 글에 달린 아래 댓글에 **답글**을 씁니다.

[내 블로그]
{me_name} — {me_who}

[내 글 제목]
{title}

[달린 댓글]
{who}님: {comment}

[답글 규칙]
- 1~2문장. 짧게. 답글은 길면 부담스럽습니다.
- **댓글 내용에 실제로 반응**하세요. 댓글이 질문이면 답을 하고, 감상이면 거기에 맞장구를 칩니다.
- 고맙다는 말은 한 번만. "감사합니다"를 반복하지 마세요.
- 상대 블로그에 다녀온 사이라면 자연스럽게 아는 척해도 좋습니다(억지로 하지는 말고).
- 존댓말. 이모티콘은 쓰더라도 하나까지만.

[절대 금지]
- "방문 감사합니다 자주 놀러오세요" 같은 아무 댓글에나 붙는 말
- 내 다른 글 홍보, 링크
- 과장된 리액션, 느낌표 남발

[출력]
답글 문장만 그대로 출력하세요. 따옴표·머리말·설명 없이.
"""


def make_reply(me, title, who, comment):
    prompt = PROMPT.format(me_name=me["name"], me_who=me["who"], title=title[:60], who=who, comment=comment[:300])
    for attempt in (1, 2):
        try:
            out = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "text"],
                capture_output=True, text=True, timeout=180,
            )
            txt = (out.stdout or "").strip().strip('"').strip()
            if txt:
                return txt.split("\n")[0][:200], ""
        except Exception as e:
            last = type(e).__name__
        if attempt == 1:
            time.sleep(3)
    return "", "생성 실패"


BANNED = ["방문 감사", "놀러오세요", "자주 오세요", "좋은 하루 되세요"]


def check(txt):
    bad = []
    if not txt:
        return ["빈 초안"]
    if len(txt) < 8:
        bad.append("너무 짧음")
    if len(txt) > 200:
        bad.append("너무 김")
    for w in BANNED:
        if w in txt:
            bad.append(f"상투어 '{w}'")
    if txt.count("!") > 2:
        bad.append("느낌표 과다")
    return bad


def banner(page, text, color="#03c75a"):
    try:
        page.evaluate(
            """(o) => {
                let b = document.getElementById('__edi_guide');
                if (!b) {
                    b = document.createElement('div');
                    b.id = '__edi_guide';
                    b.style.cssText = 'position:fixed;left:10px;bottom:12px;z-index:2147483647;'
                      + 'max-width:62vw;padding:9px 13px;border-radius:18px;'
                      + 'font:700 13px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;'
                      + 'color:#fff;box-shadow:0 3px 12px rgba(0,0,0,.3);pointer-events:none;opacity:.94';
                    document.body.appendChild(b);
                }
                b.style.background = o.c; b.textContent = o.t;
            }""",
            {"t": text, "c": color},
        )
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="내 글 댓글에 답글 달기(반자동)")
    ap.add_argument("--blog", default="hsh-2022")
    ap.add_argument("--posts", type=int, default=10, help="훑을 내 최근 글 수")
    ap.add_argument("--limit", type=int, default=20, help="한 번에 처리할 댓글 수")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    me = ME.get(args.blog)
    if not me:
        ap.error(f"모르는 블로그: {args.blog}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright 미설치")
        return 1
    sess = session_file(args.blog)
    if not os.path.exists(sess):
        log(f"세션 없음: {sess}")
        return 1

    ledger = load_json(LEDGER, {})
    replied = load_json(REPLIED, {})
    posts = fetch_my_posts(args.blog, args.posts)
    log(f"내 최근 글 {len(posts)}편에서 댓글을 찾습니다.")

    today = date.today().isoformat()
    done = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.dry)
        ctx = browser.new_context(storage_state=sess, user_agent=UA, viewport={"width": 430, "height": 930})
        page = ctx.new_page()

        for post in posts:
            if done >= args.limit or page.is_closed():
                break
            url = f"https://m.blog.naver.com/CommentList.naver?blogId={args.blog}&logNo={post['logNo']}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                if "nidlogin" in page.url:
                    log("세션 만료 — 체험단 도구에서 --login 후 다시")
                    break
                page.wait_for_timeout(2200)
            except Exception as e:
                log(f"  글 열기 실패: {str(e)[:60]}")
                continue

            rows = page.evaluate(
                """() => {
                    const out = [];
                    document.querySelectorAll('a[href*="trackingCode=blog_comment"]').forEach((a, i) => {
                        const m = (a.getAttribute('href')||'').match(/blogId=([A-Za-z0-9_-]+)/);
                        const box = a.closest('li, [class*=comment], [class*=Comment]');
                        if (!m || !box) return;
                        // 내가 쓴 답글은 제외(내 글이므로 답글도 이 목록에 섞인다)
                        const txt = (box.innerText||'').replace(/\\s+/g,' ').trim();
                        const nm = (a.innerText||'').trim();
                        out.push({ who: m[1], nick: nm, text: txt.slice(0, 200) });
                    });
                    // 같은 댓글이 두 번 잡히므로 중복 제거
                    const seen = new Set();
                    return out.filter(r => { const k = r.who + '|' + r.text.slice(0,40);
                        if (seen.has(k)) return false; seen.add(k); return true; });
                }"""
            )
            rows = [r for r in rows if r["who"] != args.blog]
            if not rows:
                continue

            for idx, r in enumerate(rows):
                if done >= args.limit or page.is_closed():
                    break
                who = r["who"]
                key = f"{who}|{post['logNo']}"
                if key in replied:
                    continue

                # 댓글 본문만 뽑기(작성자명·날짜·버튼 텍스트 제거)
                ctext = re.sub(r"옵션 열기|신고|답글|공감\s*\d*|삭제|수정|\d{4}\.\s?\d+\.\s?\d+\.?\s?\d*:?\d*", " ", r["text"])
                ctext = re.sub(r"\s+", " ", ctext).strip()
                # ⚠️댓글 덩어리는 '닉네임 + 본문' 순서다. 아이디(vol87)로 부르면 어색하니
                #   맨 앞 닉네임(Remote Shop)을 떼어내 호칭으로 쓰고, 본문에서는 지운다.
                nick = r.get("nick") or ""
                if nick and ctext.startswith(nick):
                    ctext = ctext[len(nick):].strip()
                who_call = nick or who

                back = "답방" if ledger.get(who, {}).get("commented") else ""
                print("\n" + "═" * 68)
                print(f"[{done+1}] {r.get('nick') or who} ({who})  {('← ' + back) if back else ''}")
                print(f"  내 글  : {post['title'][:46]}")
                print(f"  댓글   : {ctext[:110]}")

                reply, err = make_reply(me, post["title"], who_call, ctext)
                flags = [err] if err else check(reply)
                print(f"  답글안 : {reply}")
                print(f"  검수   : {', '.join(flags) or '통과'}")
                if flags:
                    continue
                if args.dry:
                    done += 1
                    continue

                # 🔴🔴대댓글이어야 한다. 맨 아래 '댓글쓰기' 칸에 쓰면 **새 댓글**이 되어
                #   상대는 답이 온 줄도 모르고, 보는 사람도 무슨 말인지 알 수 없다(실측 사고 2건).
                #   ① 그 사람의 댓글에 달린 '답글' 버튼을 눌러야 하고
                #   ② 열린 입력칸이 **`.u_cbox_reply_area` 안**인지 반드시 확인해야 한다.
                #      (일반 댓글칸과 클래스가 `.u_cbox_text`로 똑같아서 이걸 안 보면 구분이 안 된다)
                ok = page.evaluate(
                    """(who) => {
                        const btns = [...document.querySelectorAll('a.u_cbox_btn_reply')];
                        // 그 사람의 댓글 덩어리에 속한 답글 버튼을 찾는다(인덱스는 답글이 늘면 밀린다)
                        const btn = btns.find(b => {
                            const li = b.closest('li, [class*=u_cbox_comment]');
                            if (!li) return false;
                            const a = li.querySelector('a[href*="trackingCode=blog_comment"]');
                            return a && (a.getAttribute('href')||'').includes('blogId=' + who);
                        });
                        if (!btn) return false;
                        btn.scrollIntoView({block:'center'});
                        btn.click();
                        return true;
                    }""",
                    who,
                )
                if not ok:
                    print("  ⚠ 이 사람의 '답글' 버튼을 못 찾았습니다. 건너뜁니다.")
                    continue
                page.wait_for_timeout(1400)
                typed = page.evaluate(
                    """() => {
                        const vis = el => el && el.offsetParent !== null;
                        // ★답글창 = .u_cbox_reply_area 안에 있는 입력칸. 이것만 잡는다.
                        const el = [...document.querySelectorAll('.u_cbox_text, textarea')]
                            .filter(vis)
                            .find(e => e.closest('.u_cbox_reply_area, .u_cbox_reply'));
                        if (!el) return false;
                        el.scrollIntoView({block:'center'}); el.click(); el.focus();
                        return true;
                    }"""
                )
                if not typed:
                    print("  ⚠ 답글창이 안 열렸습니다(일반 댓글칸에는 쓰지 않습니다). 건너뜁니다.")
                    continue
                page.wait_for_timeout(300)
                page.keyboard.type(reply, delay=random.randint(18, 42))
                page.wait_for_timeout(400)

                # 🔴반드시 '실제로 들어갔는지' 확인하고 넘어간다.
                #   답글창이 안 열리면 스크립트가 원래 비어 있는 일반 댓글창을 붙잡는데,
                #   그게 비어 있으니 아래 대기 루프가 곧바로 "등록됨"으로 오판한다
                #   (실측: 사람이 한 번만 눌렀는데 2건이 기록됐다).
                probe = re.sub(r"\s", "", reply)[:12]
                filled = page.evaluate(
                    """(p) => {
                        const vis = el => el && el.offsetParent !== null;
                        const el = [...document.querySelectorAll('.u_cbox_text, textarea')].filter(vis)
                            .find(e => e.closest('.u_cbox_reply_area, .u_cbox_reply'));
                        if (!el) return false;
                        return (el.innerText || el.value || '').replace(/\\s/g, '').includes(p);
                    }""",
                    probe,
                )
                if not filled:
                    print("  ⚠ 답글창에 글이 안 들어갔습니다. 이 건은 건너뜁니다(기록도 안 남김).")
                    continue

                banner(page, f"답글이 채워졌습니다 — [등록]을 누르세요  ({done+1})")
                # 사람이 등록할 때까지 기다린다(입력칸이 비면 등록된 것)
                deadline = time.time() + 240
                posted = False
                while time.time() < deadline:
                    if page.is_closed():
                        break
                    try:
                        cur = page.evaluate(
                            """() => {
                                const vis = el => el && el.offsetParent !== null;
                                const el = [...document.querySelectorAll('.u_cbox_text, textarea')].filter(vis)
                                    .find(e => e.closest('.u_cbox_reply_area, .u_cbox_reply'));
                                return el ? (el.innerText || el.value || '').replace(/\\s/g,'') : null;
                            }"""
                        )
                    except Exception:
                        break
                    if cur is None or len(cur) < 4:
                        posted = True
                        break
                    time.sleep(1.2)

                if posted:
                    replied[key] = today
                    save_json(REPLIED, replied)
                    done += 1
                    log(f"  ✓ 답글 등록됨 ({done})")
                    time.sleep(random.randint(8, 25))  # 답글은 내 블로그라 위험이 낮다 — 짧게
                else:
                    log("  건너뜀")

        # ★세션 되저장 — 네이버가 갱신해 준 쿠키를 반영해야 로그인이 오래 간다.
        #   이걸 안 하면 실행할 때마다 갱신분을 버려서 세션이 서서히 죽는다.
        try:
            ctx.storage_state(path=sess)
            log("세션 갱신 저장 ✓")
        except Exception as e:
            log(f"세션 저장 실패(무시): {str(e)[:40]}")
        browser.close()

    log(f"완료 — 답글 {done}건")
    if args.dry:
        print("\n※ DRY 모드 — 아무것도 등록하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
