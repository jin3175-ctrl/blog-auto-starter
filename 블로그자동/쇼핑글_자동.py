"""쇼핑커넥트 글 한 편 → 에고라이트로 임시저장 (2026-11-01 · 3기 4주차).

    python 쇼핑글_자동.py 온수매트     # 제품을 정해서
    python 쇼핑글_자동.py              # 계절에 맞는 제품을 클로드가 고른다

gen_shopping 이 글을 쓰고 [커넥트 - 제품] 자리를 만든다 → ego/publish.mjs 가 수수료 높은 상품 카드를 넣는다.
🔴지금은 임시저장까지만 한다 — 에고라이트 카드 삽입을 실제 네이버에서 시험하기 전이라 공개하지 않는다(2026-11-01).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 오늘글_자동 as A  # noqa: E402


def main(argv) -> int:
    hint = argv[0] if argv else ""
    if not A._find_tools():
        A.log("✗ claude 를 못 찾았습니다 — 클로드 코드가 설치·로그인돼 있는지 보세요")
        return 1
    import config
    import gen_shopping
    import pipeline
    folder = os.path.join(config.SOURCE_ROOT, config.today_str())
    os.makedirs(folder, exist_ok=True)
    used = [int(f[:2]) for f in os.listdir(folder) if f[:2].isdigit()]
    no = f"{max(used, default=0) + 1:02d}"
    A.log(f"쇼핑커넥트 글을 씁니다(제품: {hint or '클로드가 고름'})")
    gen_shopping.generate(folder, no=no, hint=hint)
    r = pipeline.process_post(no, A.log, publish=False, folder=folder)   # 먼저 임시저장 — 카드가 들어갔는지 본다
    if not r.get("ok"):
        A.log(f"✗ 임시저장 실패: {r.get('message', '')[:300]}")
        return 1
    A.log("✓ " + r.get("message", ""))
    for n in r.get("notes") or []:
        A.log("  · " + str(n))
    if any("쇼핑커넥트" in str(n) for n in r.get("notes") or []):
        A.log("상품 카드를 못 넣었습니다 — 글을 열어 직접 넣고 발행하세요")
    else:
        A.log("네이버 「저장」 목록에서 상품 카드를 확인하고 발행하세요")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
