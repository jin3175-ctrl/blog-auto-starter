# -*- coding: utf-8 -*-
"""블로그 자동화 대시보드 — 버튼만 누르면 됩니다.

🔴이 화면의 버튼은 **초안을 화면에 채워주는 데까지만** 합니다.
   [등록]·[확인]은 반드시 본인이 누르세요. 자동으로 누르면 네이버가 잡습니다.
   글이 아니라 **계정이 저품질**로 갑니다. 블로그 하나 키우는 데 몇 달이 걸립니다.

⚠️추가 설치가 필요 없게 파이썬 표준 라이브러리(http.server)만 씁니다.
"""
import json, os, subprocess, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "블로그자동"))
NEIGH = os.path.join(BASE, "이웃관리")
WORK = os.path.join(BASE, "work"); os.makedirs(WORK, exist_ok=True)
PORT = 4322                      # ⚠️에디님 경영판(4321)과 겹치지 않게

try:
    import myinfo
    BLOG = myinfo.get("내 블로그ID") or ""
    TOPIC = myinfo.get("내 블로그 주제") or ""
except Exception:
    BLOG, TOPIC = "", ""

PY_EXE = sys.executable or "python3"


def log_path(kind):
    return os.path.join(WORK, f"대시보드_{kind}.log")


def spawn(kind, cmds):
    """여러 단계를 순서대로 돌린다. 오래 걸리므로 백그라운드로 띄우고 로그로 본다."""
    def work():
        with open(log_path(kind), "w", encoding="utf-8") as f:
            for c in cmds:
                f.write(f"\n$ {' '.join(c)}\n"); f.flush()
                try:
                    p = subprocess.Popen(c, cwd=NEIGH, stdout=f, stderr=subprocess.STDOUT)
                    if p.wait() != 0:
                        f.write(f"\n[멈춤] 이 단계에서 오류가 났습니다.\n"); break
                except Exception as e:
                    f.write(f"\n[오류] {e}\n"); break
            f.write("\n[끝] 브라우저 화면을 확인하세요.\n")
    threading.Thread(target=work, daemon=True).start()


PAGE = """<!doctype html><meta charset="utf-8">
<title>블로그 자동화 대시보드</title>
<style>
 body{font-family:-apple-system,"Malgun Gothic",sans-serif;max-width:760px;margin:32px auto;padding:0 18px;
      color:#1a1f27;background:#fafbfc;line-height:1.6}
 h1{font-size:22px;margin:0 0 6px} .sub{color:#5c6b7a;font-size:14px;margin-bottom:22px}
 .warn{background:#fff8e1;border:1px solid #ffe08a;border-radius:10px;padding:14px 16px;font-size:14px;margin-bottom:22px}
 .card{background:#fff;border:1px solid #e3e8ee;border-radius:12px;padding:18px;margin-bottom:16px}
 .h3{font-weight:700;margin:0 0 10px;font-size:16px}
 .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
 input[type=number]{width:64px;padding:8px;border:1px solid #cfd6de;border-radius:8px;font-size:15px;text-align:center}
 button{padding:9px 15px;border-radius:8px;border:1px solid #cfd6de;background:#fff;cursor:pointer;font-size:14px}
 button.go{background:#1a1f27;color:#fff;border-color:#1a1f27;font-weight:600}
 .rule{color:#5c6b7a;font-size:13px;margin-top:10px}
 pre{background:#0f1720;color:#d7e3ee;padding:14px;border-radius:10px;font-size:12.5px;
     max-height:340px;overflow:auto;white-space:pre-wrap}
 .bad{background:#ffecec;border:1px solid #ffb3b3;border-radius:10px;padding:14px;font-size:14px}
</style>
<h1>블로그 자동화 대시보드</h1>
<div class="sub">내 블로그 <b>__BLOG__</b> __TOPIC__</div>
__NOINFO__
<div class="warn">
 <b>이 버튼은 초안을 화면에 채워주는 데까지만 합니다.</b> [등록]·[확인]은 직접 누르세요.<br>
 자동으로 누르면 네이버가 잡습니다 — 글이 아니라 <b>계정이 저품질</b>로 갑니다.
</div>

<div class="card">
 <div class="h3">💬 댓글 · 서로이웃</div>
 <div class="rule">① 내 주제로 블로그 찾기 → ② 댓글 초안 만들기 → ③ 화면에 채워주기</div>
 <div class="row">
  <input type="number" id="n1" min="1" max="10" value="2">
  <button class="go" onclick="run('comment')">개 준비해서 시작</button>
  <button onclick="showLog('comment')">진행 로그</button>
 </div>
 <div class="rule">①②는 네이버에 아무것도 쓰지 않습니다. 브라우저가 열리면 확인하고 [등록]을 누르세요.</div>
</div>

<div class="card">
 <div class="h3">↩️ 내 글 댓글에 답글</div>
 <div class="row">
  <input type="number" id="n2" min="1" max="20" value="10">
  <button class="go" onclick="run('reply')">건까지 지금 돌리기</button>
  <button onclick="showLog('reply')">진행 로그</button>
 </div>
 <div class="rule">내 블로그에 온 댓글에 답하는 것이라 위험이 낮습니다. 그래도 마지막 확인은 직접 하세요.</div>
</div>

<pre id="out">버튼을 누르면 여기에 진행 상황이 나옵니다.</pre>
<script>
async function run(kind){
  const n = document.getElementById(kind==='comment'?'n1':'n2').value;
  document.getElementById('out').textContent = '시작했습니다. 잠시 뒤 [진행 로그]를 눌러보세요…';
  await fetch('/run?kind='+kind+'&n='+n);
  setTimeout(()=>showLog(kind), 3000);
}
async function showLog(kind){
  const r = await fetch('/log?kind='+kind);
  document.getElementById('out').textContent = await r.text();
}
setInterval(()=>{ const o=document.getElementById('out').textContent;
  if(o.includes('$ ') && !o.includes('[끝]')) showLog(window._last||'comment'); }, 4000);
</script>
"""


class H(BaseHTTPRequestHandler):
    def _send(self, body, ctype="text/plain; charset=utf-8"):
        b = body.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/":
            noinfo = "" if BLOG else ('<div class="bad">🔴 <b>내정보.txt 의 「내 블로그ID」가 비어 있습니다.</b> '
                                      '메모장으로 열어 채운 뒤 이 창을 새로고침하세요.</div>')
            self._send(PAGE.replace("__BLOG__", BLOG or "(비어 있음)")
                           .replace("__TOPIC__", f"· {TOPIC}" if TOPIC else "")
                           .replace("__NOINFO__", noinfo), "text/html; charset=utf-8")
        elif u.path == "/run":
            kind = q.get("kind", [""])[0]; n = q.get("n", ["2"])[0]
            if not BLOG:
                self._send("내정보.txt 의 내 블로그ID를 먼저 채워주세요."); return
            if kind == "comment":
                spawn("comment", [[PY_EXE, "collect.py"],
                                  [PY_EXE, "draft.py", "--limit", n],
                                  [PY_EXE, "run.py", "--limit", n]])
            elif kind == "reply":
                spawn("reply", [[PY_EXE, "reply.py", "--posts", "15", "--limit", n]])
            self._send("시작했습니다")
        elif u.path == "/log":
            p = log_path(q.get("kind", ["comment"])[0])
            self._send(open(p, encoding="utf-8").read() if os.path.exists(p) else "아직 기록이 없습니다.")
        else:
            self._send("not found")

    def log_message(self, *a):     # 콘솔을 조용하게
        pass


if __name__ == "__main__":
    print(f"\n  대시보드가 열립니다 →  http://127.0.0.1:{PORT}")
    print("  이 창은 닫지 마세요. 끝내려면 Ctrl+C 를 누르세요.\n")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        HTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except KeyboardInterrupt:
        print("\n  대시보드를 닫았습니다.")
