"""연예인 얼굴을 '유튜브 영상 화면 캡처'로 확보 (에디 블로그 이식본, 2026-08-01).

제이 경제 블로그(/Users/edi/경제이슈 블로그 자동화/celeb_video.py)의 검증된 방식을 이식:
  유튜브 '시청 페이지'(embed 아님) 영상을 Playwright(headless, --use-gl=swiftshader)로 재생하며
  여러 시점을 스크린샷 → Gemini 비전으로 그 연예인 얼굴이 선명한 프레임만 선별.

에디 블로그용 차이:
  · 영상 검색을 제이의 YouTube Data API(OAuth) 대신 **키리스 스크래핑**(celeb_image._yt_search_video_ids)으로.
  · 썸네일(사진 1장)+본문(여러 장) 용도로 **fetch_multi**(여러 장 반환) 추가. (에디님: 여기선 사진만, 텍스트 얹기 없음.)

⚠️ 방송/유튜브 캡처는 저작권 소지(그 판에선 흔함). 최종 사용은 에디님 판단.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request

import celeb_image        # 키리스 유튜브 영상ID 검색 재사용
import gemini_thumb as GT  # VISION_MODEL
import image_finder        # _load_key


def _search(name: str, log=print, n: int = 22, context: str = "") -> list[tuple[str, str]]:
    """영상 검색(키리스) → [(videoId, channel)]. 채널명은 키리스라 미상('').

    ★context(프로그램명+기수)를 반드시 앞에 붙인다(2026-08-03 사고):
      '나는 솔로'의 출연자는 **영수·영식·영철·광수·상철·영자·정숙·영숙·순자·현숙·옥순** 같은
      **기수마다 반복되는 가명**이다. '옥순 인터뷰'로 검색하면 32기가 아닌 다른 기수 옥순이,
      심지어 영숙 사진이 섞여 들어온다(실제 발생). 'context'로 기수를 고정해야 한다.
    """
    q = (f"{context} {name}".strip() if context else f"{name} 인터뷰")
    try:
        ids = celeb_image._yt_search_video_ids(q, n=n)
        if len(ids) < 4 and context:      # 너무 적으면 프로그램만으로 한 번 더
            ids += [v for v in celeb_image._yt_search_video_ids(context, n=n) if v not in ids]
        log(f"  검색어: '{q}' → 영상 {len(ids)}개")
        return [(vid, "") for vid in ids]
    except Exception as e:  # noqa: BLE001
        log(f"  유튜브 검색 실패: {str(e)[:60]}")
        return []


# '나는 솔로' 계열은 출연자를 기수마다 같은 가명으로 부른다 → 얼굴로 신원 판별 불가.
ALIAS_NAMES = ("영수", "영식", "영철", "영호", "광수", "상철", "동수", "경수",
               "영자", "정숙", "영숙", "순자", "현숙", "옥순", "영옥")


def is_alias_name(name: str) -> bool:
    """나는솔로식 가명인가(→ 이름 자막이 보여야만 그 사람으로 인정)."""
    n = (name or "").strip()
    return any(a == n or n.endswith(a) for a in ALIAS_NAMES)


def _face_ok(img_path: str, name: str, key: str, log=print, season: str = "") -> bool:
    """그 연예인 얼굴이 선명하게 잡혔나(단독·정면 위주). 검사 실패=탈락(안전)."""
    try:
        b64 = base64.b64encode(open(img_path, "rb").read()).decode()
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GT.VISION_MODEL}:generateContent?key={key}")
        # ★'옥순·영숙·영수'처럼 나는솔로 가명은 실존 유명인이 아니라 비전이 신원을 못 가린다
        #   → 'wrong_person' 판정에 기대지 말고 **프레임 품질**(얼굴 또렷·단독)로만 거른다.
        #   신원 정확도는 검색어(프로그램+기수)로 확보한다. 2026-08-03.
        # ★'옥순·영숙·영수'처럼 나는솔로 가명은 얼굴로 신원을 못 가린다 → **화면 자막/이름표**를 읽는다.
        #   이 프로그램들은 발언자 이름을 화면에 표시하는 일이 많아, 그걸로 본인 프레임을 골라낼 수 있다.
        #   (2026-08-03: 32기 옥순 글에 남자 출연자·다른 기수 사진이 섞여 들어간 사고)
        q = (f'대상 인물: "{name}". 이 방송 캡처 프레임에 대해 JSON 하나로만: '
             '{"face_clear": 사람 얼굴이 또렷하게 크게 보이면 true(뒷모습·너무 작음·풍경·'
             '자막만·여러 명이 작게 나오면 false), '
             f'"name_shown": 화면 자막이나 이름표에 "{name}"이라는 이름이 보이면 true 아니면 false, '
             f'"season_text": 화면에 보이는 기수 표기를 그대로(예 "30기", "32기"). 없으면 "", '
             f'"is_target": 화면에서 가장 크게 보이는 인물이 "{name}"으로 보이면 true, '
             '명백히 다른 사람이거나 알 수 없으면 false}')
        body = json.dumps({"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": b64}}, {"text": q}]}]}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=25).read())
        import re
        m = re.search(r"\{.*\}", data["candidates"][0]["content"]["parts"][0]["text"], re.S)
        r = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001
        return False
    if not r.get("face_clear"):
        return False
    # ★가명 출연자('나는 솔로'의 옥순·영숙·영수…)는 얼굴로 신원을 못 가린다 → **이름 자막이 보일 때만** 채택.
    #   (2026-08-03 에디님 B안: "틀린 사람 사진보다 장수가 적은 게 낫다")
    #   오은영·이호선처럼 실존 유명인은 비전이 식별하므로 is_target도 인정한다.
    # ★기수 불일치는 탈락(2026-08-03: '32기 옥순' 글에 **30기 옥순** 인터뷰가 들어왔다).
    #   같은 가명이 기수마다 있으므로 화면 기수 표기가 요청 기수와 다르면 다른 사람이다.
    shown_season = (r.get("season_text") or "").strip()
    if season and shown_season and shown_season.replace(" ", "") != season.replace(" ", ""):
        return False
    if is_alias_name(name):
        return bool(r.get("name_shown"))
    return bool(r.get("name_shown") or r.get("is_target"))


def _capture_frames(vid: str, out_dir: str, fracs=(0.15, 0.35, 0.55, 0.75), log=print) -> list[str]:
    """한 영상에서 여러 시점 프레임 캡처. 반환: png 경로 리스트."""
    shots = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=[
                "--autoplay-policy=no-user-gesture-required", "--use-gl=swiftshader"])
            pg = b.new_context(viewport={"width": 1280, "height": 720}, locale="ko-KR").new_page()
            pg.goto(f"https://www.youtube.com/watch?v={vid}", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(4000)
            for t in ["모두 수락", "동의", "Accept all"]:
                try:
                    pg.click(f'button:has-text("{t}")', timeout=1200); break
                except Exception:  # noqa: BLE001
                    pass
            pg.wait_for_timeout(2000)
            dur = pg.evaluate('()=>{const v=document.querySelector("video");return v?v.duration:0;}') or 120
            for i, fr in enumerate(fracs):
                tsec = max(5, dur * fr)
                pg.evaluate(f'()=>{{const v=document.querySelector("video");if(v){{v.muted=true;v.currentTime={tsec};v.play();}}}}')
                pg.wait_for_timeout(3200)
                el = pg.query_selector("video")
                if el:
                    fp = os.path.join(out_dir, f"_vcap_{vid}_{i}.png")
                    el.screenshot(path=fp); shots.append(fp)
            b.close()
    except Exception as e:  # noqa: BLE001
        log(f"  캡처 실패({vid}): {str(e)[:60]}")
    return shots


def fetch(name: str, out_path: str, log=print, max_videos: int = 3) -> dict | None:
    """유튜브 영상 캡처로 연예인 얼굴 1장. 반환 {path, source, channel} 또는 None."""
    got = fetch_multi(name, os.path.dirname(os.path.abspath(out_path)) or "/tmp",
                      prefix=os.path.splitext(os.path.basename(out_path))[0],
                      want=1, log=log, max_videos=max_videos)
    if not got:
        return None
    os.replace(got[0]["path"], out_path)
    return {"path": out_path, "source": got[0]["source"], "channel": got[0]["channel"]}


def _frame_quality_ok(img_path: str, key: str) -> bool:
    """'이미 본인 확인된 영상'의 추가 프레임용 — 사람 얼굴이 또렷한지만 본다(신원은 영상으로 보증)."""
    try:
        b64 = base64.b64encode(open(img_path, "rb").read()).decode()
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GT.VISION_MODEL}:generateContent?key={key}")
        q = ('이 방송 캡처에 대해 JSON 하나로만: {"face_clear": 사람 얼굴이 또렷하고 크게 보이면 true, '
             '뒷모습·너무 작음·풍경·자막만이면 false}')
        body = json.dumps({"contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": b64}}, {"text": q}]}]}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=25).read())
        import re
        m = re.search(r"\{.*\}", data["candidates"][0]["content"]["parts"][0]["text"], re.S)
        return bool((json.loads(m.group(0)) if m else {}).get("face_clear"))
    except Exception:  # noqa: BLE001
        return False


def _img_sig(path: str) -> str:
    """이미지 지문(중복 프레임 판별용). 작게 줄여 그레이스케일 해시 — 거의 같은 장면이면 같은 값."""
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((12, 12))
        px = list(im.getdata())
        avg = sum(px) / len(px)
        return "".join("1" if v > avg else "0" for v in px)
    except Exception:  # noqa: BLE001
        import hashlib
        return hashlib.md5(open(path, "rb").read()).hexdigest()


def _too_similar(sig: str, seen: list[str], thresh: int = 12) -> bool:
    """이미 채택한 프레임과 거의 같은가(해밍거리)."""
    for s in seen:
        if len(s) == len(sig) and sum(a != b for a, b in zip(s, sig)) <= thresh:
            return True
    return False


def fetch_multi(name: str, out_dir: str, prefix: str, want: int = 5,
                log=print, max_videos: int = 20, context: str = "",
                anon: bool = False) -> list[dict]:
    """유튜브 영상들에서 그 인물 프레임을 want장까지 확보.
    context = 프로그램명+기수(예: '나는 솔로 32기') — 가명 출연자 구분에 필수.

    anon=True(★2026-08-06 신설): 출연자가 **일반인·비공개**인 경우(이혼숙려캠프 23기 부부,
    나는솔로 28기 옥순처럼 이름으로 얼굴을 특정할 수 없는 경우). 이름 기반 `_face_ok`는
    제미나이가 매칭할 수 없어 **영상 20개를 돌아도 0장**이 나온다(실측). 이 모드에서는
    이름 검증 대신 **프로그램 검색 결과 + 프레임 품질**로 채택한다. 신원 보증이 약해지므로
    호출부는 '발행 전 인물 확인' 로그를 남길 것(연예편은 임시저장 후 검토가 전제).

    반환: [{path, source, channel}] (path = {out_dir}/{prefix}_얼굴{N}.png)."""
    key = image_finder._load_key("GEMINI_API_KEY")
    if not key:
        log("  GEMINI_API_KEY 없음 → 얼굴 캡처 불가")
        return []
    vids = _search(name, log, context=context)
    if not vids:
        log(f"  '{name}' 영상 검색 결과 없음")
        return []
    os.makedirs(out_dir, exist_ok=True)
    import re as _re
    _m = _re.search(r"(\d{1,2}\s*기)", context or "")
    _season = _m.group(1).replace(" ", "") if _m else ""    # 예 '32기' — 다른 기수 프레임 배제용
    picked: list[dict] = []
    sigs: list[str] = []          # 채택한 프레임 지문(같은 장면 반복 방지)
    for vid, ch in vids[:max_videos]:
        if len(picked) >= want:
            break
        log(f"  영상 캡처: {ch or '유튜브'} ({vid})")
        # ★한 영상에서 많이 뽑으면 '거의 같은 장면'이 연달아 나온다(2026-08-02 에디님 지적:
        #   1·2·3번, 4·5·6번 사진이 똑같아 보임). 시점을 멀리 띄우고, 영상당 채택은 2장으로 제한해
        #   여러 영상에 고루 퍼지게 한다.
        fracs = (0.10, 0.25, 0.40, 0.55, 0.70, 0.85)  # 판정이 엄격해져 후보를 넉넉히 본다
        frames = _capture_frames(vid, out_dir, fracs=fracs, log=log)
        per_video = 0
        # ★이름 자막이 한 번이라도 확인된 영상은 '그 사람 영상'으로 보고, 같은 영상의 다른 프레임도
        #   인정한다(2026-08-03). 자막은 항상 떠 있지 않아 엄격 판정만으론 1장밖에 못 건졌다.
        verified_video = False
        for fp in frames:
            if len(picked) >= want or per_video >= 2:   # 영상당 최대 2장(중복 장면 방지)
                break
            sig = _img_sig(fp)
            if _too_similar(sig, sigs):       # 앞서 채택한 것과 거의 같은 장면이면 버린다
                continue
            _ok = (_frame_quality_ok(fp, key) if anon
                   else (_face_ok(fp, name, key, log, season=_season)
                         or (verified_video and _frame_quality_ok(fp, key))))
            if _ok:
                dst = os.path.join(out_dir, f"{prefix}_얼굴{len(picked)+1}.png")
                os.replace(fp, dst)
                picked.append({"path": dst, "source": f"https://www.youtube.com/watch?v={vid}",
                               "channel": ch})
                sigs.append(sig)
                per_video += 1
                verified_video = True
                log(f"  ✅ 얼굴 프레임 {len(picked)} 확보")
        for fp in frames:  # 남은 프레임 정리
            if os.path.exists(fp):
                try: os.remove(fp)
                except OSError: pass
    log(f"  → 총 {len(picked)}/{want}장 확보")
    return picked


if __name__ == "__main__":
    import sys
    nm = sys.argv[1] if len(sys.argv) > 1 else "오은영"
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    out = os.path.join(os.path.expanduser("~/홈판자료/블로그오토"), "_celeb_video_test")
    print("결과:", json.dumps(fetch_multi(nm, out, prefix=f"test_{nm}", want=want, log=print),
                              ensure_ascii=False, indent=1))
