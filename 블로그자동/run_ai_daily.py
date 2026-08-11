#!/usr/bin/env python3
"""에디 AI 블로그 하루치 자동 생성 → 발행/임시저장 (ioiykd8599 = 40대 가장의 AI 생존기).

하루 8편 (2026-08-10 확정 · 이번 달 애드포스트 100만원 목표):
  01~03 = AI 실전글(gen_ai)          → 자동 예약 발행
  04    = 쇼핑커넥트(gen_shopping)    → 자동 예약 발행
  05~08 = 연예 90%+AI 10%(gen_celeb_ai mode=celeb_ai10) → **임시저장**(사진은 에디님이 직접 삽입)

★배치는 새벽 01:30에 시작해 05:40 전후 종료(생성·업로드는 조용히 새벽에).
★발행은 낮에만 — PUBLISH_SLOTS(09:30·12:10·15:00·20:00 ±지터). 근거는 아래 상수 주석.
★연예편은 이미지를 만들지 않는다(gen_celeb_ai.CELEB_AUTO_PHOTOS=False) — 마커+출처만 남긴다.

사용:
  python3 run_ai_daily.py                       # 기본 = AI3 + 쇼핑1 + 연예4 (대기 없음)
  python3 run_ai_daily.py --dry                 # 계획·예약 시각 미리보기(네이버 안 건드림)
  python3 run_ai_daily.py --gen-only            # 생성만(품질 확인용)
  python3 run_ai_daily.py --ai 3 --shop 1 --celeb 4 --stagger 1200   # launchd가 쓰는 형태
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

BANK = os.path.expanduser("~/홈판자료/AI실전_소재뱅크30.md")
USED_FILE = os.path.join(config.WORK_DIR, "ai_topics_used.json")

# 네이버 블로그 카테고리(2026-07-24 정리 확정). 이름이 정확히 일치해야 선택된다.
CAT_AUTOMATION = "AI 자동화 실전"     # 기본·자동화·시스템·만들기
CAT_MONEY = "AI 수익화·부업"          # 수익·부업·돈·전자책
CAT_TOOL = "AI 툴 리뷰·비교"          # 툴 비교·리뷰·후기·vs
CAT_CELEB = "연예이슈강점"            # ★순수 연예(홈판 트래픽). 새 '연예 이슈' 칸 원하면 이 값만 교체.
CAT_SHOP = "AI 에디의 일상"           # ★쇼핑커넥트 글 카테고리(2026-08-01 에디님 지정). 생활·쇼핑템을 '일상' 칸에.

_RE_TOOL = re.compile(r"\bvs\b|비교|리뷰|후기|툴\s*\d|어떤\s*(툴|앱)|무료\s*AI\s*(툴|이미지).*(정리|추천)|3(가지|개)\s*(툴|앱)", re.I)
_RE_MONEY = re.compile(r"수익|부업|돈\b|월\s*\d|전자책|팔아|팔았|수익화|매출|파이프라인|월급|벌었|벌기|현금")


def categorize(text: str) -> str:
    """글 주제/AI주제 문자열을 내용에 맞는 카테고리로 배정(매번 같은 카테고리 방지)."""
    t = text or ""
    if _RE_TOOL.search(t):
        return CAT_TOOL
    if _RE_MONEY.search(t):
        return CAT_MONEY
    return CAT_AUTOMATION            # 자동화·시스템·만들기·그 외 기본


# ★자동 발행(AI·쇼핑) 예약 시각 = '낮 시간대 고정 슬롯 + 랜덤 흔들기' (2026-08-10 에디님 결정)
#
#   근거: 애드포스트 90만원(하루 방문 3천~1만)이던 2026-04의 발행 시각을 실측했더니
#   10:28 / 12:46 / 12:47 / 12:50 / 14:24 / 14:30 / 16:15 / 16:59 / 20:59 / 22:08 —
#   **10~22시, 중심 12~16시. 새벽 발행은 한 건도 없었다.**
#   홈피드는 발행 직후 노출 기회가 가장 크므로, 보는 사람이 없는 새벽에 내보내면
#   초기 클릭·체류가 안 붙어 이후 노출까지 불리해진다.
#   → 생성·업로드는 새벽(01:30~)에 조용히 끝내고, **발행만 낮으로 예약**한다.
#
#   슬롯을 매일 ±지터로 흔드는 이유: 매일 같은 시각이면 그것 자체가 기계 티다.
PUBLISH_SLOTS = [(9, 30), (12, 10), (15, 0), (20, 0)]   # 시, 분
SLOT_JITTER_MIN, SLOT_JITTER_MAX = -20, 30              # 분


def _reserve_times(count: int, now: datetime | None = None) -> list:
    """자동 발행 count편의 예약 시각을 슬롯 순서대로 만든다.

    - 이미 지난 슬롯(또는 15분 내 임박)은 건너뛴다 — 네이버는 과거 시각 예약이 안 된다.
    - 슬롯이 모자라면 마지막 시각에서 70~100분씩 뒤로 이어 붙인다.
    """
    import random
    from datetime import timedelta

    now = now or datetime.now()
    out: list = []
    idx = 0
    for _ in range(count):
        picked = None
        while idx < len(PUBLISH_SLOTS):
            hh, mm = PUBLISH_SLOTS[idx]
            idx += 1
            t = now.replace(hour=hh, minute=mm, second=0, microsecond=0) \
                + timedelta(minutes=random.randint(SLOT_JITTER_MIN, SLOT_JITTER_MAX))
            if t > now + timedelta(minutes=15):
                picked = t
                break
        if picked is None:
            base = out[-1] if out else now + timedelta(minutes=45)
            picked = base + timedelta(minutes=random.randint(70, 100))
            # ★심야 발행 금지(2026-08-10): 늦은 시각에 수동 실행하면 슬롯이 소진돼
            #   00시·01시로 밀린다. 90만원 시절 발행은 10~22시였다 → 22:30을 넘으면 다음 날 낮 슬롯으로.
            if picked.hour >= 23 or (picked.hour == 22 and picked.minute > 30):
                nxt = (out[-1] if out else now) + timedelta(days=1)
                hh, mm = PUBLISH_SLOTS[len([o for o in out if o.date() > now.date()]) % len(PUBLISH_SLOTS)]
                picked = nxt.replace(hour=hh, minute=mm, second=0, microsecond=0) \
                    + timedelta(minutes=random.randint(SLOT_JITTER_MIN, SLOT_JITTER_MAX))
        out.append(picked)
    return out


def _log(m: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {m}", flush=True)


def _alert(title: str, msg: str) -> None:
    """실패를 즉시 눈에 보이게 한다(맥 알림 + 가능하면 메일).

    새벽 4:30 실행이라 로그에만 남기면 아무도 안 본다. 특히 '네이버 세션 만료'는
    조용히 그날치를 통째로 날리므로 반드시 알린다. (제이 블로그 run_morning과 같은 방침)
    """
    import subprocess
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "{title}" sound name "Basso"'],
            timeout=10, capture_output=True, check=True)
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 맥 알림 실패({type(e).__name__}) — 로그로만: {title} / {msg}")
    # 맥 알림은 자리에 없으면 놓친다 → 메일도(제이 blog_report 재사용, 없으면 조용히 생략)
    try:
        sys.path.insert(0, os.path.expanduser("~/경제이슈 블로그 자동화"))
        import blog_report
        blog_report.send_alert(f"[에디 블로그] {title}", msg, log=_log)
    except Exception:  # noqa: BLE001
        pass


def _topics() -> list[str]:
    """소재뱅크의 번호 목록('1. 주제') 파싱."""
    out = []
    try:
        with open(BANK, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*\d+\.\s+(.+)$", line.strip())
                if m:
                    out.append(m.group(1).strip())
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 소재뱅크 읽기 실패: {e}")
    return out


def _used() -> list[str]:
    try:
        with open(USED_FILE, encoding="utf-8") as f:
            return json.load(f).get("used", [])
    except Exception:  # noqa: BLE001
        return []


def _mark_used(topics: list[str]) -> None:
    used = _used()
    used.extend(t for t in topics if t not in used)
    try:
        with open(USED_FILE, "w", encoding="utf-8") as f:
            json.dump({"used": used}, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 사용이력 저장 실패: {e}")


def pick_topics(n: int) -> list[str]:
    """아직 안 쓴 소재뱅크 주제 n개. **소진되어도 이력을 초기화하지 않는다.**

    ★2026-08-03 사고: 소진되면 이력을 통째로 지우고 처음부터 다시 썼다. 그래서 뱅크 앞쪽
      주제('코딩 한 줄 몰랐던 내가 AI로 자동화 툴…')가 며칠 간격으로 계속 재등장했다.
      이제 소진되면 빈 리스트를 주고, 호출부가 '오늘 홈판 트렌드'에서 새 주제를 뽑게 한다.
      (뱅크 주제는 '내 경험담' 결이라 홈판 후킹도 약하다 — 트렌드 주제가 원래 1순위다)
    """
    all_t = _topics()
    if not all_t:
        return []
    used = set(_used())
    fresh = [t for t in all_t if t not in used]
    if not fresh:
        _log("[소재뱅크] 미사용 주제 소진 → 뱅크 폴백 없이 트렌드 주제로만 진행")
    return fresh[:n]


def generate_all(out_dir: str, ai_count: int, celeb_count: int,
                 celeb_story_count: int = 0, shop_count: int = 0,
                 celeb_info_count: int = 1) -> list[tuple[str, str]]:
    """AI 실전 + 쇼핑커넥트 + 연예×AI 생성. 성공한 (글번호, 카테고리) 목록 반환.
    번호 순서: AI(01~) → 쇼핑(그 뒤) → 연예(맨 뒤).
    celeb_story_count: 연예×AI 중 '연예70/AI30' 스토리 모드로 만들 편수(뒤쪽부터)."""
    import gen_ai
    import gen_celeb_ai

    os.makedirs(out_dir, exist_ok=True)
    made: list[tuple[str, str]] = []

    # 그날의 홈판 공식·트렌드는 1회만 수집해 공유(구조·주제가 매일 달라지도록)
    live_ctx = None
    try:
        live_ctx = gen_ai.collect_live_context(_log)
    except Exception as e:  # noqa: BLE001
        _log(f"[경고] 홈판 공식 수집 실패(폴백 뼈대로 진행): {e}")

    # ★주제 소싱: 먼저 '오늘 홈판 트렌드'에서 뽑고(매일 다르게), 부족하면 소재뱅크로 폴백.
    used_hist = _used()
    topics = []
    if live_ctx:
        try:
            topics = gen_ai.derive_topics(live_ctx, ai_count, used=used_hist, log=_log)
        except Exception as e:  # noqa: BLE001
            _log(f"[경고] 오늘의 주제 도출 실패(뱅크 폴백): {e}")
    if len(topics) < ai_count:
        need = ai_count - len(topics)
        _log(f"[주제] 트렌드 {len(topics)}개 + 소재뱅크 {need}개 보충")
        for t in pick_topics(need + len(topics)):
            if t not in topics:
                topics.append(t)
            if len(topics) >= ai_count:
                break
    # ★그래도 모자라면 트렌드에서 더 뽑는다(뱅크 재탕 금지 — 2026-08-03 중복 사고).
    if len(topics) < ai_count and live_ctx:
        try:
            more = gen_ai.derive_topics(live_ctx, ai_count * 2,
                                        used=used_hist + topics, log=_log)
            for t in more:
                if t not in topics:
                    topics.append(t)
                if len(topics) >= ai_count:
                    break
            _log(f"[주제] 트렌드에서 추가 확보 → 총 {len(topics)}개")
        except Exception as e:  # noqa: BLE001
            _log(f"[경고] 추가 주제 도출 실패: {e}")
    topics = topics[:ai_count]

    done_topics = []
    for i, topic in enumerate(topics):
        no = str(i + 1).zfill(2)
        try:
            _log(f"[생성] AI 실전 {no}: {topic[:40]}")
            gen_ai.generate(topic, out_dir, no=no, log=_log, ctx=live_ctx)
            cat = categorize(topic)
            made.append((no, cat))
            done_topics.append(topic)
        except Exception as e:  # noqa: BLE001
            _log(f"[생성] AI 실전 {no} 실패(건너뜀): {e}")
    if done_topics:
        _mark_used(done_topics)

    # ★쇼핑커넥트(2026-08-01 편입): 시의성 소비재 구매가이드 + [커넥트-제품] 마커.
    #   업로드 시 pipeline이 마커를 인식해 naver 쇼핑커넥트 상품카드(관련도 1위)를 자동 삽입한다.
    #   번호는 AI 다음 칸(ai_count+1 ..). 실패해도 나머지 편에 영향 없게 개별 try.
    for k in range(shop_count):
        no = str(ai_count + k + 1).zfill(2)
        try:
            import gen_shopping
            _log(f"[생성] 쇼핑커넥트 {no}")
            gen_shopping.generate(out_dir, no=no)
            made.append((no, CAT_SHOP))
        except Exception as e:  # noqa: BLE001
            _log(f"[생성] 쇼핑커넥트 {no} 건너뜀: {e}")

    # ★역할 분리(C, 2026-07-31): 연예 글 = 순수 홈판 트래픽(celeb_pure, AI 0%). AI 글은 별도 순수 AI.
    # 인물 중복 방지 — used_persons 공유. 연예 본문 공식(연예 홈판 위너 dir=12) 1회 추출 공유.
    used_persons: set = set()
    celeb_body_formula = ""
    celeb_pool = None
    if celeb_count:
        try:
            celeb_body_formula = gen_celeb_ai.collect_celeb_body_formula(_log)
        except Exception as e:  # noqa: BLE001
            _log(f"[경고] 연예 본문 공식 실패(뼈대로 진행): {e}")
        # 후보 풀(랭킹 + 1순위 소재 검색)을 1회만 구성해 연예 글들이 공유
        try:
            celeb_pool = gen_celeb_ai.build_pure_pool(_log)
        except Exception as e:  # noqa: BLE001
            _log(f"[경고] 연예 후보 풀 실패(랭킹만 진행): {e}")
    # ★연예 4편 중 일부는 '정보형'(신작 드라마 등장인물·인물관계도·줄거리)으로 돌린다.
    #   2026-08-11 에디님 결정: 이슈 3 + 정보 1. 이슈형은 유입 수명이 2~3일이라 재고가 안 쌓이는데,
    #   작품 정보글은 방영 기간 내내 검색 유입이 들어온다(같은 편수로 '쌓이는 글'을 만드는 장치).
    info_n = min(celeb_info_count, celeb_count)
    issue_n = celeb_count - info_n
    for j in range(issue_n):
        no = str(ai_count + shop_count + j + 1).zfill(2)
        try:
            _log(f"[생성] 연예90/AI10(홈판 온램프) {no}")
            r = gen_celeb_ai.generate(out_dir, no=no, log=_log, mode="celeb_ai10",
                                      exclude_persons=used_persons,
                                      thumb_formula=(live_ctx or {}).get("thumb_formula", ""),
                                      body_formula=celeb_body_formula, news=celeb_pool)
            person = (r or {}).get("person", "")
            if person:
                used_persons.add(person)
            made.append((no, CAT_CELEB))   # 순수 연예 → 연예 카테고리
        except Exception as e:  # noqa: BLE001
            _log(f"[생성] 순수 연예 {no} 건너뜀: {e}")

    for j in range(info_n):
        no = str(ai_count + shop_count + issue_n + j + 1).zfill(2)
        try:
            import gen_drama_info
            _log(f"[생성] 연예 정보형(검색 재고) {no}")
            gen_drama_info.generate(out_dir, no=no, log=_log,
                                    thumb_formula=(live_ctx or {}).get("thumb_formula", ""))
            made.append((no, CAT_CELEB))
        except Exception as e:  # noqa: BLE001
            _log(f"[생성] 정보형 {no} 건너뜀: {e}")

    return made


def _acquire_lock() -> bool:
    """중복 실행 방지(2026-08-06 사고). 맥이 자다 깨면서 어제 걸린 작업과 오늘 배치가 동시에
    브라우저를 띄워 오늘 01~03이 전부 '본문 영역 못 찾음'으로 죽었다. 한 번에 하나만 돌린다."""
    lock = os.path.join(config.WORK_DIR, "ai_daily.lock")
    try:
        if os.path.exists(lock):
            with open(lock) as f:
                pid = int((f.read() or "0").strip() or 0)
            try:
                os.kill(pid, 0)           # 살아있으면 실행 중
                _log(f"[중단] 이미 실행 중입니다(PID {pid}). 중복 실행 방지.")
                return False
            except OSError:
                pass                      # 죽은 프로세스가 남긴 잠금 → 무시하고 덮어씀
        with open(lock, "w") as f:
            f.write(str(os.getpid()))
        import atexit
        atexit.register(lambda: os.path.exists(lock) and os.remove(lock))
        return True
    except Exception:  # noqa: BLE001
        return True                       # 잠금 실패가 본 작업을 막지는 않게


def main(ai_count: int = 3, celeb_count: int = 4, celeb_story_count: int = 0,
         gen_only: bool = False, dry: bool = False, stagger: int = 0, shop_count: int = 1,
         celeb_info_count: int = 1) -> int:
    celeb_story_count = min(celeb_story_count, celeb_count)
    if not dry and not _acquire_lock():
        return 1
    date = config.today_str()
    out_dir = os.path.join(config.SOURCE_ROOT, f"gen_{date}")
    _log(f"=== 에디 블로그 하루치: AI 홈판 {ai_count}편 + 쇼핑커넥트 {shop_count}편 + 연예90/AI10 온램프 {celeb_count}편 → {out_dir} ===")

    if dry:
        _log("[dry] AI 홈판 예정 주제:")
        for t in pick_topics(ai_count):
            _log(f"   - {t}")
        if shop_count:
            _log(f"[dry] 쇼핑커넥트 {shop_count}편: 시의성 소비재 → 구매가이드 + [커넥트-제품] 자동삽입(카테고리 '{CAT_SHOP}')")
        _log(f"[dry] 연예90/AI10 {celeb_count}편(홈판 온램프)은 1순위 소재 우선, 사망·범죄·비방 제외")
        _log(f"[dry] 업로드는 편당 {stagger//60}분 간격(velocity 분산)")
        _rt = _reserve_times(ai_count + shop_count)
        _log("[dry] AI·쇼핑 예약 발행 시각: " + (", ".join(t.strftime("%H:%M") for t in _rt) or "없음"))
        _log(f"[dry] 연예 {celeb_count}편 = 이슈 {celeb_count - min(celeb_info_count, celeb_count)}"
             f" + 정보형 {min(celeb_info_count, celeb_count)} → 임시저장(사진은 직접 삽입)")
        return 0

    # ★생성 전에 세션 유효성 확인(2026-08-02 사고): 만료된 쿠키로 6편을 2시간 걸려 만든 뒤
    #   업로드에서 0/6으로 전멸했다. 만료면 지금 알리고 멈춘다(생성 자체를 낭비하지 않는다).
    if not gen_only:
        import naver as _nv
        if not _nv.session_alive(_log):
            _log("[중단] 네이버 세션 만료 — 생성 전에 감지. 재로그인 후 다시 실행하세요.")
            _alert("네이버 세션 만료 — 오늘 블로그 생성 안 함",
                   "재로그인 후 'python3 run_ai_daily.py --ai 4 --shop 1 --celeb 1'을 실행하세요.")
            return 1

    made = generate_all(out_dir, ai_count, celeb_count, celeb_story_count,
                        shop_count, celeb_info_count)
    _log(f"=== 생성 완료: {len(made)}편 ({', '.join(n for n, _ in made) or '없음'}) ===")
    if not made:
        _log("[중단] 생성된 글이 없습니다.")
        return 1
    if gen_only:
        _log("[생성만] 발행 단계 건너뜀.")
        return 0

    # ── 임시저장 (공개발행 절대 X) ──
    import naver
    import pipeline

    if not naver.session_alive(_log):   # 파일 존재가 아니라 '실제 유효성'을 본다
        _log("[중단] 네이버 로그인 세션 없음/만료 → 생성물은 폴더에 남아있습니다. "
             "재로그인 후 다시 발행하세요.")
        _alert("네이버 세션 만료 — 오늘 블로그 미발행",
               f"{len(made)}편 생성은 끝났지만 임시저장을 못 했습니다. "
               "네이버 재로그인 후 'python3 run_ai_daily.py'를 다시 실행하세요(원고는 보존됨).")
        return 1

    ok = 0
    # 자동 발행할 편(AI·쇼핑)의 예약 시각을 **한 번에** 낮 슬롯으로 배정한다.
    _pub_slots = _reserve_times(sum(1 for _, c in made if c != CAT_CELEB))
    if _pub_slots:
        _log("예약 발행 시각: " + ", ".join(t.strftime("%H:%M") for t in _pub_slots))
    _slot_i = 0
    for i, (no, cat) in enumerate(made):
        # ★AI 티 안 나게 velocity 분산: 편 사이에 stagger(초)만큼 쉬었다 다음 편 임시저장(첫 편은 바로)
        if stagger and i > 0:
            import time
            _log(f"[대기] 다음 편까지 {stagger//60}분 쉼(사람처럼 천천히)…")
            time.sleep(stagger)
        # ★발행 정책(2026-08-06 에디님 지시로 변경):
        #   · AI·쇼핑편 → **자동 공개 발행**(경험 슬롯 없이 완성본으로 나감)
        #   · 연예편 → 임시저장 유지(에디님이 사진·표현 확인 후 직접 발행)
        do_publish = (cat != CAT_CELEB)
        # ★예약 시각은 위에서 만든 낮 슬롯(PUBLISH_SLOTS)에서 순서대로 꺼낸다.
        rsv = None
        if do_publish and _slot_i < len(_pub_slots):
            rsv = _pub_slots[_slot_i]
            _slot_i += 1
        try:
            _log(f"[{no}] {('예약 발행 ' + rsv.strftime('%H:%M')) if rsv else ('공개 발행' if do_publish else '임시저장')}"
                 f" 시작 → 카테고리 '{cat}'")
            res = pipeline.process_post(
                no, lambda m, n=no: _log(f"   [{n}] {m}"),
                publish=do_publish, folder=out_dir,
                category=cat, reserve_at=rsv)
            _log(f"[{no}] 결과: ok={res.get('ok')} · {res.get('message')}")
            if res.get("ok"):
                ok += 1
        except Exception as e:  # noqa: BLE001
            _log(f"[{no}] 오류: {e}")

    _log(f"=== 완료: {ok}/{len(made)} 임시저장 ===")
    _log("→ 네이버에서 [[경험 슬롯]] 채우고 검토 후 직접 발행하세요.")
    # 일부/전부 실패도 조용히 넘기지 않는다(세션이 중간에 끊기는 경우가 있다)
    if ok < len(made):
        _alert(f"블로그 임시저장 {ok}/{len(made)}편만 성공",
               "일부 편이 업로드되지 않았습니다. 네이버 세션·로그(work/ai_daily.log)를 확인하세요.")
    return 0


if __name__ == "__main__":
    def _val(flag, default):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                try:
                    return int(sys.argv[i + 1])
                except ValueError:
                    pass
        return default

    sys.exit(main(ai_count=_val("--ai", 3), celeb_count=_val("--celeb", 4),
                  celeb_story_count=_val("--celeb-story", 0), stagger=_val("--stagger", 0),
                  shop_count=_val("--shop", 1), celeb_info_count=_val("--celeb-info", 1),
                  gen_only="--gen-only" in sys.argv, dry="--dry" in sys.argv))
