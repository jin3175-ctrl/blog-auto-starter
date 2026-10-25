"""이웃관리가 쓰는 브라우저 (2026-10-24 · 3기 3주차부터).

  맥     → **에고라이트(ego lite)** — `ego-browser nodejs` 로 작업 공간 「이웃관리」의 탭 하나를 움직인다.
  윈도우 → **어사이드(Aside)**     — `aside repl` 을 하나 띄워 두고 거기에 명령을 이어 보낸다.
  (예전 크롬 방식은 `내정보.txt`의 「브라우저: 크롬」으로만 쓴다 — 블로그자동/session 이 있어야 한다.)

왜 이렇게 하나: 10/17부터 네이버 로그인은 크롬이 아니라 에고라이트·어사이드에 **본인이 직접** 한다.
그래서 예전 run.py(크롬 + session 파일)는 새로 받은 분 컴퓨터에서 「세션 없음」으로 멈췄다.
그리고 윈도우에서 어사이드 자체 AI(Ask 칸)에 프롬프트를 붙여넣는 방식은 「안 된다」고 막혔다(2·3기).
→ 어사이드 CLI(`aside`)를 깔면 **프로그램이 어사이드 창을 직접** 열고 칸을 채운다. AI에게 부탁하지 않는다.

🔴어느 브라우저든 **등록·확인 버튼은 누르지 않는다.** 칸을 채우고, 사람이 눌렀는지 «보고만» 있는다.

실측(2026-10-24 에디 맥 · Aside 1.0.1022 · CLI 1.26.1023):
  · `aside repl "코드"` 한 번짜리로 연 탭(openTab)은 **명령이 끝나면 닫힌다.**
    → 사람이 [등록]을 누를 시간이 없다. 그래서 `aside repl` 을 **하나 띄워 두고** 줄마다 명령을 보낸다.
  · 그 안에서 연 탭은 어사이드 창에 그대로 보이고, 댓글 칸(contenteditable DIV)에 `keyboard.type`이 먹는다.
  · `window.open`으로 새 탭은 안 열린다(막힘). `page.context()`도 없다.
  · 에고라이트는 같은 이름의 작업 공간을 부르면 탭이 그대로 남아 있다(호출 한 번 0.2초).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SPACE_NAME = "이웃관리"


def mode() -> str:
    """'chrome'(기본) | 'ego' | 'aside' — 환경변수 EDI_NEIGHBOR_BROWSER > 내정보.txt 「이웃관리 브라우저:」 줄 > 크롬.

    🔴2026-10-25 에디님: 「댓글, 서이추는 크롬으로 반자동으로 진행」 — 2기 4주차에 돌던 방식으로 되돌린다.
      (글 임시저장은 그대로 맥=에고라이트 · 윈도우=어사이드. 그건 블로그자동/browser_upload.py 가 정한다)
      에고라이트·어사이드 길(10/24)은 지우지 않고 「이웃관리 브라우저: 에고/어사이드」로 남겨 둔다."""
    v = (os.environ.get("EDI_NEIGHBOR_BROWSER") or "").strip().lower()
    if not v:
        for d in (os.path.dirname(HERE), HERE):
            try:
                m = re.search(r"^이웃관리\s*브라우저\s*[:：]\s*(\S+)",
                              open(os.path.join(d, "내정보.txt"), encoding="utf-8").read(), re.M)
            except OSError:
                continue
            v = (m.group(1) if m else "").lower()
            break
    if v in ("에고", "에고라이트", "ego", "egolite"):
        return "ego"
    if v in ("어사이드", "aside"):
        return "aside"
    return "chrome"


def _one_line(js: str) -> str:
    """REPL은 한 줄이 명령 하나다. 우리가 만든 짧은 명령만 합친다(페이지에 넣는 함수는 evaluate 가 따로 싼다)."""
    return " ".join(s.strip() for s in js.strip().splitlines() if s.strip())


# ── 어사이드 CLI 찾기 ─────────────────────────────────────────────

def aside_bin() -> str:
    cands = [shutil.which("aside"), os.path.expanduser("~/.local/bin/aside")]
    la = os.environ.get("LOCALAPPDATA")
    if la:   # 윈도우 설치 위치(설치 스크립트 기본값 %LOCALAPPDATA%\Aside\CLI) — 🔴윈도우 실기 미확인
        for name in ("aside.exe", "aside.cmd", "aside"):
            cands += [os.path.join(la, "Aside", "CLI", name), os.path.join(la, "Aside", "CLI", "bin", name)]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return ""


def ego_bin() -> str:
    for c in (shutil.which("ego-browser"), os.path.expanduser("~/.local/bin/ego-browser")):
        if c and os.path.exists(c):
            return c
    return ""


class _Keyboard:
    def __init__(self, page):
        self._p = page

    def type(self, text, delay=30):
        self._p._type(text, delay)


class AsidePage:
    """`aside repl` 하나를 띄워 두고 줄 단위로 명령을 보낸다. 탭은 어사이드 창에 그대로 보인다."""

    def __init__(self):
        b = aside_bin()
        if not b:
            raise RuntimeError(
                "어사이드 CLI(aside)가 없습니다 — 어사이드 앱 → 왼쪽 아래 프로필 → Settings → Developers → "
                "「Aside CLI」 Install. 설치 뒤에는 클로드 코드 창을 닫았다가 다시 여세요(새 창이라야 aside 를 찾습니다).")
        self._n = 0
        self._closed = False
        self._q: queue.Queue = queue.Queue()
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000   # CREATE_NO_WINDOW — 검은 창을 하나 더 띄우지 않는다
        self._proc = subprocess.Popen([b, "repl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                      errors="replace", bufsize=1, **kw)
        threading.Thread(target=self._pump, daemon=True).start()
        self.keyboard = _Keyboard(self)
        self._opened = False

    def _pump(self):
        for line in self._proc.stdout:
            self._q.put(line)
        self._q.put(None)

    def _send(self, js: str, timeout=110):
        """명령 한 줄을 보내고 `@@R{...}` 한 줄을 받는다. 실패하면 RuntimeError."""
        self._n += 1
        tag = f"@@R{self._n}@@"
        line = (f"try {{ const __v{self._n} = await (async () => {{ {_one_line(js)} }})(); "
                f"console.log({json.dumps(tag)} + JSON.stringify({{ok: true, v: __v{self._n} ?? null}})); }} "
                f"catch (e) {{ console.log({json.dumps(tag)} + JSON.stringify({{ok: false, e: String(e).slice(0, 300)}})); }}")
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError):
            self._closed = True
            raise RuntimeError("어사이드 REPL이 끝났습니다")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                out = self._q.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            if out is None:
                self._closed = True
                raise RuntimeError("어사이드 REPL이 끝났습니다 — 어사이드 앱이 켜져 있는지 보세요")
            i = out.find(tag)
            if i >= 0:
                r = json.loads(out[i + len(tag):].strip())
                if not r.get("ok"):
                    raise RuntimeError(r.get("e") or "어사이드 명령 실패")
                return r.get("v")
        raise RuntimeError("어사이드가 응답하지 않습니다(시간 초과)")

    def goto(self, url, wait_until=None, timeout=25000):
        if not self._opened:
            self._send(f"globalThis.__edi = await openTab({json.dumps(url)}); return __edi.url();")
            self._opened = True
        else:
            self._send(f"await __edi.goto({json.dumps(url)}); return __edi.url();")

    @property
    def url(self):
        try:
            return self._send("return __edi.url();", timeout=20) or ""
        except RuntimeError:
            return ""

    def evaluate(self, fn: str, arg=None):
        a = "" if arg is None else ", " + json.dumps(arg, ensure_ascii=False)
        # 함수 원문은 JSON 문자열로 보내 new Function 으로 되살린다 — 줄바꿈·// 주석이 있어도 한 줄 명령이 된다.
        return self._send(f"return await __edi.evaluate(new Function('return ' + {json.dumps(fn, ensure_ascii=False)})(){a});")

    def _type(self, text, delay):
        self._send(f"await __edi.keyboard.type({json.dumps(text, ensure_ascii=False)}, {{delay: {int(delay)}}}); return 1;",
                   timeout=110)

    def wait_for_timeout(self, ms):
        time.sleep(ms / 1000)

    def is_closed(self):
        if self._closed or self._proc.poll() is not None:
            return True
        if not self._opened:
            return False
        try:
            return bool(self._send("return (typeof __edi.isClosed === 'function') ? __edi.isClosed() : false;", timeout=20))
        except RuntimeError:
            return True

    def close(self):
        """우리가 연 탭만 닫고 REPL을 끝낸다. 사람이 쓰던 다른 탭은 건드리지 않는다."""
        try:
            if self._opened and not self._closed:
                # 글자가 든 탭은 «나가시겠습니까» 때문에 안 닫힌다(10/25 실측) → 창을 수락하고 비운 뒤 닫는다
                self._send("__edi.on('dialog', d => d.accept().catch(() => {}));"
                           "await __edi.evaluate(() => location.replace('about:blank')).catch(() => {});"
                           "await sleep(1200); await closeTab(__edi); return 1;", timeout=30)
        except RuntimeError:
            pass
        try:
            self._proc.stdin.write("exit\n")
            self._proc.stdin.flush()
            self._proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self._proc.kill()


class EgoPage:
    """에고라이트 작업 공간 「이웃관리」의 탭 p1. 호출마다 `ego-browser nodejs` 를 한 번 부른다(0.2초 안팎)."""

    def __init__(self):
        self._b = ego_bin()
        if not self._b:
            raise RuntimeError("에고라이트가 없습니다 — https://lite.ego.app 에서 설치하고 앱을 한 번 열어 주세요.")
        self._closed = False
        self.keyboard = _Keyboard(self)

    def _run(self, body: str, timeout=120):
        tag = "@@R@@"
        src = (f'const __t = await taskSpace({json.dumps(SPACE_NAME)});\n'
               f'const __p = __t.page("p1");\n'
               f'try {{ const __v = await (async () => {{\n{body}\n}})();\n'
               f'  console.log({json.dumps(tag)} + JSON.stringify({{ok: true, v: __v ?? null}})); }}\n'
               f'catch (e) {{ console.log({json.dumps(tag)} + JSON.stringify({{ok: false, e: String(e).slice(0, 300)}})); }}\n')
        p = subprocess.run([self._b, "nodejs"], input=src, text=True, capture_output=True, timeout=timeout)
        # 결과 줄이 stderr 쪽에 섞여 나올 때가 있다(업데이트 안내와 같이 — 10/24 실측). 둘 다 본다.
        for line in ((p.stdout or "") + "\n" + (p.stderr or "")).splitlines():
            i = line.find(tag)
            if i >= 0:
                r = json.loads(line[i + len(tag):])
                if not r.get("ok"):
                    raise RuntimeError(r.get("e") or "에고라이트 명령 실패")
                return r.get("v")
        tail = ((p.stdout or "") + (p.stderr or "")).strip()[-200:]
        if "control" in tail:
            raise RuntimeError("에고라이트 창을 지금 직접 쓰고 계십니다 — 손을 떼고 다시 실행해 주세요.")
        raise RuntimeError("에고라이트 응답 없음: " + tail)

    def goto(self, url, wait_until=None, timeout=25000):
        self._run(f"await __p.goto({json.dumps(url)}); return 1;", timeout=max(60, timeout // 1000 + 30))

    @property
    def url(self):
        try:
            return self._run("return await __p.url();", timeout=30) or ""
        except RuntimeError:
            return ""

    def evaluate(self, fn: str, arg=None):
        a = "" if arg is None else ", " + json.dumps(arg, ensure_ascii=False)
        return self._run(f"return await __p.evaluate({fn}{a});")

    def _type(self, text, delay):
        # 에고라이트는 insertText가 검증된 길이다(블로그자동/ego/publish.mjs). 글자를 한 번에 넣는다.
        self._run(f"await __p.keyboard.insertText({json.dumps(text, ensure_ascii=False)}); return 1;")

    def wait_for_timeout(self, ms):
        time.sleep(ms / 1000)

    def is_closed(self):
        return self._closed

    def close(self):
        try:
            self._run("await __t.finish({ keep: [] }); return 1;", timeout=30)
        except Exception:  # noqa: BLE001 — 공간을 못 닫았다고 실패로 만들지 않는다
            pass
        self._closed = True


def open_page():
    """(page, 닫기함수, 안내문). 크롬 모드면 (None, None, '') — 호출측이 예전 Playwright 길로 간다."""
    m = mode()
    if m == "chrome":
        return None, None, ""
    try:
        pg = AsidePage() if m == "aside" else EgoPage()
    except RuntimeError as e:
        return None, None, str(e)
    return pg, pg.close, ""


def login_ok(page, blog_id: str) -> tuple:
    """내 블로그 글쓰기 화면이 열리면 로그인된 것. (ok, 안내문)"""
    name = "어사이드" if isinstance(page, AsidePage) else "에고라이트"
    try:
        page.goto("https://blog.naver.com/GoBlogWrite.naver")
        page.wait_for_timeout(2500)
        u = page.url
    except RuntimeError as e:
        return False, f"{name}를 움직이지 못했습니다: {str(e)[:160]}"
    if "nidlogin" in u:
        return False, f"{name}에서 네이버 로그인이 안 돼 있습니다 — {name}를 열고 본인이 직접 로그인해 주세요(로그인 상태 유지 켜기)."
    if blog_id and blog_id not in u:
        return False, f"{name}가 다른 블로그로 열립니다({u[:70]}) — 내 블로그 계정으로 로그인해 주세요."
    return True, ""


def main():
    """`python browser_drive.py` — 연결 점검. 로그 읽는 법 첫 줄이 여기다."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "블로그자동"))
    m = mode()
    print(f"브라우저: {m}  ({'맥' if sys.platform == 'darwin' else '윈도우' if os.name == 'nt' else sys.platform})")
    if m == "chrome":
        sess = [p for p in (os.path.join(os.path.dirname(HERE), "블로그자동", "session", "naver_state.json"),) if os.path.exists(p)]
        print("댓글·서이추는 크롬(반자동)으로 합니다. " + ("크롬 로그인 기록 ✓ 있음" if sess else
              "✗ 크롬 로그인 기록이 없습니다 — 「댓글용 네이버 로그인 시켜줘」(python 이웃관리/크롬_로그인.py)"))
        return 0 if sess else 1
    print("프로그램 위치:", (aside_bin() if m == "aside" else ego_bin()) or "없음")
    try:
        import myinfo
        bid = myinfo.blog_id() or ""
    except BaseException:  # noqa: BLE001 — 빈칸이면 myinfo가 SystemExit로 멈춘다
        bid = ""
    page, closer, why = open_page()
    if why:
        print("✗", why)
        return 1
    try:
        ok, why = login_ok(page, bid)
    finally:
        closer()
    if not ok:
        print("✗", why)
        return 1
    print(f"✓ 연결됨 — 네이버 로그인 확인({bid or '블로그ID 빈칸'}). 이제 run.py 를 돌려도 됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
