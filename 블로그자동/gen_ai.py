"""AI 실전 브랜딩 원고 '반자동' 생성기 (ioiykd8599 = 40대 가장의 AI 생존기).

셀럽/강점 아님. 축=AI 실전(자동화·수익화·부업). 화자=40대 밑바닥서 AI로 산 에디.
- 소재는 소재뱅크(~/홈판자료/AI실전_소재뱅크30.md) 또는 인자로 받은 topic.
- 완전 무인 X → 초안 + [[경험 슬롯]]을 남긴다. 에디님이 경험 채우고 검토 후 발행(저품질 회피 필수).
- 넓은 후킹 제목(직장인·결과·초보). 연예인 후킹 X.

사용: python3 gen_ai.py "AI로 블로그 글 자동 발행, 진짜 되는지 3개월 해봤습니다"
"""
from __future__ import annotations

import json
import os
import re
import sys

from claude_cli import run_claude_p
import celeb_sources as S
import config
import formula
import gen_common as G
import gen_templates as T
import gemini_thumb

# 네이버 블로그 주제 디렉토리(2026-07 실측): 30 = IT·컴퓨터(AI 주제축) / 0 = 전체 주제(홈판 전체).
# 주제는 AI축(dir=30)에서, '제목·본문·썸네일 공식'은 전체 홈판(dir=0) 지금 잘 나가는 것에서 뽑는다.
DIR_IT = 30
DIR_HOME = 0

EDI_AI_PROFILE = """[화자 '에디' — 1인칭]
- 40대에 실직·폐업까지 겪고 밑바닥에서 AI로 다시 일어섰다. 코딩은 원래 한 줄도 몰랐다.
- 지금은 AI로 블로그·유튜브·콘텐츠를 직접 만들고 굴리며, 되는 것·안 되는 것을 몸으로 겪는다.
- ★이 블로그의 목적: 자기 홍보·상품 판매가 아니라, 검색·홈피드에서 만난 독자에게 '직접 해보고 남은 실전 정보'를 주는 것.
- 톤: 과장 없음. 직접 해본 사람의 담백한 1인칭. "해봤더니 이렇더라" 같은 태도.
- ★어투는 항상 **존댓말**("~해봤습니다", "~이렇습니다"). 반말로 쓰지 않는다.
- 유튜브 채널 @AI생존기Edi 운영(글 끝에 가볍게 한 번만 언급, 홍보 X).
"""

# 에디님 실제 서사(경험 문단 재료). 신뢰(경험)를 주는 용도지 자기 브랜딩·사업 홍보용이 아니다.
# ★과장·지어내기 금지: 고객 수·매출·판매 실적 등 없는 수치·사실 금지.
EDI_STORY = """[에디의 실제 이야기 — 경험 문단은 이 사실들에 뿌리를 둔다. 이 밖의 구체 수치·날짜·고객수·매출은 지어내지 말 것]
- 마흔 무렵 회사에서 밀려나고 벌여둔 사업까지 접었다. 돈을 크게 날렸고, 컴퓨터·코딩은 문외한이었다("이 나이에 뭘 새로 배우나" 겁부터 났다).
- 밑바닥에서 AI를 붙잡고 다시 일어섰다. 코딩 대신 'AI에게 시키는 법'을 익혀, 블로그·유튜브·콘텐츠를 직접 만들고 자동화했다.
- 그래서 이 글은 '전문가 이론'이 아니라 '직접 해보고 남은 실전 정보'다. 헛발질·실패도 겪었기에 함정도 안다.
- ★목적은 자기 자랑·사업 홍보가 아니다. 검색·홈피드에서 온 독자에게 진짜 쓸모를 주는 것. '나도 됐으니 당신도 된다'는 태도로 담백하게.
- ★단, 네이버 블로그만은 저품질 때문에 '반자동'이 안전하다고 본다(이 판의 룰이라서). 이 디테일까지 아는 게 신뢰 근거."""

TITLE_PROMPT = """너는 네이버 홈피드에 잘 뜨는 제목만 만드는 카피라이터다. 아래 주제로 후킹 제목 5개.

[★지금 이 판(IT·컴퓨터)에서 네이버가 실제로 밀어주고 있는 제목들 — 오늘 수집한 것]
{live_titles}

[오늘의 제목 공식 — 위 위너들에서 실시간 추출한 것. 이걸 우선 따른다]
{title_formula}

[★★이 블로그에서 '실제로 조회수가 나온' 제목 구조 — 2026-08-06 실측. 이 구조를 최우선으로 따른다]
  · "다들 얼굴 얘기만 하는데, 영자가 **진짜로 넘은 건 따로 있었습니다**"
  · "다들 틱이라 했는데 아니었다… 순자가 **병원에서 받은 진짜 진단**"
  · "솔로지옥에서는 커플이었는데…**이관희가 최혜선을 지목한 한마디**"
  · "남편 외도 증거 모은 아내, **정작 전문가가 짚은 건 따로 있었다**"
공통 문법 = ①통념/예상을 먼저 깔고("다들 ~라 했는데", "~인 줄 알았는데")
            ②그걸 뒤집고("아니었다", "따로 있었다")
            ③**결론은 감춘다**(무엇인지 말하지 않아 클릭해야 알 수 있게).

[★절대 하지 말 것 — 조회수가 안 나온 제목들의 특징]
  · 결론을 제목에 다 말해버리기: "정부지원금, AI한테 물었더니 몰랐던 돈이 나왔다"(X)
    → 고치면: "정부지원금 다 받고 있다 생각했는데, AI가 찾아준 건 따로 있었습니다"(O)
  · 담백한 정보 요약·기능 설명형. 읽을 이유(궁금증)가 없는 제목.

[보조 후킹 장치 — 위 구조 위에 얹는다]
① 구체 숫자·결과 (월 100만/하루 30분/3개월)
② 직장인·40대·초보 공감
③ 통념 반박 ("~인 줄 알았는데", "이것부터 안 하면")

[주제] {topic}

규칙: **위 '실측 구조'를 이 주제에 적용**. 40자 이내 한 줄. 연예인 이름 X.
★5개는 서로 다른 구조로(전부 같은 틀로 찍어내지 말 것).
글에 없는 수치는 지어내지 말 것(막연히 큰 숫자 금지). 설명·번호 없이 제목만 한 줄씩.
"""

BODY_PROMPT = """당신은 'AI 실전' 블로거 '에디'입니다. 아래 주제로 네이버 블로그 글을 씁니다.
검색하는 사람이 진짜 궁금한 '실용 정보'를 주되, 과장 없이 직접 해본 톤으로.
2026년 네이버는 'AI가 다 쓴 대량 글'을 저품질로 잡는다 — 그래서 실전 정보 + 경험이 핵심이다.

{profile}

{story}

[이 글 주제] {topic}
[타겟] 불안한 직장인·부업 희망자·AI 초보(넓게). "40대"는 화자 신뢰 근거지 타겟 필터 아님.

[★오늘의 본문 공식 — 지금 네이버가 밀어주는 글들에서 실시간 추출. 이 흐름을 따라 쓴다]
{body_formula}

★구조를 매번 똑같이 찍어내지 말 것. 위 '오늘의 공식'이 최우선이고,
   아래 기본 뼈대는 공식이 비어 있을 때만 쓰는 폴백이다.
★★도입부 규칙(홈판 필수): **첫 문장부터 후킹으로 바로 들어간다.** 인사·자기소개 절대 금지 —
   '안녕하세요', '~입니다', '에디입니다', '여러분', '오늘은' 으로 시작하지 말 것. 홈판 위너는 인사로 시작 안 한다.
[폴백 뼈대]
1. 도입 후킹 2~4줄: 지금 왜 이게 궁금한지 + "그런데 해보니 이렇더라" (인사·자기소개 금지, 첫 줄부터 후킹)
2. 이게 뭔지 / 왜 지금 중요한지 (짧게)
3. ★핵심 실전 정보: 단계·방법·비교를 구체적으로 (검색자가 원하는 답)
4. 2026 현실·주의점: 함정도 알려준다 (신뢰 = 파는 사람이 아니라 겪은 사람)
5. 정리(불릿 3개)
6. 질문형 CTA(댓글 유도)로 마무리. ★유튜브 채널 언급·홍보 금지(2026-08-02 에디님 지시).

[반드시 지킬 것]
- ★★어투 고정: **존댓말('~합니다/~습니다/~됩니다')로 끝까지 통일.** 반말·평서체(`~다`, `~더라`, `~하자`) 절대 금지.
  위 '오늘의 공식'은 **구조·전개만** 참고하는 것이고, 어투까지 따라가지 말 것(레퍼런스 블로그가 반말이어도 우리는 존댓말).
- ★지어내기 금지: 툴 기능·수치·가격은 확실한 것만. 불확실하면 '알려진 바로는'·'제 경우엔' 톤. 단정 금지.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지(이모지는 소제목에 한두 개만).

★★★'AI가 쓴 티' 제거 — 지금 홈판에서 실제로 뜨는 글은 이렇게 씁니다(2026-08-06 실측 수집).
  이건 문체 규칙이지 어투 규칙이 아닙니다. **존댓말은 그대로 유지**하되, 아래를 지키세요.
  [따라야 할 것]
   · 문장을 짧게, 툭툭 끊습니다. 길이를 일부러 들쭉날쭉하게(한 줄짜리 문장도 섞어서).
   · **구체적인 숫자·이름·상황**을 넣습니다. "빠르다"(X) → "3분 만에 나왔습니다"(O).
     두루뭉술한 형용사 대신 실제 겪은 장면을 적습니다.
   · 잘 모르는 건 모른다고 씁니다("이건 저도 확실치 않은데", "제 경우엔 이랬습니다").
   · 곁가지·군더더기를 조금 남깁니다. 사람 글은 완벽하게 정돈돼 있지 않습니다.
  [절대 쓰지 말 것 — 이게 'AI 냄새'의 정체]
   · 매끄러운 연결어: "또한", "따라서", "이처럼", "뿐만 아니라", "결론적으로", "정리하자면"
   · 교과서식 마무리: "~해보시기 바랍니다", "도움이 되셨길 바랍니다", "지금 바로 시작해보세요"
   · 모든 문단이 같은 길이·같은 리듬으로 반복되는 것
   · 속 빈 수식어: "정말 유용한", "매우 효과적인", "혁신적인", "놀라운"
   · 항목마다 균일하게 3개씩 딱 떨어지는 나열(사람은 2개나 4개도 씁니다)
- 본문에 마커 포함:
  [사진N - 화면/장면 설명 / 출처: 직접 촬영 또는 해당 툴 화면] 5~8개
  [표] (비교/단계 표 1개. 내용은 아래 카드 JSON의 '표')
  ★경험 문단(중요): 빈 슬롯을 남기지 말고, 위 [에디의 실제 이야기]를 이 글 주제와 자연스럽게 이은
    1인칭 경험 문단을 본문 1~2곳에 **직접 써 넣는다**(2~4문장). 예: 실직·폐업하고 코딩도 몰랐던 내가
    이 주제(예: AI 이미지)를 처음 만났을 때 어땠는지 → 지금은 어떻게 쓰는지.
    · 단, [에디의 실제 이야기] 밖의 구체 수치·날짜·사건은 지어내지 말 것(예: '조회수 3배' 같은 가짜 숫자 금지).
    · ★**빈 슬롯([[경험 보태기: …]] 같은 것)을 절대 남기지 마라**(2026-08-06 에디님: 자동 발행으로 전환).
      경험 문단은 위 [에디의 실제 이야기] 범위 안에서 **완성된 문장으로 끝맺는다**. 대괄호 자리표시자 금지.
- ★소주제 규칙(엄수): 소주제는 **[사진N] 바로 다음 줄에만** 놓는다. 3~5개, 짧은 명사형/의문형 한 줄(20자 이내, 마침표 없이).
  · 사진과 상관없는 자리에 소주제를 흘리지 말 것. 소주제를 두 줄 연속으로 붙이지 말 것.
  · 소주제 뒤에는 반드시 그 소주제를 설명하는 본문이 이어져야 한다(제목만 덩그러니 두지 말 것).
- 마지막: 해시태그 10개(#로 시작, 검색키워드 포함). ★'@출처' 줄은 넣지 말 것(2026-08-02 에디님: 내 경험 글엔 불필요).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["기준/단계","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"AI 실전"}}}}
"""


def _clean_title(line: str) -> str:
    """제목 후보 한 줄 정리: 앞의 번호/불릿/대괄호 라벨([셀럽 후킹] 등)·따옴표 제거."""
    t = re.sub(r"^\s*(?:\d+[.)]|[-–—•*·])\s*", "", line)
    t = re.sub(r"^\s*\[[^\]]{0,20}\]\s*", "", t)   # 프롬프트 라벨 누수 제거
    # ★LLM이 붙이는 장식 기호 제거(2026-08-04: '★넷플릭스…', '★[AI 프사]★ …'가 그대로 업로드됨).
    #   홈판 제목에 이런 기호가 있으면 광고글처럼 보인다.
    t = re.sub(r"[★☆✔✅◆■▶▲※]+", " ", t)
    t = re.sub(r"[*_`#]+", "", t)                  # 마크다운 강조(**제목**, *제목) 누수 제거
    t = re.sub(r"^\s*\[[^\]]{0,20}\]\s*", "", t)   # 기호 제거 후 드러난 라벨도 한 번 더
    t = re.sub(r"\s{2,}", " ", t)
    t = t.strip()
    # ★따옴표는 '제목 전체를 감싼 경우'에만 벗긴다(2026-08-06 버그 수정).
    #   기존 strip("\"'")는 «'코인 부부', 이호선 앞에서…»처럼 **앞부분만 인용**한 제목에서
    #   여는 따옴표만 떼어내 «코인 부부', 이호선…»으로 깨뜨렸다(홈판 제목이 오타처럼 보인다).
    while len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1].strip()
    # 한쪽만 남아 홀수 개면(과거 산출물·LLM 누수) 여는 따옴표를 복원
    for q in ("'", '"'):
        if q in t and t.count(q) % 2 == 1 and not t.startswith(q):
            t = q + t
            break
    return t.strip()


def _parse_json(out: str) -> dict:
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {}


def _parse_body(out: str) -> tuple[str, dict]:
    body, cards = "", {}
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


def _set_title_line(body: str, title: str) -> str:
    lines = body.splitlines()
    for i, ln in enumerate(lines[:5]):
        if re.match(r"^\s*제목\s*[:：]", ln):
            lines[i] = f"제목: {title}"
            return "\n".join(lines)
    return f"제목: {title}\n\n" + body


def _sanitize(topic: str) -> str:
    kw = re.sub(r"[^가-힣0-9A-Za-z]", "", topic)
    return kw[:20] or "AI실전"


def collect_live_context(log=print) -> dict:
    """지금 홈판(IT·컴퓨터)이 밀어주는 제목·본문을 읽어 '오늘의 공식'을 추출.

    구조가 매일 똑같이 찍혀 나오던 문제(2026-07-24 에디님 지적)의 해결책.
    여러 편을 생성할 땐 이 결과를 공유해 수집·추출을 1회만 한다.
    실패해도 빈 공식으로 진행(생성기는 폴백 뼈대를 씀).
    """
    ctx = {"titles": [], "home_titles": [], "title_formula": "", "body_formula": "", "thumb_formula": ""}
    # (1) AI 주제 도출용 = IT·컴퓨터(dir=30) 트렌드(축을 AI로 유지)
    try:
        log("AI 주제 트렌드(IT·컴퓨터) 수집 중…")
        ctx["titles"] = S.fetch_theme_titles(DIR_IT, 30)
    except Exception as e:  # noqa: BLE001
        log(f"AI 주제 트렌드 수집 실패(폴백 진행): {str(e)[:100]}")
    # (2) 제목·썸네일·본문 '공식' = 전체 홈판(dir=0) 지금 잘 나가는 것에서 뽑는다(에디님 지시)
    try:
        log("전체 홈판(dir=0) 위너 제목 수집 중…")
        ctx["home_titles"] = S.fetch_theme_titles(DIR_HOME, 30)
    except Exception as e:  # noqa: BLE001
        log(f"전체 홈판 제목 수집 실패: {str(e)[:100]}")
    try:
        log("전체 홈판 썸네일 레퍼런스 수집·공식 추출 중…")
        ctx["thumb_formula"] = gemini_thumb.extract_thumb_formula(
            S.fetch_theme_thumbnails(DIR_HOME, 6), log=log)
    except Exception as e:  # noqa: BLE001
        log(f"썸네일 공식 추출 실패(자유 디자인): {str(e)[:100]}")
    samples = []
    try:
        # ★본문 공식은 '같은 쪽 잘되는 글'에서 — AI 글이니 AI/IT(dir=30) 위너 본문을 공식화
        for post in S.fetch_theme_posts(DIR_IT, 3):
            bt = S.fetch_blog_body(post["url"], 1400)
            if bt:
                samples.append(bt)
    except Exception as e:  # noqa: BLE001
        log(f"위너 본문 수집 실패(폴백 진행): {str(e)[:100]}")
    formula_titles = ctx["home_titles"] or ctx["titles"]
    if formula_titles or samples:
        try:
            log("오늘의 제목·본문 공식 추출 중(전체 홈판 기준, claude -p)…")
            fx = formula.extract_formulas(formula_titles, samples)
            ctx["title_formula"] = fx.get("title", "")
            ctx["body_formula"] = fx.get("body", "")
        except Exception as e:  # noqa: BLE001
            log(f"공식 추출 실패(폴백 뼈대 사용): {str(e)[:100]}")
    return ctx


DAILY_TOPIC_PROMPT = """오늘 네이버 홈판(홈피드)에 '실제로 뜨고 있는' 것들이다.
목적: ★'무조건 홈판에 뜰' AI 글감 {n}개만 뽑는다. 홈판에 안 뜰 니치·전문·마이너 주제는 절대 넣지 마라.

[지금 '전체 홈판'에 뜨는 제목들 — 진짜 뜨는 것의 기준(맛집·여행·돈·이슈·화제 등)]
{home_titles}

[AI·IT 쪽에서 뜨는 제목들]
{titles}

[에디 축] AI 자동화·수익화·부업·툴 실전(직접 해본 정보). 화자=40대 밑바닥서 AI로 산 에디(코딩0). 타겟 넓게.

[★홈판 검증 — 이 기준 통과한 주제만 뽑는다]
① 넓은 관심: 돈·부업·수익·일상 편의·화제의 신기술처럼 '아무나 궁금해할' 것. (개발자·전문가만 관심 = 탈락)
② 검색·클릭 수요: 사람들이 실제 검색하거나 클릭할 제목이 나오는 주제.
③ 지금 뜨는 흐름과 연결: 위 전체 홈판에 뜬 트렌드(신제품·돈·화제·이슈)에 AI 각도를 붙인 것 우선.
★탈락(넣지 마): '특정 API 사용법', '무슨 모델 벤치마크', '프롬프트 엔지니어링 이론' 같은 니치·전문 주제.
★채택(좋은 예): 'Z폴드8 나왔는데 AI로 리뷰 콘텐츠 30분 만에', '요즘 부업 화제…코딩 몰라도 AI로 부업 만드는 법',
   '챗GPT 새 기능, 초보가 바로 써먹는 법', 'AI로 여행 계획 5분에 짜봤더니'.
※내 시스템 자랑·사업 홍보형 X. 독자가 얻어갈 게 확실한 것만.

[최근에 쓴 주제 — 겹치지 말 것]
{used}

규칙: 각 주제는 그대로 제목/주제로 쓸 구체적 한 줄. ★홈판에 뜰 확신이 있는 것만(애매하면 빼라). 억지·니치 금지.
연예인 이름 X. 정확히 {n}개, 설명·번호 없이 한 줄씩만.
"""


def derive_topics(ctx: dict, n: int, used: list | None = None, log=print) -> list:
    """오늘 '전체 홈판(dir=0)' + AI 트렌드에서 '홈판에 뜰' 글감 n개를 뽑는다(니치·전문 주제 제외).
    실패하거나 부족하면 빈/부분 리스트 반환 → 호출측이 소재뱅크로 폴백."""
    titles = (ctx or {}).get("titles") or []
    home = (ctx or {}).get("home_titles") or []
    if len(titles) + len(home) < 5:
        log("홈판 트렌드 제목이 부족 → 오늘의 주제 도출 생략(뱅크 폴백)")
        return []
    used = used or []
    tl = "\n".join(f"- {t}" for t in titles[:25])
    hl = "\n".join(f"- {t}" for t in home[:25]) or "(수집 실패)"
    ul = "\n".join(f"- {t}" for t in used[-40:]) or "(없음)"
    try:
        # ★중복 방지(2026-08-10): 'used'(내부 이력)만으로는 표현이 조금 달라진 재탕을 못 막는다.
        #   블로그에 **실제로 발행된 제목**과 최근 남용한 제목 틀을 같이 보여준다.
        import history
        _recent = history.recent_titles(60, log)
        out = run_claude_p(
            DAILY_TOPIC_PROMPT.format(n=n, home_titles=hl, titles=tl, used=ul)
            + "\n\n" + history.prompt_block(_recent), timeout=180)
    except Exception as e:  # noqa: BLE001
        log(f"오늘의 주제 도출 실패(뱅크 폴백): {str(e)[:100]}")
        return []
    bad = re.compile(r"^주제|^다음|규칙|트렌드|공식|출력|글감\s*\d|^\[")
    topics = []
    for l in out.splitlines():
        t = re.sub(r"^\s*(?:\d+[.)]|[-–—•*·])\s*", "", l).strip().strip("\"'")
        if 8 <= len(t) <= 60 and not bad.search(t) and t not in used and t not in topics:
            _dup = history.too_similar(t, _recent, 0.5)
            if _dup:
                log(f"  [중복] 주제 버림: {t[:32]} ↔ 발행분 '{_dup[:32]}'")
                continue
            topics.append(t)
    log(f"오늘의 주제 {len(topics)}개 도출(홈판 트렌드 기반)")
    return topics[:n]


def generate(topic: str, out_dir: str, no: str = "20", log=print, ctx: dict | None = None) -> dict:
    """AI 실전 원고 1편(반자동 초안). 제목 후보 3개 + 본문(경험슬롯 포함) + 표 + 썸네일.

    ctx: collect_live_context() 결과. 넘기면 그날의 홈판 공식대로 쓰고, 없으면 직접 수집한다.
    """
    log(f"[{no}] AI 실전 초안 생성: {topic[:30]}")
    table_title = f"{_sanitize(topic)[:12]} 핵심 정리"
    if ctx is None:
        ctx = collect_live_context(log)
    # 제목 공식 참고는 '전체 홈판'에서 지금 잘 나가는 제목들(에디님 지시)
    live_titles = "\n".join(f"- {t}" for t in (ctx.get("home_titles") or ctx.get("titles") or [])[:25]) or "(수집 실패)"
    title_formula = ctx.get("title_formula") or "(추출 실패 — 아래 후킹 장치로 대체)"
    body_formula = ctx.get("body_formula") or "(추출 실패 — 아래 폴백 뼈대를 쓸 것)"

    # 제목 후보 3개
    titles = []
    try:
        import history
        _recent = history.recent_titles(60, log)
        out = run_claude_p(TITLE_PROMPT.format(
            topic=topic, live_titles=live_titles, title_formula=title_formula)
            + "\n\n" + history.prompt_block(_recent), timeout=150)
        titles = [_clean_title(l) for l in out.splitlines() if l.strip()]
        # LLM이 지시문/설명문(프리앰블)을 제목으로 뱉는 경우 제거.
        #  예: "제목만 출력합니다." / "…5개 서로 다른 구조로 뽑았습니다."(← 실제 네이버 업로드 오염 사례)
        bad = re.compile(r"^제목|제목만|제목\s*\d|개입니다|출력|구분자|형식|규칙|^다음|다음과|^아래|번호 없|설명 없|드립니다|나열|"
                         r"뽑았|서로 다른 구조|후보입니다|후보를|버전으로 뽑|개 뽑|개를 뽑|구조로 뽑|골랐습니다|만들었습니다|작성했습니다")
        titles = [t for t in titles if 6 <= len(t) <= 45 and not bad.search(t)]
        # ★최근 발행 제목과 겹치는 후보는 뒤로 밀어낸다(전부 겹치면 그대로 쓰되 경고)
        _fresh = [t for t in titles if not history.too_similar(t, _recent, 0.5)]
        if _fresh:
            titles = _fresh
        elif titles:
            log(f"[{no}] !! 제목 후보가 전부 최근 발행분과 겹침 — 그대로 사용({titles[0][:28]})")
        titles = titles[:3]
    except Exception as e:  # noqa: BLE001
        log(f"[{no}] 제목 생성 실패: {e}")
    best = titles[0] if titles else topic

    # 본문 (claude -p가 부하로 가끔 빈 응답을 줘서 최대 3회 재시도)
    body, cards = "", {}
    prompt = BODY_PROMPT.format(profile=EDI_AI_PROFILE, story=EDI_STORY, topic=topic,
                                table_title=table_title, body_formula=body_formula)
    for k in range(3):
        body, cards = _parse_body(run_claude_p(prompt, timeout=320))
        if body and cards and len(body.strip()) >= 300:
            break
        log(f"[{no}] 본문 재시도 {k+1}/3 (길이 {len(body.strip())})")
    if not body or not cards or len(body.strip()) < 300:
        raise RuntimeError(f"본문 생성 실패(재시도 소진, 길이 {len(body.strip())})")
    body = _set_title_line(body, best)
    # 홈판 규칙: 생성 단계에서도 인사·자기소개 도입을 제거해 복붙용/미리보기까지 깨끗하게.
    #  (업로드 pipeline에도 백스톱이 있으나, LLM이 프롬프트 금지에도 가끔 인사말을 붙여 사이드카에 남았음.)
    from pipeline import _strip_greeting_intro
    body = _strip_greeting_intro(body)

    keyword = _sanitize(topic)
    os.makedirs(out_dir, exist_ok=True)
    G.clear_no(out_dir, no)
    with open(os.path.join(out_dir, f"{no}_{keyword}_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    # AI 실전 초안 표식(대시보드가 옛 셀럽/강점 글과 구분)
    open(os.path.join(out_dir, f"{no}_{keyword}_ai.flag"), "w").close()
    # 제목 후보를 사이드카로 저장(에디님이 고르게)
    if titles:
        with open(os.path.join(out_dir, f"{no}_{keyword}_제목후보.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(titles))
    T.write_celeb_table(out_dir, no, keyword, cards.get("표제목", table_title), cards.get("표", []))
    # 썸네일 3단 폴백:
    #  ① 글 전문을 제미나이에 주고 '요약·디자인까지' 맡김(문구 지정 X — 템플릿화 방지)
    #  ② 실패 시 문구 지정형(배지/큰글씨)  ③ 그래도 실패 시 HTML 디자인형
    thumb = cards.get("썸네일", {})
    fn = f"{no}_{keyword}_썸네일.png"
    ref_formula = (ctx or {}).get("thumb_formula", "")
    if not gemini_thumb.make_from_article(out_dir, fn, body, log=log, ref_formula=ref_formula):
        if not gemini_thumb.make_from_thumb(out_dir, fn, thumb, query_hint=topic, log=log):
            T.render_text_thumbnail(out_dir, fn, thumb)
    log(f"[{no}] 완료 → {keyword} (제목후보 {len(titles)}개, 경험슬롯 포함)")
    return {"no": no, "topic": topic, "keyword": keyword, "titles": titles}


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI로 블로그 글 자동 발행, 진짜 되는지 3개월 해봤습니다"
    out = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    generate(topic, out, no="20")
