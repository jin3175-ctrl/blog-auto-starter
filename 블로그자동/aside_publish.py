"""윈도우 임시저장 — 어사이드 CLI로 글쓰기 화면에 직접 넣는다 (2026-10-25 · 3기 3주차).

예전(10/17~10/24): `어사이드용/` 폴더에 .html과 프롬프트를 만들고, 사람이 어사이드 Ask 칸에 붙여넣었다
→ 2·3기 윈도우에서 「안 된다」로 막혔다. 이제 어사이드 AI에게 부탁하지 않고 **프로그램이 직접** 넣는다.
CLI가 없거나 중간에 실패하면 browser_upload.py 가 예전 .html 방식으로 넘어간다(그건 그대로 둔다).

어사이드 REPL의 제약(2026-10-25 에디 맥 실측 · Aside 1.0.1022 · CLI 1.26.1023):
  · 명령 하나에 120초 — 글 한 편을 한 번에 못 돌린다. REPL 안 백그라운드 작업은 명령 사이에 멈춘다.
    → 파이썬이 「제목 → 블록 하나씩 → 태그 → 저장」을 **짧은 명령으로 나눠** 보낸다.
  · 에디터는 iframe `#mainFrame` 안이다 → `frameLocator('#mainFrame')` 로 누른다(에고라이트는 저절로 통과했다).
  · `setFiles(경로)`는 어사이드 작업 폴더 밖이면 막힌다(「escapes the session directory」)
    → 사진은 **내용(base64)을 넘겨** `setFiles({name, mimeType, buffer})` 로 넣는다.
  · 글이 든 글쓰기 탭은 「나가시겠습니까」 창 때문에 안 닫힌다 → 그 창을 자동 수락하고 about:blank 로 비운 뒤 닫는다.

🔴**임시저장까지만.** 발행 버튼은 누르지 않는다. (`config.AUTO_PUBLISH`와 상관없이 이 파일에는 발행 코드가 없다)
  · 🔴어사이드의 locator/getByText는 네이버 에디터에서 못 믿는다(떠 있는 팝업을 0개로 셌다) · 요소를 눌러도 초점이 안 간다
    → 요소는 페이지 안에서 직접 찾아 좌표를 구하고 **진짜 마우스**(`mouse.click`, isTrusted=true)로 누른다(`_click`).
⚠️아직 없는 것: 빨강·노랑 서식(글자만 들어간다) · 사진 설명(캡션) · 링크 카드(주소 글자로) · 표(건너뜀) · 인용구 모양 섞기.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "이웃관리"))
import browser_drive  # noqa: E402  — 어사이드 REPL을 띄워 두는 부품(이웃관리와 같이 쓴다)

J = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731

# 에디터 안(#mainFrame) 문서를 잡는 짧은 JS — evaluate 안에서 쓴다
_DOC = "const f = document.querySelector('#mainFrame'); const d = (f && f.contentDocument) ? f.contentDocument : document;"


def available() -> bool:
    return bool(browser_drive.aside_bin())


def _pt(s, css: str, text: str = "", nth: int = 0):
    """에디터(#mainFrame) 안에서 css(+보이는 글자)로 요소를 찾아 화면 가운데로 올리고 화면 좌표를 돌려준다. 없으면 None.
    🔴어사이드의 locator/getByText는 이 페이지에서 못 믿는다(10/25 실측: 떠 있는 「작성 중인 글」 팝업을 0개로 셌다).
       그래서 요소는 페이지 안에서 직접 찾고, 누르는 건 **진짜 마우스**(`mouse.click` — isTrusted=true 확인)로 한다."""
    return s(f"return await __edi.evaluate(([css, text, nth]) => {{ {_DOC}"
             "const vis = e => e && (e.offsetParent !== null || e.getClientRects().length);"
             "let els = [...d.querySelectorAll(css)].filter(vis);"
             "if (!els.length && d !== document) els = [...document.querySelectorAll(css)].filter(vis);"
             "if (text) els = els.filter(e => (e.innerText || e.textContent || '').replace(/\\s+/g, '').includes(text.replace(/\\s+/g, '')));"
             "const el = els[nth < 0 ? els.length + nth : nth]; if (!el) return null;"
             "el.scrollIntoView({block: 'center'}); const r = el.getBoundingClientRect();"
             "const inFrame = el.ownerDocument !== document; const fr = inFrame ? f.getBoundingClientRect() : {left: 0, top: 0};"
             f"return {{x: fr.left + r.left + Math.min(r.width / 2, 40), y: fr.top + r.top + r.height / 2}}; }}, {J([css, text, nth])});")


def _click(s, css: str, text: str = "", nth: int = 0, wait: float = 0.4) -> bool:
    pt = _pt(s, css, text, nth)
    if not pt:
        return False
    s(f"await __edi.mouse.click({pt['x']}, {pt['y']}); await sleep({int(wait * 1000)}); return 1;")
    return True


def _title_text(s) -> str:
    return s(f"return await __edi.evaluate(() => {{ {_DOC} const t = d.querySelector('.se-section-documentTitle'); return t ? t.innerText.trim() : ''; }});") or ""


def _save_count(s) -> int:
    v = s(f"return await __edi.evaluate(() => {{ {_DOC} const b = d.querySelector('button[class*=\"save_count_btn\"]'); return b ? b.innerText.trim() : ''; }});")
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def draft(blog_id: str, title: str, blocks: list, log=print, category: str = "", align: str = "",
          ai_mark: bool = True) -> dict:
    """{ok, message, notes}. 실패해도 예외를 던지지 않는다 — 호출측이 예전 방식으로 넘어간다."""
    notes: list = []
    images = 0
    if not blog_id:
        return {"ok": False, "message": "내정보.txt 의 블로그ID가 비어 있습니다", "notes": notes}
    try:
        pg = browser_drive.AsidePage()
    except RuntimeError as e:
        return {"ok": False, "message": str(e)[:300], "notes": notes}
    s = pg._send
    try:
        # ── 1) 글쓰기 화면 ──
        pg.goto(f"https://blog.naver.com/{blog_id}?Redirect=Write&")
        s("__edi.on('dialog', d => d.accept().catch(() => {})); return 1;")
        if "nidlogin" in pg.url:
            return {"ok": False, "message": "어사이드에서 네이버 로그인이 안 돼 있습니다 — 어사이드를 열고 본인이 직접 로그인해 주세요.",
                    "notes": notes}
        for _ in range(40):          # 제목 칸이 뜰 때까지(최대 40초)
            if _pt(s, ".se-section-documentTitle .se-text-paragraph"):
                break
            time.sleep(1)
        else:
            return {"ok": False, "message": "에디터가 안 열립니다(제목 칸 없음)", "notes": notes}
        time.sleep(1.5)
        # «작성 중인 글이 있습니다» → 취소(새 글로 시작). 확인을 누르면 지난 내용이 딸려 들어온다.
        if _pt(s, ".se-popup-alert", "작성 중인 글"):
            _click(s, ".se-popup-alert button", "취소", wait=1.2)
            log("«작성 중인 글» → 취소(새 글로 시작)")
        if _pt(s, ".se-popup-dim"):
            s("await __edi.keyboard.press('Escape'); await sleep(500); return 1;")
        u = pg.url
        if blog_id and blog_id not in u:
            return {"ok": False, "message": f"다른 계정으로 열립니다: {u[:80]} — 어사이드에서 내 블로그 계정으로 로그인해 주세요.",
                    "notes": notes}
        before = _save_count(s)

        # ── 2) 제목 ──
        _click(s, ".se-section-documentTitle .se-text-paragraph")
        s(f"await __edi.keyboard.insertText({J(title)}); await sleep(300); return 1;")
        got = _title_text(s)
        if title[:8] not in got:
            return {"ok": False, "message": f"제목이 안 들어갔습니다(지금 제목 칸: {got[:30]!r}) — 어사이드 창을 가리지 말고 다시 해 주세요.",
                    "notes": notes}
        s("await __edi.keyboard.press('Enter'); await sleep(500); return 1;")
        log("제목 입력: " + title[:40])
        if align == "center":
            try:
                s("await __edi.keyboard.press('Control+Shift+E'); return 1;")
            except RuntimeError:
                pass

        # ── 3) 본문 블록 ──
        for b in blocks:
            t = b.get("type")
            txt = b.get("text", "") or ""
            try:
                if t in ("blank", "hashtags"):
                    continue
                if t in ("text", "marker", "photo"):
                    s(f"await __edi.keyboard.insertText({J(txt)}); await __edi.keyboard.press('Enter');"
                      "await __edi.keyboard.press('Enter'); return 1;")
                elif t == "subhead":
                    on = _click(s, "button.se-bold-toolbar-button", wait=0.2)
                    s(f"await __edi.keyboard.insertText({J(txt)}); return 1;")
                    if on:
                        _click(s, "button.se-bold-toolbar-button", wait=0.2)
                    s("await __edi.keyboard.press('Enter'); return 1;")
                elif t == "image":
                    p = b.get("path") or ""
                    if not (p and os.path.exists(p)):
                        notes.append("이미지 파일 없음")
                        continue
                    data = base64.b64encode(open(p, "rb").read()).decode()
                    mime = mimetypes.guess_type(p)[0] or "image/jpeg"
                    pt = _pt(s, "button.se-image-toolbar-button")
                    if not pt:
                        notes.append("사진 버튼 없음")
                        continue
                    n = s("const __fcp = __edi.waitForEvent('filechooser', {timeout: 15000});"
                          f"await __edi.mouse.click({pt['x']}, {pt['y']});"
                          "const __fc = await __fcp;"
                          f"await __fc.setFiles({{name: {J(os.path.basename(p))}, mimeType: {J(mime)}, buffer: Buffer.from({J(data)}, 'base64')}});"
                          "await sleep(4000);"
                          f"return await __edi.evaluate(() => {{ {_DOC} return d.querySelectorAll('.se-component.se-image').length; }});",
                          timeout=90)
                    images = int(n or images)
                    _exit_block(s)
                elif t == "quote":
                    if not _click(s, "button.se-insert-quotation-default-toolbar-button", wait=0.7):
                        s(f"await __edi.keyboard.insertText({J(txt)}); await __edi.keyboard.press('Enter'); return 1;")
                        notes.append("인용구 버튼 없음 → 글자로")
                        continue
                    for i, line in enumerate(str(txt).split("\n")):
                        if i:
                            s("await __edi.keyboard.press('Shift+Enter'); return 1;")
                        s(f"await __edi.keyboard.insertText({J(line)}); return 1;")
                    _exit_block(s)
                elif t == "oglink":
                    s(f"await __edi.keyboard.insertText({J(b.get('url') or txt)}); await __edi.keyboard.press('Enter'); return 1;")
                    notes.append("링크 카드 대신 주소 글자로 넣음")
                else:
                    notes.append(f"건너뜀: {t}")
            except RuntimeError as e:
                notes.append(f"{t} 실패: {str(e)[:80]}")
        log(f"본문 완료 · 사진 {images}장")

        # ── 4) AI 활용 표기(사진이 있으면) ──
        if ai_mark and images:
            try:
                if _click(s, ".se-component.se-image .se-image-resource", wait=0.7) and \
                        _click(s, "button, a, span, div[role=button]", "전체AI활용", wait=0.6):
                    log("AI 활용 표기: 전체AI활용")
                else:
                    notes.append("AI 활용 표기 버튼 없음")
                _exit_block(s)
            except RuntimeError:
                notes.append("AI 활용 표기 실패")

        # ── 5) 카테고리·태그 (발행 패널을 열었다가 발행하지 않고 닫는다) ──
        tags = [w[1:] for w in next((b.get("text", "") for b in blocks if b.get("type") == "hashtags"), "").split()
                if w.startswith("#")]
        if category or tags:
            try:
                if _click(s, 'button[class*="publish_btn"]', wait=2.0):
                    if category:
                        if _click(s, 'button[aria-label="카테고리 목록 버튼"], button[class*="selectbox_button"]', wait=0.9) and \
                                _click(s, "label, span, a, li", category, nth=-1, wait=0.6):
                            log("카테고리: " + category)
                        else:
                            notes.append(f"카테고리 선택 실패(기본 칸): {category}")
                    if tags and _click(s, 'input[class*="tag_input"]', wait=0.3):
                        for tg in tags:
                            s(f"await __edi.keyboard.insertText({J(tg)}); await __edi.keyboard.press('Enter'); await sleep(180); return 1;")
                        log(f"태그 {len(tags)}개")
                    s("await __edi.keyboard.press('Escape'); await sleep(800); return 1;")
                else:
                    notes.append("발행 패널을 못 열어 카테고리·태그 건너뜀")
            except RuntimeError as e:
                notes.append(f"카테고리·태그 건너뜀: {str(e)[:60]}")

        # ── 6) 임시저장 — 「발행」이 아니라 「저장」만 누른다 ──
        if not _click(s, 'button[class*="save_btn"]', "저장", wait=4.0):
            return {"ok": False, "message": "저장 버튼을 못 찾았습니다", "notes": notes}
        after = _save_count(s)
        if before >= 0 and after >= 0 and after <= before:
            notes.append(f"임시저장 수가 그대로입니다({before}→{after}) — 같은 글을 덮어썼을 수 있습니다. 저장 목록을 확인하세요")
        log(f"임시저장 완료 (임시저장 글 {before}→{after})")
        return {"ok": True, "message": f"어사이드 임시저장 완료 · 사진 {images}장", "notes": notes}
    except RuntimeError as e:
        return {"ok": False, "message": "어사이드 실패: " + str(e)[:300], "notes": notes}
    finally:
        # 글이 든 탭은 «나가시겠습니까» 때문에 안 닫힌다 → 빈 페이지로 바꾸고 닫는다(goto는 30초 기다려서 안 쓴다)
        try:
            s("await __edi.evaluate(() => location.replace('about:blank')); await sleep(1500); return 1;", timeout=30)
        except Exception:  # noqa: BLE001
            pass
        pg.close()


def _exit_block(s):
    """인용구·사진 밖으로 빠져나온다 — 마지막 컴포넌트 아래 30px을 누른다(ego/publish.mjs exitBlock과 같은 방법)."""
    try:
        pt = s(f"return await __edi.evaluate(() => {{ {_DOC}"
               "const c = d.querySelectorAll('.se-component'); if (!c.length) return null; const last = c[c.length - 1];"
               "last.scrollIntoView({block: 'center'}); const r = last.getBoundingClientRect(); const fr = f.getBoundingClientRect();"
               "return {x: fr.left + r.left + r.width / 2, y: fr.top + r.bottom + 30}; });")
        if pt:
            time.sleep(0.25)
            s(f"await __edi.mouse.click({pt['x']}, {pt['y']}); await sleep(350); return 1;")
            return True
    except RuntimeError:
        pass
    try:
        s("await __edi.keyboard.press('ArrowDown'); await __edi.keyboard.press('Enter'); return 1;")
    except RuntimeError:
        pass
    return False
