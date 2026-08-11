"""네이버 블로그 자동 생성·발행 대시보드 (Flask).

- 네이버 로그인(세션 저장)
- [오늘 10편 생성] 버튼 → 백그라운드로 인사이트1·연예8·쇼핑1 생성(gen_{날짜} 폴더)
- 실시간 로그 스트리밍(폴링)
- 편별 제목·썸네일 미리보기 + [임시저장]/[공개발행] 버튼
"""
from __future__ import annotations

import os
import re
import threading

from flask import Flask, jsonify, render_template, send_file, abort, request

import config
import naver
import pipeline
import posts as posts_mod

app = Flask(__name__)

JOB = {"running": False, "kind": None, "logs": [], "result": None}
_lock = threading.Lock()


def _log(msg: str) -> None:
    JOB["logs"].append(str(msg))


def _reset_job(kind: str) -> None:
    JOB["running"] = True
    JOB["kind"] = kind
    JOB["logs"] = []
    JOB["result"] = None


def _active_folder() -> str | None:
    """오늘 생성 폴더(gen_{날짜})가 있으면 우선, 없으면 최신 날짜 폴더."""
    gen = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    if os.path.isdir(gen):
        return gen
    return config.resolve_date_folder()


def _post_title(body_path: str, keyword: str) -> str:
    try:
        with open(body_path, encoding="utf-8") as f:
            head = f.read(600)
        m = re.search(r"(?m)^\s*제목\s*[:：]\s*(.+)$", head)
        if m:
            return m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    # 제목줄이 없으면(주로 인사이트) 친절한 폴백
    kw = keyword.replace("_강점인사이트", "").replace("_쇼핑커넥트", "").replace("_", " ").strip()
    return f"{kw} · 발행 시 제목 생성"


# --- 백그라운드 작업 ---------------------------------------------------------

def _run_login():
    try:
        JOB["result"] = naver.login_and_save(_log)
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
        JOB["result"] = {"ok": False, "message": str(e)}
    finally:
        JOB["running"] = False


def _run_generate():
    try:
        import run_daily
        _log("오늘 10편 생성 시작(인사이트1·연예8·쇼핑1). 몇 분 걸립니다…")
        folder = run_daily.generate_all(config.today_str(), _log)
        _log("생성 완료.")
        JOB["result"] = {"ok": True, "message": "생성 완료", "folder": folder}
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
        JOB["result"] = {"ok": False, "message": str(e)}
    finally:
        JOB["running"] = False


def _run_process(no: str, publish: bool):
    try:
        JOB["result"] = pipeline.process_post(no, _log, publish=publish, folder=_active_folder())
    except Exception as e:  # noqa: BLE001
        _log(f"오류: {e}")
        JOB["result"] = {"ok": False, "message": str(e)}
    finally:
        JOB["running"] = False


# --- 라우트 -----------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    folder = _active_folder()
    date_str = os.path.basename(folder) if folder else None
    post_list = []
    if folder:
        for p in posts_mod.list_posts(folder):
            cat = posts_mod.category(p["body_path"])
            post_list.append({
                "no": p["no"],
                "keyword": p["keyword"],
                "type": {"insight": "강점인사이트", "shopping": "쇼핑커넥트", "celeb": "연예강점"}[cat],
                "cat": cat,
                "title": _post_title(p["body_path"], p["keyword"]),
                "has_thumb": bool(p["thumb_path"]),
            })
    meta = naver.load_meta()
    return jsonify({
        "logged_in": naver.is_logged_in(),
        "blog_id": meta.get("blog_id"),
        "date": date_str,
        "posts": post_list,
        "job": {"running": JOB["running"], "kind": JOB["kind"],
                "logs": JOB["logs"], "result": JOB["result"]},
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "다른 작업이 실행 중입니다."}), 409
        _reset_job("login")
    threading.Thread(target=_run_login, daemon=True).start()
    return jsonify({"ok": True, "message": "로그인 창을 띄웁니다."})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "다른 작업이 실행 중입니다."}), 409
        _reset_job("generate")
    threading.Thread(target=_run_generate, daemon=True).start()
    return jsonify({"ok": True, "message": "생성을 시작합니다."})


@app.route("/api/process/<no>", methods=["POST"])
def api_process(no: str):
    publish = request.args.get("publish") == "1"
    with _lock:
        if JOB["running"]:
            return jsonify({"ok": False, "message": "다른 작업이 실행 중입니다."}), 409
        if not naver.is_logged_in():
            return jsonify({"ok": False, "message": "먼저 네이버 로그인을 해주세요."}), 400
        _reset_job(f"process-{no}")
    threading.Thread(target=_run_process, args=(no, publish), daemon=True).start()
    action = "공개발행" if publish else "임시저장"
    return jsonify({"ok": True, "message": f"{no}편 {action}을 시작합니다."})


@app.route("/thumb/<no>")
def thumb(no: str):
    folder = _active_folder()
    if not folder:
        abort(404)
    path = posts_mod.find_assets(folder, no).get("썸네일")
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
