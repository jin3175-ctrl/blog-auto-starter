#!/usr/bin/env python3
"""연예 '정보형' 원고 생성기 — 신작·방영중 드라마/예능의 등장인물·인물관계도·줄거리.

★왜 만들었나 (2026-08-10 에디님 결정: 이슈 3 + 정보 1)
기존 연예편은 **그날 방송 반응(이슈형)** 이라 유입 수명이 2~3일이다. 그래서 매일 써도
'재고'가 쌓이지 않고, 하루라도 멈추면 트래픽이 바로 0에 수렴한다(실측: 8/4 연예 중단 →
하루 방문 231명). 반면 작품 정보글은 `OOO 등장인물`·`인물관계도`·`줄거리` 같은 키워드로
**방영 기간(일일드라마면 수개월) 내내 검색 유입이 들어온다.**

이슈형(gen_celeb_ai)과 역할이 다르다:
  · 이슈형 = 그날 홈피드 트래픽 (수명 짧고 크다)
  · 정보형 = 검색 재고 (작게 시작해 오래 남는다)

원칙(이슈형과 공유): 존댓말 / 인사·자기소개 금지 / 기사에 없는 사실·추측 금지 /
사진은 자동첨부하지 않고 `[사진N - 장면 / 출처: … / 유튜브 검색: …]` 마커만 남긴다.

사용: python3 gen_drama_info.py            # 오늘 소재 자동 선정 후 원고 생성
     python3 gen_drama_info.py "욕망의 덫"  # 작품 지정
"""
from __future__ import annotations

import json
import os
import re
import sys

from claude_cli import run_claude_p
import celeb_sources as S
import config
from gen_ai import _clean_title
import gen_celeb_ai as C
import gen_templates as T

#: ★소재 찾는 방식(2026-08-10 실측으로 바꿈)
#  처음엔 "새 드라마 첫 방송" 같은 일반어로 뉴스 검색을 했는데 **전부 0건**이었다
#  (celeb_sources.fetch_news_search는 '욕망의 덫'처럼 구체적 고유명사만 결과를 준다).
#  → 연예 랭킹뉴스에서 **따옴표로 묶인 작품명**을 먼저 긁고(한국 기사는 '작품명' 표기가 관행),
#    그 이름으로 다시 뉴스 검색해 상세를 모은다.
_TITLE_QUOTE = re.compile(r"[‘'\"“]([^’'\"”]{2,18})[’'\"”]")
#: 작품명이 아닌 인용(발언·수식어)을 걸러낼 힌트 — 이 말이 기사에 같이 있으면 작품일 확률이 높다
_PROGRAM_HINT = re.compile(r"드라마|예능|방송|첫 방송|편성|출연|시청률|회차|부작|종영|방영")
#: ★교양·다큐 계열은 '등장인물/인물관계도' 검색 수요가 없어 정보글 소재로 부적합(2026-08-11 실측:
#  '역사스페셜-시간여행자'가 선정돼 태그에 억지로 등장인물이 붙었다). 이름·기사에 이 말이 있으면 뺀다.
_NOT_DRAMA = re.compile(r"역사스페셜|다큐|다큐멘터리|시사|르포|추적|스페셜|뉴스|토론|강연|클래식|"
                        r"동물|자연|기행|건강|교양")


def _program_candidates(log=print, top: int = 10) -> list[str]:
    """랭킹뉴스에서 작품명 후보를 빈도순으로 뽑는다."""
    from collections import Counter
    try:
        news = S.fetch_news_ranking(40)
    except Exception as e:  # noqa: BLE001
        log(f"  랭킹뉴스 수집 실패: {str(e)[:50]}")
        return []
    cnt: Counter = Counter()
    for a in news:
        t = f"{a.get('title','')} {a.get('snippet','')}"
        if not _PROGRAM_HINT.search(t):
            continue
        for m in _TITLE_QUOTE.findall(t):
            m = m.strip()
            if 2 <= len(m) <= 18 and not m.isdigit() and " " not in m[:2]:
                if _NOT_DRAMA.search(m) or _NOT_DRAMA.search(t):
                    continue
                cnt[m] += 1
    names = [w for w, _ in cnt.most_common(top * 2)]
    # 이미 다룬 작품 제외
    try:
        import history
        used = history.recent_celeb_names()
        names = [n for n in names if not any(u in n or n in u for u in used)]
    except Exception:  # noqa: BLE001
        pass
    log(f"  작품 후보 {len(names)}개: {', '.join(names[:8])}")
    return names[:top]


PICK_PROMPT = """당신은 네이버 블로그에서 '드라마·예능 정보글'을 쓰는 블로거입니다.
아래 기사 목록에서 **정보글로 쓸 작품 1개**를 고르세요.

[고르는 기준 — 검색 유입이 오래 들어올 작품]
- **드라마**(일일·주말·미니시리즈) 또는 **출연자 관계가 있는 예능**
  (연애 리얼리티·관찰·서바이벌처럼 '누가 누구와 어떻게'가 검색되는 것)
- 지금 방영 중이거나 곧 시작하는 것. 방영 기간이 길수록 좋다(일일드라마 100부작 등)
- 사람들이 `등장인물`·`인물관계도`·`줄거리`·`몇부작`·`방영시간`을 실제로 검색할 작품

[★제외 — 이건 고르면 안 된다]
- **다큐·교양·시사·역사·뉴스 프로그램**(등장인물·인물관계도 개념이 없어 검색 수요가 없다)
- 토크쇼·라디오처럼 회차마다 게스트만 바뀌는 것
- 이미 종영해 한참 지난 작품, 단발성 이슈(열애·논란·근황)
- 위 조건에 맞는 게 없으면 **번호 0**을 주고 끝낸다(억지로 고르지 말 것)

[★이미 다룬 작품 — 고르지 말 것]
{exclude}

[기사 목록]
{news}

[출력 — JSON 한 개만, 큰따옴표, 설명 금지. **기사에 있는 내용만** 채우고 모르는 건 빈 문자열]
{{"번호":정수(적합한 게 없으면 0),
 "작품명":"정확한 제목",
 "채널":"방송사(예: KBS2, MBC, tvN)",
 "방영시간":"예: 월~금 저녁 7시 50분 (기사에 있으면)",
 "편성":"예: 100부작 / 16부작 (기사에 있으면)",
 "장르":"기사에 적힌 장르",
 "OTT":"독점 스트리밍 서비스(있으면)",
 "인물":[{{"이름":"극중 이름","배우":"배우명","역할":"한 줄 설명"}}],
 "줄거리":"기사에 나온 설정·전개를 3~5문장으로",
 "관전포인트":"검색자가 궁금해할 지점 한 줄",
 "회차":"기사에 회차 표기가 있으면(없으면 '')",
 "방송일":"이 회차 방송일 YYYY-MM-DD(없으면 '')"}}
"""

BODY_PROMPT = """당신은 블로거 '에디'입니다. 아래 작품의 **정보글**을 씁니다.
검색해서 들어온 사람이 원하는 건 '등장인물이 누구고, 어떤 관계고, 무슨 이야기냐'입니다.
그걸 정확하게 주는 게 이 글의 전부입니다. 감상·평론이 아닙니다.

[작품 정보 — 이 범위 안에서만 쓴다. 여기 없는 건 쓰지 말 것]
작품명: {title}
채널·시간: {channel} / {airtime} / {episodes}
장르: {genre} / OTT: {ott}
줄거리: {plot}
관전포인트: {point}
인물: {people}

[구조]
1. 도입 2~3줄: 이 작품을 지금 찾는 이유(첫 방송·화제 등). ★인사·자기소개 금지, 첫 줄부터 본론.
2. 방영 정보: 채널·시간·편성·OTT를 한 덩어리로 깔끔하게.
3. ★등장인물과 관계: 이 글의 핵심. 누가 누구인지, 관계가 어떻게 얽혔는지 사람 이름으로 또박또박.
4. 줄거리: 스포일러는 **이미 공개된 범위**(예고·1회·보도자료)까지만.
5. 관전 포인트: 앞으로 뭘 보면 되는지 2~3개.
6. 마지막에 AI 이야기 **한 문단만**(2~3문장): 이런 인물관계·줄거리 정리도 요즘은 AI로 표까지
   뽑는다는 정도. 홍보·강의 권유 금지, 담백하게. 그리고 '?'로 끝나는 질문 한 줄.

[반드시 지킬 것]
- ★존댓말('~합니다/~습니다')로 끝까지. 반말 금지.
- ★★**추측 금지**: '짐작하기로는', '정황상', '~아닐까 싶은데' 같은 표현으로 빈칸을 메우지 말 것.
  모르면 "아직 공개되지 않았습니다"라고 쓰거나 아예 쓰지 않는다.
- 인물 이름·배우 이름·채널·시간은 위에 준 값 그대로. **틀리면 안 되는 정보**다.
- 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 마크다운 금지.
- 마커 형식(★엄수): `[사진N - 장면 설명 / 출처: 채널 '작품명' 회차(방송일) / 유튜브 검색: 검색어]`
  · 5~7개. 사진은 **에디님이 직접 찾아 넣는다** — 마커만 보고 찾을 수 있게 세 칸을 다 채운다.
  · ★★**마커를 연달아 붙이지 말 것.** 마커 사이에는 반드시 본문이 1~2문단 들어간다.
    끝에 몰아 놓지 말고 도입부터 마무리까지 고르게 흩는다.
  · '유튜브 검색' 칸은 그대로 검색창에 넣을 문구. 사진마다 다르게(인물명·장면 특징을 섞는다).
  · 회차·방송일이 없으면 그 괄호는 생략(지어내지 말 것).
- `[표]` 1개 — 등장인물 표(아래 카드 JSON의 '표').
- 마지막: 해시태그 10개. ★**검색 롱테일을 반드시 포함**:
  `#작품명` `#작품명등장인물` `#작품명인물관계도` `#작품명줄거리` `#작품명몇부작`(편성 정보가 있을 때)
  + 채널·주요 배우 이름.

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{title} 등장인물 정리",
 "표":[["극중 이름","배우 · 역할"], ["...","..."]],
 "썸네일":{{"intro":"짧은 후킹","big":"핵심 키워드(3~6자)","tail":"짧은 마무리","badge":"등장인물"}}}}
"""

TITLE_PROMPT = """너는 네이버 검색·홈피드에 잘 걸리는 제목을 만드는 카피라이터다.
아래 작품 정보글의 제목 후보 10개를 만들어라.

[작품] {title} ({channel})
[줄거리 핵심] {plot}
[관전포인트] {point}

[제목 원칙]
- 검색으로 오는 글이다. **작품명은 반드시 넣는다.**
- 절반은 정보형(`OOO 등장인물 인물관계도 정리`처럼 검색어를 그대로), 절반은 후킹형
  (통념을 깔고 뒤집되 결론은 감춘다). 둘을 섞어서 10개.
- 40자 이내. 지어낸 수치·없는 사실 금지.

[출력]
1~10번 제목만 한 줄씩. 그리고 **마지막 줄에 정확히 이 형식으로** 추천을 남긴다:
추천: <번호> — <왜 그 제목인지 한 줄>
"""


def _pool(log=print) -> list:
    """작품명 후보 → 이름별 뉴스 검색 → 금칙 제외한 기사 풀."""
    pool: list = []
    for name in _program_candidates(log):
        try:
            found = S.fetch_news_search(name, 4)
        except Exception as e:  # noqa: BLE001
            log(f"  '{name}' 검색 실패(무시): {str(e)[:40]}")
            continue
        if found:
            for a in found:
                a["_program"] = name
            pool.extend(found)
            log(f"  '{name}' 뉴스 {len(found)}건")
    seen, uniq = set(), []
    for a in pool:
        k = (a.get("title") or "")[:30]
        if k and k not in seen:
            seen.add(k)
            uniq.append(a)
    kept = [a for a in uniq if not C._BLOCK_RE.search(f"{a.get('title','')} {a.get('snippet','')}")]
    if len(kept) != len(uniq):
        log(f"  금칙 소재 {len(uniq)-len(kept)}건 제외")
    return kept


def pick(hint: str = "", log=print) -> dict:
    news = _pool(log)
    if not news:
        raise RuntimeError("정보형 소재 수집 실패")
    if hint:
        news = [a for a in news if hint in f"{a.get('title','')} {a.get('snippet','')}"] or news
    listing = "\n".join(f"{i}. {a['title']} — {a.get('snippet','')}"
                        for i, a in enumerate(news, 1))
    try:
        import history
        excl = ", ".join(sorted(history.recent_celeb_names())) or "(없음)"
    except Exception:  # noqa: BLE001
        excl = "(없음)"
    got = C._parse_json(run_claude_p(PICK_PROMPT.format(news=listing, exclude=excl), timeout=180))
    idx = int(got.get("번호", 0) or 0)
    if not idx or not got.get("작품명"):
        raise RuntimeError("정보글로 쓸 작품을 못 골랐습니다(적합 소재 없음)")
    art = news[idx - 1]
    got["_기사"] = art
    log(f"  선정: {got.get('작품명')} ({got.get('채널','?')})")
    return got


def generate(out_dir: str, no: str = "09", hint: str = "", log=print,
             thumb_formula: str = "") -> dict:
    """정보형 1편 생성 → {no, keyword, title}. 이미지·썸네일은 만들지 않는다(사진은 직접 삽입)."""
    os.makedirs(out_dir, exist_ok=True)
    p = pick(hint, log)
    title, channel = p.get("작품명", ""), p.get("채널", "")
    people = p.get("인물") or []
    people_txt = " / ".join(f"{x.get('이름','')}({x.get('배우','')}) {x.get('역할','')}"
                            for x in people) or "(기사에 인물 정보 없음)"
    log(f"[{no}] 정보형 본문 생성: {title}")
    body, cards = "", {}
    prompt = BODY_PROMPT.format(
        title=title, channel=channel, airtime=p.get("방영시간", "") or "(미상)",
        episodes=p.get("편성", "") or "", genre=p.get("장르", "") or "",
        ott=p.get("OTT", "") or "", plot=p.get("줄거리", ""),
        point=p.get("관전포인트", ""), people=people_txt)
    for k in range(3):
        body, cards = C._parse_body(run_claude_p(prompt, timeout=320))
        if body and cards and len(body.strip()) >= 300:
            break
        log(f"[{no}] 본문 재시도 {k+1}/3")
    if not body or not cards:
        raise RuntimeError("정보형 본문 생성 실패")

    # 제목 10개 + 추천(이유까지 파일에 남긴다 — 에디님이 고를 때 근거가 된다)
    titles, rec = [], ""
    try:
        out = run_claude_p(TITLE_PROMPT.format(title=title, channel=channel,
                                              plot=p.get("줄거리", ""),
                                              point=p.get("관전포인트", "")), timeout=150)
        for line in out.splitlines():
            if line.strip().startswith("추천"):
                rec = line.strip()
                continue
            t = _clean_title(line)
            if not (6 <= len(t) <= 45):
                continue
            if re.match(r"^(제목|출력|규칙|아래|다음)", t):   # 지시문 누수 제거
                continue
            titles.append(t)
        # 작품명이 들어간 후보를 앞으로(검색 유입이 목적이므로)
        _key = (title.split() or [title])[0]
        titles.sort(key=lambda x: 0 if _key and _key in x else 1)
    except Exception as e:  # noqa: BLE001
        log(f"[{no}] 제목 생성 실패: {str(e)[:60]}")
    # 최근 발행 제목과 겹치는 후보 제거
    try:
        import history
        recent = history.recent_titles(60, log)
        fresh = [t for t in titles if not history.too_similar(t, recent, 0.5)]
        if fresh:
            titles = fresh
    except Exception:  # noqa: BLE001
        pass
    best = titles[0] if titles else f"{title} 등장인물과 인물관계도 정리"
    # 추천 번호가 있으면 그 후보를 대표로
    m = re.search(r"추천\s*[:：]\s*(\d+)", rec)
    if m and titles:
        i = int(m.group(1)) - 1
        if 0 <= i < len(titles):
            best = titles[i]
    body = C._set_title_line(body, best) if hasattr(C, "_set_title_line") else body

    # 사진 마커 출처 보정(회차·방송일·검색어) — 이슈형과 같은 백스톱을 재사용
    body = C._enrich_photo_sources(body, channel, f"{title}({channel})",
                                   p.get("회차", ""), p.get("방송일", ""),
                                   f"{title} {channel}", log)
    body = C._spread_photo_markers(body, log)   # 마커가 줄줄이 붙지 않게
    # 맨 끝 '@출처 : 방송사 \'작품명\'' 보장(이슈형과 동일 — 어느 방송을 인용했는지 남긴다)
    body = C._ensure_source_line(body, channel, title)

    keyword = C._sanitize(title, "등장인물")
    with open(os.path.join(out_dir, f"{no}_{keyword}_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    if titles:
        with open(os.path.join(out_dir, f"{no}_{keyword}_제목후보.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(titles) + (f"\n\n{rec}" if rec else ""))
    T.write_celeb_table(out_dir, no, keyword,
                        cards.get("표제목", f"{title} 등장인물"), cards.get("표", []))
    log(f"[{no}] 완료 → {title} (정보형, 사진은 직접 삽입)")
    try:
        import history
        history.mark_celeb_used(title)
    except Exception:  # noqa: BLE001
        pass
    return {"no": no, "keyword": keyword, "title": best, "program": title}


if __name__ == "__main__":
    hint = sys.argv[1] if len(sys.argv) > 1 else ""
    d = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    print(generate(d, no="09", hint=hint))
