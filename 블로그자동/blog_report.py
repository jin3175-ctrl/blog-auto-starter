#!/usr/bin/env python3
"""에디 블로그(ioiykd8599) '올린 현황'을 모아 매일 메일로 보낸다 (2026-07-22, 에디님 요청).

무엇을: 오늘 올라간 글(제목·발행시각·조회수) + 최근 7일 물량/조회 추이 + 색인 신호를
       HTML 대시보드로 만들어 지메일로 보낸다. 발송기는 검증된 notify.py 패턴 재사용.

왜 메일 본문에 대시보드를 담나:
  localhost 대시보드 주소는 서버가 떠 있어야 열리고 폰에선 안 열린다. 메일 본문 자체를
  대시보드로 만들면 서버 없이 폰·PC 어디서나 열린다. '블로그 열기'는 진짜 공개 URL로 건다.

사용:
  python3 blog_report.py --preview   # 발송 없이 /tmp/_blog_report.html 로 미리보기
  python3 blog_report.py             # 실제 메일 발송
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

import config

import myinfo  # 수강생 배포판: 내정보.txt에서 읽는다
BLOG_ID = myinfo.blog_id()
BLOG_URL = f"https://blog.naver.com/{BLOG_ID}"
KST = timezone(timedelta(hours=9))


STAT_DAILY = "https://blog.stat.naver.com/api/blog/daily/cv?timeDimension=DATE&startDate={d}&exclude="
STAT_RANK = "https://blog.stat.naver.com/api/blog/rank/cvContentPc?timeDimension=DATE&startDate={d}&exclude="


def _stat_json(pg, url: str) -> dict:
    """통계 API 호출 → {컬럼: [값…]} 형태의 rows 반환(실패 시 {})."""
    import json as _json
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=25000)
        d = _json.loads(pg.inner_text("body"))
        return (d.get("result", {}).get("statDataList") or [{}])[0].get("data", {}).get("rows", {})
    except Exception:  # noqa: BLE001
        return {}


def fetch_stats(days: int = 8, log=print) -> dict:
    """네이버 블로그 '관리자 통계'에서 진짜 조회수를 가져온다(2026-08-03).

    ★왜 필요한가: 에디 블로그는 글 목록 API(`PostTitleListAsync`)의 readCount가 빈 값이라
      조회수가 전부 0으로 보였다(제이 블로그는 값이 옴 — 블로그 설정 차이).
      실제 숫자는 admin.blog.naver.com 통계에만 있고, 이 도메인은 별도 로그인 쿠키가 필요하다
      (`naver.login_and_save`가 로그인 후 통계 페이지를 방문해 그 쿠키까지 저장한다).

    반환: {"daily": [{"date","views"}…], "posts": [{"date","title","views","rank","uri"}…]}
    """
    from datetime import timedelta
    today = datetime.now(KST).date()
    out = {"daily": [], "posts": []}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(storage_state=config.SESSION_FILE)
            pg = ctx.new_page()
            r = _stat_json(pg, STAT_DAILY.format(d=today.isoformat()))
            for dt, cv in zip(r.get("date", []), r.get("cv", [])):
                out["daily"].append({"date": dt, "views": int(cv or 0)})
            # 글별 조회수: 오늘 + 어제(오늘 집계가 아직 얕을 수 있어 둘 다 본다)
            for delta in (0, 1):
                d = (today - timedelta(days=delta)).isoformat()
                rr = _stat_json(pg, STAT_RANK.format(d=d))
                for dt, uri, cv, rk, ti in zip(rr.get("date", []), rr.get("uri", []),
                                               rr.get("cv", []), rr.get("rank", []),
                                               rr.get("title", [])):
                    out["posts"].append({"date": dt, "uri": uri, "views": int(cv or 0),
                                         "rank": int(rk or 0), "title": ti})
            b.close()
    except Exception as e:  # noqa: BLE001
        log(f"통계 수집 실패({str(e)[:60]}) — 조회수 없이 진행")
    return out


def _fetch_posts(limit: int = 60) -> list[dict]:
    """최근 글의 logNo·제목·조회수·등록표기를 가져온다."""
    rows: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=config.SESSION_FILE)
        pg = ctx.new_page()
        per = 30
        for page in range(1, limit // per + 1):
            url = (f"{BLOG_URL}/PostTitleListAsync.naver?blogId={BLOG_ID}"
                   f"&currentPage={page}&countPerPage={per}")
            pg.goto(url, wait_until="domcontentloaded", timeout=25000)
            txt = pg.inner_text("body")
            for m in re.finditer(
                    r'"logNo":"(\d+)","title":"([^"]*)".*?"readCount":"(\d*)","addDate":"([^"]*)"',
                    txt):
                ln, t, rc, ad = m.groups()
                rows.append({
                    "logNo": ln,
                    "title": urllib.parse.unquote(t.replace("+", " "))
                             .replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&"),
                    "views": int(rc or 0),
                    "date": ad,
                })
        b.close()
    return rows


def _today_str() -> str:
    return datetime.now(KST).strftime("%Y. %-m. %-d.")


def _is_today(adddate: str) -> bool:
    # 네이버 목록: 최근 글은 "N시간 전", 예전 글은 "2026. 7. 22." 형식.
    if "전" in adddate:   # 오늘/방금
        return True
    return adddate.strip() == _today_str()


def build(rows: list[dict], stats: dict | None = None) -> dict:
    """리포트에 쓸 요약 dict. stats(관리자 통계)가 있으면 조회수를 그걸로 채운다."""
    # ★글 목록 API의 readCount는 이 블로그에서 빈 값이라 0으로 보인다 → 통계의 진짜 조회수로 덮어쓴다.
    if stats and stats.get("posts"):
        by_title = {}
        for p in stats["posts"]:
            t = (p.get("title") or "").strip()
            if t:
                by_title[t] = max(by_title.get(t, 0), p.get("views", 0))
        for r in rows:
            v = by_title.get((r.get("title") or "").strip())
            if v:
                r["views"] = v
    today = [r for r in rows if _is_today(r["date"])]
    # 날짜별 집계(최근 7개 날짜)
    by_date: dict[str, list[int]] = {}
    order: list[str] = []
    for r in rows:
        key = "오늘/방금" if "전" in r["date"] else r["date"].strip()
        if key not in by_date:
            by_date[key] = []
            order.append(key)
        by_date[key].append(r["views"])
    trend = []
    for k in order[:7]:
        vs = by_date[k]
        trend.append({"date": k, "count": len(vs), "views": sum(vs),
                      "avg": (sum(vs) / len(vs)) if vs else 0})
    # 날짜별 총조회수도 통계의 실제 수치로 교체(글 목록 합산은 부정확하다)
    if stats and stats.get("daily"):
        daily_map = {d["date"]: d["views"] for d in stats["daily"]}
        for t in trend:
            k = t["date"]
            iso = None
            if k == "오늘/방금":
                iso = datetime.now(KST).strftime("%Y-%m-%d")
            else:
                m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", k)
                if m:
                    iso = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            if iso and iso in daily_map:
                t["views"] = daily_map[iso]
                t["avg"] = daily_map[iso] / t["count"] if t["count"] else 0
    rep = {"today": today, "recent": rows[:3], "trend": trend, "stats": stats or {},
           "bestworst": best_worst(rows),
           "revisions": revision_tracking(rows),
           "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    return rep


def _post_url(log_no: str) -> str:
    return f"{BLOG_URL}/{log_no}"


_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "revise_ledger.json")


def _days_since(yyyymmdd: str) -> int:
    try:
        d = datetime.strptime(yyyymmdd, "%Y%m%d").date()
        return (datetime.now(KST).date() - d).days
    except Exception:  # noqa: BLE001
        return 0


def revision_tracking(rows: list[dict]) -> list[dict]:
    """수정한 글(원장)의 '수정 후 현재 조회수'를 추적한다.

    수정 루프의 측정 절반. 조회가 올랐으면 그 방향이 맞은 것, 며칠째 0이면 노출 자체가
    아직 안 돌아온 것(제목 문제가 아니라 색인 문제)이라는 판단 근거가 된다.
    """
    import json
    try:
        with open(_LEDGER, encoding="utf-8") as f:
            led = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    cur = {r["logNo"]: r["views"] for r in rows}
    out = []
    for log_no, info in led.items():
        out.append({
            "logNo": log_no,
            "new_title": info.get("new", ""),
            "before": info.get("views_before", 0),
            "now": cur.get(log_no, 0),
            "days": _days_since(info.get("ts", "")),
        })
    # 최근 수정 순(일수 적은 것 먼저)
    out.sort(key=lambda x: x["days"])
    return out


def best_worst(rows: list[dict], window: int = 20) -> dict:
    """최근 window편 중 조회 최고/최저 글. 오늘 글은 갓 올라와 0이므로 제외(당일 제외)."""
    pool = [r for r in rows[:window] if not _is_today(r["date"])]
    if not pool:
        pool = rows[:window]
    best = max(pool, key=lambda r: r["views"], default=None)
    worst = min(pool, key=lambda r: r["views"], default=None)
    return {"best": best, "worst": worst, "pool_n": len(pool)}


def generation_hint(log=print) -> str:
    """전날 성과 → 오늘 '생성기'에 넣을 지침 문자열. 루프를 자동으로 닫는다.

    ⚠️ 신호가 있을 때만 지침을 낸다. 조회가 다 바닥(노출 회복 전)이면 '어제 1위'가 그냥
    잡음이므로 빈 문자열을 돌려준다 — 잡음을 생성기에 주입하지 않는다(정직).
    신호(최고 조회 >= 3, 그리고 최저보다 큼)가 생기면 그때부터 실제로 반영된다.
    """
    try:
        rows = _fetch_posts(40)
    except Exception as e:  # noqa: BLE001
        log(f"성과 수집 실패: {str(e)[:50]}")
        return ""
    bw = best_worst(rows)
    best, worst = bw.get("best"), bw.get("worst")
    if not best or best["views"] < 3 or best["views"] <= (worst or {}).get("views", 0):
        return ""   # 아직 배울 신호 없음
    hint = (f"어제 우리 블로그에서 가장 많이 본 제목은 \"{best['title']}\"({best['views']}회)다. "
            f"이 제목의 후킹 방식(구체 숫자·큰따옴표 대사·반전)을 오늘 제목에도 살려라. "
            f"반대로 \"{(worst or {}).get('title','')}\"({(worst or {}).get('views',0)}회)처럼 "
            f"핵심이 뒤로 밀린 설명형 제목은 피하라.")
    log(f"생성 지침(전날 성과 반영): 최고 {best['views']}회 제목의 후킹 계승")
    return hint


def _feedback(rep: dict, log=print) -> str:
    """베스트/워스트 글을 비교해 '왜'와 '다음 액션'을 LLM으로 뽑는다.

    조회수가 전반적으로 바닥이면(색인 회복 전) 억지 해석 대신 '아직 노출 회복 단계'라고
    정직하게 말하도록 컨텍스트를 준다. 실패하면 규칙 기반 한 줄로 폴백.
    """
    bw = rep["bestworst"]
    best, worst = bw.get("best"), bw.get("worst")
    trend = rep["trend"]
    if not best or not worst:
        return "아직 비교할 데이터가 부족합니다."
    yday_views = trend[1]["views"] if len(trend) > 1 else 0
    try:
        from claude_cli import run_claude_p
        prompt = (
            "너는 이 네이버 블로그의 성과 분석가다. 이 블로그의 1순위 목표는 **네이버 홈피드(홈판) 노출 → 애드포스트 수익**이다. 하루 6편(AI 실전 4 + 쇼핑커넥트 1 + 연예 1)을 자동 생성해 임시저장하고, 발행은 에디님이 직접 한다. "
            "아래 최근 성적을 보고, 운영자가 내일 바로 써먹을 피드백을 한국어로 짧게 써라.\n\n"
            f"[최근 발행 글 총조회] {yday_views}회\n"
            f"[최근 조회 1위] \"{best['title']}\" — {best['views']}회\n"
            f"[최근 조회 최저] \"{worst['title']}\" — {worst['views']}회\n"
            "[상황] 매일 새벽 04:30에 6편을 자동 생성해 30분 간격으로 임시저장한다(velocity 분산). "
            "제목·썸네일·도입부는 '지금 홈판에 뜨는 글'의 공식을 실시간 추출해 따른다. "
            "도입부 인사·자기소개는 금지(첫 줄부터 후킹). 쇼핑커넥트 글엔 제휴 상품카드가 붙어 커미션이 나온다. "
            "연예 글은 순수 홈판 트래픽용(방송 캡처 사진 다수).\n\n"
            "[출력 형식 — 정확히 3줄, 각 줄 40자 내외, 이모지·머리기호 없이]\n"
            "1줄: 오늘 숫자에 대한 냉정한 한 줄 진단(조회수가 다 낮으면 솔직하게 '아직 노출 회복 전'이라고).\n"
            "2줄: 1위와 최저 글의 '제목' 차이에서 배울 점 한 가지(구체적으로).\n"
            "3줄: 내일 적용할 액션 한 가지(제목·소재·시각 중).\n"
            "과장 금지. 데이터가 빈약하면 빈약하다고 말할 것."
        )
        out = (run_claude_p(prompt, timeout=90) or "").strip()
        if out and len(out) > 10:
            return out
    except Exception as e:  # noqa: BLE001
        log(f"피드백 생성 실패: {str(e)[:60]}")
    # 폴백(규칙 기반)
    if best["views"] <= 1:
        return ("아직 홈판 노출이 잡히지 않아 조회수가 전반적으로 바닥입니다.\n"
                "임시저장분을 실제로 발행했는지부터 확인해 보세요(발행해야 노출이 잡힙니다).\n"
                "며칠간 글당평균이 오르는지를 지켜보세요.")
    return (f"최근 1위는 '{best['title'][:20]}…'({best['views']}회)입니다.\n"
            f"최저는 '{worst['title'][:20]}…'({worst['views']}회)입니다.\n"
            "1위 제목의 후킹 요소(수치·따옴표·반전)를 다음 글에도 적용해 보세요.")


def _kpi_yesterday(rep: dict) -> tuple[str, int, int]:
    """어제 날짜 라벨, 어제 글수, 어제 총조회(=일 조회수)."""
    t = rep["trend"]
    # trend[0]=오늘/방금, trend[1]=어제 인 경우가 일반적. 오늘칸이 0편이면 [0]이 어제일 수도.
    if t and t[0]["date"] == "오늘/방금" and len(t) > 1:
        y = t[1]
    elif t:
        y = t[0]
    else:
        return ("-", 0, 0)
    return (y["date"], y["count"], y["views"])


def render_html(rep: dict, feedback: str = "") -> str:
    today = rep["today"]
    trend = rep["trend"]
    bw = rep["bestworst"]
    y_date, y_cnt, y_views = _kpi_yesterday(rep)
    fb_html = "<br>".join(x for x in (feedback or "").splitlines() if x.strip())

    best, worst = bw.get("best"), bw.get("worst")
    def _pill(label, r, color):
        if not r:
            return ""
        return (
            f'<div style="padding:12px 14px;border-radius:10px;background:{color}0d;'
            f'border:1px solid {color}33;margin-bottom:8px;">'
            f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:3px;">{label}</div>'
            f'<a href="{_post_url(r["logNo"])}" style="color:#222;text-decoration:none;font-size:14px;'
            f'font-weight:600;line-height:1.4;">{r["title"]}</a>'
            f'<div style="font-size:13px;color:#666;margin-top:3px;">조회 {r["views"]}회</div></div>')
    bestworst_block = _pill("🏆 최근 조회 1위", best, "#0d7a3f") + _pill("🥶 최근 조회 최저", worst, "#b34700")

    kpi_block = (
        f'<div style="display:flex;gap:10px;margin-bottom:4px;">'
        f'<div style="flex:1;background:#f4f6f9;border-radius:10px;padding:14px;text-align:center;">'
        f'<div style="font-size:12px;color:#888;">어제 발행</div>'
        f'<div style="font-size:22px;font-weight:800;color:#0d3b66;">{y_cnt}편</div></div>'
        f'<div style="flex:1;background:#f4f6f9;border-radius:10px;padding:14px;text-align:center;">'
        f'<div style="font-size:12px;color:#888;">어제 글 조회수</div>'
        f'<div style="font-size:22px;font-weight:800;color:#0d3b66;">{y_views}회</div></div></div>')

    # 수정 추적 섹션 (원장에 기록된 글들이 수정 후 오르고 있나)
    revs = rep.get("revisions") or []
    rev_block = ""
    if revs:
        rows_r = ""
        for v in revs:
            up = v["now"] - v["before"]
            if v["now"] > v["before"]:
                tag, col = f"▲ {up}회", "#0d7a3f"
            elif v["days"] >= 3:
                tag, col = "변화 없음", "#b34700"
            else:
                tag, col = f"관찰 {v['days']}일째", "#888"
            rows_r += (
                f'<tr>'
                f'<td style="padding:9px 10px;border-bottom:1px solid #f0f0f0;font-size:13px;">'
                f'<a href="{_post_url(v["logNo"])}" style="color:#0d3b66;text-decoration:none;">'
                f'{v["new_title"][:34]}…</a></td>'
                f'<td style="padding:9px 10px;border-bottom:1px solid #f0f0f0;text-align:center;'
                f'font-size:13px;color:#555;white-space:nowrap;">{v["now"]}회</td>'
                f'<td style="padding:9px 10px;border-bottom:1px solid #f0f0f0;text-align:center;'
                f'font-size:12px;font-weight:700;color:{col};white-space:nowrap;">{tag}</td></tr>')
        rev_block = (
            '<div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;">'
            '<div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:8px;">'
            '🔧 수정한 글 추적</div>'
            '<table style="width:100%;border-collapse:collapse;">'
            f'{rows_r}</table>'
            '<div style="font-size:12px;color:#999;margin-top:8px;line-height:1.6;">'
            '수정 후 조회가 오르면 방향이 맞은 것, 3일+ 변화 없으면 노출(색인)이 아직 안 돌아온 것입니다.'
            '</div></div>')

    # 오늘 글이 아직이면(예: 아침 8시, 발행은 09·14시) 최근 글을 대신 보여준다.
    show = today if today else rep["recent"]
    if today:
        today_head = f"오늘 올린 글 {len(today)}편"
        note = ""
    else:
        today_head = "최근 올린 글"
        note = ('<div style="font-size:12px;color:#999;margin:2px 0 8px;">'
                '오늘 예약분(09·14시)은 발행 후 반영됩니다.</div>')
    rows_html = ""
    for r in show:
        rows_html += (
            f'<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eee;">'
            f'<a href="{_post_url(r["logNo"])}" style="color:#0d3b66;text-decoration:none;font-weight:600;">'
            f'{r["title"]}</a></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eee;text-align:center;'
            f'color:#333;white-space:nowrap;">{r["views"]}회</td></tr>')
    today_block = (
        note + f'<table style="width:100%;border-collapse:collapse;font-size:15px;">{rows_html}</table>')

    trend_rows = ""
    for t in trend:
        trend_rows += (
            f'<tr>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#555;">{t["date"]}</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;text-align:center;">{t["count"]}편</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;text-align:center;">{t["views"]}회</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;text-align:center;'
            f'font-weight:600;color:#0d3b66;">{t["avg"]:.1f}회</td></tr>')

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#0d3b66;color:#fff;padding:20px 24px;border-radius:12px 12px 0 0;">
    <div style="font-size:20px;font-weight:800;">AI 에디 · 블로그 현황</div>
    <div style="font-size:13px;opacity:.8;margin-top:4px;">{rep["generated"]} 기준</div>
  </div>
  <div style="background:#fff;padding:20px 24px;">
    <div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:10px;">📈 어제 성적 (일 조회수)</div>
    {kpi_block}
  </div>
  <div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;">
    <div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:6px;">💡 오늘의 피드백</div>
    <div style="font-size:14px;color:#333;line-height:1.75;background:#fffdf3;
         border-left:4px solid #f0c14b;padding:12px 14px;border-radius:0 8px 8px 0;">{fb_html}</div>
  </div>
  <div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;">
    <div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:10px;">🏆 베스트 · 워스트</div>
    {bestworst_block}
  </div>
  {rev_block}
  <div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;">
    <div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:6px;">📌 {today_head}</div>
    {today_block}
  </div>
  <div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;">
    <div style="font-size:16px;font-weight:700;color:#0d3b66;margin-bottom:10px;">📊 최근 추이 (날짜별)</div>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <thead><tr style="background:#f4f6f9;color:#666;">
        <th style="padding:8px 10px;text-align:left;">날짜</th>
        <th style="padding:8px 10px;">글수</th>
        <th style="padding:8px 10px;">총조회</th>
        <th style="padding:8px 10px;">글당평균</th></tr></thead>
      <tbody>{trend_rows}</tbody>
    </table>
    <div style="font-size:12px;color:#999;margin-top:10px;line-height:1.6;">
      ※ '글당평균'이 핵심 지표입니다. 하루 2편·평균 회복이 목표입니다.<br>
      ※ 조회수는 발행 직후엔 낮고 며칠에 걸쳐 오릅니다.
    </div>
  </div>
  <div style="background:#fff;padding:20px 24px;border-top:8px solid #f4f6f9;border-radius:0 0 12px 12px;text-align:center;">
    <a href="{BLOG_URL}" style="display:inline-block;background:#03c75a;color:#fff;
       text-decoration:none;padding:13px 28px;border-radius:8px;font-weight:700;font-size:15px;">
       블로그 열기 →</a>
  </div>
  <div style="text-align:center;color:#bbb;font-size:11px;margin-top:16px;">
    이 메일은 매일 자동 발송됩니다.
  </div>
</div></body></html>"""


def render_text(rep: dict, feedback: str = "") -> str:
    lines = [f"AI 에디 · 블로그 현황 ({rep['generated']})", ""]
    y_date, y_cnt, y_views = _kpi_yesterday(rep)
    lines.append(f"[어제 성적] 발행 {y_cnt}편 / 글 조회수 {y_views}회")
    lines.append("")
    lines.append("[오늘의 피드백]")
    for ln in (feedback or "").splitlines():
        if ln.strip():
            lines.append(f"  {ln.strip()}")
    lines.append("")
    bw = rep["bestworst"]
    if bw.get("best"):
        lines.append(f"[최근 1위] {bw['best']['title']} — {bw['best']['views']}회")
    if bw.get("worst"):
        lines.append(f"[최근 최저] {bw['worst']['title']} — {bw['worst']['views']}회")
    lines.append("")
    revs = rep.get("revisions") or []
    if revs:
        lines.append("[수정한 글 추적]")
        for v in revs:
            mark = "▲" if v["now"] > v["before"] else ("변화없음" if v["days"] >= 3 else f"{v['days']}일째")
            lines.append(f"  {v['new_title'][:30]}… — {v['now']}회 ({mark})")
        lines.append("")
    lines.append(f"[오늘 올린 글] {len(rep['today'])}편")
    for r in rep["today"]:
        lines.append(f"  · {r['title']} — {r['views']}회")
        lines.append(f"    {_post_url(r['logNo'])}")
    if not rep["today"]:
        lines.append("  (오늘 아직 없음)")
    lines.append("")
    lines.append("[최근 추이]  날짜 | 글수 | 총조회 | 글당평균")
    for t in rep["trend"]:
        lines.append(f"  {t['date']} | {t['count']}편 | {t['views']}회 | {t['avg']:.1f}회")
    lines.append("")
    lines.append(f"블로그 열기: {BLOG_URL}")
    return "\n".join(lines)


def _send(subject: str, html: str, text: str, log=print) -> bool:
    """검증된 notify.py 패턴(Gmail SMTP)으로 HTML 메일 발송."""
    import smtplib
    import ssl
    from email.message import EmailMessage
    import image_finder

    # ⚠️ gen_templates._env_key 는 유튜브 템플릿 .env 만 본다. GMAIL_APP_PASSWORD 는
    #    ~/홈판자료/.env 에 있으므로 두 경로를 다 보는 image_finder._load_key 를 쓴다.
    pw = image_finder._load_key("GMAIL_APP_PASSWORD")
    if not pw:
        log("GMAIL_APP_PASSWORD 없음 — 발송 불가")
        return False
    to_addr = myinfo.email() or ""  # 수강생 배포판: 내정보.txt의 메일로 보낸다
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = to_addr
    msg["To"] = to_addr
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=25) as s:
            s.login(to_addr, pw.replace(" ", ""))
            s.send_message(msg)
        log(f"메일 발송 완료 → {to_addr}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"메일 발송 실패: {str(e)[:120]}")
        return False


def main(preview: bool = False, log=print) -> None:
    rows = _fetch_posts(60)
    stats = fetch_stats(log=log)          # 관리자 통계에서 진짜 조회수
    rep = build(rows, stats)
    feedback = _feedback(rep, log=log)
    html = render_html(rep, feedback)
    text = render_text(rep, feedback)
    d = datetime.now(KST).strftime("%-m/%-d")
    y_date, y_cnt, y_views = _kpi_yesterday(rep)
    # 23:30에 도는 '그날 저녁 결산'이라 제목엔 오늘 올린 편수를 먼저 보여준다(2026-08-03 에디님).
    _today_cnt = len(rep.get("today") or [])
    subject = f"[AI 에디] {d} 결산 · 오늘 {_today_cnt}편 · 최근 조회 {y_views}회"

    if preview:
        with open("/tmp/_blog_report.html", "w", encoding="utf-8") as f:
            f.write(html)
        log("미리보기 저장 → /tmp/_blog_report.html")
        log("\n--- 텍스트 버전 ---\n" + text)
        return
    _send(subject, html, text, log=log)


def send_alert(subject: str, body_text: str, log=print) -> bool:
    """발행 실패 등 이상 상황을 즉시 메일로. run_morning 등에서 호출."""
    html = (f'<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">'
            f'<div style="background:#c0392b;color:#fff;padding:16px 20px;border-radius:10px 10px 0 0;'
            f'font-size:18px;font-weight:800;">⚠️ {subject}</div>'
            f'<div style="background:#fff;border:1px solid #eee;border-top:none;padding:20px;'
            f'border-radius:0 0 10px 10px;font-size:14px;line-height:1.7;white-space:pre-wrap;color:#333;">'
            f'{body_text}</div></div>')
    return _send(f"[AI 에디] ⚠️ {subject}", html, body_text, log=log)


if __name__ == "__main__":
    main(preview="--preview" in sys.argv)
