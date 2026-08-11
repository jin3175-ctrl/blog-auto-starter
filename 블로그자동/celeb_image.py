"""연예인 참고 이미지 캡처 — 유튜브(방송) 썸네일. 2026-07-31.

에디님 방침: 자막 있어도 됨. 기사(언론사) 사진 말고 방송/유튜브에 나온 것으로, 출처만 정확히.
→ 유튜브 검색 상위 영상 썸네일(방송 클립·인물 장면)을 가져온다. 출처는 본문 [사진N] 마커에
   'OOO(방송사/채널)' 로 정확히 적혀 있음(gen_celeb_ai 프롬프트가 강제).

- 인스타는 로그인·안티봇으로 자동화 취약 → 유튜브 우선.
- 저작권: 방송/유튜브 캡처 사용은 저작권 사용(연예 블로그 판에선 흔하나 침해 소지). 최종 사용은 에디님 판단.
"""
from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")}


def _yt_search_video_ids(query: str, n: int = 5, timeout: int = 15) -> list[str]:
    """유튜브 검색결과 상위 영상 videoId 목록(조회수/관련 정렬 힌트)."""
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query, "sp": "CAMSAhAB"})
    try:
        html = urllib.request.urlopen(
            urllib.request.Request(url, headers=_UA), timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return []
    ids: list[str] = []
    for m in re.finditer(r'"videoId":"([\w-]{11})"', html):
        if m.group(1) not in ids:
            ids.append(m.group(1))
        if len(ids) >= n:
            break
    return ids


def _download_thumb(video_id: str, out_path: str, timeout: int = 20) -> bool:
    for name in ("maxresdefault", "hqdefault", "mqdefault"):
        url = f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"
        try:
            data = urllib.request.urlopen(
                urllib.request.Request(url, headers=_UA), timeout=timeout).read()
            if len(data) < 3000:      # 회색 placeholder 방지
                continue
            with open(out_path, "wb") as f:
                f.write(data)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def fetch_celeb_images(name: str, program: str, out_dir: str, prefix: str,
                       n: int = 2, log=print, start: int = 1) -> list[str]:
    """인물/프로그램으로 유튜브를 검색해 상위 영상 썸네일 n장을 저장, 경로 리스트 반환.
    자막 있어도 OK(방송 출처). 실패해도 [] 반환(글은 자리표시자로 진행).
    start: 파일 번호 시작값 — 영상 캡처(celeb_video)로 이미 N장 확보한 뒤 이어붙일 때 쓴다."""
    os.makedirs(out_dir, exist_ok=True)
    # ★'옥순·영숙' 같은 나는솔로 가명은 이름만으로 검색하면 다른 기수·다른 사람이 섞인다
    #   (2026-08-03 사고) → program(프로그램명+기수)이 있으면 **이름 단독 검색은 쓰지 않는다**.
    queries = ([f"{program} {name}".strip(), program] if program
               else [name])
    queries = [q for q in queries if q]
    seen: set = set()
    saved: list[str] = []
    for q in queries:
        for vid in _yt_search_video_ids(q, n=max(4, n)):
            if vid in seen:
                continue
            seen.add(vid)
            path = os.path.join(out_dir, f"{prefix}_연예캡처{start + len(saved)}.jpg")
            if _download_thumb(vid, path):
                saved.append(path)
                if len(saved) >= n:
                    log(f"연예인 참고이미지 {len(saved)}장 캡처(유튜브 방송): '{queries[0]}'")
                    return saved
    if saved:
        log(f"연예인 참고이미지 {len(saved)}장 캡처(유튜브 방송): '{queries[0]}'")
    else:
        log(f"연예인 참고이미지 캡처 실패(자리표시자만 진행): '{name}'")
    return saved


if __name__ == "__main__":
    for nm, pg in [("나는솔로", "SBS Plus"), ("이혼숙려캠프", ""), ("오은영", "")]:
        print(nm, "→", fetch_celeb_images(nm, pg, "/tmp/celebimg", nm, n=2))
