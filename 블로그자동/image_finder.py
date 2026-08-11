"""비연예 글의 [사진N] 마커에 맞는 이미지를 Unsplash에서 찾아 다운로드."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
import urllib.request

# ── 키 찾는 곳 (수강생 배포판: 이 폴더 먼저, 그다음 옛 경로) ──
_BASE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_BASE)          # 패키지 루트(내정보.txt가 있는 곳)


def _load_key(name: str = "UNSPLASH_ACCESS_KEY") -> str | None:
    """키를 순서대로 찾는다: 환경변수 → 내정보.txt → .env → 옛 경로.

    수강생은 내정보.txt 한 파일만 채우면 된다. 없으면 None을 돌려주고,
    부르는 쪽이 이미지 없이 [사진N] 마커만 남기고 넘어간다.
    """
    v = os.environ.get(name)
    if v:
        return v.strip()

    # 내정보.txt — "제미나이 키: xxx" 처럼 콜론으로 적어도 읽는다
    label = {"GEMINI_API_KEY": ("제미나이 키", "제미나이키"),
             "UNSPLASH_ACCESS_KEY": ("사진 키", "언스플래시 키")}.get(name, ())
    for info in (os.path.join(_PKG, "내정보.txt"), os.path.join(_BASE, "내정보.txt")):
        try:
            with open(info, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or ":" not in line:
                        continue
                    k, val = line.split(":", 1)
                    k, val = k.strip(), val.strip()
                    if val.startswith("(") or not val:
                        continue
                    if k == name or k in label:
                        return val
        except Exception:  # noqa: BLE001
            pass

    # .env 파일들
    for env in (os.path.join(_PKG, ".env"), os.path.join(_BASE, ".env"),
                os.path.expanduser("~/홈판자료/.env")):
        try:
            with open(env, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(name):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:  # noqa: BLE001
            pass
    return None


def _fetch_first(query: str, out_path: str, key: str) -> bool:
    """query로 Unsplash 검색 → 첫 결과 이미지를 out_path로 저장(단일 시도)."""
    try:
        url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode({
            "query": query, "per_page": 3, "orientation": "landscape", "content_filter": "high",
        })
        req = urllib.request.Request(url, headers={"Authorization": f"Client-ID {key}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or []
        if not results:
            return False
        img_url = results[0]["urls"]["regular"]
        with urllib.request.urlopen(img_url, timeout=30) as ir:
            content = ir.read()
        with open(out_path, "wb") as f:
            f.write(content)
        return os.path.getsize(out_path) > 1000
    except Exception:  # noqa: BLE001
        return False


def search_download(query: str, out_path: str, key: str | None = None) -> bool:
    """query로 Unsplash 검색 → 첫 결과 저장. 정확 검색어에 결과가 없으면
    검색어를 점점 단순화(앞 2단어 → 첫 단어)하며 재시도해 빈손 확률을 줄인다."""
    key = key or _load_key()
    if not key:
        return False
    words = (query or "").split()
    variants = [query]
    if len(words) > 2:
        variants.append(" ".join(words[:2]))
    if len(words) > 1:
        variants.append(words[0])
    tried = set()
    for q in variants:
        q = (q or "").strip()
        if not q or q in tried:
            continue
        tried.add(q)
        if _fetch_first(q, out_path, key):
            return True
    return False


GEMINI_IMAGE_MODELS = ("gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation")


def generate_gemini(desc: str, out_path: str, key: str | None = None) -> bool:
    """Unsplash에서 못 찾은 사진을, 설명(desc)으로 Gemini가 직접 생성해 out_path에 저장.
    REST(generateContent)로 호출하며, 실패하면 False."""
    key = key or _load_key("GEMINI_API_KEY")
    if not key or not (desc or "").strip():
        return False
    prompt = (
        "Generate a realistic, high-quality photograph for a blog post. "
        "No text, no watermark, no logo, natural lighting, clean composition. "
        f"Scene: {desc.strip()}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode("utf-8")
    for model in GEMINI_IMAGE_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key}")
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        with open(out_path, "wb") as f:
                            f.write(base64.b64decode(inline["data"]))
                        if os.path.getsize(out_path) > 1000:
                            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def translate_queries(descriptions: list[str]) -> list[str]:
    """한국어 사진 설명들을 Unsplash 검색용 영어 키워드로 변환(claude -p). 실패 시 원문 반환."""
    if not descriptions:
        return []
    try:
        from claude_cli import run_claude_p
        numbered = "\n".join(f"{i+1}. {d}" for i, d in enumerate(descriptions))
        prompt = (
            "다음 한국어 사진 설명들을 각각 Unsplash 사진 검색에 적합한 '짧은 영어 키워드'로 바꿔줘.\n"
            "규칙: 입력 순서 그대로, 한 줄에 하나씩, 번호·설명·따옴표 없이 영어 키워드만.\n\n"
            + numbered
        )
        out = run_claude_p(prompt, timeout=90)
        lines = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip().strip("\"'") for l in out.splitlines() if l.strip()]
        if len(lines) >= len(descriptions):
            return lines[:len(descriptions)]
    except Exception:  # noqa: BLE001
        pass
    return list(descriptions)


if __name__ == "__main__":
    ok = search_download("korean office planning whiteboard schedule", "/tmp/_unsplash_test.jpg")
    print("다운로드 성공:", ok, "| 키 로드:", bool(_load_key()))
    if ok:
        print("크기:", os.path.getsize("/tmp/_unsplash_test.jpg"))
