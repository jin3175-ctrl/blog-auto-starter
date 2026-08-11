#!/usr/bin/env python3
"""발행 이력 기반 중복 방지 (2026-08-10 신설).

에디님 지적: "이전에 했던 내용이 계속 중복된다."
실측(최근 40편)으로 확인된 중복의 정체는 '주제'가 아니라 **제목 틀과 인물**이었다.

  · `AI한테 ~시켰더니/물었더니/맡겼더니` 형식이 9/40편(22%).
    8/6은 3편 전부(통신비·정부지원금·사진정리), 8/5도 3편(글감·주가·다이어트)이 같은 틀.
  · 연예는 인물이 돌고 돈다 — 옥순×3, 나는솔로×3, 광수×2. 상투어 '결국'×3, '술렁'×2.

원인: ①주제 중복 검사가 `used` 리스트의 **정확 문자열 비교**뿐이라 틀·인물 반복을 못 잡는다.
      ②연예 `exclude_persons`가 **한 번 실행 안에서만** 유효해 어제 다룬 인물이 오늘 또 나온다.
      ③생성기가 '이미 발행한 제목'을 아예 모른 채 제목을 짓는다.

그래서 **블로그에 실제로 올라간 제목**을 읽어(세션 불필요, 공개 API) 프롬프트에 금지 목록으로
넣고, 생성된 제목이 최근 것과 겹치면 걸러낸다.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

import config

import myinfo  # 수강생 배포판: 내정보.txt에서 읽는다
BLOG_ID = myinfo.blog_id()
_LIST_URL = ("https://blog.naver.com/PostTitleListAsync.naver?blogId={bid}&viewdate="
             "&currentPage={page}&categoryNo=&parentCategoryNo=&countPerPage=30")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
CACHE = os.path.join(config.WORK_DIR, "recent_titles.json")
CELEB_USED = os.path.join(config.WORK_DIR, "celeb_used.json")
CAT_CELEB_NO = "10"          # 연예이슈강점 카테고리 번호

# 제목 유사도 계산에서 뺄 흔한 말(이게 겹쳐도 중복이 아니다)
_STOP = set("""그리고 그런데 하지만 정말 진짜 이제 결국 다들 요즘 오늘 저는 제가 내가 나도 한번
이거 그거 봤더니 했더니 시켰더니 물었더니 봤습니다 합니다 있습니다 됩니다 뭐가 어떻게 이유 방법
정리 후기 근황 공개 사실 지금 처음 마지막 때문 대해 위해 통해 라고 하는 있는 되는""".split())


def _fetch(page: int) -> str:
    req = urllib.request.Request(_LIST_URL.format(bid=BLOG_ID, page=page), headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")


_MEM: dict = {}          # 한 번 실행 안에서는 재조회하지 않는다(편마다 네트워크 왕복 방지)


def recent_posts(limit: int = 60, log=print) -> list[dict]:
    """최근 발행 글 [{date, cat, title}] — 로그인 불필요. 실패 시 캐시로 폴백."""
    if _MEM.get("rows"):
        return _MEM["rows"][:limit]
    rows: list[dict] = []
    try:
        for page in range(1, limit // 30 + 2):
            raw = _fetch(page)
            for m in re.finditer(r'"logNo":"(\d+)".*?"title":"(.*?)","categoryNo":"(\d*)"'
                                 r'.*?"addDate":"(.*?)"', raw, re.S):
                rows.append({"logNo": m.group(1),
                             "title": html.unescape(urllib.parse.unquote_plus(m.group(2))),
                             "cat": m.group(3), "date": m.group(4)})
            if len(rows) >= limit:
                break
            time.sleep(0.3)
        rows = rows[:limit]
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        log(f"[중복방지] 발행 이력 수집 실패({str(e)[:50]}) → 캐시 사용")
        try:
            with open(CACHE, encoding="utf-8") as f:
                rows = json.load(f)[:limit]
        except Exception:  # noqa: BLE001
            rows = []
    if rows:
        _MEM["rows"] = rows
    return rows


def recent_titles(limit: int = 60, log=print) -> list[str]:
    """최근 발행 제목만."""
    return [r.get("title", "") for r in recent_posts(limit, log) if r.get("title")]


#: 조사·어미. 이걸 떼지 않으면 '정부지원금이' ≠ '정부지원금,' 이 되어 재탕을 놓친다(실측).
_PARTICLE = re.compile(r"(에서|으로|에게|한테|처럼|보다|까지|부터|이나|이라|라고|은|는|이|가|을|를|의|에|로|와|과|도|만|나)$")


def _norm(w: str) -> str:
    """꼬리 조사를 떼어 같은 낱말로 모은다(정부지원금이 → 정부지원금)."""
    while len(w) > 2:
        w2 = _PARTICLE.sub("", w)
        if w2 == w or len(w2) < 2:
            break
        w = w2
    return w


def _tokens(t: str) -> set:
    t = re.sub(r"[^가-힣A-Za-z0-9 ]", " ", t or "")
    return {_norm(w) for w in t.split() if len(w) > 1 and w not in _STOP} - _STOP


def too_similar(cand: str, titles: list[str], threshold: float = 0.5) -> str | None:
    """cand가 최근 제목 중 하나와 threshold 이상 겹치면 그 제목을 반환(아니면 None)."""
    a = _tokens(cand)
    if not a:
        return None
    # 4자 이상 핵심어(제습기·정부지원금 같은 소재어)는 제목 문자열에 그대로 박혀 있으면 겹친 것으로 본다.
    keys = {w for w in a if len(w) >= 4}
    for t in titles:
        b = _tokens(t)
        if not b:
            continue
        hit = set(a & b) | {k for k in keys if k in t}
        if len(hit) / min(len(a), len(b)) >= threshold:
            return t
    return None


#: 반복되기 쉬운 제목 틀. (이름, 정규식) — 최근 제목에서 몇 번 쓰였는지 세어 금지 목록을 만든다.
_PATTERNS = [
    ("AI한테 ~시켰더니/물었더니 형식", r"AI한테.{0,14}(더니|봤다|시켜|시켰)"),
    ("AI로 ~하는 법 형식", r"AI로 .{0,12}(하는 법|만드는 법)"),
    ("다들 ~인데/했는데 형식", r"다들.{0,16}(는데|한데)"),
    ("~해봤습니다/써봤습니다 형식", r"(해|써|만들어|돌려)봤"),
    ("결국 ~ 형식", r"결국"),
    ("~술렁/발칵 형식", r"(술렁|발칵)"),
    ("숫자+개/가지 나열형", r"\d+\s*(개|가지)\b"),
]


def banned_patterns(titles: list[str], min_hits: int = 2) -> list[str]:
    """최근 제목에서 min_hits회 이상 쓰인 틀 = 이번엔 쓰지 말 것."""
    out = []
    for name, pat in _PATTERNS:
        n = sum(1 for t in titles if re.search(pat, t))
        if n >= min_hits:
            out.append(f"{name} (최근 {n}회 사용)")
    return out


def prompt_block(titles: list[str], head: int = 25) -> str:
    """제목 프롬프트에 그대로 끼울 '중복 금지' 블록."""
    if not titles:
        return "(발행 이력 없음)"
    ban = banned_patterns(titles)
    s = "[최근 발행한 제목 — 이것들과 같은 소재·같은 틀·같은 상투어를 쓰지 말 것]\n"
    s += "\n".join(f"- {t}" for t in titles[:head])
    if ban:
        s += "\n\n[★최근에 너무 많이 쓴 틀 — 이번엔 금지]\n" + "\n".join(f"- {b}" for b in ban)
        s += "\n같은 뜻이라도 **다른 문장 구조**로 쓸 것(질문형·대화체·수치 제시·비교형 등으로 갈아탈 것)."
    return s


# ── 연예 인물 반복 방지 ────────────────────────────────────────────────
#: 나는솔로 계열 가명 + 자주 나오는 프로그램/상담가. 제목에서 이 단어가 보이면 '그 인물을 다뤘다'고 본다.
_CELEB_WORDS = ("영수 영식 영철 광수 상철 영호 정수 영자 정숙 영숙 순자 현숙 옥순 국화 "
                "이호선 오은영 서장훈 박하선 진태현 이동건 데프콘 이이경 송해나").split()
_CELEB_PROGRAMS = ("나는솔로", "나솔사계", "나솔", "이혼숙려캠프", "이숙캠", "솔로지옥",
                   "모솔N돌싱", "모솔연애", "돌싱N모솔",
                   "오은영 리포트", "오은영리포트", "결혼 지옥", "결혼지옥",
                   "미운 우리 새끼", "무엇이든 물어보살")


def recent_celeb_names(days: int = 10, log=print) -> set:
    """최근 연예 글에서 다룬 인물·프로그램 집합(제목 기반 + 저장 이력 병합)."""
    names: set = set()
    for r in recent_posts(60, log):
        if r.get("cat") != CAT_CELEB_NO:
            continue
        t = r.get("title", "")
        for w in _CELEB_WORDS:
            if w in t:
                names.add(w)
        for p in _CELEB_PROGRAMS:
            if p in t:
                names.add(p)
    try:
        with open(CELEB_USED, encoding="utf-8") as f:
            saved = json.load(f)
        cutoff = time.time() - days * 86400
        names |= {n for n, ts in saved.items() if ts >= cutoff}
    except Exception:  # noqa: BLE001
        pass
    return {n for n in names if n}


def mark_celeb_used(name: str) -> None:
    """이번에 다룬 인물을 기록(다음 날 제외 대상이 된다)."""
    if not name:
        return
    try:
        saved = {}
        if os.path.exists(CELEB_USED):
            with open(CELEB_USED, encoding="utf-8") as f:
                saved = json.load(f)
        for part in re.split(r"[·,/()\s]+", name):
            if len(part) >= 2:
                saved[part] = time.time()
        with open(CELEB_USED, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    rows = recent_posts(60)
    print(f"최근 {len(rows)}편")
    ts = [r["title"] for r in rows]
    print("\n금지 틀:", banned_patterns(ts) or "(없음)")
    print("\n최근 연예 인물:", ", ".join(sorted(recent_celeb_names())) or "(없음)")
