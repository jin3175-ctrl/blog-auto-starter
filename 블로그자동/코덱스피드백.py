"""오늘 쓴 글을 코덱스(유료 ChatGPT)에게 따로 피드백 받기 (2026-11-01 · 3기 4주차).

    python 코덱스피드백.py          # 가장 최근 원고 한 편

글을 다 쓴 뒤에 **따로** 돌린다. 글을 고치지는 않고 work/코덱스피드백_날짜.md 로 저장한다.
기준은 ../에디피드백.md. 코덱스가 없으면 없다고 말하고 끝난다 — 그때는 클로드에게 같은 파일로 피드백을 받는다.
결과: work/코덱스피드백.log 맨 아랫줄(✓ 받음 / ✗ 못 받음).
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOG = os.path.join(HERE, "work", "코덱스피드백.log")

if hasattr(sys.stdout, "reconfigure"):      # 🔴한글 윈도우 cp949 — ✓ 에서 죽지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str):
    line = f"[{datetime.now():%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_codex() -> str:
    """PATH → 챗GPT 앱 안 → npm. 🔴윈도우 경로는 실기 미확인."""
    found = shutil.which("codex")
    if found:
        return found
    la, ad = os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", "")
    res = "/Contents/Resources/"
    cands = [os.path.expanduser(a + "/ChatGPT.app" + res + r) for a in ("/Applications", "~/Applications")
             for r in ("codex-cli/bin/codex", "codex")]
    if os.name == "nt":
        cands = [os.path.join(la, "Programs", "ChatGPT", "resources", "codex-cli", "bin", "codex.exe"),
                 os.path.join(la, "Programs", "ChatGPT", "resources", "codex.exe"),
                 os.path.join(ad, "npm", "codex.cmd"), os.path.join(ad, "npm", "codex.exe")]
    return next((c for c in cands if c and os.path.exists(c)), "")


def latest_post() -> str:
    import config
    found = glob.glob(os.path.join(config.SOURCE_ROOT, "**", "*_복붙용.txt"), recursive=True)
    return max(found, key=os.path.getmtime) if found else ""


def main() -> int:
    post = latest_post()
    if not post:
        log("✗ 못 받음 — 원고가 없습니다. 글을 먼저 쓰세요")
        return 1
    codex = find_codex()
    if not codex:
        log("✗ 못 받음 — 코덱스가 없습니다(유료 ChatGPT와 코덱스 필요). 클로드에게 「에디피드백.md 읽고 오늘 쓴 글 피드백해줘」")
        return 1
    guide = open(os.path.join(os.path.dirname(HERE), "에디피드백.md"), encoding="utf-8").read()
    text = open(post, encoding="utf-8").read()
    prompt = guide + "\n\n자동 실행이다. 질문하지 말고 아래 글을 A. 블로그 글 전체로 보고 바로 피드백한다.\n\n===글===\n" + text
    out = os.path.join(HERE, "work", f"코덱스피드백_{datetime.now():%Y%m%d_%H%M}.md")
    args = ["exec", "-s", "read-only", "--skip-git-repo-check", "-C", HERE, "-o", out, "-"]
    cmd = (["cmd", "/c", codex] if codex.lower().endswith((".cmd", ".bat")) else [codex]) + args
    log(f"코덱스에게 보냅니다: {os.path.basename(post)}")
    try:
        r = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", errors="replace",
                           capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        log("✗ 못 받음 — 10분 안에 답이 없습니다")
        return 1
    if r.returncode or not os.path.exists(out) or os.path.getsize(out) < 200:
        log("✗ 못 받음 — " + ((r.stderr or r.stdout or "").strip()[-200:] or "빈 답") + " · 로그인이 풀렸으면 코덱스에 본인이 다시 로그인")
        return 1
    log(f"✓ 받음 — {os.path.relpath(out, os.path.dirname(HERE))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
