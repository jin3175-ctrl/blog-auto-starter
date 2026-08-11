"""유튜브 @AI생존기Edi 최신 영상 썸네일 가져오기.

네이버는 본문에 외부 링크를 바로 다는 걸 좋아하지 않는다(2026-07-24 에디님 지적).
그래서 유튜브 안내 문구 뒤에는 **링크 대신 최신 영상 썸네일 이미지**만 붙인다.

채널 RSS(공개)에서 최신 영상 ID를 얻어 i.ytimg.com 썸네일을 내려받는다. API 키 불필요.
"""
from __future__ import annotations

import os
import re
import urllib.request

CHANNEL_ID = "UCFg5xp3Vmrdwe7SpEygkPNg"   # @AI생존기Edi
RSS = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
_UA = {"User-Agent": "Mozilla/5.0"}


def latest_video(timeout: int = 15) -> dict:
    """최신 영상 {video_id, title}. 실패 시 {}."""
    try:
        req = urllib.request.Request(RSS, headers=_UA)
        xml = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return {}
    vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", xml)
    title = re.search(r"<media:title>([^<]+)</media:title>", xml)
    if not vid:
        return {}
    return {"video_id": vid.group(1), "title": (title.group(1).strip() if title else "")}


def fetch_thumbnail(out_dir: str, filename: str = "yt_latest.jpg",
                    log=print, timeout: int = 20) -> str | None:
    """최신 영상 썸네일을 out_dir에 내려받고 경로 반환. 실패하면 None(글은 정상 진행)."""
    info = latest_video()
    if not info:
        log("유튜브 최신 영상 조회 실패 — 썸네일 생략")
        return None
    vid = info["video_id"]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    # maxres가 없는 영상도 있어 순서대로 폴백
    for name in ("maxresdefault", "hqdefault", "mqdefault"):
        url = f"https://i.ytimg.com/vi/{vid}/{name}.jpg"
        try:
            req = urllib.request.Request(url, headers=_UA)
            data = urllib.request.urlopen(req, timeout=timeout).read()
            if len(data) < 3000:      # 유튜브가 주는 회색 placeholder 방지
                continue
            with open(path, "wb") as f:
                f.write(data)
            log(f"유튜브 최신 썸네일 확보: {info.get('title','')[:30]} ({name})")
            return path
        except Exception:  # noqa: BLE001
            continue
    log("유튜브 썸네일 다운로드 실패 — 생략")
    return None


if __name__ == "__main__":
    print(latest_video())
    print(fetch_thumbnail("/tmp"))
