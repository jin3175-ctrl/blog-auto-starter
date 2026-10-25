"""매일 아침 「오늘글_자동.py」 예약 걸기·끄기 (2026-10-25 · 3기 3주차).

    python 매일예약.py 켜기 07:00     # 매일 07:00에 한 편 → 임시저장
    python 매일예약.py 끄기
    python 매일예약.py 상태

맥 = launchd(~/Library/LaunchAgents/com.homepan.todaypost.plist) · 윈도우 = 작업 스케줄러(「블로그 오늘글」)
🔴노트북이 켜져 있어야 돈다. 뚜껑을 닫으면 잠들어서 안 돈다. 맥은 caffeinate로 도는 동안만 깨워 둔다.
🔴맥은 에고라이트, 윈도우는 어사이드 앱이 **켜져 있어야** 임시저장까지 간다(꺼져 있으면 원고만 남고 로그에 이유가 적힌다).
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "오늘글_자동.py")
LABEL = "com.homepan.todaypost"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
TASK = "블로그 오늘글"


def _hm(s: str) -> tuple:
    m = re.match(r"^(\d{1,2}):(\d{2})$", s or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise SystemExit("시각은 07:00 처럼 적어 주세요.")
    return int(m.group(1)), int(m.group(2))


def on(t: str) -> int:
    h, m = _hm(t)
    if sys.platform == "darwin":
        plist = {
            "Label": LABEL,
            "ProgramArguments": ["/usr/bin/caffeinate", "-i", sys.executable, SCRIPT],
            "WorkingDirectory": HERE,
            "StartCalendarInterval": {"Hour": h, "Minute": m},
            "StandardOutPath": os.path.join(HERE, "work", "오늘글_예약_출력.log"),
            "StandardErrorPath": os.path.join(HERE, "work", "오늘글_예약_출력.log"),
        }
        os.makedirs(os.path.dirname(PLIST), exist_ok=True)
        os.makedirs(os.path.join(HERE, "work"), exist_ok=True)
        uid = os.getuid()
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
        with open(PLIST, "wb") as f:
            plistlib.dump(plist, f)
        r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", PLIST], capture_output=True, text=True)
        if r.returncode != 0:
            print("예약을 못 걸었습니다:", (r.stderr or r.stdout).strip()[:200])
            return 1
    elif os.name == "nt":
        # 🔴윈도우 실기 미확인(2026-10-25). 작업 스케줄러 — 로그인한 동안 매일 그 시각에 돈다
        tr = f'"{sys.executable}" "{SCRIPT}"'
        r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TASK, "/TR", tr,
                            "/ST", f"{h:02d}:{m:02d}"], capture_output=True, text=True)
        if r.returncode != 0:
            print("예약을 못 걸었습니다:", (r.stderr or r.stdout).strip()[:200])
            return 1
    else:
        print("맥·윈도우만 됩니다.")
        return 1
    print(f"✓ 매일 {h:02d}:{m:02d}에 글 한 편을 써서 임시저장합니다.")
    print("  · 노트북을 켜 두세요(뚜껑 닫으면 안 돕니다)")
    print("  · " + ("에고라이트" if sys.platform == "darwin" else "어사이드") + "를 켜 두세요")
    print("  · 결과는 블로그자동/work/오늘글_자동.log — 아침에 네이버 「저장」 목록에서 열어 고친 뒤 직접 발행")
    return 0


def off() -> int:
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
        if os.path.exists(PLIST):
            os.remove(PLIST)
    elif os.name == "nt":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True)
    print("✓ 매일 예약을 껐습니다.")
    return 0


def status() -> int:
    if sys.platform == "darwin":
        if not os.path.exists(PLIST):
            print("예약 없음")
            return 0
        c = plistlib.load(open(PLIST, "rb"))["StartCalendarInterval"]
        r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True)
        print(f"예약: 매일 {c['Hour']:02d}:{c['Minute']:02d} · " + ("등록됨" if r.returncode == 0 else "파일은 있는데 등록 안 됨 — 「켜기」 다시"))
    elif os.name == "nt":
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True, text=True)
        print(r.stdout.strip() if r.returncode == 0 else "예약 없음")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "상태"
    if cmd in ("켜기", "on"):
        sys.exit(on(a[1] if len(a) > 1 else "07:00"))
    if cmd in ("끄기", "off"):
        sys.exit(off())
    sys.exit(status())
