"""매일 아침 글 한 편 → 임시저장 (사람 없이 · 2026-10-25 · 3기 3주차).

    python 오늘글_자동.py          # 지금 한 편 (예약이 부르는 것도 이것)
    python 오늘글_자동.py --dry    # 글만 쓰고 임시저장은 안 함(원고 파일만)

하는 일
  1) 기사거리 — 내정보.txt 「내 블로그 주제」로 최근 기사 몇 개(기사거리.py와 같은 검색)
  2) 클로드(`claude -p`)가 내이야기.md · 홈판채점표.md 를 보고 한 편을 쓴다. 90점 넘긴 최종본만 받는다
  3) 원고/오늘날짜/NN_키워드_복붙용.txt 로 저장
  4) pipeline.process_post → 맥=에고라이트 · 윈도우=어사이드 CLI 로 **임시저장**
     (어사이드는 2주차처럼 어사이드 AI에게 부탁하지 않는다 — aside_publish.py 가 창을 직접 움직인다)

🔴임시저장까지만. 발행은 아침에 사람이 내 경험·사진을 넣고 직접 누른다(config.AUTO_PUBLISH=False).
기록: work/오늘글_자동.log — 멈추면 이 파일 맨 아랫줄부터 읽는다(3주차 「로그 읽는 법」).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
LOG = os.path.join(HERE, "work", "오늘글_자동.log")
LOCK = os.path.join(HERE, "work", "오늘글_자동.lock")


def log(msg: str):
    line = f"[{datetime.now():%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _find_tools():
    """예약(launchd·작업 스케줄러)은 PATH가 짧다 — claude·aside·ego-browser 자리를 PATH에 더한다."""
    home = os.path.expanduser("~")
    extra = [os.path.join(home, ".local", "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    la = os.environ.get("LOCALAPPDATA")
    if la:
        extra += [os.path.join(la, "Aside", "CLI"), os.path.join(la, "Aside", "CLI", "bin")]
    if os.name == "nt":
        extra += [os.path.join(home, ".local", "bin"), os.path.join(home, "AppData", "Roaming", "npm")]
    os.environ["PATH"] = os.pathsep.join([p for p in extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])
    return shutil.which("claude")


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def _news(topic: str) -> list:
    try:
        import celeb_sources as S
        import 기사거리 as G
    except Exception as e:  # noqa: BLE001
        log(f"기사거리 모듈을 못 불렀습니다(기사 없이 씁니다): {str(e)[:80]}")
        return []
    out, seen = [], set()
    for w in G._topic_words(topic)[:3]:
        try:
            for it in S.fetch_news_search(w, limit=6):
                k = it["title"][:30]
                if k not in seen:
                    seen.add(k)
                    out.append(it)
        except Exception as e:  # noqa: BLE001
            log(f"[{w}] 기사 검색 실패: {str(e)[:60]}")
    return out[:6]


PROMPT = """너는 아래 블로그 주인 대신 네이버 블로그 홈판(홈피드)용 글 한 편을 쓴다. 존댓말.

[내 블로그]
{info}

[내 이야기 — 이 중 하나 이상을 글에 꼭 넣는다. 지어내지 않는다]
{story}

[최근 기사거리 — 하나를 골라 오늘 이야깃거리로 쓴다. 기사 문장을 베끼지 않는다]
{news}

[채점표 — 스스로 점수를 매겨 90점이 안 되면 고쳐 쓴다. 점수는 출력하지 않는다]
{score}

[출력 형식 — 이 형식의 최종본 하나만 출력한다. 설명·점수·인사말 금지]
제목: (제목 한 줄)
(본문 — 휴대폰에서 읽기 좋게 두 줄마다 빈 줄)
[소주제] 소제목 문장   ← 소제목은 이렇게. 3~4개
[사진1 - 넣을 사진 장면 설명]   ← 사진 자리는 이렇게 독립된 줄로. 3~4개, 붙여 쓰지 않는다
#태그1 #태그2 #태그3 #태그4 #태그5   ← 맨 끝 한 줄

[지킬 것]
- 「안녕하세요 오늘은」으로 시작하지 않는다. 필명·자기소개를 지어내지 않는다
- 지어낸 수치·후기 금지. 수익·효과를 약속하지 않는다(필요하면 「제 경우」와 기간)
- 병이 낫는다·효과 보장 같은 표현 금지
- 사람 얼굴·연예인·상표가 들어가는 사진 설명은 쓰지 않는다
"""


def write_post() -> str:
    import myinfo
    info = "\n".join(f"{k}: {v}" for k, v in (("블로그 이름", myinfo.blog_name()), ("주제", myinfo.topic()),
                                              ("한줄소개", myinfo.get("내 블로그 한줄소개"))) if v)
    story = _read(os.path.join(ROOT, "내이야기.md")).strip()
    if not story:
        raise RuntimeError("내이야기.md 가 없습니다 — 클로드 코드에 「내 이야기 5개 질문해줘」를 먼저 하세요(③)")
    news = _news(myinfo.topic())
    news_txt = "\n".join(f"- {n['title']} — {(n.get('snippet') or '')[:120]}" for n in news) or "(오늘은 기사 없음 — 내 이야기로 쓴다)"
    log(f"기사거리 {len(news)}개 · 내 이야기 {len(story)}자 → 클로드가 씁니다(몇 분 걸립니다)")
    import claude_cli
    text = claude_cli.run_claude_p(PROMPT.format(info=info, story=story[:3000], news=news_txt,
                                                 score=_read(os.path.join(ROOT, "홈판채점표.md"))[:3000]),
                                   timeout=900)
    i = text.find("제목:")
    if i < 0:
        raise RuntimeError("클로드 답에 「제목:」 줄이 없습니다: " + text[:120].replace("\n", " "))
    text = text[i:].strip()
    if len(text) < 600:
        raise RuntimeError(f"글이 너무 짧습니다({len(text)}자)")
    return text


def save_manuscript(text: str) -> tuple:
    import config
    folder = os.path.join(config.SOURCE_ROOT, config.today_str())
    os.makedirs(folder, exist_ok=True)
    used = [int(m.group(1)) for f in os.listdir(folder) for m in [re.match(r"^(\d{2})_", f)] if m]
    no = f"{max(used, default=0) + 1:02d}"
    title = re.match(r"제목\s*[:：]\s*(.+)", text).group(1).strip()
    kw = re.sub(r'[\\/:*?"<>|\s]+', "", title)[:12] or "오늘글"
    path = os.path.join(folder, f"{no}_{kw}_복붙용.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    open(os.path.join(folder, f"{no}_{kw}_ai.flag"), "w").close()   # 일반 글로 처리(무료 사진 붙이기)
    return no, folder, title


def main(argv) -> int:
    dry = "--dry" in argv
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 3 * 3600:
        log("이미 돌고 있습니다(work/오늘글_자동.lock). 두 번 돌리지 않습니다.")
        return 1
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    open(LOCK, "w").close()
    try:
        log("──── 오늘 글 자동 시작 " + ("(원고만)" if dry else "(임시저장까지)"))
        if not _find_tools():
            log("✗ claude 를 못 찾았습니다 — 클로드 코드가 설치·로그인돼 있는지 보세요")
            return 1
        try:
            text = write_post()
        except Exception as e:  # noqa: BLE001
            log(f"✗ 글쓰기 실패: {str(e)[:300]}")
            return 1
        no, folder, title = save_manuscript(text)
        log(f"원고 저장: {os.path.basename(folder)}/{no} · 제목: {title}")
        if dry:
            log("✓ 원고만 만들었습니다(--dry)")
            return 0
        import pipeline
        r = pipeline.process_post(no, log, publish=False, folder=folder)
        if r.get("ok"):
            log(f"✓ 임시저장 끝 — {r.get('message', '')} · 아침에 네이버 「저장」 목록에서 열어 내 경험·사진을 넣고 발행하세요")
            for n in r.get("notes") or []:
                log("  · " + str(n))
            return 0
        log(f"✗ 임시저장 실패: {r.get('message', '')[:300]}")
        return 1
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
