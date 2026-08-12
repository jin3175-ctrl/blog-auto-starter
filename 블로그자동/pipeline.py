"""1편 처리 파이프라인:
   본문은 _복붙용.txt 그대로 복붙, 제목만 '지금 뜨는 인기글 패턴' 기반으로 AI 생성."""
from __future__ import annotations

import os
import re
from typing import Callable

import blog_related
import config
import image_finder
import keyword_select
import naver
import naver_titles
import parse_post
import posts
import quote_select
import render_assets
import title_gen
from claude_cli import NotLoggedInError

Logger = Callable[[str], None]


def _make_title(body: str, folder: str, post_no: str, log: Logger) -> str:
    """지금 뜨는 인기 제목 30개 → 패턴화 → 제목 생성. 실패 시 manifest 부제로 폴백."""
    try:
        log("네이버 블로그 홈 인기글 제목 수집 중…")
        trending = naver_titles.fetch_trending_titles(count=30)
        log(f"인기 제목 {len(trending)}개 수집. 패턴 분석 후 제목 생성(claude -p)…")
        title = title_gen.generate_title(body, trending)
        if not title.strip():
            log("AI 제목이 비어 있어 한 번 더 시도합니다…")
            title = title_gen.generate_title(body, trending)
        if title.strip():
            log(f"AI 생성 제목: {title}")
            return title.strip()
        log("AI 제목이 계속 비어 폴백을 사용합니다.")
    except NotLoggedInError as e:
        log(f"제목 AI 생성 건너뜀: {e}")
    except Exception as e:  # noqa: BLE001
        log(f"제목 생성 중 오류(폴백 사용): {e}")
    fallback = posts.get_manifest_subtitle(folder, post_no) or "제목 없음"
    log(f"폴백 제목 사용: {fallback}")
    return fallback


# 갤럽 34 테마 목차 순서(강점인사이트 시리즈 제목 순번용)
INSIGHT_THEME_ORDER = [
    "성취", "행동", "적응", "분석", "정리", "신념", "주도력", "커뮤니케이션", "승부", "연결성",
    "공정성", "회고", "심사숙고", "개발", "체계", "공감", "집중", "미래지향", "화합", "발상",
    "포용", "개별화", "수집", "지적사고", "배움", "최상화", "긍정", "절친", "책임", "복구",
    "자기확신", "존재감", "전략", "사교성",
]


def _insight_prefix(folder: str, post_no: str) -> str:
    """강점인사이트 글이면 '[순번. 테마] ' 접두 반환(갤럽 목차 순서)."""
    assets = posts.find_assets(folder, post_no)
    vis = assets.get("강점시각화") or assets.get("장점") or assets.get("맹점")
    if not vis:
        return ""
    m = re.match(r"\d+_(.+?)_(?:강점시각화|장점|맹점)", os.path.basename(vis))
    if not m:
        return ""
    theme = m.group(1)
    try:
        n = INSIGHT_THEME_ORDER.index(theme) + 1
    except ValueError:
        return ""
    return f"[{n}. {theme}] "


def _sentence_span(text: str, idx: int) -> tuple[int, int]:
    """text에서 idx를 포함하는 '한 문장'의 (start,end). 마침표 기준."""
    e = text.find(".", idx)
    e = e + 1 if e >= 0 else len(text)
    s = text.rfind(".", 0, idx)
    s = s + 1 if s >= 0 else 0
    while s < len(text) and text[s] == " ":
        s += 1
    return s, e


_RE_SOURCE_LINE = re.compile(r"^\s*@?\s*출처\s*[:：\-–—]\s*(.+)$")


def _normalize_source_line(blocks: list[dict], log: Logger) -> None:
    """맨 끝 출처 줄의 표기를 '@출처 : 매체명'으로 통일한다.

    생성기마다 "@출처 - Gallup, Inc." / "출처: MHN스포츠" 처럼 제각각이라 프롬프트로만
    맞추면 LLM이 흘린다. 여기서 최종 형태를 강제한다.
    (본문 중간의 [사진N - ... / 출처: ...] 마커는 photo 블록이라 여기 안 걸린다.)
    """
    for b in blocks:
        if b.get("type") != "text":
            continue
        m = _RE_SOURCE_LINE.match(b["text"])
        if not m:
            continue
        fixed = f"@출처 : {m.group(1).strip()}"
        if b["text"].strip() != fixed:
            log(f"출처 표기 통일: {b['text'].strip()[:40]} → {fixed[:40]}")
            b["text"] = fixed


# '1단계…' 또는 '첫째,/둘째,/셋째…' 처럼 연속 열거로 시작하는 머리줄
_STEP_RE = re.compile(
    r"^\s*(?:\d+\s*단계\b"
    r"|(?:첫째|둘째|셋째|넷째|다섯째|여섯째|일곱째|첫 번째|두 번째|세 번째|네 번째|다섯 번째)\s*[,，]?)")


def _apply_step_quotes(blocks: list[dict], log: Logger) -> int:
    """'1단계, …' '2단계 …' 같은 단계 머리줄을 인용구2(버티컬 라인)로 바꿔 깔끔하게."""
    n = 0
    for i, b in enumerate(blocks):
        if b.get("type") == "text" and _STEP_RE.match(b.get("text", "")):
            blocks[i] = {"type": "quote", "style": "small",
                         "nstyle": "quotation_line", "text": b["text"].strip()}
            n += 1
    if n:
        log(f"단계 머리줄 {n}곳 → 인용구2(라인형)")
    return n


def _apply_photo_subheads(blocks: list[dict], log: Logger) -> int:
    """사진(또는 사진 대체 이미지) 바로 뒤에 오는 '소주제' 줄을 66박스 인용으로 바꾼다.

    연예 원고는 사진 뒤를 소주제로 여는 패턴이 굳어져 있는데([사진4] → '무엇을 벗어던졌나'),
    프롬프트에 [소주제] 마커가 없어서 평문으로 깔렸다. AI 선정(quote_select)에 맡기면
    놓치므로 규칙으로 고정한다.

    소주제 판정: 사진 직후 첫 text 블록 + 짧음(24자 이하) + 문장부호로 끝나지 않음.
    (마침표로 끝나면 일반 문장이므로 건드리지 않는다.)
    """
    applied = []
    for i, b in enumerate(blocks):
        # 사진 자리표시자(photo) 또는 자동첨부된 본문 이미지(image/kind=body)
        is_photo = b.get("type") == "photo" or (
            b.get("type") == "image" and b.get("kind") == "body")
        if not is_photo:
            continue
        # 뒤쪽 첫 text 블록 찾기(빈 줄 건너뜀)
        j = i + 1
        while j < len(blocks) and blocks[j].get("type") == "blank":
            j += 1
        if j >= len(blocks) or blocks[j].get("type") != "text":
            continue
        t = blocks[j]["text"].strip()
        # 이미 인용/서식이 잡힌 건 건드리지 않음
        if not t or blocks[j].get("spans"):
            continue
        if len(t) > 24 or t[-1] in ".?!…\"'”’)":
            continue          # 길거나 문장부호로 끝나면 일반 문장
        blocks[j] = {"type": "quote", "style": "small", "nstyle": "default", "text": t}
        applied.append(t)
    if applied:
        log(f"사진 뒤 소주제 {len(applied)}곳 → 따옴표(66박스) 인용: {applied}")
    return len(applied)


_YT_CTA_RE = re.compile(r"AI\s*생존기\s*Edi|유튜브\s*@|@AI생존기|유튜브.{0,12}(채널|에서).{0,20}(구독|놀다|이어|보실|오세요|좋아요)")


def _strip_youtube_cta(blocks: list[dict], log: Logger) -> int:
    """연예 글에서 유튜브 채널 홍보 문단을 제거한다(2026-08-02 에디님 지시).

    연예 글은 '순수 홈판 트래픽'용이라 채널 홍보가 붙으면 성격이 흐려진다.
    프롬프트로 금지해도 LLM이 종종 넣어서 업로드 단계에서 한 번 더 걷어낸다.
    """
    keep, removed = [], 0
    for b in blocks:
        if b.get("type") == "text" and _YT_CTA_RE.search(b.get("text") or ""):
            removed += 1
            continue
        keep.append(b)
    if removed:
        blocks[:] = keep
        log(f"유튜브 채널 홍보 {removed}문단 제거(연예 글 규칙)")
    return removed


def _insert_youtube_thumb(blocks: list[dict], workdir: str, log: Logger) -> bool:
    """유튜브 안내 문구 뒤에 '최신 영상 썸네일 이미지'를 넣는다(링크는 넣지 않음).

    네이버가 본문 외부링크를 선호하지 않으므로 링크 대신 썸네일만 붙인다(2026-07-24 에디님 지시).
    실패해도 글은 그대로 진행(베스트 에포트).
    """
    idx = None
    for i, b in enumerate(blocks):
        if b.get("type") != "text":
            continue
        t = b.get("text") or ""
        if "AI생존기Edi" in t or ("유튜브" in t and "채널" in t):
            idx = i          # 마지막으로 언급된 자리에 붙인다
    if idx is None:
        return False
    try:
        import youtube_thumb
        path = youtube_thumb.fetch_thumbnail(workdir, "yt_latest.jpg", log=log)
    except Exception as e:  # noqa: BLE001
        log(f"유튜브 썸네일 실패(건너뜀): {str(e)[:100]}")
        return False
    if not path:
        return False
    blocks.insert(idx + 1, {"type": "image", "kind": "body", "path": path,
                            "label": "유튜브최신", "missing": False})
    log("유튜브 안내 뒤에 최신 영상 썸네일 삽입(링크 없음)")
    return True


def _apply_orphan_subheads(blocks: list[dict], log: Logger) -> int:
    """사진 뒤가 아닌 자리에 '홀로 떨어진' 소주제 줄을 라인형 인용으로 정리한다.

    생성기가 소주제를 [사진N] 바로 뒤가 아닌 곳에도 흘려 놓으면(예: '왜 지금 다들 찾는지',
    '저품질 함정') 평문으로 깔려서 문맥 없는 파편처럼 보인다(2026-07-24 에디님 지적).
    사진 뒤 소주제(66박스)와 구분되도록 여기선 라인형을 쓴다.

    판정(오탐 방지로 빡빡하게): 앞뒤가 모두 빈 줄인 독립 줄 + 22자 이하 +
    문장부호로 끝나지 않음 + 서식 없음.
    """
    applied = []
    for i, b in enumerate(blocks):
        if b.get("type") != "text" or b.get("spans"):
            continue
        # ★제로폭 공백(U+200B 등)은 눈에 안 보이지만 strip()으로 안 지워진다 → '빈 줄'인데도
        #   소주제로 잡혀 '내용을 입력하세요' 빈 인용박스가 대량 생성됐다(2026-08-02, 45곳).
        t = (b.get("text") or "").replace("​", "").replace("﻿", "").strip()
        # ★32자로 완화(2026-08-02): 22자 제한 때문에 목차의 '04 2026년 주의점 — 이건 조심하세요'(23자)만
        #   인용구가 안 걸려 4번 항목만 평문으로 남는 문제가 있었다(에디님 지적).
        if not t or len(t) > 32 or t[-1] in ".?!…\"'”’)":
            continue
        # 장식 기호(◆ ▶ ■ 등)는 소주제 앞에 붙어도 본문에선 지저분하다 → 떼고 쓴다
        t = re.sub(r"^[◆◇▶▷■□●○★☆※]+\s*", "", t).strip()
        if not t:
            continue
        b["text"] = t
        # 출처·해시태그·마커 줄은 소주제가 아니다(2026-07-24: '@출처 : 직접 운영 경험'이
        # 인용구로 바뀌는 버그가 있었음)
        if t.startswith(("@", "#", "[", "★", "※", "·", "-")) or "출처" in t:
            continue
        prev_blank = i == 0 or blocks[i - 1].get("type") == "blank"
        next_blank = i + 1 >= len(blocks) or blocks[i + 1].get("type") == "blank"
        if not (prev_blank and next_blank):
            continue          # 문단 속 짧은 문장은 건드리지 않음
        blocks[i] = {"type": "quote", "style": "small",
                     "nstyle": "quotation_line", "text": t}
        applied.append(t)
    if applied:
        log(f"고아 소주제 {len(applied)}곳 → 인용구2(라인형): {applied}")
    return len(applied)


def _build_spans(blocks: list[dict], folder: str, post_no: str, body: str, log: Logger) -> None:
    """각 text 블록에 서식 spans 부여.
      - 강점 키워드: 모든 등장 → 굵게+빨강
      - 핵심 키워드(첫 등장): 그 '문장'에 노랑 배경 + 키워드만 굵게
    """
    import re
    red = _detect_emphasis(folder, post_no, body)  # 강점 키워드(예: 승부(Competition))
    for b in blocks:
        if b.get("type") == "text":
            spans = []
            for p in red:
                for m in re.finditer(re.escape(p), b["text"]):
                    spans.append((m.start(), m.end(), {"bold": True, "color": naver.EMPH_RED}))
            b["spans"] = spans
    if red:
        log(f"굵게+빨강(강점): {red}")

    try:
        # 글이 길어(사진 8~12장) 6개로는 강조가 3~4곳에 그쳐 '중간중간' 느낌이 안 난다 → 10개로 확대
        kws = keyword_select.select_keywords(body, max_n=10)
    except Exception as e:  # noqa: BLE001
        log(f"핵심 키워드 선정 건너뜀: {e}")
        kws = []
    kws = [k for k in kws if k and k not in red]
    used = set()
    applied = []
    for kw in kws:
        for b in blocks:
            if b.get("type") != "text":
                continue
            idx = b["text"].find(kw)
            if idx < 0:
                continue
            s, e = _sentence_span(b["text"], idx)
            key = (id(b), s, e)
            spans = b.setdefault("spans", [])
            if key not in used:
                used.add(key)
                spans.append((s, e, {"bg": naver.EMPH_YELLOW_BG}))  # 문장 노랑 배경
            spans.append((idx, idx + len(kw), {"bold": True}))       # 키워드 굵게
            applied.append(kw)
            break
    if applied:
        log(f"노랑 하이라이트(핵심 문장): {applied}")


def _detect_emphasis(folder: str, post_no: str, body: str) -> list[str]:
    """강점 키워드 자동 감지 → 굵게+빨강 강조할 문구 목록.

    강점 이름은 '강점시각화' 에셋 파일명(예: 01_승부_강점시각화.html)에서 뽑고,
    본문에서 '승부(Competition)' 같은 '강점(영문)' 패턴을 찾아 반환.
    """
    assets = posts.find_assets(folder, post_no)
    vis = assets.get("강점시각화") or assets.get("장점") or assets.get("맹점")
    if not vis:
        return []
    m = re.match(r"\d+_(.+?)_(?:강점시각화|장점|맹점)", os.path.basename(vis))
    if not m:
        return []
    strength = m.group(1)
    phrases: list[str] = []
    # '강점(영문)' 패턴 (예: 승부(Competition))
    for mm in re.finditer(re.escape(strength) + r"\([A-Za-z][A-Za-z ]*\)", body):
        if mm.group(0) not in phrases:
            phrases.append(mm.group(0))
    # '강점 재능' 도 있으면 강조
    if f"{strength} 재능" in body and f"{strength} 재능" not in phrases:
        phrases.append(f"{strength} 재능")

    # ★ 연예 글은 프롬프트가 '강점명 1~2번, 갤럽 용어 최소화'를 지시하므로
    #   위의 '강점(영문)'·'강점 재능' 교과서식 표기가 거의 안 나온다 → 강조가 통째로 비어버린다.
    #   그래서 영문 병기가 없어도 '강점명' 자체를 굵게+빨강으로 잡는다.
    #   (이미 '강점(영문)'으로 잡힌 구간과 겹치면 _build_spans에서 뒤 span이 덮으므로 무해)
    if not phrases and re.search(r"(?<![가-힣])" + re.escape(strength) + r"(?![가-힣])", body):
        phrases.append(strength)
    return phrases


def _insert_related_links(blocks: list[dict], body: str, current_title: str, log: Logger) -> None:
    """내 블로그의 비슷한 글 3개를 '함께 보면 좋은 글' 링크카드로 @출처 앞에 삽입."""
    blog_id = naver.load_meta().get("blog_id")
    if not blog_id:
        return
    hashlines = [l for l in body.splitlines() if l.strip().startswith("#")]
    kws = [w[1:] for w in hashlines[-1].split() if w.startswith("#")] if hashlines else []
    if not kws:
        return
    try:
        mine = blog_related.fetch_my_posts(blog_id)
        rel = blog_related.pick_related(kws, current_title, mine, n=3)
    except Exception as e:  # noqa: BLE001
        log(f"관련글 수집 실패(건너뜀): {e}")
        return
    if not rel:
        log("관련글을 찾지 못해 링크 섹션 생략")
        return

    section = [{"type": "subhead", "text": "함께 보면 좋은 글"}]
    for r in rel:
        section.append({"type": "oglink", "url": r["url"], "title": r["title"]})

    # @출처 텍스트 블록 앞에 삽입(없으면 해시태그 앞, 그도 없으면 끝)
    idx = next((i for i, b in enumerate(blocks)
                if b["type"] == "text" and b["text"].lstrip().startswith("@출처")), None)
    if idx is None:
        idx = next((i for i, b in enumerate(blocks) if b["type"] == "hashtags"), len(blocks))
    blocks[idx:idx] = section
    log(f"관련글 {len(rel)}개 링크를 출처 앞에 배치: " + " / ".join(r["title"][:18] for r in rel))


_RE_PHOTO_DESC = re.compile(r"\[사진[^\]\-]*-\s*(.*?)\s*/\s*출처", re.S)


_RE_PHOTO_SRC = re.compile(r"출처\s*[:：]\s*(.+?)\s*\]?\s*$")
# 자기/툴 촬영 신호(자동첨부 대상). 이게 아니면 연예/외부 출처로 보고 자리표시자로 남긴다.
_SELF_SHOT_RE = re.compile(r"직접\s*촬영|해당\s*툴|툴\s*화면|화면\s*캡처|직접\s*제작|본인\s*(촬영|제작)|작업\s*화면")
# 연예/외부 출처 신호(사람이 직접 삽입 — 자동첨부 금지)
_CELEB_SRC_RE = re.compile(r"유튜브|인스타|채널|방송|MBC|SBS|KBS|tvN|JTBC|ENA|Mnet|화보|프로그램|드라마|예능|콘서트|공연|기자회견|@\w")


def _is_celeb_photo(text: str) -> bool:
    """[사진N …/출처: XXX] 마커가 '연예인 장면'인가 → 그렇다면 자동첨부하지 않고 자리표시자로 남긴다.

    연예인 사진은 저작권상·정확성상 에디님이 직접 넣는다(예전 연예+강점 방식). 2026-07-24 지시.
    판정: 출처가 '직접 촬영/툴 화면'이면 자기 자료(자동첨부 O). 유튜브·방송·인스타 등이면 연예(자동첨부 X).
    """
    m = _RE_PHOTO_SRC.search(text or "")
    src = (m.group(1) if m else "").strip()
    if not src:
        return False
    if _SELF_SHOT_RE.search(src):
        return False
    return bool(_CELEB_SRC_RE.search(src))


def _fill_celeb_captures(blocks: list[dict], celeb_idxs: list[int], folder: str,
                         post_no: str, log: Logger) -> int:
    """연예인 [사진N] 자리에 '확보해둔 방송 캡처'를 채운다(2026-08-02 에디님 지시).

    예전엔 저작권·정확성 때문에 자리표시자로 두고 직접 넣었지만(7/24), 이제 생성 단계에서
    유튜브 방송 캡처(`{no}_{kw}_연예캡처N.jpg`)를 확보하므로 그걸 순서대로 꽂는다.
    캡처가 모자라면 남은 자리는 그대로 자리표시자로 둔다(없는 사진을 지어내지 않는다).
    """
    import glob, re as _re
    caps = (glob.glob(os.path.join(folder, f"{post_no}_*_연예캡처*.jpg"))
            + glob.glob(os.path.join(folder, f"{post_no}_*_연예캡처*.png")))
    # 연예캡처2 < 연예캡처10 이 되도록 숫자 기준 정렬(문자열 정렬이면 10이 2보다 앞선다)
    caps.sort(key=lambda p: int((_re.search(r"연예캡처(\d+)", p) or _re.match(r"(0)", "0")).group(1)))
    if not caps:
        return 0
    filled = 0
    for n, i in enumerate(celeb_idxs):
        if n >= len(caps):
            break
        blocks[i] = {"type": "image", "kind": "body", "path": caps[n],
                     "missing": False, "label": f"연예캡처{n+1}"}
        filled += 1
    log(f"연예인 방송 캡처 {filled}장 자동 삽입"
        + (f" (자리 {len(celeb_idxs)}곳 중 {len(celeb_idxs)-filled}곳은 캡처 부족으로 자리표시자 유지)"
           if filled < len(celeb_idxs) else ""))
    return filled


def _attach_stock_images(blocks: list[dict], workdir: str, log: Logger,
                         folder: str = "", post_no: str = "") -> int:
    """[사진N] 자리표시자를 설명에 맞는 Unsplash/Gemini 이미지로 교체.
    연예인 장면은 확보된 방송 캡처로 채우고, 부족분만 자리표시자로 남긴다."""
    celeb_idxs = [i for i, b in enumerate(blocks)
                  if b.get("type") == "photo" and _is_celeb_photo(b.get("text", ""))]
    if celeb_idxs:
        filled = _fill_celeb_captures(blocks, celeb_idxs, folder, post_no, log) if folder else 0
        if not filled:
            log(f"연예인 사진 {len(celeb_idxs)}곳은 자리표시자로 유지(캡처 없음 — 직접 삽입)")
        # 채워진 자리는 photo가 아니게 되므로 아래 스톡 대상에서 자동 제외된다
        celeb_idxs = [i for i in celeb_idxs if blocks[i].get("type") == "photo"]
    photo_idxs = [i for i, b in enumerate(blocks)
                  if b.get("type") == "photo" and i not in celeb_idxs]
    if not photo_idxs:
        return 0
    descs = []
    for i in photo_idxs:
        m = _RE_PHOTO_DESC.search(blocks[i]["text"])
        descs.append(m.group(1).strip() if m else blocks[i]["text"])
    log(f"본문 이미지 {len(descs)}개 검색어 번역 중(claude -p)…")
    queries = image_finder.translate_queries(descs)
    attached = 0
    # ★웹 구독 이미지는 **한 브라우저 세션에서 일괄 생성**(2026-08-04).
    #   장당 브라우저를 새로 띄우던 방식은 5분27초/장이라 6장에 33분이 걸렸다.
    out_paths = [os.path.join(workdir, f"body_{n+1:02d}.jpg") for n in range(len(photo_idxs))]
    web_ok = [False] * len(photo_idxs)
    try:
        import web_image
        # ★로그아웃된 프로필로 시도하면 장당 2.5분씩 헛되이 태운다(2026-08-04 실측: 6장 15분).
        #   먼저 로그인 여부를 한 번만 확인하고, 아니면 즉시 API/스톡으로 넘어간다.
        #   EDI_NO_WEBIMG=1 이면 아예 건너뛴다(급할 때).
        if os.environ.get("EDI_NO_WEBIMG"):
            log("웹 구독 이미지 생략(EDI_NO_WEBIMG) → API/스톡 사용")
        else:
            log(f"본문 이미지 {len(descs)}개 웹 구독(제미나이) 일괄 생성 중…")
            web_ok = web_image.make_many(descs, out_paths, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"웹 이미지 일괄 생성 실패 → 스톡 폴백({str(e)[:40]})")
    for n, i in enumerate(photo_idxs):
        out_path = out_paths[n]
        q = queries[n] if n < len(queries) else descs[n]
        # 웹 생성이 안 된 자리만 Unsplash/Gemini API로 채운다.
        made = bool(web_ok[n]) if n < len(web_ok) else False
        if made:
            blocks[i] = {"type": "image", "kind": "body", "path": out_path,
                         "missing": False, "label": f"본문사진{n+1}"}
            attached += 1
        elif image_finder.search_download(q, out_path):
            blocks[i] = {"type": "image", "kind": "body", "path": out_path,
                         "missing": False, "label": f"본문사진{n+1}"}
            attached += 1
        elif image_finder.generate_gemini(descs[n], out_path):
            # Unsplash에서 못 찾으면 설명대로 Gemini API가 사진을 생성해 대체
            blocks[i] = {"type": "image", "kind": "body", "path": out_path,
                         "missing": False, "label": f"본문사진{n+1}"}
            attached += 1
            log(f"본문사진{n+1} Unsplash 실패 → Gemini 생성으로 대체")
        else:
            # 수강생 배포판: 이미지가 안 붙어도 '어디에 넣어야 하는지'는 남긴다.
            # (원본은 마커를 지웠지만, 키가 없는 사람은 자리 표시가 없으면 사진을 못 넣는다)
            blocks[i] = {"type": "text", "text": f"[사진{n+1} - {descs[n]}]"}
            log(f"본문사진{n+1} 이미지 없음 → 자리 표시만 남김(발행 전 직접 넣으세요)")
    log(f"본문 이미지 {attached}/{len(descs)}개 자동 첨부 완료")
    return attached


ENUM_RE = re.compile(r"(첫째|둘째|셋째|넷째|다섯째|여섯째|일곱째|여덟째|아홉째|열째)\s*[,，]")


def _split_enumerations(blocks: list[dict], log: Logger) -> None:
    """'첫째, … 둘째, …'처럼 한 문단에 몰린 열거를 각각 별도 문단으로 분리
    (문단마다 자동으로 한 줄 띄우므로 눈에 잘 보이게 됨)."""
    out: list[dict] = []
    changed = 0
    for b in blocks:
        if b.get("type") != "text":
            out.append(b)
            continue
        text = b["text"]
        starts = [m.start() for m in ENUM_RE.finditer(text)]
        if len(starts) < 2:
            out.append(b)
            continue
        if starts[0] > 0:
            pre = text[:starts[0]].strip()
            if pre:
                out.append({"type": "text", "text": pre})
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(text)
            seg = text[s:e].strip()
            if seg:
                out.append({"type": "text", "text": seg})
        changed += 1
    if changed:
        blocks[:] = out
        log(f"열거(첫째·둘째…) {changed}곳을 줄 나눔")


def _spread_insight_visuals(blocks: list[dict], log: Logger) -> None:
    """강점 시각화 3종(강점시각화·장점·맹점 카드)을 한곳에 몰지 않고 흩어 배치.
    강점시각화 → 첫 소주제 앞(키워드 설명 뒤), 장점 → 표 뒤, 맹점 → 대주제(그림자) 뒤."""
    def pop_card(label):
        for i, b in enumerate(blocks):
            if b.get("type") == "image" and b.get("kind") == "card" and b.get("label") == label:
                return blocks.pop(i)
        return None

    viz = pop_card("강점시각화")
    merit = pop_card("장점카드")
    blind = pop_card("맹점카드")
    if not any([viz, merit, blind]):
        return

    def ins(block, pred, after=False):
        if block is None:
            return
        idx = next((i for i, b in enumerate(blocks) if pred(b)), None)
        if idx is None:
            blocks.append(block)
        else:
            blocks.insert(idx + 1 if after else idx, block)

    ins(viz, lambda b: b.get("type") == "quote" and b.get("style") == "small", after=False)
    ins(merit, lambda b: b.get("type") == "table_paste", after=True)
    ins(blind, lambda b: b.get("type") == "quote" and b.get("style") == "big", after=True)
    log("강점 시각화 3종을 본문에 흩어 배치(시각화→장점→맹점)")


_GREET_RE = re.compile(
    r"^\s*(안녕하세요|안녕하십니까|반갑습니다).*$|"                               # 인사
    r"^\s*여러분.*$|"                                                          # '여러분…'(뒤 조사 '의' 등 포함)
    r"^\s*오늘은[,\s].*$|"                                                     # '오늘은, …'
    r"^\s*.{0,25}(에디|저)\s*입니다[.!]?\s*$|"                                  # '…에디/저입니다'
    r".*(정리해|전해|소개해|안내해|전달해|알려)\s*드리는\s*\S{1,12}(입니다|이에요|예요|에요)[.!~]*\s*\S{0,3}$|"  # '~해 드리는 OO입니다/이에요'
    r".*블로거\s*\S{1,12}(입니다|이에요|예요|에요)[.!~]*\s*\S{0,3}$|"                 # '블로거 OO입니다'
    # 지어낸 페르소나 자기소개: '…OO이에요/예요'로 끝나는 짧은 줄(이모지 허용).
    #  실측: '안녕하세요~ 햄찡이에요 🐹'(08-02), '…정리해 드리는 엘라입니다'(08-01).
    r"^\s*.{0,20}(이에요|예요|에요|입니다)[.!~]*\s*[\U0001F300-\U0001FAFF☀-➿]+\s*$")


def _strip_greeting_intro(body: str, log=lambda m: None) -> str:
    """본문 첫 부분의 인사·자기소개 줄을 제거한다(홈판 위너는 인사로 시작 안 함).
    '제목:' 줄은 보존하고, 그 아래 첫 텍스트 줄들 중 인사/자기소개만 걷어낸다."""
    lines = body.splitlines()
    out, removed, scanned = [], 0, 0
    for ln in lines:
        s = ln.strip()
        if re.match(r"^\s*제목\s*[:：]", ln) or not s:
            out.append(ln)
            continue
        # ★도입부 앞 8줄까지 훑는다(2026-08-02): 후킹 2~3줄을 먼저 쓴 뒤 인사를 끼우는
        #   패턴이 있었다("안녕하세요~ 햄찡이에요 🐹"가 3번째 줄). 첫 줄만 보면 놓친다.
        if scanned < 8:
            scanned += 1
            if removed < 3 and _GREET_RE.match(s):
                removed += 1
                continue
        out.append(ln)
    if removed:
        log(f"도입 인사·자기소개 {removed}줄 제거(홈판 규칙)")
    return "\n".join(out)


def process_post(post_no: str, log: Logger, publish: bool = False, folder: str | None = None,
                 category: str = "", reserve_at=None) -> dict:
    folder = folder or config.resolve_date_folder()
    if not folder:
        return {"ok": False, "message": "원고 폴더를 찾을 수 없습니다."}
    date_str = os.path.basename(folder)

    post = posts.get_post(folder, post_no)
    if not post:
        return {"ok": False, "message": f"{post_no}편을 폴더에서 찾지 못했습니다."}

    cat = posts.category(post["body_path"])
    log(f"원고 읽는 중({cat}): {os.path.basename(post['body_path'])}")
    with open(post["body_path"], encoding="utf-8") as f:
        body = f.read()
    # ★보이지 않는 문자 제거(2026-08-02): LLM이 문단 간격용으로 제로폭 공백(U+200B)만 든 줄을
    #   38개 넣었고, strip()으로 안 지워져 '빈 줄'이 아닌 소주제로 잡혀 '내용을 입력하세요'
    #   빈 인용박스가 45곳 생겼다. 파싱 전에 원본에서 걷어낸다.
    _zw = body.count("​") + body.count("﻿")
    if _zw:
        body = body.replace("​", "").replace("﻿", "")
        log(f"보이지 않는 문자(제로폭 공백) {_zw}개 제거")
    # ★LLM이 남긴 편집 지시용 라벨 줄 제거(2026-08-02): '[요약 3줄]'이 본문에 그대로 노출됐다.
    #   [사진N]·[표]·[커넥트]는 실제 마커라 남긴다.
    _lab = re.compile(r"^\s*\[(?!사진|표|커넥트)[^\]]{1,20}\]\s*$", re.M)
    _hits = len(_lab.findall(body))
    if _hits:
        body = _lab.sub("", body)
        log(f"편집 라벨 줄 {_hits}개 제거(예: [요약 3줄])")
    # ★[[경험 보태기: …]] 같은 편집용 자리표시자 제거(2026-08-06 자동 발행 전환).
    #   프롬프트로 금지해도 LLM이 남길 때가 있는데, 공개 발행되면 그대로 노출된다.
    # ★[사진N]·[표]·[커넥트] 마커가 문장 끝/중간에 붙어 있으면 파서(줄 전체 매칭)가 못 잡아
    #   본문에 대괄호 텍스트가 그대로 노출된다(2026-08-06 실측: "…씁니다. [사진7 - …]").
    #   → 마커 앞뒤를 줄바꿈으로 떼어 독립된 줄로 만든다.
    _fix = len(re.findall(r"(?<!\n)\s*\[(?:사진|표|커넥트)[^\]]*\]", body))
    if _fix:
        body = re.sub(r"[ \t]*(\[(?:사진|표|커넥트)[^\]]*\])[ \t]*", r"\n\n\1\n\n", body)
        body = re.sub(r"\n{3,}", "\n\n", body)
        log(f"본문에 붙어 있던 마커 {_fix}개를 독립 줄로 분리")
    _slot = len(re.findall(r"\[\[[^\]]*\]\]", body))
    if _slot:
        body = re.sub(r"\s*\[\[[^\]]*\]\]\s*", " ", body)
        log(f"편집용 슬롯 {_slot}개 제거(자동 발행 대비)")
    body = _strip_greeting_intro(body, log)   # 홈판 필수: 인사·자기소개 도입 제거

    workdir = config.work_dir_for(date_str, post_no)

    # 제목: 원고 상단에 '제목:' 줄이 있으면(생성기가 만든 후킹 제목) 그대로 사용,
    # 없으면 인기글 패턴으로 AI 생성.
    _tm = re.search(r"(?m)^\s*제목\s*[:：]\s*(.+)$", body[:600])
    if _tm and _tm.group(1).strip():
        title = _tm.group(1).strip()
        log(f"원고 후킹 제목 사용: {title}")
    else:
        title = _make_title(body, folder, post_no, log)
    # 강점인사이트는 제목 앞에 시리즈 순번 '[N. 테마] ' 추가
    if cat == "insight":
        prefix = _insight_prefix(folder, post_no)
        if prefix and not title.lstrip().startswith("["):
            title = prefix + title
            log(f"제목에 시리즈 순번 추가 → {title}")

    log("HTML 카드/표를 이미지로 렌더링 중…")
    html_assets = posts.find_assets(folder, post_no)
    png_map, rlogs = render_assets.render_assets(html_assets, workdir)
    for l in rlogs:
        log("  " + l)

    # 본문은 원문 그대로 파싱(마커→블록). 제목은 위에서 만든 것을 사용.
    _, blocks = parse_post.parse_rewritten(body, png_map)

    # 비연예 글은 [사진N]을 Unsplash/Gemini 이미지로 자동 교체(연예글은 방송캡처라 자리표시자 유지)
    # AI 실전 글(ai.flag)도 이미지 자동첨부 대상(직접 촬영 자리를 비워두지 않음)
    import glob as _glob
    is_ai = bool(_glob.glob(os.path.join(folder, f"{post_no}_*_ai.flag"))) if folder else False
    if cat != "celeb" or is_ai:
        _attach_stock_images(blocks, workdir, log, folder=folder, post_no=post_no)
    else:
        # 순수 연예글: 스톡 이미지는 안 붙이되, 확보해둔 '실제 방송 캡처'는 [사진N]에 채운다
        # (2026-08-02 에디님: 연예 글에 사진 10~13장). 캡처가 없으면 자리표시자 그대로.
        _celeb_idxs = [i for i, b in enumerate(blocks)
                       if b.get("type") == "photo" and _is_celeb_photo(b.get("text", ""))]
        if _celeb_idxs and folder:
            if not _fill_celeb_captures(blocks, _celeb_idxs, folder, post_no, log):
                log(f"연예인 사진 {len(_celeb_idxs)}곳은 자리표시자로 유지(캡처 없음)")

    # 표: 이미지 대신 '텍스트 표'로 붙여넣기(더 크고 선명, 복사 가능)
    if html_assets.get("표"):
        for i, b in enumerate(blocks):
            if b.get("type") == "image" and b.get("kind") == "table":
                blocks[i] = {"type": "table_paste", "html_path": html_assets["표"]}
                log("표를 텍스트 표(붙여넣기)로 전환")
                break

    # 인사이트: 강점 시각화 3종을 한곳에 몰지 않고 본문에 흩어 배치
    if cat == "insight":
        _spread_insight_visuals(blocks, log)

    # 썸네일 배치: 항상 맨 위 대표사진으로(네이버가 첫 이미지를 대표사진으로 잡음).
    # (강점 카드가 있던 시절엔 그 앞에 뒀으나, 셀럽 실용정보 전환으로 강점 카드가 없어져 맨 위로 통일)
    thumb = png_map.get("썸네일")
    if thumb:
        tb = {"type": "image", "kind": "thumb", "path": thumb, "label": "대표썸네일", "missing": False}
        blocks.insert(0, tb)
        log("썸네일을 맨 위 대표사진으로 배치")

    # 열거(첫째·둘째…)는 각각 줄 나눠 눈에 잘 보이게
    _split_enumerations(blocks, log)

    # '1단계, 2단계…' 머리줄 → 인용구2(라인형)로 깔끔하게
    _apply_step_quotes(blocks, log)

    # 사진 뒤 소주제 → 따옴표(66박스) 인용. quote_select보다 먼저 돌려서
    # 소주제가 quote로 바뀌면, 평문만 고르는 quote_select가 중복 선택하지 않는다.
    _apply_photo_subheads(blocks, log)

    # 사진 뒤가 아닌 곳에 홀로 남은 소주제 → 라인형 인용(평문 파편 방지)
    _apply_orphan_subheads(blocks, log)

    # ★유튜브 채널 홍보는 모든 글에서 뺀다(2026-08-02 에디님: "에디 채널 이야기 넣지 말라니까").
    #  전엔 연예편만 제거하고 AI·쇼핑편엔 썸네일까지 붙였는데, 그것도 빼라는 지시.
    _strip_youtube_cta(blocks, log)
    # '@출처 : 직접 운영 경험' 류도 뺀다(내 경험 글엔 불필요). 단 연예글은 방송/매체 출처가 필요해 유지.
    if cat != "celeb":
        _n = len(blocks)
        blocks[:] = [b for b in blocks
                     if not (b.get("type") == "text"
                             and re.match(r"^\s*@?\s*출처\s*[:：]", b.get("text") or ""))]
        if len(blocks) < _n:
            log(f"'@출처' 줄 {_n - len(blocks)}개 제거")

    # 중간중간 가독성 인용(질문/반전/강조) — AI가 본문 문장 선정 → 인용구 변환
    # (단, 열거 항목에는 인용을 넣지 않음)
    try:
        picks = quote_select.select_quotes(body, max_n=4)
        n = quote_select.apply_quotes(blocks, picks)
        if n:
            log(f"가독성 인용 {n}곳 추가(질문/반전/강조 자동 선정)")
    except Exception as e:  # noqa: BLE001
        log(f"가독성 인용 건너뜀: {e}")

    log(f"파싱 완료: 블록 {len(blocks)}개 (본문 원문 유지)")

    # 처리 결과 미리보기 저장
    with open(os.path.join(workdir, "제목.txt"), "w", encoding="utf-8") as f:
        f.write(title + "\n")

    # 출처 표기를 '@출처 : 매체명'으로 통일.
    # (_insert_related_links가 '@출처'로 시작하는 블록을 찾아 그 앞에 링크를 넣으므로 반드시 먼저 실행)
    _normalize_source_line(blocks, log)

    # '함께 보면 좋은 글' 관련글 링크 카드를 출처 앞에 삽입
    _insert_related_links(blocks, body, title, log)

    # 서식 스팬 구성: 강점=굵게+빨강(모든 등장), 중요문장=노랑배경+키워드굵게(첫 등장)
    _build_spans(blocks, folder, post_no, body, log)

    action = "공개 발행" if publish else "임시저장"
    log(f"네이버 스마트에디터로 {action}을 시작합니다…")
    result = naver.save_draft(title, blocks, png_map.get("썸네일"), log, publish=publish,
                              category=category, reserve_at=reserve_at)

    result.setdefault("notes", [])
    result["title"] = title
    return result
