"""연예인 후킹 × AI 실전 '접목' 원고 생성 (ioiykd8599 = 40대 가장의 AI 생존기).

쉬즈블랑 공식의 'AI판'. 지금 뜨는 연예 이슈를 후킹으로 쓰되, 알맹이는 에디의 실제 AI 활용법.
셀럽/강점 분석 아님 — 셀럽은 미끼, 본문은 검색자가 따라 할 수 있는 AI 실전 정보 + 경험.

★ 절대 원칙(핸드오프):
- 억지 연결 금지. AI로 자연스럽게 이어지는 이슈만 고른다(연결강도 '중' 이상). 없으면 슬롯 포기.
- 제목 = 본문 일치. 셀럽 가십을 미끼로 걸고 딴 얘기 하지 말 것(어그로 금지). 제목 자체가 셀럽→AI를 정직하게 잇는다.
- 지어내기 금지. AI 툴 기능·수치·가격은 확실한 것만. 셀럽 사실은 기사 범위 안에서만.
- 완전 무인 X → [[경험 슬롯]]을 남긴다. 에디님이 채우고 검토 후 발행(저품질 회피 핵심).

이 글도 gen_ai와 같이 ai.flag를 남겨 대시보드가 'AI 글'로 분류한다(C-Rank AI축 유지).

사용: python3 gen_celeb_ai.py                 # 오늘 랭킹에서 AI로 이을 수 있는 이슈 자동 선정
     python3 gen_celeb_ai.py "AI 화보"          # 힌트 우선
"""
from __future__ import annotations

import json
import os
import re
import sys

from claude_cli import run_claude_p
import celeb_sources as S
import config
from gen_ai import EDI_STORY, _clean_title  # 에디 실제 서사·제목정리 재사용
import gen_common as G
import gen_templates as T
import gemini_thumb

EDI_AI_PROFILE = """[화자 '에디' — 1인칭]
- 40대에 실직·폐업까지 겪고 밑바닥에서 다시 일어섰다. 코딩은 원래 한 줄도 몰랐다.
- 지금은 AI로 블로그·유튜브·콘텐츠를 직접 만들고 굴리며 되는 것·안 되는 것을 몸으로 겪는다. (블로그 목적=자기 홍보·판매 아니라 독자에게 실전 정보 주기)
- 톤: 과장 없음. 직접 해본 사람의 담백한 1인칭. "해봤더니 이렇더라" 같은 태도.
- ★어투는 항상 **존댓말**("~해봤습니다", "~이렇습니다"). 반말로 쓰지 않는다.
- 유튜브 채널 @AI생존기Edi 운영.
"""

# AI로 '자연스럽게' 이어지는 셀럽 소재 축(억지 연결 방지 기준)
BRIDGE_AXES = (
    "AI 직접 사용(AI 화보·AI 커버곡·딥페이크·AI 성대모사·AI 프로필·챗GPT 언급) / "
    "부업·수익·창업·1인 콘텐츠(→ AI 자동화·부업 도구) / "
    "재테크·자기계발·공부·이직(→ AI 활용법) / "
    "SNS·유튜브·사진·영상 제작(→ AI 편집·생성 도구)"
)

DIR_CELEB = 12   # 네이버 블로그 주제: 스타·연예인(연예 위너 본문 공식 추출용)

#: 연예편 사진·썸네일 자동첨부 여부. ★2026-08-07 에디님 지시로 False(끔).
#  자동 캡처가 엉뚱한 프로그램·기수·예고 그래픽을 붙여, 지우고 다시 넣는 게 더 힘들다.
#  False면 이미지를 만들지 않고 본문 `[사진N - 장면 / 출처: …]` 마커만 남긴다(에디님이 직접 삽입).
#  다시 켜려면 프레임의 프로그램·기수·그래픽 여부를 판정하는 검증을 먼저 붙일 것.
CELEB_AUTO_PHOTOS = False


def collect_celeb_body_formula(log=print) -> str:
    """오늘 연예(스타·연예인) 홈판에서 잘되는 글 본문을 읽어 '연예 본문 공식'을 뽑는다.
    연예 글이 연예 쪽 잘되는 글 구조를 따르게 한다(에디님 지시). 실패 시 빈 문자열."""
    import formula
    samples = []
    try:
        for post in S.fetch_theme_posts(DIR_CELEB, 3):
            bt = S.fetch_blog_body(post["url"], 1400)
            if bt:
                samples.append(bt)
    except Exception as e:  # noqa: BLE001
        log(f"연예 위너 본문 수집 실패: {str(e)[:80]}")
    if not samples:
        return ""
    try:
        log("연예 본문 공식 추출 중(claude -p)…")
        return formula.extract_formulas([], samples).get("body", "")
    except Exception as e:  # noqa: BLE001
        log(f"연예 본문 공식 추출 실패: {str(e)[:80]}")
        return ""


# 연예 선정 1순위(에디님 지정 2026-07-25). 오늘 기사 목록에 이게 있으면 최우선 선택.
# 관계·상담·자기계발 결이라 AI(자기계발·상담·궁합·자기소개 등)로 잇기도 자연스럽다.
PRIORITY_SUBJECTS = ["나는솔로", "나솔", "나는솔로 사계", "나솔사계",
                     "이혼숙려캠프", "이혼숙려", "이호선", "오은영",
                     # ★2026-08-10 에디님 추가. 중복 방지로 나솔·이숙캠 인물이 제외되는 날에도
                     #   연예 슬롯(4편)을 채우려면 후보 프로그램이 더 필요하다.
                     "모솔N돌싱", "모솔연애"]

PICK_PROMPT = """당신은 'AI 실전' 블로거 '에디'입니다(40대, 코딩 몰라도 AI로 먹고삼).
아래는 지금 네이버에서 화제인 연예 랭킹뉴스입니다. 이 중 '연예인 후킹 → AI 실전 정보'로
정직하게 이어지는 이슈 1개를 고르세요. 후킹은 셀럽, 알맹이는 '검색자가 따라 할 AI 활용법'입니다.

★가장 중요한 판단: '이 이슈를 미끼로 걸고, 본문에서 AI 활용법을 줘도 독자가 속았다고 느끼지 않는가?'
   연결이 억지스러우면(제목만 셀럽, 본문은 무관) 절대 고르지 말 것.

[★1순위 소재 — 아래가 기사 목록에 '있으면' 최우선으로 고른다(단, AI로 이을 수 있을 때).
 없으면 무시하고 일반 기준으로 고른다. 억지로 끼워 넣지 말 것]
{priority}

[AI로 자연스럽게 잇는 축 — 이 중 하나에 맞아야 함]
{axes}
  예) 'OO 배우 AI 화보 논란' → 나도 AI로 프로필/화보 만드는 법
      'OO 부업으로 월 얼마' → 40대가 AI로 부업하는 현실적 방법
      'OO 유튜브 시작' → 코딩 몰라도 AI로 영상·콘텐츠 만드는 법

[피할 것] 사망·중대 범죄·자극적 사생활·단순 외모/가십처럼 AI로 이을 구실이 없는 것. 억지 연결.
[힌트가 있으면 우선] {hint}

[★이미 다룬 인물 — 절대 다시 고르지 말 것(다른 인물로)]
{exclude}

[기사 목록]
{news}

[출력 — JSON 한 개만, 큰따옴표, 설명 금지]
{{"번호":정수(적합한 게 없으면 0),
 "인물":"핵심 인물명",
 "셀럽후킹":"기사에서 미끼로 쓸 사실 한 줄(기사에 실제로 있는 것만)",
 "AI주제":"이 후킹에서 이어질 AI 실전 주제 한 줄(에디가 가르칠 것 — 예: 'AI로 인물 프로필 사진 만들기', 'AI 블로그 자동화 부업')",
 "연결강도":"상|중|하 (하면 번호 0으로)",
 "연결설명":"셀럽→AI가 왜 자연스러운지 한 줄",
 "검색키워드":"본문에 반복할 AI 검색어(예: 'AI 프로필 만들기', 'AI 부업')",
 "매체":"출처 표기용 기사 매체/방송사",
 "프로그램":"셀럽 장면을 유튜브에서 찾게 — 프로그램명+방송사 또는 채널명(기사에 명시된 것만, 없으면 '')",
 "표제목":"본문 AI 정보/비교 표 제목(예: 'AI 프로필 앱 3종 비교', 'AI 부업 시작 4단계')"}}
"""

BODY_PROMPT = """당신은 'AI 실전' 블로거 '에디'입니다. 지금 뜨는 연예 이슈를 후킹으로 걸되,
본문은 검색하는 사람이 진짜 따라 할 수 있는 'AI 실전 정보'를 주는 글을 씁니다.
셀럽은 미끼일 뿐, 알맹이는 AI 활용법 + 직접 해본 경험입니다. 2026년 네이버는 'AI가 다 쓴 대량 글'을
저품질로 잡습니다 — 그래서 실전 정보 + 경험이 핵심입니다.

{profile}

{story}

[후킹으로 쓸 셀럽 이슈 — 기사 사실 재료. 이 범위 안에서만, 없는 사실 지어내지 말 것]
제목: {art_title}
본문: {art_body}
[미끼 포인트] {celeb_hook}

[이 글이 진짜 전할 것 = AI 주제] {ai_topic}
[검색 키워드(제목·본문에 자연스럽게 반복)] {search_kw}

★제목·본문 일치 원칙: 셀럽으로 후킹하되, 도입 3~5줄 안에 반드시 AI 주제로 자연스럽게 넘어간다.
   "그런데 사실 이거, 요즘은 누구나 AI로 됩니다" 식의 정직한 다리. 끝까지 셀럽 가십만 하다 끝내지 말 것.

[오늘 연예 홈판에서 잘되는 글의 본문 공식 — 이 흐름·리듬을 참고(어투는 존댓말 유지)]
{body_formula}

[본문 구조 — 이 뼈대 그대로]
1. 도입 후킹(2~3줄): 지금 화제인 셀럽 이슈 → "그런데 진짜 눈에 띈 건 ○○(AI)". 계속 읽을 이유. ("안녕하세요 오늘은~" 금지)
2. 다리 놓기(2~3줄): 이 이슈가 왜 AI 얘기로 이어지는지. 정직하게. (억지 연결이면 차라리 담백하게)
3. ★핵심 실전 정보: 검색자가 원하는 AI 활용법을 구체적으로 — 단계·도구·비교. (이게 본문의 8할)
4. 2026 현실·주의점: 함정도 알려준다(신뢰 = 파는 사람이 아니라 겪은 사람). 무료/유료, 한계.
5. 정리(불릿 3개)
6. 질문형 CTA(댓글 유도) + 유튜브 @AI생존기Edi 연결

[반드시 지킬 것]
- ★★어투 고정: **존댓말('~합니다/~습니다')로 끝까지 통일.** 반말·평서체(`~다`, `~더라`, `~하자`) 절대 금지.
- ★연예인과 '나'를 우열로 비교하지 말 것. 연예인의 어려움·생계·실패를 깔고 내 성공을 자랑하는 톤 금지.
  연예 이슈는 후킹(현상의 문)일 뿐, 본문 알맹이는 독자에게 주는 AI 방법.
- ★지어내기 금지: AI 툴 기능·수치·가격은 확실한 것만. 불확실하면 '알려진 바로는'·'제 경우엔' 톤, 단정 금지.
  셀럽 사실도 기사에 있는 것만.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지(이모지는 소제목에 한두 개만).
- 본문에 마커 포함:
  [사진N - 화면/장면 설명 / 출처: ...] 6~9개. 이 중 앞쪽 1~3개는 셀럽 장면, 나머지는 AI 활용 장면.
    · ★셀럽(연예인) 장면 사진 = 에디님이 직접 삽입한다(자동 첨부 안 됨). 그러니 **어느 방송/영상/화보의 어떤 장면인지 구체적으로** 적어
      에디님이 그 장면을 찾을 수 있게 한다. 출처는 프로그램명+방송사/채널로. 이 소재 프로그램="{program}", 매체="{media}".
      좋은 예: `출처: 나 혼자 산다(MBC)` / `출처: OOO 인스타그램(@계정)`. 나쁜 예(금지): `출처: SNS`, `출처: 방송`.
    · ★AI 활용 장면 사진은 반드시 `출처: 직접 촬영(해당 툴 화면)` 으로 적는다(이건 자동 첨부됨).
    · 두 종류의 출처 표기를 절대 섞지 말 것(셀럽=프로그램/채널, AI=직접 촬영).
  [표] (AI 방법/비교 표 1개. 내용은 아래 카드 JSON의 '표')
  ★경험 문단(중요): 빈 슬롯을 남기지 말고, 위 [에디의 실제 이야기]를 이 AI 주제와 자연스럽게 이은
    1인칭 경험 문단을 본문 1~2곳에 **직접 써 넣는다**(2~4문장). [에디의 실제 이야기] 밖의 구체 수치·날짜·사건은 지어내지 말 것.
    · ★빈 슬롯([[경험 보태기: …]])을 남기지 말고 완성된 문장으로 끝맺는다(2026-08-06).
- ★소주제 규칙(엄수): 소주제는 **[사진N] 바로 다음 줄에만** 놓는다. 3~5개, 짧은 명사형/의문형 한 줄(20자 이내, 마침표 없이).
  · 사진과 상관없는 자리에 소주제를 흘리지 말 것. 두 줄 연속 금지. 소주제 뒤엔 반드시 설명 본문이 이어져야 함.
  좋은 예: `왜 AI 화보가 화제일까` / `무료로 따라 하는 법` / `40대도 되나`
- 마지막: 짧은 면책(공개정보·개인 경험 기반), '?'로 끝나는 CTA 질문,
  "@출처 : {media} / 직접 운영 경험"(형식 그대로), 해시태그 10개(#로 시작, AI 검색키워드 포함).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["기준/단계","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"연예 X AI"}}}}
"""

TITLE_PROMPT = """너는 네이버 홈피드에 잘 뜨는 제목만 만드는 카피라이터다.
아래는 '연예인 후킹 → AI 실전'으로 이어지는 글이다. 제목도 그 다리를 정직하게 담아라(어그로 금지).

[셀럽 후킹] {celeb_hook}
[AI 주제] {ai_topic}
[검색 키워드] {search_kw}

[제목 원칙 — 연예 이슈는 '들어가는 문(후킹)', 약속은 독자에게]
- 연예인은 화제/현상으로만 건다. 제목의 알맹이는 '독자가 AI로 ~하는 법/정보'다.

[좋은 제목 뼈대 — 셀럽으로 열고, AI 정보는 '독자·방법'으로]
- "OO 화보가 화제…요즘은 셀카 몇 장이면 AI로 됩니다"
- "'OO도 유튜브' 시대, 코딩 몰라도 AI로 채널 만드는 법"
- "OO 이슈로 다시 뜬 그것, AI로 하면 이렇게 쉽습니다"

[★절대 금지]
- 연예인과 '나/나도/저도'를 나란히 비교하는 형 금지: "OO도 ~한데 나는 ~", "OO도 아닌 내가~", "OO도 ~…나도 따라".
- 연예인의 어려움·실패·생계 이야기를 미끼로 내 성공을 자랑하는 형 금지(예: "OO도 알바하는데 나는 AI로 벌었다"). 무례하게 읽힌다.
- 무명 화자를 연예인과 대등하게 놓지 말 것.

[공식 — 최소 2개 조합]
① 셀럽/화제로 열기 (OO 화보, 'OO도' 시대, OO 이슈)
② 독자를 향한 AI 방법·결과 (AI로 ~하는 법, 코딩 몰라도, 셀카 몇 장이면)
③ 궁금증·공감

규칙: 40자 이내 한 줄씩 5개. ★제목이 약속한 걸 본문이 준다(AI 활용법). 셀럽 가십만 약속하는 제목 금지.
글에 없는 수치 지어내지 말 것. 설명·번호 없이 제목만 한 줄씩.
"""

# ── 연예 70% + AI 30% 모드(스토리 중심) ──
BODY_PROMPT_STORY = """당신은 'AI 실전' 블로거 '에디'입니다. 이 글은 **연예인 이야기 70% + AI 이야기 30%** 비율입니다.
지금 화제인 연예 이슈를 '이야기 중심'으로 풀되, 끝부분에서 자연스럽게 에디의 AI 이야기로 이어 붙입니다.
연예 소비글로 끝내지 말고, 마지막엔 반드시 'AI로 이런 것도 된다'는 에디만의 관점을 남깁니다.

{profile}

{story}

[소재 기사 — 사실 재료. 이 범위 안에서만, 없는 사실 지어내지 말 것]
제목: {art_title}
본문: {art_body}
[핵심 인물] {person}
[미끼/화제 포인트] {celeb_hook}
[끝에 이을 AI 한 스푼] {ai_topic}

[오늘 연예 홈판에서 잘되는 글의 본문 공식 — 이 흐름·리듬을 참고(어투는 존댓말 유지)]
{body_formula}

[본문 구조 — 연예 70% / AI 30%]
1. 도입 후킹(2~3줄): 지금 왜 화제인지. 계속 읽을 이유. ("안녕하세요 오늘은~" 금지)
2. ★연예 이야기(본문의 약 70%): 인물의 근황·서사·이슈의 맥락을 이야기하듯 풍부하게.
   기사에 있는 사실로만. 왜 화제인지, 어떤 반응인지, 배경은 무엇인지 흐름 있게.
3. 자연스러운 다리(1~2줄): "그런데 이런 거, 요즘은 저 같은 사람도 AI로 해봅니다" 식으로 넘어감.
4. ★AI 이야기(본문의 약 30%): 이 맥락에 맞는 에디의 AI 활용을 가볍게. 깊은 튜토리얼 말고
   "AI로 이 정도는 됩니다 + 제 경험" 수준. (아래 경험 문단 포함)
5. 짧은 정리 + 질문형 CTA(댓글 유도) + 유튜브 @AI생존기Edi 연결

[반드시 지킬 것]
- ★★어투 고정: **존댓말('~합니다/~습니다')로 끝까지 통일.** 반말·평서체 금지.
- ★연예인과 '나'를 우열로 비교하지 말 것. 특히 연예인의 어려움·생계·실패를 깔고 내 성공을 자랑하는 톤 절대 금지.
  연예 이슈는 '현상·공감의 문'으로만 쓰고, AI 이야기는 독자에게 도움 주는 담백한 톤으로.
- ★지어내기 금지: 연예 사실은 기사 범위, AI 기능·수치는 확실한 것만.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지.
- 본문에 마커 포함:
  [사진N - 화면/장면 설명 / 출처: ...] 6~9개. 연예 비중이 높으니 셀럽 장면이 4~6개, AI 장면 2~3개.
    · ★셀럽(연예인) 장면 사진 = 에디님이 직접 삽입한다(자동 첨부 안 됨). 어느 방송/영상/화보의 어떤 장면인지 구체적으로.
      출처는 프로그램명+방송사/채널로. 이 소재 프로그램="{program}", 매체="{media}". 나쁜 예(금지): `출처: SNS`, `출처: 방송`.
    · ★AI 활용 장면 사진은 반드시 `출처: 직접 촬영(해당 툴 화면)`.
    · 두 종류의 출처 표기를 섞지 말 것.
  [표] (표 1개. 내용은 아래 카드 JSON의 '표')
  ★경험 문단: AI 이야기 파트에 위 [에디의 실제 이야기]를 이은 1인칭 경험 문단을 직접 써 넣는다(2~3문장). 지어낸 수치 금지.
    끝에 선택 슬롯 하나: [[경험 보태기: (구체 사례 있으면 한두 줄 — 없으면 지워도 됨)]]
- ★소주제 규칙: 소주제는 [사진N] 바로 다음 줄에만. 짧은 명사형/의문형 한 줄(20자 이내, 마침표 없이). 두 줄 연속 금지.
- ★마지막 줄(연예인 글 필수): 반드시 "@출처 : {media}" 형식으로 기사 매체/방송사를 밝힌다(비우지 말 것). 그 뒤 해시태그 10개.

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["항목","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"이슈 X AI"}}}}
"""

# ── 순수 연예(홈판 트래픽 전용, AI 0%) 모드 — 2026-07-31 '역할 분리(C)' ──
BODY_PROMPT_PURE = """당신은 네이버 홈피드에서 '연예 이슈·근황'으로 조회수를 끄는 블로거입니다.
목적은 오직 홈판 트래픽입니다. AI 얘기·자기 얘기·홍보는 절대 넣지 마세요. 순수하게 이 연예 이슈만 잘 풀어 씁니다.
단, 단순 가십 나열이 아니라 '검색자가 궁금해할 사실'을 정리해 끝까지 읽히게 합니다(DIA+).

[소재 기사 — 사실 재료. 이 범위 안에서만, 없는 사실·수치 지어내지 말 것]
제목: {art_title}
본문: {art_body}
[핵심 인물] {person}
[화제 포인트] {celeb_hook}

[오늘 연예 홈판에서 잘되는 글의 본문 공식 — 이 흐름·리듬 참고(어투는 존댓말)]
{body_formula}

[본문 구조 — 순수 연예]
1. 도입 후킹(2~3줄): 지금 왜 화제인지 즉시. 계속 읽을 이유. ("안녕하세요 오늘은~" 금지)
2. 무슨 일인지 사실 정리: 언제·누가·무엇을(기사 사실로만). 반응·배경도 흐름 있게.
3. 사람들이 궁금해하는 포인트: 이유·맥락·비하인드(기사 범위 안).
4. 짧은 정리 + 질문형 CTA(댓글 유도)
※ AI·부업·자동화·에디 개인 얘기·유튜브 홍보 전부 금지. 순수 연예로만.

[반드시 지킬 것]
- ★★어투 고정: 존댓말('~합니다/~습니다/~더라고요') 통일. 반말 금지.
- ★지어내기 금지: 기사에 있는 사실만. 억측·허위 금지. 사생활 비방·혐오 표현 금지.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지.
- 본문에 마커 포함:
  [사진N - 장면 설명 / 출처: ...] 6~9개. ★연예인 사진 = 에디님이 직접 삽입(자동첨부 안 됨).
    어느 방송/영상/화보의 어떤 장면인지 구체적으로. 출처는 프로그램명+방송사/채널. 이 소재 프로그램="{program}", 매체="{media}".
    나쁜 예(금지): `출처: SNS`, `출처: 방송`.
  [표] (정보/타임라인 표 1개. 내용은 아래 카드 JSON의 '표')
- ★소주제: [사진N] 바로 다음 줄에 짧은 명사형/의문형 한 줄(20자 이내, 마침표 없이). 두 줄 연속 금지.
- ★마지막 줄 필수: "@출처 : {media}"(기사 매체/방송사, 비우지 말 것). 그 뒤 해시태그 10개(#, 인물·프로그램명 포함).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["항목","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"연예 이슈"}}}}
"""

# ── 연예 90% + AI 10% (홈판 트래픽 온램프, AI 블로그에 살짝 걸치게) — 2026-07-31 ──
BODY_PROMPT_AI10 = """당신은 네이버 홈피드에서 '연예 이슈'로 조회수를 끄는 블로거입니다.
이 글은 **연예 90% + AI 10%**입니다. 90%는 순수 연예 이슈를 잘 풀고, 맨 끝에서 딱 한 번,
이 이슈와 자연스럽게 이어지는 'AI로 해볼 만한 것' 하나만 2~3문장 가볍게 얹습니다(억지면 생략).

[소재 기사 — 사실 재료. 이 범위 안에서만, 없는 사실 지어내지 말 것]
제목: {art_title}
본문: {art_body}
[핵심 인물] {person}
[화제 포인트] {celeb_hook}

[오늘 연예 홈판에서 잘되는 글의 본문 공식 — 흐름·리듬 참고(존댓말)]
{body_formula}

★★★도입부 절대 규칙(홈판 필수 — 어기면 글 전체를 버립니다):
  **첫 줄부터 곧바로 후킹으로 들어갑니다. 인사·자기소개는 글 어디에도 넣지 마세요.**
  · 금지: "안녕하세요", "여러분", "~입니다/이에요/예요"로 끝나는 자기소개, 필명·닉네임·캐릭터 이름.
  · ★특히 **없는 사람 이름을 지어내지 마세요**(실제 사고: "안녕하세요~ 햄찡이에요 🐹", "정리해 드리는 엘라입니다").
    이 블로그 필자는 '에디' 한 사람뿐이고, 그 이름조차 본문에 쓰지 않습니다.
  · 마무리에도 "○○이었어요" 같은 필명 사인오프 금지.
  · 지금 홈판에 뜨는 글들은 인사 없이 첫 문장부터 사건·장면·대사로 시작합니다. 그 방식만 따르세요.

[본문 구조 — 연예 90% / AI 10%]
1. 도입 후킹(2~3줄): 지금 왜 화제인지 즉시. 계속 읽을 이유. (인사·자기소개 없이 바로)
2. ★연예 이슈 본문(약 90%): 무슨 일인지·반응·배경·궁금 포인트를 사실로 풍부하게. 순수 연예로.
3. ★AI 10%(맨 끝 딱 1문단, 2~3문장): 이 이슈에서 자연스럽게 이어지는 'AI로 해볼 만한 것' 하나만 가볍게.
   예) 화보 이슈면 "요즘은 이런 사진, AI 프로필로도 만들 수 있습니다" 수준. 튜토리얼·자랑·홍보 금지. 억지면 생략.
4. 질문형 CTA(댓글)로 마무리. ★유튜브 채널 언급·홍보 금지(2026-08-02 에디님: 연예 글은 순수 홈판 트래픽용).

[반드시 지킬 것]
- ★★어투: 존댓말 통일. 반말 금지.

★★★'AI가 쓴 티' 제거(2026-08-06 에디님 지시, 홈판 위너 실측 기준) — 존댓말은 유지하되:
  [따라야 할 것] 문장을 짧게 툭툭 끊고 길이를 들쭉날쭉하게 / **구체적 숫자·이름·장면**을 넣기
    ("빠르다"(X) → "3분 만에 나왔습니다"(O)) / 모르는 건 모른다고 쓰기 / 곁가지를 조금 남기기.
  [금지] "또한·따라서·이처럼·뿐만 아니라·결론적으로·정리하자면" 같은 매끄러운 연결어,
    "~해보시기 바랍니다/도움이 되셨길 바랍니다" 교과서식 마무리,
    "정말 유용한·매우 효과적인·놀라운" 속 빈 수식어, 문단마다 똑같은 길이·리듬,
    항목마다 균일하게 3개씩 딱 떨어지는 나열.

- ★연예인과 '나' 우열 비교·자랑 금지. 연예 어려움 미끼로 자랑 금지.
- ★지어내기 금지: 연예 사실은 기사 범위, AI는 확실한 것만.
- 한 문장 45자 내외, 문단 1~2문장 + 여백. 마크다운 금지.
- 마커 형식(★엄수): `[사진N - 장면 설명 / 출처: 방송사 '프로그램' 회차(방송일) / 유튜브 검색: 검색어]`
  실제 예: `[사진3 - 상담 테이블에서 부부를 마주 본 이호선의 정색한 표정 / 출처: JTBC '이혼숙려캠프' {episode}({airdate}) / 유튜브 검색: {scene_q}]`
  · **세 칸(장면 / 출처 / 유튜브 검색)을 모두 채운다.** 하나라도 빠지면 에디님이 그 장면을 못 찾는다.
  · 회차·방송일은 위에 준 값을 쓰고, 기사에 없으면 그 괄호만 생략한다(지어내지 말 것).
  · '유튜브 검색' 칸은 **그대로 복사해 유튜브 검색창에 넣을 문구**다. 사진마다 조금씩 달라야 한다
    (예: 오프닝 자막 / 가사조사 공개 / 상담가 반응 처럼 그 장면 특유의 낱말을 넣는다).
  6~9개. ★사진은 **에디님이 직접 찾아 넣는다**(자동 삽입 안 함).
  · ★★**마커를 연달아 붙이지 말 것.** `[사진5]`·`[사진6]`을 붙여 쓰면 사진을 한 자리에 몰아 넣게 되어
    글이 '사진 덩어리 + 글 덩어리'로 갈린다. **마커 사이에는 반드시 본문이 1~2문단 들어간다.**
    글 끝에 남은 마커를 몰아 놓는 것도 금지 — 도입부터 마무리까지 고르게 흩는다.
  그러므로 마커만 보고 그 장면을 찾을 수 있어야 한다 — **어느 방송의 몇 회/어느 대목의 어떤 장면인지 구체적으로** 쓴다.
  · 장면 설명에는 **누가·무엇을 하는 장면인지**를 넣는다. 예: `[사진3 - 상담 중 눈물을 보이는 아내와 마주 앉은 이호선 / 출처: 이혼숙려캠프(JTBC)]`
  · 출처는 **프로그램명(방송사)** 또는 **채널명/인스타 계정**으로. 이 소재 프로그램="{program}", 매체="{media}".
  · ⛔모호한 출처 금지: `출처: 방송`, `출처: SNS`, `출처: 인터넷`, `출처: 유튜브`(채널명 없이) — 이러면 찾을 수 없다.
  · AI 장면이 있으면 그것만 `출처: 직접 촬영(해당 툴 화면)`. 두 종류 표기를 섞지 말 것.
  [표] 1개(정보/타임라인). 소주제는 [사진N] 다음 줄에만(20자 이내, 마침표 없이).
- ★마지막 줄 필수: "@출처 : {media}". 그 뒤 해시태그 10개(#, 인물·프로그램명 포함).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["항목","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"연예 이슈"}}}}
"""

TITLE_PROMPT_PURE = """너는 네이버 홈피드에 잘 뜨는 '연예 이슈' 제목만 만드는 카피라이터다.
목적은 오직 홈판 클릭이다. AI·부업·홍보 넣지 말고, 순수 연예 후킹으로 세게.

[핵심 인물] {person}
[화제 포인트] {celeb_hook}

[좋은 제목 뼈대 — 홈판 연예 위너식(강한 후킹)]
- "OO, 결국 이렇게 됐다…'○○' 발언에 술렁"
- "'충격 근황' OO, 알고 보니 이런 사정이"
- "OO가 왜 그랬나 했더니…뒤늦게 밝혀진 진짜 이유"

[공식 — 최소 2개 조합]
① 인물 + 화제(하차·근황·발언·논란·복귀 등)
② 궁금증·반전·충격 장치 (알고 보니, 진짜 이유, 결국, 뒤늦게)
③ 구체 팩트 살짝 (기사에 있는 것만)

규칙: 40자 이내 한 줄씩 5개. ★과장·허위 금지(기사 사실 범위). 사생활 비방·혐오 금지.
어그로여도 '제목=본문 일치'는 지킨다. 설명·번호 없이 제목만 한 줄씩.
"""

TITLE_PROMPT_STORY = """너는 네이버 홈피드에 잘 뜨는 제목만 만드는 카피라이터다.
아래는 '연예 이야기 중심(70%)'에 AI 한 스푼(30%)을 얹은 글이다. 제목도 연예 이슈가 앞서고 AI는 살짝 걸친다.

[핵심 인물] {person}
[화제 포인트] {celeb_hook}
[끝에 걸칠 AI] {ai_topic}

[좋은 제목 뼈대 — 연예 이슈가 메인, AI는 은근히(독자·현상 쪽으로)]
- "화제의 OO 이야기, 그 끝에 생각난 요즘 AI 활용 하나"
- "OO 근황이 남긴 질문…요즘 같은 때 준비하는 법"
- "다들 OO 소식에 공감한 이유, 그리고 지금 해볼 것"

[★절대 금지]
- 연예인과 '나/나도/저도'를 나란히 비교하지 말 것("OO도 ~한데 나는 ~", "OO도…나도 따라").
- 연예인의 어려움·생계·실패를 미끼로 내 성공을 자랑하지 말 것("OO도 알바하는데 나는 AI로 벌었다" 류 — 무례).
- 무명 화자를 연예인과 대등하게 놓지 말 것.

규칙: 40자 이내 한 줄씩 5개. ★제목=본문 일치(연예가 메인인 글이니 연예를 앞세우되 과장 금지).
글에 없는 수치·사실 지어내지 말 것. 설명·번호 없이 제목만 한 줄씩.
"""


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


def _sanitize(person: str, kw: str) -> str:
    base = f"{person}{kw}".replace(" ", "")
    s = re.sub(r"[^가-힣0-9A-Za-z]", "", base)
    return s[:20] or "연예AI"


PICK_PROMPT_PURE = """당신은 네이버 홈피드에서 조회수 잘 나오는 연예 이슈를 고르는 편집자입니다.
아래 연예 랭킹뉴스 중 '홈판에서 클릭 폭발할' 이슈 1개를 고르세요(AI 연결 불필요, 순수 연예 트래픽 목적).
좋은 소재 = 하차·복귀·논란·발언·충격 근황처럼 궁금증이 센 것.
★반드시 제외(에디님 지시): ①사망·부고·자살 ②범죄·수사·마약·음주운전·성범죄 ③비방·저격·명예훼손성 폭로. 이런 건 번호 0으로 거른다.

[★1순위 — 기사 목록에 있으면 최우선]
{priority}
[이미 다룬 인물 — 겹치지 말 것]
{exclude}
[기사 목록]
{news}

[출력 — JSON 한 개, 큰따옴표, 설명 금지]
{{"번호":정수, "인물":"핵심 인물명", "셀럽후킹":"기사에서 미끼로 쓸 사실 한 줄(기사에 있는 것만)",
 "매체":"출처 표기용 기사 매체/방송사",
 "프로그램":"장면을 찾게 — 프로그램명+방송사/채널(기사에 있는 것만, 없으면 '')",
 "회차":"방송 회차. 기사에 '94회'·'23기' 같은 표기가 있으면 그대로(없으면 '')",
 "방송일":"이 장면이 방송된 날. 기사에 '6일 오후 10시'처럼 있으면 YYYY-MM-DD로(없으면 '')",
 "장면검색어":"에디님이 유튜브에서 이 장면을 찾을 때 그대로 붙여넣을 검색어. 프로그램+인물+사건 핵심어 3~6단어 (예: '이혼숙려캠프 코인부부 이호선 상담')",
 "표제목":"본문 정보/타임라인 표 제목"}}
"""


def pick_article(news: list, hint: str = "", exclude_urls: set | None = None,
                 exclude_persons: set | None = None, relaxed: bool = False,
                 pure: bool = False) -> dict:
    """연예 이슈 1개 선정. pure=True면 순수 홈판 연예(AI 연결 불필요).
    exclude_persons: 이미 다룬 인물 반복 방지. relaxed=True(스토리)면 연결강도 '하'도 허용."""
    exclude_urls = exclude_urls or set()
    exclude_persons = set(exclude_persons or set())
    # ★중복 방지(2026-08-10 에디님 지적): exclude_persons는 '한 번 실행 안'에서만 유효했다.
    #   그래서 어제 옥순을 썼는데 오늘 또 옥순이 나왔다(실측: 최근 20편에 옥순×3·나는솔로×3·광수×2).
    #   → 발행된 연예 글 제목에서 최근 인물·프로그램을 읽어 함께 제외한다.
    try:
        import history
        exclude_persons |= history.recent_celeb_names()
    except Exception:  # noqa: BLE001
        pass
    avail = [a for a in news if a["url"] not in exclude_urls]
    if not avail:
        raise RuntimeError("남은 기사 없음(모두 소진)")
    listing = "\n".join(f"{i}. {a['title']} — {a['snippet']}" for i, a in enumerate(avail, 1))
    excl = ", ".join(sorted(p for p in exclude_persons if p)) or "(없음)"
    prio = ", ".join(PRIORITY_SUBJECTS)
    if pure:
        prompt = PICK_PROMPT_PURE.format(priority=prio, exclude=excl, news=listing)
    else:
        prompt = PICK_PROMPT.format(axes=BRIDGE_AXES, priority=prio, hint=hint or "(없음)",
                                    exclude=excl, news=listing)
    pick = _parse_json(run_claude_p(prompt, timeout=180))
    idx = int(pick.get("번호", 0) or 0)
    person = (pick.get("인물") or "").strip()
    if pure:
        if idx == 0 or not person:
            raise RuntimeError("홈판 연예 이슈 선정 실패")
    else:
        strength = (pick.get("연결강도") or "").strip()
        weak_ok = relaxed or strength != "하"
        if idx == 0 or not weak_ok or not pick.get("AI주제"):
            raise RuntimeError("AI로 자연스럽게 이을 셀럽 이슈 없음(억지 연결 회피 → 슬롯 포기)")
    if person and person in exclude_persons:
        raise RuntimeError(f"이미 다룬 인물({person}) 재선정 → 스킵")
    if not (1 <= idx <= len(avail)):
        raise RuntimeError("기사 선정 실패(번호 범위)")
    # ★안전망: 사망·범죄·비방 소재는 모델이 골라도 거른다(에디님 지시)
    check = f"{avail[idx - 1].get('title','')} {pick.get('셀럽후킹','')} {avail[idx - 1].get('snippet','')}"
    if _BLOCK_RE.search(check):
        raise RuntimeError(f"제외 소재(사망·범죄·비방) 감지 → 스킵: {avail[idx-1].get('title','')[:24]}")
    pick["url"] = avail[idx - 1].get("url", "")
    pick["뉴스제목"] = avail[idx - 1]["title"]
    pick["뉴스본문"] = avail[idx - 1].get("body", "") or avail[idx - 1].get("snippet", "")
    return pick


def _source_label(media: str, program: str = "") -> str:
    """맨 끝 '@출처' 줄에 쓸 문구 — **방송사 + 프로그램명**까지 (2026-08-11 에디님 지시).

    예전엔 매체만 써서 `@출처 : MBC` 처럼 나왔다. 오은영처럼 여러 프로그램에 나오는 인물은
    이러면 어느 방송을 인용했는지 알 수 없다("오은영은 오은영리포트 결혼지옥에 많이 나오니까
    마지막 출처에 이것도 넣어달라"). → `@출처 : MBC '오은영 리포트-결혼 지옥'`.
    프로그램 문자열에 이미 방송사가 괄호로 붙어 있으면(예 "…(MBC)") 중복 없이 정리한다.
    """
    m = (media or "").strip()
    prog = (program or "").strip()
    if not prog:
        return m or "연예 기사"
    # "오은영 리포트-결혼 지옥(MBC)" → 프로그램명 / 채널 분리
    inner = re.search(r"\(([^)]+)\)\s*$", prog)
    chan_in_prog = inner.group(1).strip() if inner else ""
    prog_name = re.sub(r"\s*\([^)]*\)\s*$", "", prog).strip()
    chan = m or chan_in_prog
    if not prog_name:
        return chan or "연예 기사"
    if chan and chan not in prog_name:
        return f"{chan} '{prog_name}'"
    return f"'{prog_name}'"


def _ensure_source_line(body: str, media: str, program: str = "") -> str:
    """맨 끝에 `@출처 : 방송사 '프로그램'` 줄을 보장한다.

    ⚠️**'출처'를 본문 전체에서 찾으면 안 된다**(2026-08-11 실측 버그). 사진 마커가
    `[사진1 - … / 출처: MBC '오은영 리포트' 180회]` 형태라서, 전체 검색으로는
    ①"이미 출처가 있다"고 오판해 끝 줄을 아예 안 붙이고
    ②보강 치환이 **사진 마커를 덮어쓴다**.
    → 반드시 **줄 시작이 `@출처`/`출처`인 줄**만 대상으로 한다.
    """
    src = _source_label(media, program)
    prog_name = re.sub(r"\s*\([^)]*\)\s*$", "", (program or "").strip()).strip()
    lines = body.rstrip().splitlines()
    head = re.compile(r"^\s*@?\s*출처\s*[:：]\s*(.*)$")
    for k, ln in enumerate(lines):
        m = head.match(ln)
        if not m:
            continue
        cur = m.group(1).strip()
        # 매체만 적혀 있으면 프로그램명까지 채운다(오은영처럼 여러 프로그램에 나오는 인물 대비)
        if not cur or (prog_name and prog_name not in cur):
            lines[k] = f"@출처 : {src}"
        return "\n".join(lines)
    # 없으면 해시태그 줄 앞에 새로 넣는다
    ins_at = len(lines)
    for k in range(len(lines) - 1, -1, -1):
        if lines[k].strip().startswith("#"):
            ins_at = k
        elif lines[k].strip():
            break
    lines.insert(ins_at, f"@출처 : {src}")
    return "\n".join(lines)

def _is_anon_person(person: str) -> bool:
    """이름으로 얼굴을 특정할 수 없는 출연자인가(일반인·가명)."""
    p = (person or "").strip()
    if not p:
        return True
    if _ANON_RE.search(p):
        return True
    return any(n in p for n in _ANON_NAMES)


_BLOCK_RE = re.compile(
    r"사망|별세|부고|숨져|숨진|타계|영면|빈소|자살|극단적\s*선택|투신|"
    r"구속|체포|기소|송치|입건|피의자|혐의|수사|경찰\s*조사|검찰|"
    r"마약|대마|필로폰|음주운전|성범죄|성추행|성폭행|성희롱|불법촬영|몰카|"
    r"폭행|폭력|학폭|사기\s*혐의|횡령|고소|고발|명예훼손|저격|폭로전")


_PHOTO_LINE = re.compile(r"^\s*\[사진\s*\d+")
_TAIL_LINE = re.compile(r"^\s*(@?\s*출처\s*[:：]|#)")


def _spread_photo_markers(body: str, log=print) -> str:
    """★사진 마커를 본문 사이사이로 고르게 흩는다 (2026-08-11 에디님 지적).

    실측: 핑퐁 편에서 `[사진5]`·`[사진6]`·`[사진7]`이 본문 없이 줄줄이 붙어 나왔다
    (마커 7개 중 2·2·3개씩 뭉침). 그러면 사진을 한 자리에 몰아 넣게 되고 글이
    '사진 덩어리 + 글 덩어리'로 갈린다(체험단 블로그의 IMG IMG 문제와 같다).

    프롬프트로도 금지하지만 LLM이 종종 어기므로 코드로 강제한다.
    ⚠️처음엔 '연속된 마커를 뒤쪽 빈자리로 한 칸씩 밀기'로 했는데, **뒤에 본문이 없으면
    갈 곳이 없어 그대로 쌓였다**(재배치 40회를 돌고도 3개 뭉침 잔존). → 지금은 마커를 전부 뽑아
    **본문 문단 사이에 균등 배치**한다. 문단 수보다 마커가 많으면 남는 마커는 버린다
    (앞뒤에 글이 없는 사진 자리는 어차피 쓸모가 없다).
    `@출처`·해시태그 줄 뒤로는 절대 보내지 않는다.
    """
    chunks = [l.strip() for l in body.split("\n") if l.strip()]
    if not chunks:
        return body
    tail_i = next((i for i, c in enumerate(chunks) if _TAIL_LINE.match(c)), len(chunks))
    head, tail = chunks[:tail_i], chunks[tail_i:]
    marks = [c for c in head if _PHOTO_LINE.match(c)]
    content = [c for c in head if not _PHOTO_LINE.match(c)]
    if len(marks) < 2 or len(content) < 2:
        return body
    # 이미 잘 흩어져 있으면 건드리지 않는다(원래 배치가 문맥상 더 자연스럽다)
    orig = [bool(_PHOTO_LINE.match(c)) for c in head]
    if not any(orig[k] and orig[k + 1] for k in range(len(orig) - 1)):
        return body

    # 배치 가능한 간격: content 사이(1..len(content)-1). 제목 줄 바로 뒤(=0)는 피한다.
    slots = list(range(1, len(content)))
    keep = marks[:len(slots)]
    dropped = len(marks) - len(keep)
    step = len(slots) / len(keep)
    at = {slots[min(int(k * step), len(slots) - 1)]: m for k, m in enumerate(keep)}

    out: list = []
    for k, c in enumerate(content):
        if k in at:
            out.append(at[k])
        out.append(c)
    # 번호 재정렬
    n = 0
    for k, c in enumerate(out):
        if _PHOTO_LINE.match(c):
            n += 1
            out[k] = _PHOTO_LINE.sub(f"[사진{n}", c, count=1)
    log(f"  사진 마커 {len(keep)}개를 본문 사이로 균등 재배치"
        + (f" (자리 부족으로 {dropped}개 제거)" if dropped else ""))
    return "\n\n".join(out + tail)

def _enrich_photo_sources(body: str, media: str, program: str, episode: str,
                          airdate: str, scene_q: str, log=print) -> str:
    """★사진 마커의 출처를 '찾을 수 있는' 형태로 보정한다(2026-08-10 에디님 지시).

    에디님이 실제 발행글에서 지적: `출처: 이혼숙려캠프(JTBC)` 만 있으면 **몇 회차의 어느 장면인지
    몰라 유튜브에서 찾을 수가 없다**. 프롬프트로 형식을 지시해도 LLM은 종종 빠뜨리므로
    (이 저장소의 다른 규칙들처럼) 코드로 한 번 더 막는다.

    - `유튜브 검색:` 칸이 없으면 붙인다. 검색어는 장면 설명의 낱말을 섞어 사진마다 달라지게 한다.
    - 회차·방송일이 있는데 출처에 없으면 끼워 넣는다(없으면 건드리지 않는다 — 지어내기 금지).
    """
    prog = re.sub(r"\s*\(.*?\)", "", program or "").strip() or (media or "")
    fixed = 0

    def _one(m):
        nonlocal fixed
        inner = m.group(1)
        if "직접 촬영" in inner:          # AI 툴 화면은 자동첨부 대상 → 그대로
            return m.group(0)
        parts = [p.strip() for p in inner.split("/")]
        scene = parts[0] if parts else inner
        src = next((p for p in parts if p.startswith("출처")), "")
        has_q = any("검색" in p for p in parts)
        # 회차·방송일 보강
        if src and episode and episode not in src:
            src = src + f" {episode}" + (f"({airdate})" if airdate and airdate not in src else "")
        if not has_q:
            # 장면 설명에서 특징 낱말 2개를 뽑아 검색어를 사진마다 다르게 만든다
            # 장면 설명에서 그 사진만의 특징어 1~2개를 뽑아 검색어를 사진마다 다르게 만든다.
            _stop = ("사진", "모습", "장면", "표정", "화면", "직후", "당시", "이후")
            _tail = re.compile(r"(에서|으로|에게|한테|까지|부터|은|는|이|가|을|를|의|에|로|와|과|도|만)$")
            words = []
            for w in re.findall(r"[가-힣]{2,}", re.sub(r"^\s*사진\d+\s*-\s*", "", scene)):
                w2 = _tail.sub("", w)
                if len(w2) >= 2 and w2 not in _stop and w2 not in words:
                    words.append(w2)
                if len(words) >= 2:
                    break
            base = scene_q or " ".join(x for x in [prog, episode] if x)
            q = (base + " " + " ".join(words)).strip()
            new_inner = " / ".join([p for p in [scene, src or f"출처: {prog}"] if p] + [f"유튜브 검색: {q}"])
            fixed += 1
            return "[" + new_inner + "]"
        if src != next((p for p in parts if p.startswith("출처")), ""):
            fixed += 1
            return "[" + " / ".join([scene, src] + [p for p in parts[2:]]) + "]"
        return m.group(0)

    out = re.sub(r"\[(사진\d+[^\]]*)\]", _one, body)
    if fixed:
        log(f"  사진 출처 보정 {fixed}곳(회차·유튜브 검색어 추가)")
    return out


def _write_one(out_dir: str, no: str, pick: dict, log=print, mode: str = "ai_hook",
               thumb_formula: str = "", story_title_ai: bool | None = None,
               body_formula: str = "") -> dict:
    person = pick.get("인물", "")
    celeb_hook = pick.get("셀럽후킹", pick.get("뉴스제목", ""))
    ai_topic = pick.get("AI주제", "")
    search_kw = pick.get("검색키워드", ai_topic)
    # 매체는 비면 프로그램/뉴스제목로 폴백(연예 글 끝 출처 표기 필수)
    media = (pick.get("매체") or "").strip() or (pick.get("프로그램") or "").strip() or "연예 기사"
    program = pick.get("프로그램", "")
    table_title = pick.get("표제목", f"{search_kw} 핵심 정리")
    keyword = _sanitize(person, search_kw)
    story_mode = (mode == "celeb_story")
    pure_mode = (mode == "celeb_pure")
    ai10_mode = (mode == "celeb_ai10")

    _tag0 = ("순수연예" if pure_mode else "연예90/AI10" if ai10_mode
             else "연예70/AI30" if story_mode else "AI접목")
    log(f"[{no}] 기사 본문 확보 → {_tag0} 본문 생성: {person} → {(ai_topic or celeb_hook)[:20]}")
    # URL 있으면 기사 전문, 없으면(검색 스니펫 소재) 스니펫을 본문 재료로
    if pick.get("url"):
        art = S.fetch_article(pick["url"])
    else:
        art = {"title": pick.get("뉴스제목", ""), "body": pick.get("뉴스본문", "")}
    # ★art_title은 아래 캡처 컨텍스트(기수 추출)에서도 쓰므로 지역변수로 잡아둔다.
    #   (2026-08-06 버그: 651줄이 bare art_title을 참조해 NameError로 연예편 전멸)
    art_title = art.get("title") or pick.get("뉴스제목", "")
    bf = (body_formula or "").strip() or "(오늘 공식 없음 — 아래 뼈대를 따를 것)"
    # ★사진 출처를 '찾을 수 있게' 만드는 재료(2026-08-10 에디님 지시).
    #   `출처: 이혼숙려캠프(JTBC)`만 있으면 몇 회차·어느 장면인지 몰라 유튜브에서 찾을 수 없다.
    #   → 회차·방송일·검색어를 뽑아 마커에 함께 박는다. 없으면 빈칸(지어내지 않는다).
    _src = f"{art_title} {celeb_hook} {(art.get('body') or '')[:400]}"
    episode = (pick.get("회차") or "").strip()
    if not episode:
        _m = re.search(r"(\d{1,3}\s*회|\d{1,2}\s*기)", _src)
        episode = _m.group(1).replace(" ", "") if _m else ""
    airdate = (pick.get("방송일") or "").strip()
    scene_q = (pick.get("장면검색어") or "").strip() or " ".join(
        x for x in [re.sub(r"\s*\(.*?\)", "", program or "").strip(), episode, person] if x)
    if pure_mode or ai10_mode:
        _pt = BODY_PROMPT_AI10 if ai10_mode else BODY_PROMPT_PURE
        prompt = _pt.format(
            body_formula=bf, art_title=art_title,
            art_body=(art.get("body") or "")[:2400],
            person=person, celeb_hook=celeb_hook,
            media=media, program=program or "(기사에 프로그램 명시 없음)", table_title=table_title,
            episode=episode or "(회차 미상)", airdate=airdate or "방송일 미상", scene_q=scene_q)
    elif story_mode:
        prompt = BODY_PROMPT_STORY.format(
            profile=EDI_AI_PROFILE, story=EDI_STORY, body_formula=bf,
            art_title=art_title,
            art_body=(art.get("body") or "")[:2400],
            person=person, celeb_hook=celeb_hook, ai_topic=ai_topic,
            media=media, program=program or "(기사에 프로그램 명시 없음)", table_title=table_title)
    else:
        prompt = BODY_PROMPT.format(
            profile=EDI_AI_PROFILE, story=EDI_STORY, body_formula=bf,
            art_title=art_title,
            art_body=(art.get("body") or "")[:2200],
            celeb_hook=celeb_hook, ai_topic=ai_topic, search_kw=search_kw,
            media=media, program=program or "(기사에 프로그램 명시 없음)",
            table_title=table_title)
    body, cards = "", {}
    for k in range(3):
        body, cards = _parse_body(run_claude_p(prompt, timeout=320))
        if body and cards and len(body.strip()) >= 300:
            break
        log(f"[{no}] 본문 재시도 {k+1}/3 (길이 {len(body.strip())})")
    if not body or not cards or len(body.strip()) < 300:
        raise RuntimeError(f"본문 생성 실패(재시도 소진, 길이 {len(body.strip())})")
    body = _ensure_source_line(body, media, program)   # 연예인 글 끝 출처(방송사+프로그램) 보장
    if pure_mode or ai10_mode:                # 사진을 직접 찾아 넣으므로 출처를 최대한 자세히
        body = _enrich_photo_sources(body, media, program, episode, airdate, scene_q, log)
        body = _spread_photo_markers(body, log)   # 마커가 줄줄이 붙지 않게

    # 제목: 모드에 맞는 프롬프트로 후킹 5개(첫 개 사용, 나머지 사이드카)
    titles = []
    try:
        if pure_mode or ai10_mode:   # 90/10도 제목은 연예 후킹(AI 안 넣음)
            import history
            _recent = history.recent_titles(60, log)
            out = run_claude_p(TITLE_PROMPT_PURE.format(
                person=person, celeb_hook=celeb_hook)
                + "\n\n" + history.prompt_block(_recent), timeout=150)
        elif story_mode:
            out = run_claude_p(TITLE_PROMPT_STORY.format(
                person=person, celeb_hook=celeb_hook, ai_topic=ai_topic), timeout=150)
        else:
            out = run_claude_p(TITLE_PROMPT.format(
                celeb_hook=celeb_hook, ai_topic=ai_topic, search_kw=search_kw), timeout=150)
        titles = [_clean_title(l) for l in out.splitlines() if l.strip()]
        bad = re.compile(r"^제목|제목만|제목\s*\d|개입니다|출력|구분자|형식|규칙|^다음|다음과|^아래|번호 없|설명 없|공식|드립니다|나열|"
                         r"뽑았|서로 다른 구조|후보입니다|후보를|버전으로 뽑|개 뽑|개를 뽑|구조로 뽑|골랐습니다|만들었습니다|작성했습니다")
        titles = [t for t in titles if 6 <= len(t) <= 45 and not bad.search(t)][:5]
    except Exception as e:  # noqa: BLE001
        log(f"[{no}] 제목 생성 실패(본문 제목 유지): {e}")
    # 스토리 모드에서 '제목에 AI 넣기/빼기'가 지정되면 후보 중 조건에 맞는 걸 앞으로
    if story_mode and story_title_ai is not None and titles:
        want = [t for t in titles if bool(_AI_TITLE_SIG.search(t)) == story_title_ai]
        if want:
            titles = [want[0]] + [t for t in titles if t != want[0]]
            log(f"[{no}] 제목 스타일: {'AI 포함' if story_title_ai else '순수 연예'} 선택")
    if titles:
        body = _set_title_line(body, titles[0])
        log(f"[{no}] 제목 → {titles[0]}")

    # 홈판 규칙: 생성 단계에서 인사·자기소개 도입 제거.
    #  (연예편도 LLM이 '여러분의…, 정리해 드리는 OO입니다' 식 지어낸 자기소개를 붙인 사례가 있었음.)
    from pipeline import _strip_greeting_intro
    body = _strip_greeting_intro(body)

    os.makedirs(out_dir, exist_ok=True)
    G.clear_no(out_dir, no)
    with open(os.path.join(out_dir, f"{no}_{keyword}_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    # ai.flag: AI접목/스토리만. 순수 연예·90:10(연예 90%)은 연예-우세라 표식 안 함.
    if not (pure_mode or ai10_mode):
        open(os.path.join(out_dir, f"{no}_{keyword}_ai.flag"), "w").close()
    if titles:
        with open(os.path.join(out_dir, f"{no}_{keyword}_제목후보.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(titles))
    T.write_celeb_table(out_dir, no, keyword, cards.get("표제목", table_title), cards.get("표", []))
    # ★★2026-08-07 에디님 지시 — 연예편 이미지 자동첨부 전면 중단(옛 자리표시자 방식 복귀).
    #   이유: 자동 캡처가 엉뚱한 화면을 붙인다. 실측 사고 —
    #     · 이호선이 출연한 **옛 JTBC 토크쇼(성재기 회차)** 캡처가 이혼숙려캠프 글 대표사진으로 들어감
    #     · '31기 막방 LIVE' **예고 그래픽**, **다른 기수·다른 출연자**(솔로 리액션 광수)가 28기 옥순 글에 들어감
    #   틀린 이미지를 지우고 다시 넣는 게 처음부터 넣는 것보다 힘들다는 게 에디님 판단.
    #   → 이미지·썸네일을 **아무것도 만들지 않고**, 본문의 `[사진N - 장면 / 출처: …]` 마커만 남긴다.
    #     (pipeline._fill_celeb_captures는 캡처 파일이 없으면 마커를 그대로 보존한다)
    #   다시 켜려면 CELEB_AUTO_PHOTOS = True. 켜기 전에 '지정 프로그램 화면인지 / 예고 그래픽 아닌지 /
    #   기수가 맞는지'를 판정하는 검증(_scene_ok)을 먼저 붙여야 한다.
    if (pure_mode or ai10_mode) and not CELEB_AUTO_PHOTOS:
        log(f"[{no}] 연예편 이미지 자동첨부 OFF(에디님 지시) — "
            "[사진N] 자리표시자 + 출처만 남깁니다. 사진은 직접 삽입.")
        log(f"[{no}] 완료 → {person} ({_tag0})")
        try:                   # ★현재 기본 경로 — 인물 기록을 빠뜨리면 내일 또 같은 인물이 나온다
            import history
            history.mark_celeb_used(person)
            history.mark_celeb_used(program)
        except Exception:  # noqa: BLE001
            pass
        return {"no": no, "person": person, "ai_topic": ai_topic, "keyword": keyword,
                "titles": titles, "mode": mode}
    WANT = 13
    got = 0
    # ★검색 컨텍스트 = 프로그램명 + 기수(2026-08-03 사고 대응).
    #   '나는 솔로' 출연자는 옥순·영숙·영수처럼 **기수마다 반복되는 가명**이라, 이름만으로 검색하면
    #   32기 옥순 대신 다른 기수 옥순이나 아예 영숙 사진이 딸려온다. 기사 제목·본문에서 기수를 뽑아 고정한다.
    _gi = re.search(r"(\d{1,2})\s*기", f"{art_title} {celeb_hook} {program}")
    _ctx = " ".join(x for x in [program, (_gi.group(0).replace(" ", "") if _gi else "")] if x).strip()
    if _ctx:
        log(f"[{no}] 캡처 검색 컨텍스트: '{_ctx}' + '{person}'")
    # ★익명 출연자 판별(2026-08-06): 이혼숙려캠프 '23기 부부'·나는솔로 '28기 옥순'처럼
    #   일반인·가명이면 이름으로 얼굴 검증이 불가능해 캡처가 0장으로 끝난다(영상 20개 헛돌이 실측).
    #   이 경우 프로그램 검색 + 프레임 품질로 채택하고, 인물 확인은 에디님 검토에 맡긴다.
    _anon = bool(_is_anon_person(person))
    if _anon:
        log(f"[{no}] 익명·가명 출연자('{person}') → 얼굴 검증 생략, 프로그램 영상 프레임으로 채택. "
            "★발행 전 인물이 맞는지 확인하세요.")
    try:
        import celeb_video
        picked = celeb_video.fetch_multi(person or program, out_dir, f"{no}_{keyword}",
                                         want=WANT, log=log, context=_ctx, anon=_anon)
        # pipeline이 찾는 이름(`_연예캡처N`)으로 맞춘다. 캡처는 png라 확장자를 유지한다.
        for k, item in enumerate(picked):
            src = item["path"]
            ext = os.path.splitext(src)[1] or ".png"
            dst = os.path.join(out_dir, f"{no}_{keyword}_연예캡처{k+1}{ext}")
            try:
                os.replace(src, dst); got += 1
            except OSError:
                pass
        log(f"[{no}] 유튜브 영상 캡처 {got}장 확보")
    except Exception as e:  # noqa: BLE001
        log(f"[{no}] 영상 캡처 실패(썸네일 방식으로 보충): {str(e)[:80]}")
    if got < WANT:
        try:
            import celeb_image
            celeb_image.fetch_celeb_images(person, (_ctx or program), out_dir, f"{no}_{keyword}",
                                           n=WANT - got, start=got + 1, log=log)
        except TypeError:
            # start 인자를 지원하지 않는 구버전이면 기존 방식(덮어쓰기 방지 위해 캡처 없을 때만)
            if got == 0:
                import celeb_image
                celeb_image.fetch_celeb_images(person, (_ctx or program), out_dir, f"{no}_{keyword}",
                                               n=WANT, log=log)
        except Exception as e:  # noqa: BLE001
            log(f"[{no}] 연예인 참고이미지 보충 실패(무시): {str(e)[:80]}")
    # ★썸네일 = 확보한 '실제 방송 캡처' 1장 그대로(2026-08-02 에디님: 여기선 사진만, 텍스트 얹기 없음).
    #  이전엔 제미나이 생성 이미지를 썼는데 실존 인물이 아닌 '가짜 부부'가 대표사진으로 올라갔다(08-02 사고).
    #  캡처가 하나도 없을 때만 옛 생성 방식으로 폴백한다.
    thumb = cards.get("썸네일", {})
    fn = f"{no}_{keyword}_썸네일.png"
    _cap1 = next((p for p in (os.path.join(out_dir, f"{no}_{keyword}_연예캡처1{e}")
                              for e in (".png", ".jpg")) if os.path.exists(p)), "")
    if _cap1:
        try:
            import shutil
            from PIL import Image
            Image.open(_cap1).convert("RGB").save(os.path.join(out_dir, fn))
            log(f"[{no}] 썸네일 = 방송 캡처 1번(사진 그대로)")
        except Exception:  # noqa: BLE001
            shutil.copyfile(_cap1, os.path.join(out_dir, fn))
            log(f"[{no}] 썸네일 = 방송 캡처 1번(복사)")
    elif pure_mode or ai10_mode:
        # ★연예편에서 캡처가 0장이면 '생성 이미지' 폴백을 쓰지 않는다(2026-08-06 보강).
        #   08-02 사고: 실존 인물이 아닌 '가짜 부부' 생성 이미지가 대표사진으로 올라갔다.
        #   특히 이혼숙려캠프처럼 **출연자가 일반인·비공개**면 얼굴 캡처가 안 잡혀 이 경로로 빠진다.
        #   → 사람 이미지를 만들지 않는 '텍스트 썸네일'로만 폴백하고, 로그로 수동 교체를 요청한다.
        T.render_text_thumbnail(out_dir, fn, thumb)
        log(f"[{no}] !! 방송 캡처 0장 → 텍스트 썸네일로 대체. "
            "생성 이미지(가짜 인물) 폴백은 막았습니다 — 에디님이 실제 방송 캡처로 교체하세요.")
    elif not gemini_thumb.make_from_article(out_dir, fn, body, log=log, ref_formula=thumb_formula):
        if not gemini_thumb.make_from_thumb(out_dir, fn, thumb, query_hint=(ai_topic or celeb_hook), log=log):
            T.render_text_thumbnail(out_dir, fn, thumb)
    log(f"[{no}] 완료 → {person} ({_tag0})")
    try:                       # 이번에 다룬 인물 기록 → 다음 며칠간 제외 대상
        import history
        history.mark_celeb_used(person)
        history.mark_celeb_used(program)
    except Exception:  # noqa: BLE001
        pass
    return {"no": no, "person": person, "ai_topic": ai_topic, "keyword": keyword,
            "titles": titles, "mode": mode}


def build_pure_pool(log=print) -> list:
    """순수 연예 후보 풀 = 연예 랭킹뉴스 + 1순위 소재 능동 검색(오늘 랭킹에 없어도 포함).
    랭킹 기사(url O=기사전문) + 검색 기사(url ''=스니펫 소재)를 합쳐 dedup."""
    pool: list = []
    try:
        pool.extend(S.fetch_news_ranking(30))
    except Exception as e:  # noqa: BLE001
        log(f"랭킹뉴스 수집 실패: {str(e)[:60]}")
    for subj in PRIORITY_SUBJECTS:
        try:
            found = S.fetch_news_search(subj, 3)
            if found:
                pool.extend(found)
                log(f"1순위 '{subj}' 뉴스 {len(found)}건 추가")
        except Exception as e:  # noqa: BLE001
            log(f"'{subj}' 검색 실패(무시): {str(e)[:50]}")
    # 제목 기준 dedup
    seen: set = set()
    uniq = []
    for a in pool:
        k = (a.get("title") or "")[:30]
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(a)
    # ★금칙(사망·범죄·비방) 기사는 '풀에서' 빼둔다(2026-08-06 사고 근본수정).
    #   전에는 pick_article이 고른 뒤에야 금칙 판정을 해서 스킵했는데, 슬롯마다 같은 풀을 보고
    #   실패한 인물은 exclude_persons에 안 들어가므로 **같은 기사를 3번 연속 고르고 3번 스킵**했다
    #   (8/7 새벽: 연예 3슬롯이 전부 '오은영 살 빠진' 기사 하나로 실패 → 연예 0편).
    kept = [a for a in uniq
            if not _BLOCK_RE.search(f"{a.get('title','')} {a.get('snippet','')}")]
    if len(kept) != len(uniq):
        log(f"금칙 소재 {len(uniq) - len(kept)}건 풀에서 제외 → 후보 {len(kept)}건")
    return kept


def generate(out_dir: str, no: str = "20", hint: str = "", log=print,
             mode: str = "ai_hook", exclude_persons: set | None = None,
             thumb_formula: str = "", story_title_ai: bool | None = None,
             body_formula: str = "", news: list | None = None) -> dict:
    """연예인×AI 1편(반자동 초안). mode='celeb_story'면 연예 70%/AI 30%. AI 연결 억지면 RuntimeError.
    exclude_persons: 이미 다룬 인물. thumb_formula: 홈판 썸네일 공식. body_formula: 연예 본문 공식.
    story_title_ai: 스토리 모드에서 True=제목 AI 포함 / False=순수 연예 / None=자동. 반환에 'person'."""
    _celeb_pick = mode in ("celeb_pure", "celeb_ai10")   # 순수/90:10 = 연예 후보 풀 + AI게이트 없음
    if news is None:
        log("연예 뉴스 수집 → 이슈 선정 중…")
        news = build_pure_pool(log) if _celeb_pick else S.fetch_news_ranking(30)
    if not news:
        raise RuntimeError("연예 뉴스 수집 실패")
    pick = pick_article(news, hint, exclude_persons=exclude_persons,
                        relaxed=(mode == "celeb_story"), pure=_celeb_pick)
    return _write_one(out_dir, no, pick, log, mode=mode, thumb_formula=thumb_formula,
                      story_title_ai=story_title_ai, body_formula=body_formula)


def generate_many(out_dir: str, count: int = 2, start_no: int = 31, log=print) -> list:
    """연예인×AI 접목 여러 편(인물 중복 없이). 억지 연결 슬롯은 건너뜀."""
    log("연예 랭킹뉴스 수집 → AI로 이을 이슈들 선정 중…")
    news = S.fetch_news_ranking(30)
    if not news:
        raise RuntimeError("랭킹뉴스 수집 실패")
    used_urls: set = set()
    results = []
    attempts = 0
    i = 0
    while len(results) < count and attempts < count + 4:
        attempts += 1
        no = str(start_no + i).zfill(2)
        try:
            pick = pick_article(news, exclude_urls=used_urls)
            used_urls.add(pick["url"])
            results.append(_write_one(out_dir, no, pick, log))
            i += 1
        except Exception as e:  # noqa: BLE001
            log(f"[{no}] 접목 생성 건너뜀: {e}")
            # AI로 이을 이슈가 없으면 반복해도 같음 → 중단
            if "억지 연결 회피" in str(e) or "남은 기사 없음" in str(e):
                break
    log(f"연예인×AI 접목 {len(results)}/{count}편 생성 완료")
    return results


if __name__ == "__main__":
    hint = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
    out = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    generate(out, no="31", hint=hint)
