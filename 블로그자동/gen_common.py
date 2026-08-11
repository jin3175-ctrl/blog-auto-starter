"""생성(원고 자동 작성) 공통: 테마 목록, 리소스 가이드 추출, 에디 프로필."""
from __future__ import annotations

import os
import re

# 갤럽 34테마 (한국어, 영문) — 목차 순서
THEMES = [
    ("성취", "ACHIEVER"), ("행동", "ACTIVATOR"), ("적응", "ADAPTABILITY"), ("분석", "ANALYTICAL"),
    ("정리", "ARRANGER"), ("신념", "BELIEF"), ("주도력", "COMMAND"), ("커뮤니케이션", "COMMUNICATION"),
    ("승부", "COMPETITION"), ("연결성", "CONNECTEDNESS"), ("공정성", "CONSISTENCY"), ("회고", "CONTEXT"),
    ("심사숙고", "DELIBERATIVE"), ("개발", "DEVELOPER"), ("체계", "DISCIPLINE"), ("공감", "EMPATHY"),
    ("집중", "FOCUS"), ("미래지향", "FUTURISTIC"), ("화합", "HARMONY"), ("발상", "IDEATION"),
    ("포용", "INCLUDER"), ("개별화", "INDIVIDUALIZATION"), ("수집", "INPUT"), ("지적사고", "INTELLECTION"),
    ("배움", "LEARNER"), ("최상화", "MAXIMIZER"), ("긍정", "POSITIVITY"), ("절친", "RELATOR"),
    ("책임", "RESPONSIBILITY"), ("복구", "RESTORATIVE"), ("자기확신", "SELF-ASSURANCE"),
    ("존재감", "SIGNIFICANCE"), ("전략", "STRATEGIC"), ("사교성", "WOO"),
]
THEME_KO = [t[0] for t in THEMES]
THEME_EN = {ko: en for ko, en in THEMES}

GUIDE_PATH = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/05. 배움·수집 (iCloud)/5-10. 강점코칭/강점 교재/코치를 위한 리소스 가이드.txt")

EDDIE_PROFILE = """[블로거 '에디'(김종문) — 1인칭 화자, 갤럽 공인 강점코치, MBTI ENFP]
- 본인 강점 Top: 행동·미래지향·정리·최상화·커뮤니케이션·수집·발상·긍정·개별화·자기확신·사교성·전략.
- 서사(경험 재료): 부모 이혼·잦은 전학·혼자 울던 유년 / 역도 선수(고3 전국체전 동메달, 살 찌우려 토하며 실행) /
  IMF로 대학 못 감·알바 3개·짜장면 배달·막노동 / 27살 늦깎이 대학·중국 유학 / 중국서 여러 직장(생산팀장→임원, 점장, 영업소장) /
  '바인더의 힘' 읽고 독서·독서모임 창설 / 40세 귀국·창업 / 책 출간 / 코로나 위기·무자본창업 연속 실패 /
  어려운 시절 길에서 직접 장사도 해봄 / 타코야끼 푸드트럭 운영(첫달 500만) / 갤럽 강점코치 자격 /
  지금은 당근 모임(중국어·독서·AI)과 시니어 교육 운영.
- 톤: 솔직하고 꾸밈없음. 실패를 많이 겪고도 계속 시도한 사람. 겸손하지만 단단함.
- 규칙: 개인 경험 앵커는 '테마와 자연스럽게 맞을 때만' 1개 정도 짧게. 억지로 매번 넣지 말 것. 톤·코치 관점은 항상 유지.
- 표현 순화(중요): '노점'이라는 단어는 쓰지 말 것(어감이 안 좋음). 대신 "어려울 때 길에서 장사해본 적이 있다"식으로 부드럽게.
  타코야끼는 '노점'이 아니라 '푸드트럭'으로 표현."""


def clear_no(out_dir: str, no: str) -> None:
    """재생성 시 같은 편 번호의 기존 산출물({no}_*)을 지운다(중복 누적 방지)."""
    import glob
    for f in glob.glob(os.path.join(out_dir, f"{no}_*")):
        try:
            os.remove(f)
        except OSError:
            pass


def extract_theme_section(theme_ko: str, max_chars: int = 6000) -> str:
    """리소스 가이드에서 해당 테마 섹션 텍스트 추출(다음 테마 전까지, 길면 잘라냄)."""
    try:
        with open(GUIDE_PATH, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        return ""
    en = THEME_EN.get(theme_ko, "")
    # 실제 본문 섹션 시작 앵커: "테마명(ENGLISH) 테마가 특히 강한 사람" (목차·이미지 건너뜀)
    anchor = rf"{re.escape(theme_ko)}\({re.escape(en)}\)\s*테마가 특히 강한 사람"
    start_m = re.search(anchor, text)
    if not start_m:
        # 폴백: 트레이드마크 헤더
        start_m = re.search(rf"{re.escape(theme_ko)}\({re.escape(en)}\)\s*[™®]", text)
    if not start_m:
        return ""
    start = start_m.start()
    # 다음 테마의 같은 앵커까지
    idx = THEME_KO.index(theme_ko)
    end = len(text)
    for nxt_ko, nxt_en in THEMES[idx + 1:]:
        m = re.search(rf"{re.escape(nxt_ko)}\({re.escape(nxt_en)}\)\s*테마가 특히 강한 사람", text[start + 50:])
        if m:
            end = start + 50 + m.start()
            break
    section = text[start:end].strip()
    return section[:max_chars]


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "집중"
    sec = extract_theme_section(t)
    print(f"[{t}({THEME_EN.get(t)})] 추출 {len(sec)}자")
    print(sec[:600])
