"""강점 인사이트 원고 자동 생성 (테마 → 본문+카드+표+썸네일).

claude -p 로 '본문(마커 포함) + 카드/표/썸네일 내용(JSON)'을 만들고,
템플릿을 채워 발행 엔진이 쓰는 폴더 형태로 저장한다.

사용: python3 gen_insight.py 집중            # 특정 테마
     python3 gen_insight.py                 # 진행현황 다음 테마 자동
"""
from __future__ import annotations

import json
import os
import re
import sys

from claude_cli import run_claude_p
import config
import gen_common as G
import gen_templates as T

PROGRESS = os.path.join(os.path.expanduser("~/홈판자료/블로그오토"), "강점인사이트_진행현황.txt")

PROMPT = """당신은 갤럽 공인 강점코치 '에디'입니다. 아래 화자 정보의 '나(에디)' 1인칭 시점으로,
네이버 블로그 '강점 인사이트' 글을 씁니다.

{eddie}

[이번 테마] {ko}({en})
[갤럽 리소스 가이드 발췌 — 정의/특징 참고. OCR로 뒷부분이 깨졌으면 당신의 강점 지식으로 보완]
{guide}

[글쓰기 규칙 — 홈판(추천피드)형]
- 3초 후킹 도입(2~3줄, 장면/질문) → 공감/본능 → 강점 정의(갤럽) → 행동 특징 → 그림자(맹점)+보완 → 실전 3단계 → 독자에게 묻는 CTA 질문.
- 이모지·마크다운 금지, 한 문장 50자 내외 단문. 사실 왜곡·과장 금지.
- 에디의 개인 경험 앵커는 테마와 자연스러울 때만 1개 정도 짧게(억지 금지). 톤·코치 관점은 항상.
- 본문에 아래 마커를 포함:
  [사진1 - 장면설명 / 출처: Unsplash] 형태를 8~12개(설명은 Unsplash에서 찾기 쉬운 일반 장면).
  [소주제] 한 줄  /  [대주제] 한 줄(그림자 도입)  /  [표]
  [강점시각화 삽입 - {no}_{ko}_강점시각화]  [장점카드 삽입 - {no}_{ko}_장점]  [맹점카드 삽입 - {no}_{ko}_맹점]
  마지막: 면책 문단, '?'로 끝나는 질문, "@출처 : Gallup, Inc."
  (형식 그대로 — '@출처' + 공백 + 콜론 + 공백), 해시태그 10개(#로 시작).

[출력 형식 — 정확히 이 구분자]
===본문===
(위 규칙대로 본문)
===카드===
(아래 JSON 한 개. 큰따옴표 사용)
{{"정의":"한 문장","힘":"한 문장","장벽":"한 문장","팁":"한 문장",
 "삼단계":"Name 문구 · Claim 문구 · Aim 문구",
 "장점":["문장1","문장2","문장3"],"장점요약":"한 줄 요약",
 "맹점":["문장1","문장2"],"맹점보완":"한 줄 보완팁",
 "표":[["핵심","..."],["좋아하는 상황","..."],["행동 특징","..."],["맹점","..."],["함께 일하는 법","..."]],
 "썸네일":{{"intro":"짧은 도입구","tail":"짧은 설명구","box":"XX가 아니라","check":"핵심 한 줄","photo":"인물 사진 영어 프롬프트(사무실 실사, 인물 오른쪽 배치)"}}}}
"""


def _done_themes(txt: str) -> set:
    """진행현황의 '발행 완료'·'누적 추가 완료' 줄에 적힌, 이미 만든 테마 집합(건너뛸 대상)."""
    done = set()
    for line in txt.splitlines():
        if ("발행 완료" in line) or ("누적 추가" in line):
            done |= {t for t in G.THEME_KO if t in line}
    return done


def next_theme() -> str:
    """마지막 완료 다음(목차순)이되, 이미 발행한 테마는 건너뛴다."""
    try:
        with open(PROGRESS, encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"마지막 완료\s*[:：]\s*([가-힣]+)", txt)
        if m and m.group(1) in G.THEME_KO:
            done = _done_themes(txt)
            i = G.THEME_KO.index(m.group(1))
            for j in range(i + 1, len(G.THEME_KO)):
                if G.THEME_KO[j] not in done:  # 이미 만든 테마 skip
                    return G.THEME_KO[j]
    except Exception:  # noqa: BLE001
        pass
    return "집중"


def mark_done(theme: str) -> None:
    """진행현황 파일에 '마지막 완료: {theme}' 기록(다음 실행이 다음 테마 선택)."""
    try:
        txt = open(PROGRESS, encoding="utf-8").read() if os.path.exists(PROGRESS) else ""
    except Exception:  # noqa: BLE001
        txt = ""
    if re.search(r"마지막 완료\s*[:：]", txt):
        txt = re.sub(r"마지막 완료\s*[:：].*", f"마지막 완료: {theme}", txt)
    else:
        txt = (txt.rstrip() + f"\n마지막 완료: {theme}\n").lstrip("\n")
    try:
        os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
        open(PROGRESS, "w", encoding="utf-8").write(txt)
    except Exception:  # noqa: BLE001
        pass


def _parse(out: str) -> tuple[str, dict]:
    body = ""
    cards: dict = {}
    bm = re.search(r"===본문===\s*(.*?)\s*===카드===", out, re.S)
    if bm:
        body = bm.group(1).strip()
    cm = re.search(r"===카드===\s*(\{.*\})", out, re.S)
    if cm:
        try:
            cards = json.loads(cm.group(1))
        except Exception:  # noqa: BLE001
            cards = {}
    return body, cards


def generate(theme_ko: str, out_dir: str, no: str = "10") -> dict:
    en = G.THEME_EN.get(theme_ko, "")
    guide = G.extract_theme_section(theme_ko)
    prompt = PROMPT.format(eddie=G.EDDIE_PROFILE, ko=theme_ko, en=en, guide=guide or "(없음)", no=no)
    print(f"[{theme_ko}({en})] 원고 생성 중(claude -p)…", flush=True)
    out = run_claude_p(prompt, timeout=300)
    body, cards = _parse(out)
    if not body or not cards:
        raise RuntimeError("생성 결과 파싱 실패(구분자/JSON 확인)")

    os.makedirs(out_dir, exist_ok=True)
    G.clear_no(out_dir, no)
    stem = f"{no}_{theme_ko}"
    with open(os.path.join(out_dir, f"{stem}_강점인사이트_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    T.write_cards(out_dir, no, theme_ko, en, cards)
    T.render_thumbnail(out_dir, f"{stem}_썸네일.png", theme_ko, cards.get("썸네일", {}))
    print(f"완료 → {out_dir} ({stem}_*)", flush=True)
    return {"theme": theme_ko, "out_dir": out_dir}


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else next_theme()
    date = config.today_str()
    out = os.path.join(config.SOURCE_ROOT, f"gen_{date}")
    generate(theme, out)
