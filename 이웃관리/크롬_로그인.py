"""댓글·서이추용 네이버 로그인 — 크롬 창을 띄우고 **본인이 직접** 로그인한다 (2026-10-25 · 3기 3주차).

    python 크롬_로그인.py

· 크롬(플레이라이트 내장) 창이 뜨면 5분 안에 네이버에 로그인한다. 아이디·비밀번호는 사람이 친다.
  「로그인 상태 유지」 켜기 · 「IP 보안」 끄기 — 둘 중 하나만 어겨도 하루도 못 간다.
· 로그인 기록은 블로그자동/session/naver_state.json 에 남고, run.py·collect.py·reply.py 가 그걸 쓴다.
· 글 임시저장(맥=에고라이트 · 윈도우=어사이드)과는 따로다. 그쪽 로그인은 그 브라우저에서 한다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "블로그자동"))

import naver  # noqa: E402

if __name__ == "__main__":
    r = naver.login_and_save(print, timeout_sec=300)
    print(("✓ " if r.get("ok") else "✗ ") + r.get("message", ""))
    if r.get("ok"):
        print("이제 「댓글·서이추 화면에 채워줘」로 하면 됩니다.")
    sys.exit(0 if r.get("ok") else 1)
