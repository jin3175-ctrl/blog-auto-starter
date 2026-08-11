"""현재 홈판이 밀어주는 위너(제목·본문)에서 '지금 먹히는 공식'을 실시간 추출.

강의 방식: 뜨고 있는 제목/글을 GPT에 넣어 공식화 → 그 공식을 내 소재에 적용.
하드코딩 규칙 대신 '그날의 홈판 공식'을 뽑아 생성기에 넘긴다.
"""
from __future__ import annotations

import re

from claude_cli import run_claude_p

PROMPT = """아래는 지금 네이버 홈판(추천 피드)이 '밀어주고 있는' 실제 제목들과 실제 블로그 본문들이다.
이들이 공통으로 쓰는 '지금 먹히는 공식'을 분석해, 그대로 재사용 가능한 공식으로 정리하라.
특정 블로거 스타일이 아니라, 여러 위너에서 반복되는 '패턴'만 추출한다.

[지금 밀어주는 제목들]
{titles}

[지금 밀어주는 본문들(발췌)]
{bodies}

[출력 — 정확히 이 구분자. 설명·군더더기 없이 공식만.]
===제목공식===
- 구조(순서): (예: 후킹요소 + 대상 + 궁금증 종결)
- 자주 쓰는 후킹 장치: (구체적으로, 3~5개)
- 자주 쓰는 종결/마무리 패턴: (3~5개)
- 길이·금기: (글자수 감각, 피할 것)
===본문공식===
- 도입부 공식: (첫 2~4줄을 어떻게 여는가)
- 전개 순서: (문단이 흐르는 뼈대, 단계로)
- 문장·문단 리듬: (길이, 여백, 리스트 사용 등)
- 정보 제시 방식: (숫자·기준·비교 등 신뢰 주는 법)
- 마무리·독자 유도: (어떻게 닫고 무엇으로 참여 유도)
"""


def extract_formulas(winner_titles: list, sample_bodies: list, timeout: int = 220) -> dict:
    """{'title': 제목공식 텍스트, 'body': 본문공식 텍스트}. 실패 시 빈 문자열."""
    titles = "\n".join(f"- {t}" for t in (winner_titles or [])[:35]) or "(없음)"
    bodies = ("\n\n---\n\n".join(sample_bodies))[:3500] if sample_bodies else "(없음)"
    out = run_claude_p(PROMPT.format(titles=titles, bodies=bodies), timeout=timeout) or ""
    tf, bf = "", ""
    tm = re.search(r"===제목공식===\s*(.*?)\s*===본문공식===", out, re.S)
    if tm:
        tf = tm.group(1).strip()
    bm = re.search(r"===본문공식===\s*(.*)", out, re.S)
    if bm:
        bf = bm.group(1).strip()
    return {"title": tf, "body": bf}


if __name__ == "__main__":
    import celeb_sources as S
    w = S.fetch_theme_titles(12, 20)
    samples = [S.fetch_blog_body(p["url"], 900) for p in S.fetch_theme_posts(12, 2)]
    f = extract_formulas(w, samples)
    print("=== 제목공식 ===\n" + f["title"])
    print("\n=== 본문공식 ===\n" + f["body"])
