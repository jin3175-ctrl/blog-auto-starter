"""공통 설정 및 경로 유틸."""
from __future__ import annotations

import os
import re
from datetime import date

# 원고가 저장되는 루트 (에디 블로그 자동화 스킬 출력 폴더)
SOURCE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "원고")
os.makedirs(SOURCE_ROOT, exist_ok=True)

# 이 프로젝트 루트
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, "session")
WORK_DIR = os.path.join(BASE_DIR, "work")
SESSION_FILE = os.path.join(SESSION_DIR, "naver_state.json")
BLOG_META_FILE = os.path.join(SESSION_DIR, "naver_meta.json")

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(WORK_DIR, exist_ok=True)


def today_str() -> str:
    return date.today().strftime("%Y%m%d")


def resolve_date_folder(date_str: str | None = None) -> str | None:
    """오늘 폴더가 있으면 그걸, 없으면 가장 최신 YYYYMMDD 폴더를 반환."""
    if date_str:
        cand = os.path.join(SOURCE_ROOT, date_str)
        return cand if os.path.isdir(cand) else None

    today = os.path.join(SOURCE_ROOT, today_str())
    if os.path.isdir(today):
        return today

    if not os.path.isdir(SOURCE_ROOT):
        return None
    dated = [
        d for d in os.listdir(SOURCE_ROOT)
        if re.fullmatch(r"\d{8}", d) and os.path.isdir(os.path.join(SOURCE_ROOT, d))
    ]
    if not dated:
        return None
    dated.sort(reverse=True)
    return os.path.join(SOURCE_ROOT, dated[0])


def work_dir_for(date_str: str, post_no: str) -> str:
    d = os.path.join(WORK_DIR, date_str, post_no)
    os.makedirs(d, exist_ok=True)
    return d
