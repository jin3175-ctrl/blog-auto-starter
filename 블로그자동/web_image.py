"""본문 이미지를 '웹 구독'(제미나이 Plus)에서 Playwright로 뽑는다. (에디 블로그 이식본, 2026-08-01)

제이 경제 블로그(/Users/edi/경제이슈 블로그 자동화/web_image.py)의 검증 구조를 이식.
왜: API 이미지 생성은 건당 과금. 에디님은 제미나이·챗지피티 유료 구독 중이라 '웹 UI'를 자동 구동하면
    구독 안에서 무료로 뽑는다.

구조 — naver.py와 같은 '저장 세션 + Playwright'인데, 구글은 자동화 로그인을 잘 막으므로
  기본 크로미움이 아니라 '실제 Chrome + 전용 프로필'(launch_persistent_context, channel=chrome)을 쓴다.
  · login()  = 창 뜸(headless 아님). 에디님이 제미나이에 로그인 → 프로필에 세션 저장(1회).
  · generate(desc, out) = 같은 프로필로 실행 → 프롬프트 → 생성 이미지 다운로드.
    실패(세션 만료·UI 변경·거부) 시 False → image_finder가 무료 Unsplash로 폴백.

⚠️ 무인 브라우저 자동화는 약하다(세션·UI·한도). 반드시 '실패=False→폴백'. 자동실행이 이미지 때문에 죽으면 안 된다.

재로그인/확인:  python3 web_image.py login
단독 테스트:    python3 web_image.py "코딩하는 40대 남성 뒷모습"   (헤드리스)
             python3 web_image.py "..." show               (창 띄워 눈으로 확인)
"""
from __future__ import annotations

import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE, "session")
PROFILE = os.path.join(SESSION_DIR, "gemini_profile")   # 실제 Chrome 사용자 데이터 디렉토리
GPT_PROFILE = os.path.join(SESSION_DIR, "chatgpt_profile")   # ChatGPT 폴백용(에디님 Plus 구독)
DEBUG_DIR = os.path.join(BASE, "work", "webimg_debug")

GEMINI_URL = "https://gemini.google.com/app"
_INPUT_SEL = ("div.ql-editor[contenteditable='true'], "
              "rich-textarea div[contenteditable='true'], "
              "div[contenteditable='true'][role='textbox']")

CHATGPT_URL = "https://chatgpt.com/"
_GPT_INPUT_SEL = ("div#prompt-textarea[contenteditable='true'], "
                  "div[contenteditable='true'][id='prompt-textarea'], "
                  "textarea#prompt-textarea")


def _ctx(p, headless: bool, profile: str | None = None):
    """실제 Chrome + 전용 프로필. 자동화 티를 줄여 구글/OpenAI 로그인 세션이 유지되게."""
    return p.chromium.launch_persistent_context(
        profile or PROFILE, channel="chrome", headless=headless, locale="ko-KR",
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"])


def login(timeout_sec: int = 300, log=print, service: str = "gemini") -> bool:
    """창을 띄워 에디님이 직접 로그인 → 프로필에 저장(1회). service='gemini'|'chatgpt'.

    ⚠️ 제미나이는 **비로그인 상태에서도 입력창이 보인다** → 입력창만 보고 저장하면 세션이 안 붙는다
       (실측 2026-08-01: 우상단 '로그인' 버튼 + 모델 Flash-Lite = 비로그인).
       그래서 창을 일찍 닫지 않고, 로그인 완료 신호(로그인 버튼 사라짐)를 함께 본다."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    prof = GPT_PROFILE if service == "chatgpt" else PROFILE
    url = CHATGPT_URL if service == "chatgpt" else GEMINI_URL
    sel = _GPT_INPUT_SEL if service == "chatgpt" else _INPUT_SEL
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _ctx(p, headless=False, profile=prof)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded")
        log(f"▶ 뜬 Chrome 창에서 {service}에 로그인하세요(유료 구독 계정).")
        log(f"  로그인이 끝나면 자동 저장됩니다(최대 {timeout_sec}초). 창을 먼저 닫지 마세요.")
        ok = False
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                has_input = bool(pg.query_selector(sel))
                # 로그인 버튼이 남아 있으면 아직 비로그인 → 계속 기다린다
                login_btn = pg.query_selector(
                    'button:has-text("로그인"), a:has-text("로그인"), '
                    'button:has-text("Log in"), a:has-text("Log in")')
                if has_input and not login_btn:
                    ok = True; break
            except Exception:  # noqa: BLE001
                pass
            pg.wait_for_timeout(1500)
        pg.wait_for_timeout(2000)
        ctx.close()   # 프로필에 세션 저장됨
        log("✅ 로그인 세션 저장됨" if ok else "❌ 시간 내 로그인 확인 실패(다시 시도하세요)")
        return ok


def session_alive() -> bool:
    return os.path.isdir(PROFILE) and bool(os.listdir(PROFILE))


def gpt_session_alive() -> bool:
    return os.path.isdir(GPT_PROFILE) and bool(os.listdir(GPT_PROFILE))


def _prompt(description_ko: str) -> str:
    return (
        f"블로그 본문에 넣을 사진 한 장을 만들어줘. 장면: {description_ko}. "
        "실제 사진처럼 자연스럽고 밝은 톤, 가로 16:9. "
        "알아볼 수 있는 사람 얼굴·실존 인물·특정 브랜드 로고·워터마크는 넣지 마. "
        "화면·모니터·차트에 구체적 숫자는 적지 마."
    )


def generate(description_ko: str, out_path: str, log=print,
             timeout_sec: int = 220, headless: bool = True) -> bool:
    """저장 세션으로 제미나이에 이미지 1장 생성 → 다운로드. 실패 시 False(→폴백)."""
    if not session_alive():
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return False
    os.makedirs(DEBUG_DIR, exist_ok=True)
    try:
        with sync_playwright() as p:
            ctx = _ctx(p, headless=headless)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            box = pg.query_selector(_INPUT_SEL)
            if not box:
                pg.screenshot(path=os.path.join(DEBUG_DIR, "no_input.png"))
                _dbg(log, "입력창 없음(세션 만료 의심)"); ctx.close(); return False
            box.click()
            pg.keyboard.type(_prompt(description_ko), delay=6)
            pg.keyboard.press("Enter")
            img_src = None
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                pg.wait_for_timeout(2500)
                # 생성 이미지: 응답 안 googleusercontent/blob 이미지 중 '큰 것'.
                #  ★'이미지를 만들고 있습니다' 단계의 빈 플레이스홀더를 잡지 않도록 512px 이상만.
                #    (제미나이 생성물은 보통 1024px+; 아바타·아이콘도 이 기준에서 걸러진다)
                srcs = pg.eval_on_selector_all(
                    "img",
                    "els => els.filter(e => e.naturalWidth>=512 && e.naturalHeight>=512)"
                    ".map(e => e.src).filter(s => s && (s.includes('googleusercontent')"
                    " || s.startsWith('blob:') || s.startsWith('data:image')))")
                if srcs:
                    img_src = srcs[-1]; break
            if not img_src:
                pg.screenshot(path=os.path.join(DEBUG_DIR, "no_image.png"))
                _dbg(log, "생성 이미지 못 찾음"); ctx.close(); return False
            # 다운로드: fetch(blob:)은 CORS로 막히는 경우가 많다(제이에서 'Failed to fetch' 실측).
            #  → ① fetch 시도 ② 실패 시 이미지 엘리먼트를 직접 스크린샷(가장 안정적).
            raw = None
            try:
                data = pg.evaluate(
                    """async (src) => { const r=await fetch(src); const b=new Uint8Array(await r.arrayBuffer());
                       let s=''; for(let i=0;i<b.length;i++) s+=String.fromCharCode(b[i]); return btoa(s); }""",
                    img_src)
                import base64
                raw = base64.b64decode(data)
            except Exception as e:  # noqa: BLE001
                log(f"  web_image: fetch 실패 → 엘리먼트 스크린샷으로 대체({str(e)[:40]})")
                try:
                    el = pg.query_selector(f'img[src="{img_src}"]')
                    if el:
                        el.scroll_into_view_if_needed()
                        pg.wait_for_timeout(600)
                        el.screenshot(path=out_path)
                        raw = open(out_path, "rb").read()
                except Exception as e2:  # noqa: BLE001
                    log(f"  web_image: 스크린샷도 실패({str(e2)[:40]})")
            ctx.close()
            if not raw or len(raw) < 3000:
                return False
            if not os.path.exists(out_path) or open(out_path, "rb").read() != raw:
                with open(out_path, "wb") as f:
                    f.write(raw)
            _trim_ui(out_path, log)   # 스크린샷 폴백일 때 붙는 제미나이 UI 버튼·워터마크 제거
            log("  web_image: 제미나이 생성 이미지 저장")
            return True
    except Exception as e:  # noqa: BLE001
        log(f"  web_image 예외 → 폴백: {str(e)[:70]}")
        return False


def generate_gpt_many(descriptions: list[str], out_paths: list[str], log=print,
                      per_image_sec: int = 200, headless: bool = False) -> list[bool]:
    """ChatGPT에서도 **창 하나로 여러 장** 연속 생성(2026-08-06 에디님:
    "창을 하나 열어놓고 거기서 한 편에 들어갈 이미지를 모두 만들어라").

    전엔 실패분마다 generate_gpt()를 불러 장당 새 창이 떴다(4장이면 창 4번).
    """
    n = len(descriptions)
    results = [False] * n
    if not n or not gpt_session_alive():
        return results
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return results
    try:
        with sync_playwright() as p:
            ctx = _ctx(p, headless=headless, profile=GPT_PROFILE)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3500)
            if not pg.query_selector(_GPT_INPUT_SEL):
                ctx.close()
                _dbg(log, "ChatGPT 입력창 없음(세션 만료/Cloudflare)")
                return results
            seen: set = set()
            for i, (desc, out) in enumerate(zip(descriptions, out_paths)):
                try:
                    before = len(_gpt_img_srcs(pg))
                    box = pg.query_selector(_GPT_INPUT_SEL)
                    if not box:
                        break
                    box.click()
                    pg.keyboard.type(_prompt(desc), delay=4)
                    pg.keyboard.press("Enter")
                    results[i] = _grab_new_gpt_image(pg, seen, out, per_image_sec, before)
                    log(f"  GPT이미지 {i+1}/{n} " + ("생성" if results[i] else "실패"))
                except Exception as e:  # noqa: BLE001
                    log(f"  GPT이미지 {i+1}/{n} 예외: {str(e)[:40]}")
            ctx.close()
    except Exception as e:  # noqa: BLE001
        log(f"generate_gpt_many 예외: {str(e)[:60]}")
    return results


def _gpt_img_srcs(pg) -> list[str]:
    return pg.eval_on_selector_all(
        "main img, [class*='markdown'] img, article img",
        "els => els.filter(e => e.naturalWidth>=256 && e.naturalHeight>=200"
        " && (e.naturalWidth / Math.max(1,e.naturalHeight)) >= 1.2)"
        ".map(e => e.src).filter(s => s && (s.includes('backend-api')"
        " || s.includes('estuary/content') || s.includes('oaiusercontent')"
        " || s.startsWith('blob:') || s.startsWith('data:image')))")


def _grab_new_gpt_image(pg, seen: set, out_path: str, timeout_sec: int, base_count: int) -> bool:
    """ChatGPT 응답에서 새로 생긴 이미지를 저장(개수 기준 판정)."""
    deadline = time.time() + timeout_sec
    img_src = None
    while time.time() < deadline:
        pg.wait_for_timeout(3000)
        srcs = _gpt_img_srcs(pg)
        if len(srcs) > base_count:
            img_src = srcs[-1]; break
        fresh = [s for s in srcs if s not in seen]
        if fresh:
            img_src = fresh[-1]; break
    if not img_src:
        return False
    seen.add(img_src)
    try:
        data = pg.evaluate(
            """async (src) => { const r=await fetch(src); const b=new Uint8Array(await r.arrayBuffer());
               let s=''; for(let i=0;i<b.length;i++) s+=String.fromCharCode(b[i]); return btoa(s); }""",
            img_src)
        import base64
        raw = base64.b64decode(data)
    except Exception:  # noqa: BLE001
        try:
            el = pg.query_selector(f'img[src="{img_src}"]')
            if not el:
                return False
            el.scroll_into_view_if_needed(); pg.wait_for_timeout(500)
            el.screenshot(path=out_path)
            raw = open(out_path, "rb").read()
        except Exception:  # noqa: BLE001
            return False
    if not raw or len(raw) < 3000:
        return False
    with open(out_path, "wb") as f:
        f.write(raw)
    return True


def generate_gpt(description_ko: str, out_path: str, log=print,
                 timeout_sec: int = 260, headless: bool = False) -> bool:
    """ChatGPT(유료 구독) 웹에서 이미지 1장 생성 → 저장. 제미나이 한도 초과 시 폴백용.

    ★headless 기본 False: ChatGPT는 **Cloudflare 봇 검증**('사람인지 확인하십시오')이 걸려
      headless로는 입력창에 도달하지 못한다(실측 2026-08-01). 창을 띄우면 통과한다.
      (봇 검증 우회는 하지 않는다 — 정상 브라우저로 여는 방식만 쓴다.)
    실패 시 False. 구조는 generate()와 동일(전용 프로필 + Playwright + 스크린샷 폴백)."""
    if not gpt_session_alive():
        log("  web_image: ChatGPT 세션 없음(python3 web_image.py login-gpt 필요)")
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return False
    os.makedirs(DEBUG_DIR, exist_ok=True)
    try:
        with sync_playwright() as p:
            ctx = _ctx(p, headless=headless, profile=GPT_PROFILE)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3500)
            box = pg.query_selector(_GPT_INPUT_SEL)
            if not box:
                pg.screenshot(path=os.path.join(DEBUG_DIR, "gpt_no_input.png"))
                _dbg(log, "ChatGPT 입력창 없음(세션 만료 의심)"); ctx.close(); return False
            box.click()
            pg.keyboard.type(_prompt(description_ko), delay=6)
            pg.keyboard.press("Enter")
            img_src = None
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                pg.wait_for_timeout(3000)
                # ChatGPT 생성 이미지: oaiusercontent/blob, 충분히 큰 것
                # 생성 이미지 URL 실측(2026-08-01): chatgpt.com/backend-api/estuary/content?id=file-...
                #  ⚠️ 사이드바 앱 아이콘(Canva 등)도 같은 backend-api 512x512로 잡힌다 →
                #     ① 대화 영역(main) 안쪽만 ② 정사각 아이콘 배제(가로/세로 비 1.2 이상, 16:9 사진 기준).
                srcs = pg.eval_on_selector_all(
                    "main img, [class*='markdown'] img, article img",
                    "els => els.filter(e => e.naturalWidth>=256 && e.naturalHeight>=200"
                    " && (e.naturalWidth / Math.max(1,e.naturalHeight)) >= 1.2)"
                    ".map(e => e.src).filter(s => s && (s.includes('backend-api')"
                    " || s.includes('estuary/content') || s.includes('oaiusercontent')"
                    " || s.startsWith('blob:') || s.startsWith('data:image')))")
                if srcs:
                    img_src = srcs[-1]; break
            if not img_src:
                pg.screenshot(path=os.path.join(DEBUG_DIR, "gpt_no_image.png"))
                _dbg(log, "ChatGPT 생성 이미지 못 찾음"); ctx.close(); return False
            raw = None
            try:
                data = pg.evaluate(
                    """async (src) => { const r=await fetch(src); const b=new Uint8Array(await r.arrayBuffer());
                       let s=''; for(let i=0;i<b.length;i++) s+=String.fromCharCode(b[i]); return btoa(s); }""",
                    img_src)
                import base64
                raw = base64.b64decode(data)
            except Exception:  # noqa: BLE001
                try:
                    el = pg.query_selector(f'img[src="{img_src}"]')
                    if el:
                        el.scroll_into_view_if_needed()
                        pg.wait_for_timeout(600)
                        el.screenshot(path=out_path)
                        raw = open(out_path, "rb").read()
                except Exception as e2:  # noqa: BLE001
                    log(f"  web_image(gpt): 스크린샷도 실패({str(e2)[:40]})")
            ctx.close()
            if not raw or len(raw) < 3000:
                return False
            if not os.path.exists(out_path) or open(out_path, "rb").read() != raw:
                with open(out_path, "wb") as f:
                    f.write(raw)
            log("  web_image: ChatGPT 생성 이미지 저장")
            return True
    except Exception as e:  # noqa: BLE001
        log(f"  web_image(gpt) 예외 → 폴백: {str(e)[:70]}")
        return False


def _img_srcs(pg) -> list[str]:
    return pg.eval_on_selector_all(
        "img",
        "els => els.filter(e => e.naturalWidth>=512 && e.naturalHeight>=512)"
        ".map(e => e.src).filter(s => s && (s.includes('googleusercontent')"
        " || s.startsWith('blob:') || s.startsWith('data:image')))")


def _grab_new_image(pg, seen: set, out_path: str, timeout_sec: int, log,
                    base_count: int = -1) -> bool:
    """마지막 프롬프트로 새로 생긴 이미지를 받아 저장.

    ★판정 기준(2026-08-06 수정): 예전엔 'seen에 없는 src'로만 봤는데, 제미나이가 **blob URL을
      재사용**해서 새 이미지인데도 이미 본 것으로 걸러졌다. 그래서 한 장 걸러 한 장씩
      2.5분 타임아웃으로 실패했다(홀수 성공/짝수 실패 패턴).
      이제 **이미지 개수가 늘었는지**를 먼저 보고, 늘었으면 마지막 것을 새 이미지로 쓴다.
    """
    deadline = time.time() + timeout_sec
    img_src = None
    while time.time() < deadline:
        pg.wait_for_timeout(2500)
        srcs = _img_srcs(pg)
        if base_count >= 0 and len(srcs) > base_count:
            img_src = srcs[-1]
            break
        fresh = [s for s in srcs if s not in seen]
        if fresh:
            img_src = fresh[-1]
            break
    if not img_src:
        return False
    seen.add(img_src)
    raw = None
    try:
        data = pg.evaluate(
            """async (src) => { const r=await fetch(src); const b=new Uint8Array(await r.arrayBuffer());
               let s=''; for(let i=0;i<b.length;i++) s+=String.fromCharCode(b[i]); return btoa(s); }""",
            img_src)
        import base64
        raw = base64.b64decode(data)
    except Exception:  # noqa: BLE001
        try:
            el = pg.query_selector(f'img[src="{img_src}"]')
            if el:
                el.scroll_into_view_if_needed()
                pg.wait_for_timeout(500)
                el.screenshot(path=out_path)
                raw = open(out_path, "rb").read()
        except Exception:  # noqa: BLE001
            return False
    if not raw or len(raw) < 3000:
        return False
    if not os.path.exists(out_path) or open(out_path, "rb").read() != raw:
        with open(out_path, "wb") as f:
            f.write(raw)
    _trim_ui(out_path, lambda m: None)
    return True


def make_many_once(descriptions: list[str], out_paths: list[str], log=print,
                   headless: bool = True, per_image_sec: int = 150) -> list[bool]:
    """제미나이 창 1개로 여러 장 생성(재시도 없음). make_many가 이걸 감싼다."""
    return _gemini_batch(descriptions, out_paths, log, headless, per_image_sec)


def make_many(descriptions: list[str], out_paths: list[str], log=print,
              headless: bool = True, per_image_sec: int = 150) -> list[bool]:
    """★여러 장을 **한 브라우저 세션**에서 연속 생성(2026-08-04).

    장당 브라우저를 새로 띄우면 5분 넘게 걸렸다(실측 5분27초/장 → 6장이면 33분).
    제미나이 대화창을 한 번만 열고 프롬프트를 이어서 넣으면 장당 1~2분으로 준다.
    반환: 각 장의 성공 여부 리스트(실패분은 호출부가 폴백 처리).
    """
    return _gemini_batch(descriptions, out_paths, log, headless, per_image_sec, retry_gpt=True)


#: ★한 편의 '이미지 단계' 전체 상한(초). 2026-08-10 실측 사고 대응 —
#  per_image_sec=150을 줘도 한 장에 17분을 쓰는 경우가 있어(제미나이 응답 지연/한도)
#  04편 한 편이 **182분**을 먹었다(다른 편은 13~16분). 남은 자리는 호출부가 Gemini API/스톡으로 채운다.
BATCH_BUDGET_SEC = 600


def _gemini_batch(descriptions: list[str], out_paths: list[str], log=print,
                  headless: bool = True, per_image_sec: int = 150,
                  retry_gpt: bool = False) -> list[bool]:
    """제미나이 창 1개로 연속 생성. retry_gpt=True면 실패분을 제미나이 재시도→ChatGPT 순으로 보완."""
    n = len(descriptions)
    results = [False] * n
    if not session_alive() or not n:
        return results
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return results
    try:
        with sync_playwright() as p:
            ctx = _ctx(p, headless=headless)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            box = pg.query_selector(_INPUT_SEL)
            if not box:
                ctx.close()
                _dbg(log, "입력창 없음(세션 만료 의심)")
                return results
            seen: set = set()
            try:
                pg.set_default_timeout(20000)      # 개별 Playwright 동작이 오래 매달리지 않게
            except Exception:  # noqa: BLE001
                pass
            _t0 = time.time()
            for i, (desc, out) in enumerate(zip(descriptions, out_paths)):
                if time.time() - _t0 > BATCH_BUDGET_SEC:
                    log(f"  웹이미지 예산({BATCH_BUDGET_SEC//60}분) 초과 → 남은 "
                        f"{n - i}장은 폴백(API·스톡)에 넘김")
                    break
                try:
                    before = len(_img_srcs(pg))     # 보내기 전 이미지 개수(새 이미지 판정 기준)
                    box = pg.query_selector(_INPUT_SEL) or box
                    box.click()
                    pg.keyboard.type(_prompt(desc), delay=4)
                    pg.keyboard.press("Enter")
                    results[i] = _grab_new_image(pg, seen, out, per_image_sec, log,
                                                 base_count=before)
                    log(f"  웹이미지 {i+1}/{n} " + ("생성" if results[i] else "실패"))
                except Exception as e:  # noqa: BLE001
                    log(f"  웹이미지 {i+1}/{n} 예외: {str(e)[:40]}")
            ctx.close()
    except Exception as e:  # noqa: BLE001
        log(f"web_image(make_many) 예외 → 폴백: {str(e)[:60]}")
    # ★제미나이가 실패한 자리는 ChatGPT로 재시도(2026-08-04 에디님: "챗지피티 안되면 제미나이에서
    #   진행해야지" — 단일 make엔 있던 폴백이 일괄 경로엔 빠져 있어 이미지가 통째로 비었다).
    # ★제미나이 우선(2026-08-06 에디님: "챗지피티는 이미지 제한이 자꾸 걸리니 왠만하면 제미나이로").
    #   실패분은 먼저 **제미나이에서 한 번 더** 시도하고, 그래도 안 되는 것만 ChatGPT로 넘긴다.
    retry = [i for i, ok in enumerate(results) if not ok] if retry_gpt else []
    if retry:
        log(f"  제미나이 재시도 {len(retry)}장(창 재사용)")
        try:
            again = _gemini_batch([descriptions[i] for i in retry],
                                  [out_paths[i] for i in retry],
                                  lambda m: None, headless, per_image_sec, False)
            for k, i in enumerate(retry):
                if k < len(again) and again[k]:
                    results[i] = True
            log(f"  제미나이 재시도 결과: {sum(1 for i in retry if results[i])}/{len(retry)}장")
        except Exception as e:  # noqa: BLE001
            log(f"  제미나이 재시도 실패: {str(e)[:40]}")

    # ★2026-08-06 에디님 확정: "지금부터 진행하는 모든 것은 제미나이로."
    #   ChatGPT 폴백은 **완전히 제거**했다(한도가 자주 걸려 실패만 키웠다).
    #   제미나이가 못 만든 자리는 호출부(pipeline)가 Gemini API/스톡으로 채운다.
    return results


def make(description_ko: str, out_path: str, log=print, headless: bool = True) -> bool:
    """★권장 진입점: **제미나이로만** 이미지 1장 확보(2026-08-06 에디님 확정).
    실패하면 False → 호출부(pipeline)가 Gemini API/스톡으로 폴백한다.
    ChatGPT는 이미지 생성 한도가 자주 걸려 자동 경로에서 완전히 뺐다."""
    return generate(description_ko, out_path, log=log, headless=headless)


def _trim_ui(path: str, log=print) -> None:
    """엘리먼트 스크린샷으로 받은 이미지에서 겹쳐 그려진 제미나이 UI를 잘라낸다.
    UI 위치(실측 2026-08-01): 우상단 공유/복사/다운로드 버튼(가장 큼) · 우하단 반짝이 워터마크.
    → 상단을 더 깊게(12%), 좌우·하단은 얕게(5%) 크롭. 실패해도 원본 유지(무해)."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return   # Pillow 없으면 그냥 원본 사용
    try:
        im = Image.open(path)
        w, h = im.size
        left, right = int(w * 0.05), int(w * 0.05)
        top, bottom = int(h * 0.12), int(h * 0.05)
        if w - left - right < 200 or h - top - bottom < 200:
            return
        im.crop((left, top, w - right, h - bottom)).save(path)
        log(f"  web_image: UI 크롭 → {w-left-right}x{h-top-bottom}")
    except Exception as e:  # noqa: BLE001
        log(f"  web_image: 크롭 생략({str(e)[:40]})")


def _dbg(log, msg: str) -> None:
    log(f"  web_image: {msg} → 폴백 (스크린샷: work/webimg_debug/)")


if __name__ == "__main__":
    arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg1 == "login":
        login()                          # 제미나이 로그인(1회)
    elif arg1 == "login-gpt":
        login(service="chatgpt")         # ChatGPT 로그인(1회, 한도 폴백용)
    elif arg1 == "gpt":                  # ChatGPT로만 생성 테스트(기본=창 모드, Cloudflare 때문)
        desc = sys.argv[2] if len(sys.argv) > 2 else "코딩하는 40대 남성의 뒷모습, 책상 위 노트북"
        hl = len(sys.argv) > 3 and sys.argv[3] == "headless"   # 굳이 headless로 보고 싶을 때만
        print("생성:", generate_gpt(desc, "/tmp/_webimg_test.png", headless=hl))
    else:                                # 기본: 제미나이 → ChatGPT 폴백 체인
        desc = arg1 or "코딩하는 40대 남성의 뒷모습, 책상 위 노트북"
        show = len(sys.argv) > 2 and sys.argv[2] == "show"
        print("생성:", make(desc, "/tmp/_webimg_test.png", headless=not show))
