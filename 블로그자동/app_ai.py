"""에디 블로그 자동화 — AI 실전 블로그 반자동 대시보드 (ioiykd8599).

제이 스튜디오 스타일(다크 + 검수 대기 + 썸네일) + '경험 슬롯 편집' 기능.
- 소재뱅크에서 주제 골라 gen_ai로 초안 생성(실시간 로그)
- 초안 카드: 썸네일 미리보기 + [편집] + [발행]
- 편집: 제목 후보 중 선택 + 본문(경험 슬롯) 직접 수정 + 저장
- 발행: 기존 pipeline.process_post (임시저장/공개)

실행: python3 app_ai.py  → http://127.0.0.1:5005
"""
from __future__ import annotations

import os
import re
import threading

from flask import Flask, jsonify, render_template_string, send_file, request, abort

import config
import gen_ai
import pipeline
import posts as posts_mod

app = Flask(__name__)
BANK = os.path.expanduser("~/홈판자료/AI실전_소재뱅크30.md")

JOB = {"running": False, "kind": None, "logs": [], "result": None}
_lock = threading.Lock()


def _log(m):
    JOB["logs"].append(str(m))


def _folder() -> str:
    f = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    os.makedirs(f, exist_ok=True)
    return f


def _draft_path(folder: str, no: str) -> str | None:
    for fn in os.listdir(folder):
        if re.match(rf"^{no}_.*_복붙용\.txt$", fn):
            return os.path.join(folder, fn)
    return None


def _title_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(500)
        m = re.search(r"(?m)^\s*제목\s*[:：]\s*(.+)$", head)
        if m:
            return m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    return "(제목 없음)"


def _next_no(folder: str) -> str:
    used = set()
    for fn in os.listdir(folder):
        m = re.match(r"^(\d{2})_.*_복붙용\.txt$", fn)
        if m:
            used.add(int(m.group(1)))
    for n in range(21, 60):
        if n not in used:
            return str(n)
    return "59"


def _topics() -> list[str]:
    out = []
    try:
        with open(BANK, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*\d+\.\s+(.+)$", line.strip())
                if m:
                    out.append(m.group(1).strip())
    except Exception:  # noqa: BLE001
        pass
    return out


def _ai_nos(folder: str) -> set:
    nos = set()
    for fn in os.listdir(folder):
        m = re.match(r"^(\d{2})_.*_ai\.flag$", fn)
        if m:
            nos.add(m.group(1))
    return nos


def _drafts() -> list[dict]:
    folder = _folder()
    ai = _ai_nos(folder)
    out = []
    for p in sorted(posts_mod.list_posts(folder), key=lambda x: x["no"]):
        if p["no"] not in ai:      # AI 실전 초안만(옛 셀럽/강점 제외)
            continue
        body_path = p["body_path"]
        try:
            body = open(body_path, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            body = ""
        needs_exp = "[[경험" in body
        out.append({
            "no": p["no"],
            "title": _title_of(body_path),
            "has_thumb": bool(p.get("thumb_path")),
            "needs_exp": needs_exp,
        })
    return out


# ---------- 백그라운드 작업 ----------

def _run_generate(topic: str, no: str):
    try:
        gen_ai.generate(topic, _folder(), no=no, log=_log)
        JOB["result"] = {"ok": True, "no": no}
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
        JOB["result"] = {"ok": False, "message": str(e)}
    finally:
        JOB["running"] = False


def _run_publish(no: str, publish: bool):
    try:
        res = pipeline.process_post(no, _log, publish=publish, folder=_folder())
        JOB["result"] = res
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
        JOB["result"] = {"ok": False, "message": str(e)}
    finally:
        JOB["running"] = False


# ---------- 라우트 ----------

@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/api/state")
def api_state():
    return jsonify({"drafts": _drafts(), "topics": _topics(),
                    "job": {"running": JOB["running"], "kind": JOB["kind"],
                            "logs": JOB["logs"][-40:], "result": JOB["result"]}})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    topic = (request.json or {}).get("topic", "").strip()
    if not topic:
        return jsonify({"ok": False, "message": "주제를 고르세요."}), 400
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "다른 작업 실행 중"}), 409
        JOB.update(running=True, kind="generate", logs=[], result=None)
    no = _next_no(_folder())
    threading.Thread(target=_run_generate, args=(topic, no), daemon=True).start()
    return jsonify({"ok": True, "no": no})


@app.route("/api/draft/<no>")
def api_draft(no):
    folder = _folder()
    path = _draft_path(folder, no)
    if not path:
        abort(404)
    body = open(path, encoding="utf-8").read()
    # 제목 후보
    titles = []
    for fn in os.listdir(folder):
        if re.match(rf"^{no}_.*_제목후보\.txt$", fn):
            titles = [l.strip() for l in open(os.path.join(folder, fn), encoding="utf-8") if l.strip()]
            break
    return jsonify({"no": no, "body": body, "titles": titles,
                    "thumb_url": f"/thumb/{no}"})


@app.route("/api/draft/<no>", methods=["POST"])
def api_save(no):
    folder = _folder()
    path = _draft_path(folder, no)
    if not path:
        abort(404)
    data = request.json or {}
    body = data.get("body", "")
    title = data.get("title", "").strip()
    if title:  # 제목줄 교체
        lines = body.splitlines()
        for i, ln in enumerate(lines[:5]):
            if re.match(r"^\s*제목\s*[:：]", ln):
                lines[i] = f"제목: {title}"
                break
        else:
            lines.insert(0, f"제목: {title}")
        body = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return jsonify({"ok": True})


@app.route("/api/publish/<no>", methods=["POST"])
def api_publish(no):
    publish = (request.json or {}).get("publish", False)
    folder = _folder()
    path = _draft_path(folder, no)
    if not path:
        return jsonify({"ok": False, "message": "초안 없음"}), 404
    if "[[경험" in open(path, encoding="utf-8").read():
        return jsonify({"ok": False, "message": "경험 슬롯을 먼저 채워주세요."}), 400
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "다른 작업 실행 중"}), 409
        JOB.update(running=True, kind=f"publish-{no}", logs=[], result=None)
    threading.Thread(target=_run_publish, args=(no, bool(publish)), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/thumb/<no>")
def thumb(no):
    folder = _folder()
    path = posts_mod.find_assets(folder, no).get("썸네일")
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png")


PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>에디 블로그 자동화</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#262b35;--fg:#e8eaed;--mut:#8b93a1;--acc:#f5c451;--blue:#3d7bff;--grn:#22b96a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:22px}
h1{font-size:22px;margin:0 0 2px}.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
select,button,textarea,input{font:inherit}
select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:9px;padding:10px 12px;min-width:320px;max-width:60%}
button{border:0;border-radius:9px;padding:10px 15px;cursor:pointer;font-weight:600}
.b-gen{background:var(--acc);color:#1a1a1a}.b-blue{background:var(--blue);color:#fff}.b-grn{background:var(--grn);color:#fff}
.b-ghost{background:var(--card);color:var(--fg);border:1px solid var(--line)}
.sec{font-size:15px;font-weight:700;margin:22px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px;display:flex;gap:14px}
.card img{width:150px;height:150px;object-fit:cover;border-radius:8px;background:#222;flex:none}
.card .body{flex:1;min-width:0}
.card .t{font-weight:600;margin-bottom:6px;line-height:1.35}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;margin-right:6px}
.bad-exp{background:#5a3a1a;color:#ffcf87}.bad-ok{background:#1c4a30;color:#8ff0b8}
.log{background:#0a0c10;border:1px solid var(--line);border-radius:9px;padding:10px;font-size:12px;color:#9fb0c3;max-height:150px;overflow:auto;white-space:pre-wrap;display:none}
.edit{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:10px;display:none}
.edit textarea{width:100%;height:340px;background:#0a0c10;color:var(--fg);border:1px solid var(--line);border-radius:9px;padding:12px;line-height:1.6}
.edit .titles label{display:block;padding:6px 0;cursor:pointer}
.hint{color:var(--acc);font-size:12px;margin:6px 0}
.muted{color:var(--mut);font-size:12px}
</style></head><body><div class=wrap>
<h1>🌱 에디 블로그 자동화</h1><div class=sub>40대 가장의 AI 생존기 · AI 실전 반자동</div>

<div class=row>
  <select id=topic></select>
  <button class=b-gen onclick=gen()>▶ 초안 생성</button>
  <button class=b-ghost onclick=load()>새로고침</button>
</div>
<div class=log id=log></div>

<div class=sec>📝 검수 대기 — 경험 채우고 발행</div>
<div id=drafts></div>

<div class=edit id=edit>
  <div class=sec style="margin-top:0">✏️ 편집 <span class=muted id=eno></span></div>
  <div class=hint>제목 후보에서 하나 고르고, 본문의 <b>[[경험: ...]]</b> 부분을 실제 경험으로 바꾸세요.</div>
  <div class=titles id=titles></div>
  <textarea id=ebody></textarea>
  <div class=row style="margin-top:10px">
    <button class=b-blue onclick=save()>💾 저장</button>
    <button class=b-ghost onclick=pub(false)>임시저장 발행</button>
    <button class=b-grn onclick=pub(true)>공개 발행</button>
    <button class=b-ghost onclick="document.getElementById('edit').style.display='none'">닫기</button>
    <span class=muted id=esave></span>
  </div>
</div>
</div>
<script>
let cur=null;
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function load(){
  const s=await j('/api/state');
  // 주제 셀렉트
  const sel=document.getElementById('topic');
  if(!sel.dataset.filled){sel.innerHTML=s.topics.map(t=>`<option>${t}</option>`).join('');sel.dataset.filled=1}
  // 로그
  const log=document.getElementById('log');
  if(s.job.running||(s.job.logs&&s.job.logs.length)){log.style.display='block';log.textContent=(s.job.logs||[]).join('\\n');log.scrollTop=log.scrollHeight}
  // 초안 카드
  document.getElementById('drafts').innerHTML = s.drafts.length? s.drafts.map(d=>`
    <div class=card>
      <img src="/thumb/${d.no}?t=${Date.now()}" onerror="this.style.opacity=.2">
      <div class=body>
        <div class=t>${d.title}</div>
        <div>${d.needs_exp?'<span class="badge bad-exp">경험 채우기 필요</span>':'<span class="badge bad-ok">발행 준비됨</span>'}<span class=muted>#${d.no}</span></div>
        <div class=row style="margin-top:10px">
          <button class=b-blue onclick="edit('${d.no}')">✏️ 편집</button>
          <button class=b-ghost onclick="quickpub('${d.no}')">발행</button>
        </div>
      </div></div>`).join('') : '<div class=muted>아직 초안이 없어요. 위에서 주제 골라 [초안 생성].</div>';
  if(s.job.running) setTimeout(load,1500);
}
async function gen(){
  const topic=document.getElementById('topic').value;
  document.getElementById('log').style.display='block';
  document.getElementById('log').textContent='생성 시작…';
  await j('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic})});
  setTimeout(load,1200);
}
async function edit(no){
  const d=await j('/api/draft/'+no);cur=no;
  document.getElementById('eno').textContent='#'+no;
  document.getElementById('titles').innerHTML=(d.titles||[]).map((t,i)=>`<label><input type=radio name=tt value="${t.replace(/"/g,'&quot;')}" ${i==0?'checked':''}> ${t}</label>`).join('')||'<span class=muted>제목 후보 없음</span>';
  document.getElementById('ebody').value=d.body;
  document.getElementById('edit').style.display='block';
  document.getElementById('esave').textContent='';
  document.getElementById('edit').scrollIntoView({behavior:'smooth'});
}
function chosenTitle(){const r=document.querySelector('input[name=tt]:checked');return r?r.value:''}
async function save(){
  const r=await j('/api/draft/'+cur,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:document.getElementById('ebody').value,title:chosenTitle()})});
  document.getElementById('esave').textContent=r.ok?'저장됨 ✓':'저장 실패';load();
}
async function pub(open){
  await save();
  if(document.getElementById('ebody').value.includes('[[경험')){document.getElementById('esave').textContent='⚠ 경험 슬롯을 먼저 채우세요';return}
  if(open&&!confirm('공개 발행할까요? (되돌리기 어려움)'))return;
  const r=await j('/api/publish/'+cur,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({publish:open})});
  document.getElementById('esave').textContent=r.ok?'발행 시작… (창 뜨면 지켜보세요)':(r.message||'실패');
  document.getElementById('log').style.display='block';setTimeout(load,1500);
}
async function quickpub(no){await edit(no)}
load();
</script></body></html>"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False, use_reloader=False)
