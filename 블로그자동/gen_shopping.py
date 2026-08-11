"""쇼핑커넥트 원고 자동 생성 (시의성 제품 → 구매가이드 → 커넥트 CTA).

이서이식: 이슈(시의성)+정보(고르는 법) 결합. 강점 강의 아님(강점카드 없음).
- 제품: 힌트 있으면 우선, 없으면 계절/시점에 맞는 수요 높은 소비재를 claude가 선정.
- 이미지 [사진N]은 비연예라 파이프라인이 Unsplash로 자동첨부.
- [커넥트 - 제품]은 발행 시 naver.py가 쇼핑커넥트로 관련도 1위 상품을 자동 삽입(제휴링크).
- 대가성 문구는 본문에 넣지 않음: 쇼핑커넥트 삽입 시 네이버가 자동 표기. 썸네일은 텍스트형.

사용: python3 gen_shopping.py            # 계절 맞춰 자동 선정
     python3 gen_shopping.py "제습기"    # 특정 제품 지정
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
import title_hook

# 대가성 문구 상수 제거: 쇼핑커넥트 카드를 삽입하면 네이버가 '네이버쇼핑 커넥트' 문구를
# 자동으로 표기하므로, 본문에 수동으로 넣지 않는다(중복 방지). 쿠팡 파트너스는 사용 안 함.

PICK_PROMPT = """당신은 소비 트렌드에 밝은 블로거 '에디'입니다. 지금 시점에 맞춰 블로그로 쓰기 좋은
'수요 높은 생활 소비재' 1개를 고르세요. 광고티 나는 고관여 사치품 말고, 계절/시점에 꼭 필요한 실용템.

[지금 시점] {date} (계절: {season})
[힌트가 있으면 우선] {hint}

★ [최근에 이미 다룬 제품 — 절대 겹치지 말 것]
{recent}
위 제품들과 **같거나 비슷한 것을 고르지 마세요.** 같은 카테고리(예: 선풍기/서큘레이터/넥밴드선풍기는
전부 '냉방 소형가전'으로 같은 계열)도 피하고, **다른 계열의 제품**을 고르세요.
계절이 같다고 매번 같은 물건을 고르면 안 됩니다. 여름에도 냉방기기 말고
제습·위생·주방·수면·아웃도어·차량·헤어/바디·청소·보관 등 다양한 계열이 있습니다.

[지금 뜨는 쇼핑·리빙 블로그 제목 참고]
{winners}

[출력 — JSON 한 개만, 큰따옴표, 설명 금지]
{{"제품":"구체 제품/카테고리명", "카테고리":"가전/생활/뷰티 등", "핵심이점":"왜 지금 필요한지 한 줄",
 "시의성":"계절/시점 근거 한 줄(구체 날짜·기관 발표는 지어내지 말 것, 일반론으로)",
 "표제목":"고를 때 비교 기준 표 제목(예: 평수별 권장 용량)"}}
"""

BODY_PROMPT = """당신은 블로거 '에디'입니다. 아래 제품에 대한 네이버 블로그 '구매 가이드' 글을 씁니다.
잘 되는 쇼핑 블로그의 '공식'을 따르되, 읽는 사람이 '아, 이거 나한테 필요하네 — 사야겠다'는 마음이 들게 쓴다.
거짓·과장 없이(허위 후기·가짜 할인 금지) '진짜 도움'을 주면서도, 아래 [심리 설득 장치]로 구매 욕구를 자연스럽게 끌어올린다.

{eddie}

[이번 제품] {product} ({category})
- 핵심 이점: {benefit}
- 시의성(과장·허위 금지, 일반론으로만): {timing}

[본문 구조 — 지금 홈판이 밀어주는 글에서 '실시간 추출'한 공식. 이 뼈대를 그대로 따르라]
{body_formula}

[심리 설득 장치 — '사고 싶게' 만드는 핵심. 최소 4개를 본문에 자연스럽게 녹여라]
- 손실회피/공포소구: 지금 안 사거나 잘못 고르면 겪는 곤란을 구체적 장면으로("장마철 눅눅한 이불, 벽지 곰팡이, 다음 달 전기세"). 단 과장·공포조장 금지.
- 페인포인트 공감 도입: 첫 3줄에서 독자가 겪는 그 상황을 정확히 짚어 "이거 완전 내 얘기다" 하게 만든다.
- 선택 단순화: "이 두세 가지만 보면 끝" — 복잡한 스펙을 결정 기준 2~3개로 압축해 결정 피로를 없앤다.
- 구체 수치·평수/상황별 표: 용량·평수·가격대 등 숫자로 신뢰를 준다(일반 가이드 수준, 허위 스펙 금지).
- 흔한 실수 회피: "이것만은 피하세요 3가지" — 실패 두려움을 자극해 '제대로 고른 나'를 상상하게.
- 완독·전환 유도: "이 기준만 알면 5분이면 끝"으로 끝까지 읽게 하고, 마지막에 커넥트 카드로 자연히 넘어가게.
★절대 금지: 가짜 할인·기간한정·품절임박 같은 지어낸 긴급성, 검증 안 된 특정 제품 사용후기, 허위 스펙. 설득은 오직 '진짜 정보 + 공감'으로만.

[공식 위에 반드시 지킬 것]
- 왜 지금 필요한가(시의성·페인포인트) → 고를 때 핵심 기준(숫자·기준 구체적으로) → 비교 표 → 흔한 실수(피하세요) →
  실제 사용 상황 묘사(특정 제품 미검증 후기는 지어내지 말 것 — 상황·공감 중심) → 체크포인트 요약 → 커넥트 링크 안내 → 가격·재고 안내. (공식과 충돌하면 공식 우선)
- 이모지·마크다운 금지, 한 문장 45자 내외 단문, 문단 1~2문장 + 여백. 허위 스펙·과장 금지.

★★★'AI가 쓴 티' 제거(2026-08-06 에디님 지시, 홈판 위너 실측 기준) — 존댓말은 유지하되:
  [따라야 할 것] 문장을 짧게 툭툭 끊고 길이를 들쭉날쭉하게 / **구체적 숫자·이름·장면**을 넣기
    ("빠르다"(X) → "3분 만에 나왔습니다"(O)) / 모르는 건 모른다고 쓰기 / 곁가지를 조금 남기기.
  [금지] "또한·따라서·이처럼·뿐만 아니라·결론적으로·정리하자면" 같은 매끄러운 연결어,
    "~해보시기 바랍니다/도움이 되셨길 바랍니다" 교과서식 마무리,
    "정말 유용한·매우 효과적인·놀라운" 속 빈 수식어, 문단마다 똑같은 길이·리듬,
    항목마다 균일하게 3개씩 딱 떨어지는 나열.

- 본문에 마커 포함:
  [사진N - 제품/상황 설명 / 출처: 제품 상세컷 또는 상황 연출컷] 6~10개.
  [표]  (고를 때 비교 기준. 표 내용은 아래 카드 JSON의 '표'로 제공)
  [커넥트 - {product} 추천 상품 링크]  (제휴 링크 자리, 1개)
- 마지막: "가격과 재고는 시점에 따라 달라질 수 있으니 구매 전 상세페이지에서 다시 확인해주세요.",
  '?'로 끝나는 질문, "@출처 : (참고한 일반 가이드/기준)"
  (형식 그대로 — '@출처' + 공백 + 콜론 + 공백), 해시태그 10개(#로 시작, 제품/구매 관련).
- '강점/코치' 언급 금지(이 글은 강점 글이 아님).

[출력 형식 — 정확히 이 구분자]
===본문===
제목: (임시 제목 한 줄 - 뒤에서 교체됨)
(본문)
===카드===
(JSON 한 개. 큰따옴표)
{{"표제목":"{table_title}","표":[["기준/항목","내용"],["...","..."],["...","..."],["...","..."]],
 "썸네일":{{"intro":"짧은 후킹 도입구","big":"핵심 키워드(3~6자)","tail":"짧은 마무리구","badge":"{badge}"}}}}
"""


def recent_products(days: int = 30, limit: int = 12) -> list[str]:
    """최근 생성 폴더들에서 이미 다룬 쇼핑 제품명을 뽑는다(중복 선정 방지).

    파일명이 `30_쇼핑커넥트_{제품}_복붙용.txt` 형태라 거기서 제품명을 복원한다.
    (강점인사이트는 mark_done으로 이력을 남기지만 쇼핑엔 그 장치가 없어서,
     매일 '계절에 맞는 제품'을 백지에서 고르다 7월 내내 선풍기류만 반복됐다.)
    """
    import glob
    out: list[str] = []
    pat = os.path.join(config.SOURCE_ROOT, "gen_*", "*_쇼핑커넥트_*_복붙용.txt")
    for path in sorted(glob.glob(pat), reverse=True):   # 최신 폴더부터
        m = re.search(r"_쇼핑커넥트_(.+?)_복붙용\.txt$", os.path.basename(path))
        if not m:
            continue
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


# 같은 계열로 묶어 볼 핵심어(이게 겹치면 사실상 같은 물건으로 본다).
# 예: '휴대용목걸이선풍기넥밴드형'(7/14)과 '휴대용목걸이선풍기넥밴드선풍기'(7/16)는
#     글자는 달라도 둘 다 선풍기 계열 → 중복.
_FAMILY_WORDS = ("선풍기", "서큘레이터", "쿨러", "제습기", "가습기", "공기청정기",
                 "청소기", "에어컨", "히터", "전기장판", "믹서기", "커피", "매트")


def _norm(s: str) -> str:
    return re.sub(r"[^가-힣0-9a-z]", "", (s or "").lower())


def _too_similar(product: str, prev: list[str]) -> bool:
    """선정 제품이 최근 제품과 사실상 같은 계열인지."""
    p = _norm(product)
    if not p:
        return False
    for old in prev:
        o = _norm(old)
        if not o:
            continue
        if p == o or p in o or o in p:
            return True
        # 같은 계열 핵심어를 공유하면 중복으로 본다
        for w in _FAMILY_WORDS:
            if w in p and w in o:
                return True
    return False


def _season(date: str) -> str:
    try:
        m = int(date[4:6])
    except Exception:  # noqa: BLE001
        return ""
    return {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
            6: "여름·장마", 7: "여름·장마·폭염", 8: "여름·폭염",
            9: "가을·환절기", 10: "가을", 11: "늦가을·초겨울"}.get(m, "")


def _sanitize(product: str) -> str:
    kw = re.sub(r"[^가-힣0-9A-Za-z]", "", product)
    return kw[:16] or "제품"


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
            body = "\n".join(lines)
            break
    else:
        body = f"제목: {title}\n\n" + body
    # 대가성 문구는 본문에 넣지 않는다(쇼핑커넥트 삽입 시 네이버가 자동 표기).
    return body


def generate(out_dir: str, no: str = "30", hint: str = "") -> dict:
    import os
    date = config.today_str()
    season = _season(date)
    print("지금 뜨는 쇼핑·리빙 블로그 제목 수집 중…", flush=True)
    try:
        winners = S.fetch_theme_titles(30, 25) + S.fetch_theme_titles(21, 15)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 쇼핑 위너 제목 수집 실패(제목공식 없이 진행): {e}", flush=True)
        winners = []
    wtext = "\n".join(f"- {t}" for t in winners[:30])

    prev = recent_products()
    if prev:
        print(f"최근 다룬 제품(제외): {', '.join(prev[:6])}" + (" …" if len(prev) > 6 else ""), flush=True)
    rtext = "\n".join(f"- {p}" for p in prev) or "(없음 — 첫 글)"

    print("시의성 제품 선정 중(claude -p)…", flush=True)
    pick = _parse_json(run_claude_p(
        PICK_PROMPT.format(date=date, season=season, hint=hint or "(없음)",
                           winners=wtext, recent=rtext), timeout=150))
    product = (pick.get("제품") or hint or "").strip()

    # 프롬프트로 막아도 LLM이 비슷한 걸 또 고를 수 있어, 실제로 겹치면 1회 재선정한다.
    # (힌트로 제품을 직접 지정한 경우는 사용자 의도이므로 건드리지 않는다)
    if product and prev and not hint and _too_similar(product, prev):
        print(f"⚠️ '{product}'은(는) 최근 제품과 겹침 → 재선정", flush=True)
        retry = PICK_PROMPT.format(
            date=date, season=season,
            hint=f"(없음) — 방금 '{product}'을(를) 골랐는데 최근 것과 겹칩니다. 완전히 다른 계열로 고르세요.",
            winners=wtext, recent=rtext)
        pick2 = _parse_json(run_claude_p(retry, timeout=150))
        p2 = (pick2.get("제품") or "").strip()
        if p2 and not _too_similar(p2, prev):
            pick, product = pick2, p2
            print(f"→ 재선정: {product}", flush=True)
        else:
            print(f"→ 재선정 실패, 그대로 진행: {product}", flush=True)

    if not product:
        raise RuntimeError("제품 선정 실패(JSON 확인)")
    category = pick.get("카테고리", "생활")
    benefit = pick.get("핵심이점", "")
    timing = pick.get("시의성", season)
    table_title = pick.get("표제목", f"{product} 고를 때 비교 기준")
    badge = f"{season} 필수템" if season else "구매 가이드"
    print(f"선정 제품: {product} ({category})", flush=True)

    print("지금 먹히는 제목·본문 공식 추출 중(claude -p)…", flush=True)
    try:
        samples = [S.fetch_blog_body(p["url"], 1000) for p in S.fetch_theme_posts(30, 3)]
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 본문 공식 샘플 수집 실패(공식 없이 폴백 진행): {e}", flush=True)
        samples = []
    fx = formula.extract_formulas(winners, [s for s in samples if s])

    print("본문 생성 중(claude -p)…", flush=True)
    body, cards = _parse_body(run_claude_p(BODY_PROMPT.format(
        eddie=G.EDDIE_PROFILE, product=product, category=category, benefit=benefit,
        timing=timing, body_formula=fx.get("body") or "(도입 후킹→왜 지금→기준→표→실수→경험→체크→커넥트)",
        table_title=table_title, badge=badge), timeout=320))
    if not body or not cards:
        raise RuntimeError("본문 생성 파싱 실패(구분자/JSON 확인)")

    print("후킹 제목 생성 중(claude -p)…", flush=True)
    try:
        htitle = title_hook.generate_product_title(product, benefit, timing,
                                                   live_titles=winners, formula=fx.get("title", ""))
        if htitle:
            # ★중복 방지(2026-08-10): 최근 발행 제목과 겹치면 금지 목록을 주고 한 번 더 뽑는다.
            import history
            _recent = history.recent_titles(60)
            _dup = history.too_similar(htitle, _recent, 0.5)
            if _dup:
                print(f"제목이 최근 발행분과 겹침('{_dup[:30]}') → 재생성", flush=True)
                htitle = title_hook.generate_product_title(
                    product, benefit, timing, live_titles=winners,
                    formula=(fx.get("title", "") + "\n\n" + history.prompt_block(_recent))) or htitle
            print(f"제목 → {htitle}", flush=True)
    except Exception as e:  # noqa: BLE001
        htitle = ""
        print(f"제목 생성 실패: {e}", flush=True)
    if htitle:
        body = _set_title_line(body, htitle)
    else:
        body = _set_title_line(body, product + " 구매 가이드")

    # 홈판 규칙: 생성 단계에서 인사·자기소개 도입 제거(gen_ai·gen_celeb_ai와 동일).
    from pipeline import _strip_greeting_intro
    body = _strip_greeting_intro(body)

    keyword = f"쇼핑커넥트_{_sanitize(product)}"
    os.makedirs(out_dir, exist_ok=True)
    G.clear_no(out_dir, no)
    with open(os.path.join(out_dir, f"{no}_{keyword}_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    T.write_celeb_table(out_dir, no, keyword, cards.get("표제목", table_title), cards.get("표", []))
    # ★썸네일 = '제품 사진 + 문구'(2026-08-02 에디님: "미니제빙기면 미니제빙기 이미지에 글이 있으면 좋겠다").
    #   제품 사진은 웹 구독(제미나이→ChatGPT)으로 생성 → 그 위에 문구를 얹는다. 실패 시 기존 텍스트형.
    _thumb_fn = f"{no}_{keyword}_썸네일.png"
    _bg = os.path.join(out_dir, f"{no}_{keyword}_썸네일배경.png")
    _ok = False
    try:
        import web_image
        if web_image.make(f"{product} 제품이 놓인 깔끔한 사진, 실물 위주, 글자 없음", _bg):
            try:
                import photo_thumb
                _ok = photo_thumb.make_face(_bg, os.path.join(out_dir, _thumb_fn),
                                            cards.get("썸네일", {}))
            except Exception:  # noqa: BLE001
                _ok = False
            if not _ok:   # 합성 모듈이 없으면 제품 사진만이라도 썸네일로
                import shutil
                shutil.copyfile(_bg, os.path.join(out_dir, _thumb_fn))
                _ok = True
                print("썸네일 = 제품 사진(문구 합성 없이)", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"제품 썸네일 생성 실패 → 텍스트형 폴백: {str(e)[:60]}", flush=True)
    if not _ok:
        T.render_text_thumbnail(out_dir, _thumb_fn, cards.get("썸네일", {}),
                                footer="에디의 솔직 구매가이드")
    print(f"완료 → {out_dir} ({no}_{keyword}_*)  [{product}]", flush=True)
    return {"product": product, "keyword": keyword, "out_dir": out_dir}


if __name__ == "__main__":
    import os
    hint = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
    date = config.today_str()
    out = os.path.join(config.SOURCE_ROOT, f"gen_{date}")
    generate(out, hint=hint)
