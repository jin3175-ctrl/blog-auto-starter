"""연예/라이프 홈피드 후킹 제목 생성 (이서이 강사 실제 제목 180개 패턴 학습).

핵심: 제목에 '강점'을 절대 넣지 않는다. 독자는 강점에 관심 없다.
후킹은 '연예인 + 구체적 궁금증(대사/나이/숫자/반전) + 여운 종결'로 만든다.
"""
from __future__ import annotations

import os
import re

from claude_cli import run_claude_p

_REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref_hook_titles.txt")

# 제목에 절대 나오면 안 되는 단어(독자는 강점에 관심 없음)
_FORBIDDEN = ["강점", "코치", "갤럽", "테마", "심리분석"]


def _has_forbidden(t: str) -> bool:
    return any(w in t for w in _FORBIDDEN)


def _strip_forbidden(t: str) -> str:
    """금지어가 든 꼬리 절(쉼표·… 뒤)을 잘라낸다."""
    parts = re.split(r"\s*[,，…]\s*", t)
    kept = [p for p in parts if p and not _has_forbidden(p)]
    return ", ".join(kept).strip(" ,") if kept else t


def _finalize(gen_fn, timeout: int) -> str:
    """제목 생성 → 금지어 있으면 1회 재시도 → 그래도 있으면 꼬리 절 제거."""
    t = gen_fn()
    if _has_forbidden(t):
        t2 = gen_fn()
        t = t2 if not _has_forbidden(t2) else _strip_forbidden(t2)
    return t.strip()


def _examples(live: list | None = None, n: int = 55) -> str:
    """현재 밀어주는 제목(live)을 우선, 부족분은 저장된 이서이 제목으로 채움."""
    pool: list[str] = []
    for t in (live or []):
        t = (t or "").strip()
        if t and t not in pool:
            pool.append(t)
    try:
        for l in open(_REF, encoding="utf-8"):
            l = l.strip()
            if l and l not in pool:
                pool.append(l)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(f"- {t}" for t in pool[:n])


PROMPT = """너는 네이버 '연예·라이프' 홈피드(추천 피드) 상위 노출 제목 카피라이터다.
아래는 실제로 조회수가 잘 나온 제목 예시들이다. 이 '후킹 공식'을 그대로 체화해라.

[검증된 제목 예시]
{examples}
{formula}
[제목 공식 — 반드시 지켜라]
1. 제목에 '강점 / 강점코치 / 갤럽 / 테마 / 분석 / 심리' 같은 단어 절대 금지. 독자는 강점에 관심 없다.
2. 구조: (후킹 요소) + (인물 또는 프로그램) + (궁금증을 남기는 종결).
3. 후킹 요소는 다음 중 1~2개를 섞는다:
   - 짧은 대사/인용("..."), 나이(예: 56세), 숫자·가격(10만 원대·3가지·2주),
     반전/의외, 말줄임표(…), 도발적 질문.
4. 종결은 궁금증을 남긴다: ~이유 / ~정체 / ~근황 / ~비결 / ~반응 / ~했다고? / ~보인 행동 / ~있었다.
5. 40자 내외 한 줄. 이모지·해시태그·마크다운 금지.
6. 방송에서 '실제로 있었던 장면'만 사용. 없는 사실·과장·낚시(내용과 무관한 자극) 금지.

[이번 글 소재]
- 인물/프로그램: {person} ({program})
- 실제 장면: {scene}
- 글의 숨은 포인트(제목에 직접 쓰지 말고 '궁금증'으로만 암시): {angle}

출력: 제목 딱 한 줄만. 따옴표로 전체를 감싸지 말고, 설명·머리말 없이 제목만.
"""


def _first_title_line(out: str) -> str:
    for line in (out or "").splitlines():
        t = line.strip().strip("\"'“”‘’ ").strip()
        t = re.sub(r"^(제목|title)\s*[:：]\s*", "", t, flags=re.I).strip()
        if len(t) >= 6:
            return t
    return (out or "").strip()


def _formula_block(formula: str) -> str:
    return f"\n[지금 홈판에서 실시간 추출한 제목 공식 — 이 공식을 최우선으로 적용]\n{formula}\n" if formula else ""


def generate_hook_title(person: str, scene: str, program: str = "",
                        angle: str = "", live_titles: list | None = None,
                        formula: str = "", timeout: int = 120) -> str:
    prompt = PROMPT.format(examples=_examples(live_titles), formula=_formula_block(formula),
                           person=person, program=program or "-", scene=scene, angle=angle or "-")
    return _finalize(lambda: _first_title_line(run_claude_p(prompt, timeout=timeout)), timeout)


PRODUCT_PROMPT = """너는 네이버 '쇼핑·리빙' 홈피드 상위 노출 제목 카피라이터다.
아래는 실제로 조회수가 잘 나온 제목 예시들이다. 이 후킹 감각을 그대로 체화해라.

[검증된 제목 예시]
{examples}
{formula}
[제목 공식 — 반드시 지켜라]
1. 제목에 '강점/코치/분석' 단어 금지. 광고티(‘최저가/할인/특가/공동구매’) 나는 낚시 금지.
2. 구조: (후킹 요소) + (제품/카테고리) + (궁금증·후회 방지 종결).
3. 후킹 요소는 1~2개: 실사용 경험('오래 써보니'), 숫자·기준(16L·3가지·평수), 실수/후회('~사면 후회'),
   시의성(장마·폭염·여름), 반전('싼 거 샀다가…'), 질문.
4. 종결은 궁금증/실익을 남긴다: ~이유 / ~차이 / ~고르는 법 / ~후회하는 이유 / ~아는 것 / ~전 필독.
5. 40자 내외 한 줄. 이모지·해시태그·마크다운 금지. 없는 사실·과장 금지.

[이번 글 소재]
- 제품/카테고리: {product}
- 핵심 이점/포인트: {benefit}
- 시의성(있으면): {timing}

출력: 제목 딱 한 줄만. 따옴표로 감싸지 말고, 설명·머리말 없이 제목만.
"""


def generate_product_title(product: str, benefit: str = "", timing: str = "",
                           live_titles: list | None = None, formula: str = "",
                           timeout: int = 120) -> str:
    prompt = PRODUCT_PROMPT.format(examples=_examples(live_titles), formula=_formula_block(formula),
                                   product=product, benefit=benefit or "-", timing=timing or "-")
    return _finalize(lambda: _first_title_line(run_claude_p(prompt, timeout=timeout)), timeout)


if __name__ == "__main__":
    print(generate_hook_title(
        "나는솔로 32기 광수", "아침에 가장 먼저 여자 숙소로 찾아가 옥순과 '코 점 커플'이 된 장면",
        "나는솔로", "먼저 움직여 판을 만드는 행동력"))
