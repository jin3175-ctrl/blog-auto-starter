#!/usr/bin/env python3
"""
블로그 이웃관리 3단계 — 반자동 실행 (댓글 + 서로이웃 신청).

★이 스크립트는 **등록/확인 버튼을 절대 누르지 않는다.**
  글을 열고, 초안을 입력칸에 채워놓는 데까지만 한다. 최종 클릭은 항상 에디님이 한다.
  그래서 기계적인 클릭 패턴이 안 생기고, 잘못된 댓글이 나갈 일도 없다.

사용법:
  python3 run.py --blog hsh-2022                 # 오늘치(기본 30명)
  python3 run.py --blog hsh-2022 --limit 10
  python3 run.py --blog hsh-2022 --dry           # 아무것도 입력하지 않고 화면만 점검

★터미널을 볼 필요가 없다. 브라우저 창 하나에서 끝난다.
  화면 맨 위 띠가 지금 뭘 하면 되는지 알려준다.
    ① 초록 띠  → 댓글 읽어보고 [등록] 클릭
    ② 파란 띠  → [확인] 클릭해서 서로이웃 신청
  건너뛰고 싶으면 그냥 두면 된다(시간이 지나면 넘어간다).
  그만하려면 브라우저 창을 닫으면 된다.

안전장치:
  · 하루 상한(기본 30) — 넘으면 시작조차 안 한다
  · ledger 대조 — 이미 댓글/서이추 한 곳은 자동 제외
  · 사람마다 40~120초 랜덤 간격
  · 서로이웃을 안 받는 블로그는 감지해서 기록하고 넘어간다
  · 연속 3회 실패하면 즉시 중단(제재 신호일 수 있다)
"""

import argparse
import csv
import glob
import json
import os
import random
import sys
import time
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
LEDGER = os.path.join(WORK_DIR, "ledger.json")
DAILY = os.path.join(WORK_DIR, "daily.json")
SESSION_DIR = "/Users/edi/블로그 체험단/session"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# 하루 상한. 네이버 공식 상한은 100건이지만 그건 '안전선'이 아니다 —
# 상한을 꽉 채우는 게 딱 봇 패턴이다. 2주 무사히 돌면 50으로 올린다.
DAILY_CAP = 30
FAIL_STOP = 3  # 연속 실패 몇 번이면 중단할지


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(WORK_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def session_file(blog_id):
    name = "naver_state.json" if blog_id == "hsh-2022" else f"naver_state_{blog_id}.json"
    return os.path.join(SESSION_DIR, name)


def banner(page, text, color="#03c75a"):
    """지금 뭘 하면 되는지 화면에 띄운다. 터미널을 볼 필요가 없어야 한다.

    🔴전면 띠로 만들었다가 **서이추 화면의 [확인] 버튼을 덮어버렸다**(실측).
      네이버 화면들은 맨 윗줄(취소·확인)과 오른쪽 아래(등록)에 버튼이 있다.
      → 화면 **왼쪽 아래 구석**에 작은 알약으로 띄우고, `pointer-events:none`으로
        클릭이 항상 뒤로 통과하게 한다. 어떤 버튼도 가리지 않는다.
    """
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
                      + 'color:#fff;box-shadow:0 3px 12px rgba(0,0,0,.3);pointer-events:none;'
                      + 'opacity:.94';
                    document.body.appendChild(b);
                }
                b.style.background = o.c;
                b.textContent = o.t;
            }""",
            {"t": text, "c": color},
        )
    except Exception:
        pass  # 배너는 편의 기능일 뿐, 실패해도 진행에 지장 없다


def wait_until_posted(page, timeout=300):
    """사람이 '등록'을 누를 때까지 기다린다.
    입력칸이 비면 등록된 것으로 본다(네이버는 등록 후 입력칸을 비운다).
    ★스크립트가 등록을 대신 누르지 않는다는 원칙은 그대로다 — 눌렸는지 '보고만' 있는다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.is_closed():
            return "창닫힘"
        try:
            txt = page.evaluate(
                """() => {
                    const vis = el => el && el.offsetParent !== null;
                    const el = [...document.querySelectorAll('textarea, [contenteditable=true]')].find(vis);
                    if (!el) return null;
                    return (el.innerText || el.value || '').replace(/\\s/g, '');
                }"""
            )
        except Exception:
            return "창닫힘"
        if txt is None:
            return "등록됨"  # 입력칸이 사라짐 = 화면이 넘어감
        if len(txt) < 4:
            return "등록됨"
        time.sleep(1.2)
    return "시간초과"


def wait_until_buddy_done(page, timeout=180):
    """사람이 서이추 '확인'을 누를 때까지 기다린다. 누르면 폼에서 빠져나간다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.is_closed():
            return "창닫힘"
        try:
            gone = page.evaluate("() => !document.querySelector('#bothBuddyRadio')")
        except Exception:
            return "창닫힘"
        if gone:
            return "신청됨"
        time.sleep(1.0)
    return "시간초과"


# ───────────────────────── 브라우저 동작 ─────────────────────────

def fill_comment(page, blog_id, log_no, text, dry=False):
    """댓글창을 열고 초안을 채워 넣는다. 등록은 하지 않는다."""
    url = f"https://m.blog.naver.com/CommentList.naver?blogId={blog_id}&logNo={log_no}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    if "nidlogin" in page.url:
        return "세션만료"
    page.wait_for_timeout(2500)

    box = page.evaluate(
        """() => {
            const vis = el => el && el.offsetParent !== null;
            const el = [...document.querySelectorAll('textarea, [contenteditable=true]')].find(vis);
            if (!el) return null;
            return { tag: el.tagName, ph: el.getAttribute('placeholder') || '' };
        }"""
    )
    if not box:
        return "댓글창 못찾음"
    if dry:
        return f"OK(입력칸 발견: {box['tag']})"

    # 사람처럼 — 클릭해서 포커스를 준 뒤 타이핑한다.
    page.evaluate(
        """() => {
            const vis = el => el && el.offsetParent !== null;
            const el = [...document.querySelectorAll('textarea, [contenteditable=true]')].find(vis);
            el.scrollIntoView({block:'center'}); el.click(); el.focus();
        }"""
    )
    page.wait_for_timeout(400)
    page.keyboard.type(text, delay=random.randint(18, 45))
    return "OK"


def open_buddy_form(page, target_blog, message="", dry=False):
    """서로이웃 신청 화면을 열고 '서로이웃' 선택 + 신청 메시지까지 채워둔다.
    확인 버튼은 누르지 않는다.

    ⚠️이 폼에는 신청 메시지 칸이 **있다**(placeholder "우리 서로이웃해요~").
      처음 조사할 때 id·name·placeholder가 전부 비어 있어서 메시지 칸이 아닌 줄 알고 넘겼었다.
      DOM 속성이 비었다고 기능이 없는 게 아니다 — 화면을 눈으로 봐야 한다.
    """
    page.goto(
        f"https://m.blog.naver.com/BuddyAddForm.naver?blogId={target_blog}",
        wait_until="domcontentloaded",
        timeout=25000,
    )
    if "nidlogin" in page.url:
        return "세션만료"
    page.wait_for_timeout(1800)

    state = page.evaluate(
        """() => {
            const b = document.querySelector('#bothBuddyRadio');
            const body = document.body.innerText || '';
            return {
                has: !!b,
                disabled: b ? b.disabled : null,
                already: /이미 이웃|이웃입니다|취소/.test(body) && !b,
            };
        }"""
    )
    if not state["has"] or state["disabled"]:
        # 서로이웃을 안 받는 블로그가 실제로 있다. 계속 시도해봐야 헛수고다.
        return "서이추불가"
    if dry:
        return "OK(서로이웃 선택 가능)"

    page.evaluate(
        """() => {
            const b = document.querySelector('#bothBuddyRadio');
            const l = b.closest('label') || document.querySelector('label[for=bothBuddyRadio]');
            (l || b).click();
            b.checked = true;
            b.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    page.wait_for_timeout(600)

    # 신청 메시지 — 왜 이웃하고 싶은지 한 줄이 있으면 수락률이 오른다.
    if message:
        ok = page.evaluate(
            """() => {
                const vis = el => el && el.offsetParent !== null;
                const el = [...document.querySelectorAll('textarea')].find(vis);
                if (!el) return false;
                el.scrollIntoView({ block: 'center' });
                el.click();
                el.focus();
                return true;
            }"""
        )
        if ok:
            page.wait_for_timeout(300)
            page.keyboard.type(message[:180], delay=random.randint(15, 40))
    return "OK"


# ───────────────────────── 메인 ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="이웃관리 3단계 — 반자동(최종 클릭은 사람)")
    ap.add_argument("--blog", default="hsh-2022")
    ap.add_argument("--csv", default="", help="초안 CSV (없으면 가장 최근)")
    ap.add_argument("--limit", type=int, default=DAILY_CAP)
    ap.add_argument("--dry", action="store_true", help="입력·신청 없이 화면 구조만 점검")
    ap.add_argument(
        "--buddy-only",
        action="store_true",
        help="댓글은 건너뛰고 서이추만. **이미 댓글을 주고받은 사람**에게 쓴다(수락률이 가장 높은 자리).",
    )
    args = ap.parse_args()

    limit = min(args.limit, DAILY_CAP)
    today = date.today().isoformat()
    daily = load_json(DAILY, {})
    done_today = daily.get(today, {}).get(args.blog, 0)

    if not args.dry and done_today >= DAILY_CAP:
        log(f"오늘 이미 {done_today}명 했습니다. 상한({DAILY_CAP})이라 여기서 멈춥니다.")
        log("무리해서 더 하는 게 제일 위험합니다. 내일 다시 돌리세요.")
        return 0
    room = DAILY_CAP - done_today
    limit = min(limit, room)

    path = args.csv
    if not path:
        found = sorted(glob.glob(os.path.join(WORK_DIR, f"초안_{args.blog}_*.csv")), key=os.path.getmtime)
        if not found:
            ap.error("초안 CSV가 없습니다. draft.py를 먼저 돌리세요.")
        path = found[-1]

    ledger = load_json(LEDGER, {})
    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("검수") == "통과" and r.get("댓글초안")]

    # ledger 대조 — 이미 손댄 곳은 두 번 가지 않는다(이게 봇 티의 1순위)
    todo = []
    if args.buddy_only:
        # ★댓글은 이미 달았고 서이추만 남은 사람. 서로 댓글을 주고받은 사이라 수락률이 가장 높다.
        #   (초안 CSV가 아니라 ledger에서 직접 고른다 — 답방 온 사람이 CSV엔 없을 수 있다.)
        for bid, e in ledger.items():
            if e.get("commented") and not e.get("buddy_requested") and not e.get("buddy_blocked"):
                todo.append({"blogId": bid, "출처": "댓글 주고받음", "URL": "", "글제목": "", "서이추메시지": ""})
    else:
        for r in rows:
            e = ledger.get(r["blogId"], {})
            if e.get("commented") or e.get("buddy_requested") or e.get("buddy_blocked"):
                continue
            todo.append(r)
    todo = todo[:limit]

    log(f"초안 파일: {os.path.basename(path)}")
    log(f"오늘 진행: {done_today}명 완료 / 이번에 {len(todo)}명 (상한 {DAILY_CAP})")
    if args.dry:
        log("※ DRY 모드 — 아무것도 입력하지 않고 화면 구조만 봅니다.")
    if not todo:
        log("할 대상이 없습니다.")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("playwright 미설치 — pip3 install playwright")
        return 1

    sess = session_file(args.blog)
    if not os.path.exists(sess):
        log(f"세션 없음: {sess}")
        return 1

    fails = 0
    done = 0
    with sync_playwright() as p:
        # ★headless=False — 에디님이 화면을 보고 직접 눌러야 하므로 반드시 보이는 창.
        browser = p.chromium.launch(headless=args.dry)
        ctx = browser.new_context(storage_state=sess, user_agent=UA,
                                  viewport={"width": 430, "height": 930})
        page = ctx.new_page()

        for i, r in enumerate(todo, 1):
            if page.is_closed():
                log("창이 닫혔습니다. 여기서 멈춥니다.")
                break
            started_at = time.time()  # 이 사람에게 쓴 시간(사람이 읽고 누르는 시간 포함)
            bid = r["blogId"]
            url = r.get("URL", "")
            log_no = url.rstrip("/").split("/")[-1]
            print("\n" + "═" * 70)
            print(f"[{i}/{len(todo)}]  {bid}   ({r.get('출처','')})")
            if r.get("글제목"):
                print(f"  글    : {r['글제목'][:56]}")
            if r.get("댓글초안"):
                print(f"  댓글  : {r['댓글초안']}")
            if r.get("서이추메시지"):
                print(f"  서이추: {r['서이추메시지'][:70]}")
            print("═" * 70)

            if args.buddy_only:
                # 댓글 단계를 통째로 건너뛰고 서이추 화면으로 바로 간다.
                entry = ledger.setdefault(bid, {})
                res2 = open_buddy_form(page, bid, message=r.get("서이추메시지", ""), dry=args.dry)
                if args.dry:
                    log(f"  서이추 {res2}")
                    continue
                if res2 == "서이추불가":
                    entry["buddy_blocked"] = today
                    log("  ⓘ 서로이웃을 안 받는 블로그입니다.")
                elif res2.startswith("OK"):
                    banner(page, f"맨 위 [확인]을 눌러 서로이웃 신청   ({i}/{len(todo)})", "#2f6fed")
                    got = wait_until_buddy_done(page)
                    if got == "창닫힘":
                        save_json(LEDGER, ledger)
                        break
                    if got == "신청됨":
                        entry["buddy_requested"] = today
                        log("  ✓ 서이추 신청됨")
                    else:
                        log(f"  건너뜀({got})")
                done += 1
                save_json(LEDGER, ledger)
                daily.setdefault(today, {})[args.blog] = done_today + done
                save_json(DAILY, daily)
                if i < len(todo):
                    wait = max(0, random.randint(50, 90) - int(time.time() - started_at))
                    for left in range(wait, 0, -1):
                        if page.is_closed():
                            break
                        banner(page, f"{left}초 뒤 다음({i+1}/{len(todo)})", "#777")
                        time.sleep(1)
                continue

            res = fill_comment(page, bid, log_no, r["댓글초안"], dry=args.dry)
            if res == "세션만료":
                log("세션이 만료됐습니다. 체험단 도구에서 --login 후 다시 하세요.")
                break
            if not res.startswith("OK"):
                fails += 1
                log(f"  ⚠ {res} (연속 실패 {fails}/{FAIL_STOP})")
                if fails >= FAIL_STOP:
                    log("연속 실패가 많습니다. 오늘은 여기서 멈춥니다.")
                    break
                continue
            fails = 0

            if args.dry:
                res2 = open_buddy_form(page, bid, dry=True)
                log(f"  댓글창 {res} / 서이추 {res2}")
                continue

            # ① 댓글 — 사람이 [등록]을 누를 때까지 화면에서 기다린다(터미널 볼 필요 없음)
            banner(page, f"① 읽어보고 초록색 [등록]을 누르세요   ({i}/{len(todo)})  ·  건너뛰려면 그냥 두세요")
            posted = wait_until_posted(page)
            if posted == "창닫힘":
                log("  창이 닫혔습니다. 여기서 멈춥니다.")
                break
            if posted != "등록됨":
                log(f"  건너뜀({posted})")
                continue
            log("  ✓ 댓글 등록됨")

            entry = ledger.setdefault(bid, {})
            entry["commented"] = entry.get("commented", 0) + 1
            entry["commented_at"] = today
            save_json(LEDGER, ledger)

            # ② 서로이웃 — 화면을 열고 '서로이웃'을 선택해둔 뒤, 사람이 [확인]을 누를 때까지 기다린다
            res2 = open_buddy_form(page, bid, message=r.get("서이추메시지", ""))
            if res2 == "서이추불가":
                entry["buddy_blocked"] = today
                log("  ⓘ 서로이웃을 안 받는 블로그입니다. 기록해두고 넘어갑니다.")
            elif res2.startswith("OK"):
                banner(page, f"② 맨 위 [확인]을 눌러 서로이웃 신청   ({i}/{len(todo)})", "#2f6fed")
                got = wait_until_buddy_done(page)
                if got == "창닫힘":
                    save_json(LEDGER, ledger)
                    log("  창이 닫혔습니다. 여기서 멈춥니다.")
                    break
                if got == "신청됨":
                    entry["buddy_requested"] = today
                    log("  ✓ 서이추 신청됨")
                else:
                    log(f"  서이추 건너뜀({got})")
            else:
                log(f"  ⚠ 서이추 화면: {res2}")

            done += 1
            save_json(LEDGER, ledger)
            daily.setdefault(today, {})[args.blog] = done_today + done
            save_json(DAILY, daily)

            if i < len(todo):
                # ★반자동에서는 **에디님이 읽고 누르는 시간 자체가 이미 사람 속도**다.
                #   거기에 또 1~2분을 얹으면 앉아서 기다리기만 하는 시간이 생긴다(30명에 40분).
                #   → 한 사람당 '총 간격'을 60~100초로 잡고, 사람이 쓴 시간만큼 빼고 남은 만큼만 쉰다.
                target = random.randint(60, 100)
                spent = int(time.time() - started_at)
                wait = max(0, target - spent)
                log(f"  ✓ 완료 ({done_today + done}/{DAILY_CAP}) — 작업 {spent}초 + 대기 {wait}초")
                for left in range(wait, 0, -1):
                    if page.is_closed():
                        break
                    banner(page, f"{left}초 뒤 다음 사람({i + 1}/{len(todo)})", "#777")
                    time.sleep(1)

        # ★세션 되저장 — 네이버가 갱신해 준 쿠키를 반영해야 로그인이 오래 간다.
        #   이걸 안 하면 실행할 때마다 갱신분을 버려서 세션이 서서히 죽는다.
        try:
            ctx.storage_state(path=sess)
            log("세션 갱신 저장 ✓")
        except Exception as e:
            log(f"세션 저장 실패(무시): {str(e)[:40]}")
        browser.close()

    log(f"오늘 마무리 — 이번에 {done}명, 누적 {done_today + done}/{DAILY_CAP}")
    if done_today + done >= DAILY_CAP:
        log("상한에 닿았습니다. 내일 이어서 하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
