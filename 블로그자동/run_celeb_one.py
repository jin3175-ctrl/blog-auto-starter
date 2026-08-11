#!/usr/bin/env python3
"""소재를 지정해서 연예 글만 N편 생성 + 임시저장.

run_ai_daily.py는 소재를 '오늘 랭킹/1순위 풀'에서 자동으로 고른다.
에디님이 "이혼숙려캠프로 하나, 나는솔로로 하나" 처럼 **소재를 찍어줄 때** 이걸 쓴다.
(gen_celeb_ai.generate의 hint 인자에 소재를 넘겨 pick_article이 그 소재를 고르게 한다)

    python3 run_celeb_one.py 이혼숙려캠프 나는솔로
    python3 run_celeb_one.py --gen-only 이혼숙려캠프      # 생성만(임시저장 X)

연예편은 **임시저장까지만** — 사진·표현 확인 후 에디님이 직접 발행(스킬 절대 원칙).
"""
import os
import sys
from datetime import datetime

import config
import run_ai_daily as R


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(os.path.join(config.WORK_DIR, "ai_daily.log"), "a") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


#: 소재별 별칭 — 기사 제목/스니펫 매칭용(방송 줄임말이 기사에 더 많이 쓰인다)
_ALIASES = {
    "이혼숙려캠프": ["이혼숙려캠프", "이숙캠", "이혼 숙려"],
    "나는솔로": ["나는솔로", "나는 솔로", "나솔", "솔로나라"],
    "나솔사계": ["나솔사계", "나는솔로 사계", "사계"],
}


def _pool_for_hint(pool: list, hint: str, log=print) -> list:
    """★지정소재 반영(2026-08-06): celeb_ai10 모드는 PICK_PROMPT_PURE를 쓰는데 그 프롬프트에
    hint 자리가 없어 소재를 찍어줘도 모델이 풀에서 딴 걸 고른다(오은영 기사 선정→금칙 스킵).
    그래서 프롬프트를 건드리지 않고 **풀 자체를 소재로 걸러** 넘긴다.
    금칙(사망·범죄·비방) 기사도 미리 빼서 pick_article이 헛돌지 않게 한다."""
    import celeb_sources as S
    import gen_celeb_ai as G

    keys = _ALIASES.get(hint, [hint])

    def _match(a: dict) -> bool:
        t = f"{a.get('title','')} {a.get('snippet','')}"
        return any(k in t for k in keys)

    def _clean(items: list) -> list:
        out = []
        for a in items:
            t = f"{a.get('title','')} {a.get('snippet','')}"
            if G._BLOCK_RE.search(t):
                continue
            out.append(a)
        return out

    hit = _clean([a for a in (pool or []) if _match(a)])
    log(f"[소재] '{hint}' 풀 매칭 {len(hit)}건(금칙 제외 후)")
    if len(hit) < 3:
        try:
            extra = _clean([a for a in S.fetch_news_search(hint, limit=12) if _match(a)])
            seen = {a.get("url") or a.get("title") for a in hit}
            for a in extra:
                if (a.get("url") or a.get("title")) not in seen:
                    hit.append(a)
            log(f"[소재] 뉴스검색 보충 → 총 {len(hit)}건")
        except Exception as e:  # noqa: BLE001
            log(f"[소재] 뉴스검색 보충 실패: {e}")
    return hit


def _next_no(out_dir: str) -> str:
    """폴더에서 안 쓰인 다음 글번호(01~99)."""
    used = set()
    for fn in os.listdir(out_dir) if os.path.isdir(out_dir) else []:
        head = fn.split("_")[0]
        if head.isdigit():
            used.add(int(head))
    n = 1
    while n in used:
        n += 1
    return str(n).zfill(2)


def main(hints: list[str], gen_only: bool = False) -> int:
    import gen_ai
    import gen_celeb_ai
    import naver
    import pipeline

    out_dir = os.path.join(config.SOURCE_ROOT, f"gen_{config.today_str()}")
    os.makedirs(out_dir, exist_ok=True)
    _log(f"=== 연예 지정소재 {len(hints)}편: {', '.join(hints)} → {out_dir} ===")

    if not gen_only and not naver.session_alive(_log):
        _log("[중단] 네이버 세션 만료 — 재로그인 후 다시 실행하세요.")
        return 1

    # 홈판 썸네일 공식 + 연예 본문 공식 + 후보 풀은 1회만 수집해 공유
    thumb_formula = ""
    try:
        thumb_formula = (gen_ai.collect_live_context(_log) or {}).get("thumb_formula", "")
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 홈판 공식 수집 실패(뼈대로 진행): {e}")
    body_formula = ""
    try:
        body_formula = gen_celeb_ai.collect_celeb_body_formula(_log)
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 연예 본문 공식 실패(뼈대로 진행): {e}")
    pool = None
    try:
        pool = gen_celeb_ai.build_pure_pool(_log)
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 연예 후보 풀 실패(랭킹만 진행): {e}")

    made: list[str] = []
    used_persons: set = set()
    for hint in hints:
        no = _next_no(out_dir)
        try:
            _log(f"[생성] 연예90/AI10 {no} — 지정소재 '{hint}'")
            news = _pool_for_hint(pool, hint, _log)
            if not news:
                _log(f"[생성] {no} 건너뜀: '{hint}' 소재로 쓸 기사가 없습니다"
                     "(오늘 기사가 전부 금칙 소재일 수 있음)")
                continue
            r = gen_celeb_ai.generate(out_dir, no=no, hint=hint, log=_log,
                                      mode="celeb_ai10", exclude_persons=used_persons,
                                      thumb_formula=thumb_formula,
                                      body_formula=body_formula, news=news)
            person = (r or {}).get("person", "")
            if person:
                used_persons.add(person)
            made.append(no)
            _log(f"[생성] {no} 완료 (인물: {person or '?'})")
        except Exception as e:  # noqa: BLE001
            _log(f"[생성] {no} 실패(건너뜀): {e}")

    if not made:
        _log("[중단] 생성된 글이 없습니다.")
        return 1
    if gen_only:
        _log(f"[생성만] {len(made)}편 — 임시저장 건너뜀.")
        return 0

    ok = 0
    for no in made:
        try:
            _log(f"[{no}] 임시저장 시작 → 카테고리 '{R.CAT_CELEB}'")
            res = pipeline.process_post(no, lambda m, n=no: _log(f"   [{n}] {m}"),
                                        publish=False, folder=out_dir,
                                        category=R.CAT_CELEB)
            _log(f"[{no}] 결과: ok={res.get('ok')} · {res.get('message')}")
            if res.get("ok"):
                ok += 1
        except Exception as e:  # noqa: BLE001
            _log(f"[{no}] 오류: {e}")
    _log(f"=== 완료: {ok}/{len(made)} 임시저장 (연예편은 검토 후 직접 발행) ===")
    return 0 if ok else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(args, gen_only="--gen-only" in sys.argv))
