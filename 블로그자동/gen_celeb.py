"""연예 셀럽 '실용정보' 원고 자동 생성 (이서이/쉬즈블랑 방법론).

방법: ① 지금 뜨는 네이버 연예 랭킹뉴스에서 '검색자가 실용정보를 원할' 이슈 1개 선정
     ② 기사 본문을 긁어 '사실 재료' 확보
     ③ 지금 뜨는 연예 블로그 제목/구조를 '공식'으로 삼아
     ④ 셀럽은 후킹, 알맹이는 아이템·브랜드·가격·방법·팩트(강점 코칭 금지)로 작성
     ⑤ 후킹 제목(검색키워드 + 후킹 + 아이템).
방송/기사 이미지는 저작권상 [사진N] 자리표시자(직접 캡처). 썸네일은 텍스트/디자인형.

사용: python3 gen_celeb.py               # 오늘 랭킹에서 자동 선정
     python3 gen_celeb.py "손흥민 공항패션"  # 특정 인물/키워드 우선
"""
from __future__ import annotations

import json
import re
import sys

from claude_cli import run_claude_p
import celeb_sources as S
import config
import formula
import gen_common as G
import gen_templates as T
import title_hook

AXES = "패션아이템 / 뷰티·성형·관리 / 다이어트·운동·식단 / 근황·복귀 정리 / 공항·화보 스타일링"

PICK_PROMPT = """당신은 '셀럽 라이프·실용정보' 블로거입니다(이서이/쉬즈블랑 스타일).
아래는 지금 네이버에서 화제인 연예 랭킹뉴스입니다. 이 중 '검색하는 사람이 실용 정보를 원할 만한'
셀럽 이슈 1개를 고르세요. 핵심 판단: '이 사람 → 사람들이 뭘 검색하며 궁금해하나'.

[좋은 소재 축] {axes}
  즉 착용한 옷/아이템, 뷰티·다이어트·관리법, 근황·복귀 사실, 화제가 된 이유처럼
  '브랜드·가격·방법·팩트'로 답을 줄 수 있는 것.
[피할 것] 사망·중대 범죄·자극적 사생활 폭로만 있고 정보 가치가 없는 것. 단순 악플/조롱.
[힌트가 있으면 우선] {hint}

[기사 목록]
{news}

[이미 다룬 인물 — 겹치지 말 것]
{exclude}

[출력 — JSON 한 개만, 큰따옴표, 설명 금지]
{{"번호":정수, "인물":"핵심 인물명",
 "실용축":"{axes} 중 이 글의 축 하나",
 "검색키워드":"사람들이 실제 검색할 말(예: '카리나 블라우스', '엄정화 아침식단', '손흥민 공항패션')",
 "핵심정보":"검색자가 원하는 답 한 줄 — 기사에 실제로 있는 것만(아이템/브랜드/가격 또는 방법/팩트). 없으면 '기사에 브랜드·가격 없음'",
 "프로그램":"이 소재의 방송/영상을 유튜브에서 찾을 수 있게 — 프로그램명+방송사 또는 유튜브 채널명. 기사에 명시된 것만, 없으면 ''",
 "매체":"출처 표기용(기사 매체/방송사)",
 "표제목":"글에 넣을 정보/비교 표 제목(예: '유나 수영복 스타일링 포인트 3', '유기자차 vs 무기자차')"}}
"""

BODY_PROMPT = """당신은 '셀럽 라이프·실용정보' 블로거입니다(이서이/쉬즈블랑 스타일).
지금 뜨는 연예 이슈를 후킹으로 쓰되, 검색하는 사람이 진짜 궁금해하는 '실용 정보'를 주는 글을 씁니다.
셀럽은 미끼, 알맹이는 아이템·브랜드·가격·방법·팩트입니다.

[소재 기사 — 사실 재료. 이 범위 안에서만. 없는 브랜드·가격·수치를 지어내지 말 것]
제목: {art_title}
본문: {art_body}

[이 글의 실용 축] {axis}
[검색 키워드(제목·본문에 자연스럽게 반복)] {search_kw}
[검색자가 원하는 핵심 답] {core_info}

[본문 구조 — 이서이 공식. 이 뼈대 그대로]
1. 도입 후킹(2~4줄): 지금 왜 화제인지 + "그런데 진짜 눈에 띈 건 ○○" → 계속 읽을 이유. ("안녕하세요 오늘은~" 금지)
2. 셀럽 상황/이슈 짧게 (미끼)
3. ★핵심 정보: 검색자가 원하는 답. 아이템이면 브랜드·가격·제품명, 다이어트면 식단·방법, 근황이면 팩트 정리
4. 포인트 분석(Point 2~3개): 왜 좋아 보이는지 / 핵심 특징을 구체적으로
5. 실생활 적용법: 체형별·상황별·따라 하는 법 / 주의점
6. 비슷한 것 고르는 팁 또는 대안 추천
7. 질문형 CTA(댓글 유도)

[반드시 지킬 것]
- ★셀럽을 '강점·심리·갤럽'으로 분석하지 말 것. 오직 검색자가 원하는 실용 정보에 집중.
- ★기사에 없는 브랜드·가격·수치는 절대 지어내지 말 것. 확실치 않으면 '알려진 바로는'·'유사 제품' 톤, 단정 금지.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지(이모지는 소제목에 한두 개만 허용).
- 본문에 마커 포함:
  [사진N - 구체 장면/이미지 설명 / 출처: 프로그램·영상 제목(방송사 또는 유튜브 채널명)] 8~12개
  ★ 사진 출처 규칙 — '유튜브/출처에서 찾을 수 있게' 적는다:
    · 어느 방송/영상/화보에서 나온 장면인지 구체적으로. 이 소재의 프로그램은 "{program}", 기사 매체는 "{media}".
    · 좋은 예: `출처: 나 혼자 산다(MBC)` / `출처: OOO 인스타그램(@계정)` / `출처: 데이즈드 코리아 8월호 화보`
    · 나쁜 예(금지): `출처: SNS` / `출처: 방송` / `출처: 스포츠 매체`
    · 사진마다 장면이 다르면 출처도 다르게. 없는 프로그램명 지어내지 말 것.
  [표] (정보/비교 표 1개. 내용은 아래 카드 JSON의 '표')
- ★ 소주제로 흐름 나누기: 글 중간에 소주제 4~6개를 **[사진N] 바로 다음 줄**에 놓는다.
  · 짧은 명사형/의문형 한 줄(20자 이내), 마침표 없이. (자동으로 따옴표 인용박스가 됨)
  · 좋은 예: `12만 원대의 비밀` / `왜 더 어려 보였나` / `따라 입는 법` / `비슷한 아이템 고르기`
  · 모든 사진 뒤에 넣지 말고 흐름 전환 지점에만.
- 마지막: 짧은 면책(공개정보·개인 의견 기반), '?'로 끝나는 CTA 질문,
  "@출처 : {media}" (형식 그대로 — '@출처' + 공백 + 콜론 + 공백), 해시태그 10개(#로 시작, 검색키워드 포함).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["항목/기준","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구(1~2줄)","big":"핵심 키워드(3~6자)","tail":"짧은 마무리구","badge":"{badge}"}}}}
"""


def _badge(axis: str) -> str:
    a = axis or ""
    if "뷰티" in a or "성형" in a or "관리" in a:
        return "뷰티·관리"
    if "다이어트" in a or "운동" in a or "식단" in a:
        return "다이어트"
    if "근황" in a or "복귀" in a:
        return "셀럽 근황"
    return "셀럽 스타일"


def _sanitize_keyword(person: str, topic: str) -> str:
    base = f"{person}{topic}" if topic and topic not in person else person
    kw = re.sub(r"[^가-힣0-9A-Za-z]", "", base)
    return kw[:20] or "셀럽정보"


def _parse_json(out: str) -> dict:
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {}


def _set_title_line(body: str, title: str) -> str:
    lines = body.splitlines()
    for i, ln in enumerate(lines[:5]):
        if re.match(r"^\s*제목\s*[:：]", ln):
            lines[i] = f"제목: {title}"
            return "\n".join(lines)
    return f"제목: {title}\n\n" + body


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


def pick_article(news: list, hint: str = "", exclude_urls: set | None = None,
                 exclude_persons: set | None = None) -> dict:
    exclude_urls = exclude_urls or set()
    avail = [a for a in news if a["url"] not in exclude_urls]
    if not avail:
        raise RuntimeError("남은 기사 없음(모두 소진)")
    listing = "\n".join(f"{i}. {a['title']} — {a['snippet']}" for i, a in enumerate(avail, 1))
    excl = ", ".join(sorted(exclude_persons or set())) or "(없음)"
    prompt = PICK_PROMPT.format(axes=AXES, hint=hint or "(없음)", news=listing, exclude=excl)
    pick = _parse_json(run_claude_p(prompt, timeout=180))
    idx = int(pick.get("번호", 0) or 0)
    if not (1 <= idx <= len(avail)) or not pick.get("인물") or not pick.get("검색키워드"):
        raise RuntimeError("기사 선정 실패(JSON/번호/키워드 확인)")
    pick["url"] = avail[idx - 1]["url"]
    pick["뉴스제목"] = avail[idx - 1]["title"]
    pick["snippet"] = avail[idx - 1].get("snippet", "")
    return pick


def _collect_context(log=print) -> dict:
    """여러 편이 공유할 소스: 랭킹뉴스·현재 위너 제목·본문샘플·실시간 공식(공식 추출 1회)."""
    log("연예 랭킹뉴스 + 현재 위너/공식 수집 중…")
    news = S.fetch_news_ranking(30)
    if not news:
        raise RuntimeError("랭킹뉴스 수집 실패")
    winners = S.fetch_theme_titles(12, 40)
    samples = []
    for post in S.fetch_theme_posts(12, 3):
        bt = S.fetch_blog_body(post["url"], 1200)
        if bt:
            samples.append(bt)
    log("지금 먹히는 제목·본문 공식 추출 중(claude -p)…")
    fx = formula.extract_formulas(winners, samples)
    return {"news": news, "winners": winners, "fx": fx}


def _write_one(out_dir: str, no: str, pick: dict, ctx: dict, log=print) -> dict:
    import os
    person = pick.get("인물", "")
    axis = pick.get("실용축", "패션아이템")
    search_kw = pick.get("검색키워드", person)
    core_info = pick.get("핵심정보", "")
    program = pick.get("프로그램", "")
    media = pick.get("매체", program or "기사")
    table_title = pick.get("표제목", f"{search_kw} 핵심 포인트")
    keyword = _sanitize_keyword(person, search_kw.replace(person, "").strip())
    winners, fx = ctx["winners"], ctx["fx"]

    log(f"[{no}] 기사 본문 확보 → 본문 생성: {person} / {axis}")
    art = S.fetch_article(pick["url"])
    prompt = BODY_PROMPT.format(
        art_title=art.get("title", pick["뉴스제목"]),
        art_body=(art.get("body") or "")[:2500],
        axis=axis, search_kw=search_kw, core_info=core_info or "(기사 본문에서 직접 파악)",
        body_formula=fx.get("body", ""),  # 참고용(프롬프트엔 직접 안 쓰지만 시그니처 호환)
        media=media, program=program or "(기사에 프로그램 명시 없음)",
        table_title=table_title, badge=_badge(axis))
    body, cards = _parse_body(run_claude_p(prompt, timeout=320))
    if not body or not cards:
        raise RuntimeError("본문 생성 파싱 실패(구분자/JSON 확인)")

    # 후킹 제목(검색키워드 + 후킹 + 아이템). 강점 앵글 없음.
    try:
        scene = f"{search_kw} / {core_info}".strip(" /") or pick["뉴스제목"]
        htitle = title_hook.generate_hook_title(person, scene, program, angle="",
                                                live_titles=winners, formula=fx.get("title", ""))
        if htitle:
            body = _set_title_line(body, htitle)
            log(f"[{no}] 제목 → {htitle}")
    except Exception as e:  # noqa: BLE001
        log(f"[{no}] 제목 생성 실패(본문 제목 유지): {e}")

    os.makedirs(out_dir, exist_ok=True)
    G.clear_no(out_dir, no)
    with open(os.path.join(out_dir, f"{no}_{keyword}_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    T.write_celeb_table(out_dir, no, keyword, cards.get("표제목", table_title), cards.get("표", []))
    T.render_text_thumbnail(out_dir, f"{no}_{keyword}_썸네일.png", cards.get("썸네일", {}))
    log(f"[{no}] 완료 → {person} / {axis}")
    return {"no": no, "person": person, "axis": axis, "keyword": keyword}


def generate(out_dir: str, no: str = "20", hint: str = "", log=print) -> dict:
    """셀럽 실용정보 1편."""
    ctx = _collect_context(log)
    pick = pick_article(ctx["news"], hint)
    return _write_one(out_dir, no, pick, ctx, log)


def generate_many(out_dir: str, count: int = 9, start_no: int = 21, log=print) -> list:
    """셀럽 실용정보 여러 편(인물 중복 없이). 위너·공식은 공유(공식 추출 1회)."""
    ctx = _collect_context(log)
    used_urls: set = set()
    used_persons: set = set()
    results = []
    for i in range(count):
        no = str(start_no + i).zfill(2)
        try:
            pick = pick_article(ctx["news"], exclude_urls=used_urls, exclude_persons=used_persons)
            used_urls.add(pick["url"])
            used_persons.add(pick.get("인물", ""))
            results.append(_write_one(out_dir, no, pick, ctx, log))
        except Exception as e:  # noqa: BLE001
            log(f"[{no}] 셀럽 생성 실패(건너뜀): {e}")
    log(f"셀럽 실용정보 {len(results)}/{count}편 생성 완료")
    return results


if __name__ == "__main__":
    import os
    hint = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
    date = config.today_str()
    out = os.path.join(config.SOURCE_ROOT, f"gen_{date}")
    generate(out, hint=hint)
