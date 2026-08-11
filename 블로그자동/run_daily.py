#!/usr/bin/env python3
"""매일 자동 실행: (선택) 원고 생성 → 강점인사이트=공개발행(먼저), 나머지=임시저장.

사용: python3 run_daily.py --generate           # 원고 3편 생성 후 발행(완전 자동)
     python3 run_daily.py --generate --draft-all # 생성 후 전부 임시저장(안전 확인용)
     python3 run_daily.py --gen-only            # 생성만(발행 안 함) — 품질 확인용
     python3 run_daily.py                        # 오늘 폴더 원고 발행(생성 안 함)
     python3 run_daily.py --dry                  # 무엇을 할지 미리보기
     python3 run_daily.py --draft-all            # 전부 임시저장(발행 안 함)
     python3 run_daily.py --only 10 --draft-all  # 10편만 임시저장으로 테스트
     python3 run_daily.py --folder 20260711 --only 10  # 특정 날짜 폴더의 10편만
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import naver  # noqa: E402
import pipeline  # noqa: E402
import posts  # noqa: E402


def generate_all(date: str, log, celeb_count: int = 9) -> str:
    """생성기로 gen_{date}에 하루치 원고 생성:
    21~29 셀럽 실용정보 9편(임시) · 30 쇼핑(임시). 폴더 경로 반환.
    (2026-07-16 강점인사이트 제거 — 이 블로그를 애드포스트 전용 '셀럽 실용정보' 축으로 전환)"""
    import gen_celeb
    import gen_shopping
    out = os.path.join(config.SOURCE_ROOT, f"gen_{date}")
    os.makedirs(out, exist_ok=True)

    try:
        log(f"[생성] ① 셀럽 실용정보 {celeb_count}편(랭킹뉴스, 중복 없이)")
        gen_celeb.generate_many(out, count=celeb_count, start_no=21, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"[생성] ① 셀럽 실패: {e}")

    try:
        log("[생성] ② 쇼핑커넥트(시의성 제품)")
        gen_shopping.generate(out, no="30")
    except Exception as e:  # noqa: BLE001
        log(f"[생성] ② 쇼핑 실패: {e}")

    return out


def main(dry: bool = False, draft_all: bool = False, only: str | None = None,
         folder_name: str | None = None, generate: bool = False,
         gen_only: bool = False) -> int:
    _log = lambda m: print(m, flush=True)

    # 0) 생성 단계(선택) — 발행 전에 원고 3편 생성
    if generate or gen_only:
        date = config.today_str()
        print(f"=== 원고 생성 시작: gen_{date} ===", flush=True)
        gen_folder = generate_all(date, _log)
        folder_name = f"gen_{date}"
        print(f"=== 생성 완료: {gen_folder} ===", flush=True)
        if gen_only:
            plist = posts.list_posts(gen_folder)
            print(f"[생성만] {len(plist)}편 생성됨: "
                  + ", ".join(f"{p['no']}({posts.category(p['body_path'])})" for p in plist))
            return 0

    if not naver.is_logged_in():
        print("[중단] 네이버 로그인 세션이 없습니다. 대시보드에서 먼저 로그인하세요.")
        return 1
    if folder_name:
        folder = os.path.join(config.SOURCE_ROOT, folder_name)
        if not os.path.isdir(folder):
            print(f"[중단] 폴더가 없습니다: {folder}")
            return 1
    else:
        folder = config.resolve_date_folder()
    if not folder:
        print("[중단] 원고 폴더를 찾지 못했습니다.")
        return 1
    print(f"=== 원고 폴더: {folder} ===", flush=True)

    plist = posts.list_posts(folder)
    if only:
        plist = [p for p in plist if p["no"] == only.zfill(2)]
        if not plist:
            print(f"[중단] {only}편을 찾지 못했습니다.")
            return 1
    # 강점인사이트(발행)를 먼저 → 7시 정각에 게시되도록. 나머지는 뒤에.
    plist.sort(key=lambda p: 0 if posts.category(p["body_path"]) == "insight" else 1)

    ok_cnt = 0
    for p in plist:
        cat = posts.category(p["body_path"])
        publish = (cat == "insight") and not draft_all
        action = "공개발행" if publish else "임시저장"
        print(f"\n[{p['no']}] {cat} → {action}", flush=True)
        if dry:
            continue
        try:
            res = pipeline.process_post(
                p["no"], lambda m, no=p["no"]: print(f"   [{no}] {m}", flush=True),
                publish=publish, folder=folder)
            print(f"[{p['no']}] 결과: ok={res.get('ok')} · {res.get('message')}", flush=True)
            if res.get("ok"):
                ok_cnt += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{p['no']}] 오류: {e}", flush=True)

    print(f"\n=== 완료: {ok_cnt}/{len(plist)} 성공 ===", flush=True)
    return 0


if __name__ == "__main__":
    def _argval(flag):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return None
    sys.exit(main(dry="--dry" in sys.argv, draft_all="--draft-all" in sys.argv,
                  only=_argval("--only"), folder_name=_argval("--folder"),
                  generate="--generate" in sys.argv, gen_only="--gen-only" in sys.argv))
