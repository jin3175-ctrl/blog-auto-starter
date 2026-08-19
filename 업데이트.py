# -*- coding: utf-8 -*-
"""최신판으로 업데이트 — 내 정보와 기록은 그대로 둡니다.

🔴수강생이 직접 zip을 받아 덮으면 **내정보.txt 가 빈 칸으로 덮인다.**
   (work/ · naver_state*.json 은 .gitignore 라 zip에 없어서 안전하다)
   그래서 코드 파일만 골라 덮고, 개인 파일은 손대지 않는다.
"""
import io, os, shutil, sys, tempfile, urllib.request, zipfile

ZIP = "https://github.com/jin3175-ctrl/blog-auto-starter/archive/refs/heads/main.zip"
BASE = os.path.dirname(os.path.abspath(__file__))

# 🔴이 이름들은 절대 덮지 않는다 — 수강생이 채운 것과 쌓인 기록이다
KEEP = {"내정보.txt"}
KEEP_DIRS = {"work", "session", "원고", "__pycache__"}


def main():
    print("\n  최신판을 받는 중입니다…", flush=True)
    try:
        raw = urllib.request.urlopen(ZIP, timeout=120).read()
    except Exception as e:
        print(f"\n  [실패] 인터넷 연결을 확인해 주세요.\n  {e}\n"); return 1

    tmp = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            z.extractall(tmp)
        roots = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        if not roots:
            print("\n  [실패] 받은 파일이 비어 있습니다.\n"); return 1
        src = os.path.join(tmp, roots[0])

        n = 0
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d not in KEEP_DIRS and not d.startswith(".")]
            rel = os.path.relpath(dirpath, src)
            dst_dir = BASE if rel == "." else os.path.join(BASE, rel)
            os.makedirs(dst_dir, exist_ok=True)
            for fn in filenames:
                if fn in KEEP:
                    continue                      # 내 정보는 건드리지 않는다
                shutil.copy2(os.path.join(dirpath, fn), os.path.join(dst_dir, fn))
                n += 1
        print(f"\n  ⭕ 업데이트 끝났습니다. 파일 {n}개를 새로 받았습니다.")
        print("  내정보.txt 와 그동안 쌓인 기록은 그대로 있습니다.\n")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    code = main()
    try:
        input("  이 창을 닫으려면 엔터를 누르세요. ")
    except EOFError:
        pass
    sys.exit(code)
