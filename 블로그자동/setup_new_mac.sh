#!/bin/bash
# 새 맥(집 노트북)에서 이 저장소를 돌릴 수 있게 만드는 세팅 스크립트.
#
#   git clone https://github.com/jin3175-ctrl/edi-blog-auto.git ~/"클로드 코드 블로그 자동화 웹"
#   cd ~/"클로드 코드 블로그 자동화 웹" && bash setup_new_mac.sh
#
# 여러 번 실행해도 안전하다(이미 된 단계는 건너뛴다). 실패한 단계만 다시 돌리면 된다.
set -u

PY=/usr/bin/python3          # 맥 기본 파이썬(3.9). 홈브루 파이썬을 쓰려면 이 줄만 바꾼다.
REPO="$(cd "$(dirname "$0")" && pwd)"
OUT="$HOME/홈판자료/블로그오토"
ENVF="$HOME/홈판자료/.env"
SKILL_SRC="$REPO/skills/eddie-blog-auto"
SKILL_DST="$HOME/.claude/skills/eddie-blog-auto"
TODO=()

ok()   { printf '  \033[32m✅\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m⚠️\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31m⛔\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }

step 1 "필수 도구 확인"
command -v git >/dev/null || { bad "git 없음 → 터미널에서 'xcode-select --install' 먼저"; exit 1; }
ok "git $(git --version | awk '{print $3}')"
[ -x "$PY" ] || { bad "$PY 없음 → 스크립트 상단 PY= 를 실제 파이썬 경로로"; exit 1; }
ok "python $("$PY" -V 2>&1 | awk '{print $2}')"

step 2 "파이썬 패키지"
# 맥 기본 파이썬은 --user 가 필요하다(없으면 'externally-managed' 로 거부).
if "$PY" -c "import playwright, PIL, requests" 2>/dev/null; then
  ok "playwright · pillow · requests 이미 설치됨"
else
  "$PY" -m pip install --user --quiet --upgrade pip >/dev/null 2>&1
  if "$PY" -m pip install --user --quiet playwright pillow requests flask; then
    ok "설치 완료"
  else
    bad "pip 설치 실패 → 'python3 -m pip install --user playwright pillow requests' 를 직접 실행해 메시지 확인"
    TODO+=("파이썬 패키지 설치")
  fi
fi

step 3 "Playwright 크로미움(자동화 브라우저)"
if "$PY" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p: p.chromium.launch(headless=True).close()
" 2>/dev/null; then
  ok "크로미움 정상"
else
  echo "  다운로드 중(수백 MB, 몇 분 걸립니다)…"
  "$PY" -m playwright install chromium && ok "크로미움 설치 완료" || { bad "크로미움 설치 실패"; TODO+=("playwright install chromium"); }
fi

step 4 "원고 출력 폴더"
mkdir -p "$OUT" && ok "$OUT"

step 5 "API 키 파일(.env)"
if [ -f "$ENVF" ] && grep -q "^GEMINI_API_KEY=..*" "$ENVF"; then
  ok "GEMINI_API_KEY 있음"
else
  mkdir -p "$(dirname "$ENVF")"
  grep -q "^GEMINI_API_KEY=" "$ENVF" 2>/dev/null || printf '\n# 썸네일·비전 검증·이미지 폴백용\nGEMINI_API_KEY=\n' >> "$ENVF"
  warn "$ENVF 의 GEMINI_API_KEY= 뒤에 키를 붙여넣어야 합니다(썸네일·이미지가 안 나옵니다)"
  TODO+=("$ENVF 에 GEMINI_API_KEY 입력")
fi

step 6 "Claude Code CLI (본문 생성에 claude -p 사용)"
if command -v claude >/dev/null; then
  ok "claude $(command -v claude)"
  warn "로그인 안 돼 있으면 터미널에서 'claude login' 한 번 (이 스크립트는 대신 못 합니다)"
else
  bad "claude 없음 → 설치 후 'claude login'"
  echo "     npm i -g @anthropic-ai/claude-code    (또는 https://claude.com/claude-code 설치 안내)"
  TODO+=("Claude Code 설치 + claude login")
fi

step 7 "스킬 설치(심링크 → git pull 하면 스킬도 갱신됨)"
mkdir -p "$HOME/.claude/skills"
if [ -L "$SKILL_DST" ]; then
  ok "이미 심링크: $(readlink "$SKILL_DST")"
elif [ -e "$SKILL_DST" ]; then
  warn "$SKILL_DST 가 실제 폴더로 있습니다. 백업 후 심링크로 바꾸려면:"
  echo "     mv \"$SKILL_DST\" \"$SKILL_DST.bak\" && ln -s \"$SKILL_SRC\" \"$SKILL_DST\""
  TODO+=("스킬 심링크 교체")
else
  ln -s "$SKILL_SRC" "$SKILL_DST" && ok "심링크 생성"
fi

step 8 "네이버 로그인 세션"
if "$PY" -c "
import sys; sys.path.insert(0,'$REPO')
import naver; sys.exit(0 if naver.session_alive(lambda m: None) else 1)
" 2>/dev/null; then
  ok "세션 살아 있음"
else
  warn "세션 없음/만료 — 로그인 창을 띄웁니다."
  echo "     ★창에서 '로그인 상태 유지' ON / 'IP 보안' OFF 로 로그인하세요(안 그러면 하루도 못 갑니다)."
  printf '     지금 로그인 창을 띄울까요? [y/N] '
  read -r ans
  if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
    "$PY" -c "
import sys; sys.path.insert(0,'$REPO')
import naver; print(naver.login_and_save(print))
"
  else
    echo "     나중에: python3 -c \"import naver; naver.login_and_save(print)\""
    TODO+=("네이버 로그인")
  fi
fi

step 9 "이미지 생성용 제미나이 웹 로그인"
if [ -d "$REPO/session/gemini_profile" ]; then
  ok "제미나이 프로필 있음"
else
  warn "없음 → 나중에 'python3 web_image.py login' (본문 이미지가 안 나오면 이것부터)"
  TODO+=("제미나이 웹 로그인")
fi

step 10 "매일 04:30 자동 실행 등록(launchd)"
# 저장소의 plist는 예전 맥의 절대경로가 박혀 있다. 새 맥에서는 **이 스크립트가 경로를 채워 새로 쓴다**
# (경로를 손으로 고치는 단계가 사라진다). 두 대 동시 구동을 막기 위해 등록 여부는 물어본다.
gen_plist() {  # $1=label $2=출력경로 $3=시 $4=분 $5=로그이름 $6..=명령 인자
  local label="$1" out="$2" hh="$3" mm="$4" logname="$5"; shift 5
  { printf '<?xml version="1.0" encoding="UTF-8"?>\n'
    printf '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    printf '<plist version="1.0">\n<dict>\n'
    printf '  <key>Label</key><string>%s</string>\n' "$label"
    printf '  <key>ProgramArguments</key>\n  <array>\n'
    for a in "$@"; do printf '    <string>%s</string>\n' "$a"; done
    printf '  </array>\n'
    printf '  <key>WorkingDirectory</key><string>%s</string>\n' "$REPO"
    printf '  <key>EnvironmentVariables</key>\n  <dict>\n'
    printf '    <key>HOME</key><string>%s</string>\n' "$HOME"
    printf '    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>\n'
    printf '  </dict>\n'
    printf '  <key>StartCalendarInterval</key>\n  <dict>\n'
    printf '    <key>Hour</key><integer>%s</integer>\n    <key>Minute</key><integer>%s</integer>\n' "$hh" "$mm"
    printf '  </dict>\n'
    printf '  <key>StandardOutPath</key><string>%s</string>\n' "$REPO/work/$logname.log"
    printf '  <key>StandardErrorPath</key><string>%s</string>\n' "$REPO/work/$logname.err.log"
    printf '  <key>RunAtLoad</key><false/>\n</dict>\n</plist>\n'
  } > "$out"
}

LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA" "$REPO/work"
PLIST_OUT="${SETUP_PLIST_DIR:-$LA}"          # 테스트 시 SETUP_PLIST_DIR로 출력 위치를 바꿀 수 있다
gen_plist com.edi.aiblog "$PLIST_OUT/com.edi.aiblog.plist" 4 30 ai_daily \
  /usr/bin/caffeinate -i "$PY" "$REPO/run_ai_daily.py" \
  --ai 2 --shop 1 --celeb 3 --stagger 1200
gen_plist com.edi.aiblog.report "$PLIST_OUT/com.edi.aiblog.report.plist" 23 30 report \
  /usr/bin/caffeinate -i "$PY" "$REPO/blog_report.py"
ok "plist 2개 생성(경로 자동 반영): $PLIST_OUT"
if [ "$PLIST_OUT" = "$LA" ]; then
  echo "     ⚠️ 예전 맥에서 같은 작업이 켜져 있으면 **같은 블로그에 중복 발행**됩니다."
  echo "        예전 맥에서 끄기: launchctl bootout gui/\$(id -u)/com.edi.aiblog"
  echo "        (조회에 안 잡히면 plist 이름을 com.edi.aiblog.plist.disabled 로 바꾸고 재로그인)"
  printf '     이 맥에 자동 실행을 등록할까요? [y/N] '
  read -r ans2
  if [ "${ans2:-N}" = "y" ] || [ "${ans2:-N}" = "Y" ]; then
    for l in com.edi.aiblog com.edi.aiblog.report; do
      launchctl bootout "gui/$(id -u)/$l" 2>/dev/null
      launchctl bootstrap "gui/$(id -u)" "$LA/$l.plist" && launchctl enable "gui/$(id -u)/$l" \
        && ok "$l 등록" || { bad "$l 등록 실패"; TODO+=("$l 등록"); }
    done
  else
    TODO+=("자동 실행 등록(launchctl bootstrap)")
  fi
fi

printf '\n\033[1m───── 정리 ─────\033[0m\n'
if [ ${#TODO[@]} -eq 0 ]; then
  ok "세팅 끝. 다음 순서로 확인하세요:"
else
  echo "  남은 일:"
  for t in "${TODO[@]}"; do echo "   · $t"; done
  echo "  위를 끝낸 뒤 확인:"
fi
cat <<'NEXT'
     python3 run_ai_daily.py --dry        # 무엇을 할지만 출력(네이버 안 건드림)
     python3 run_ai_daily.py --gen-only   # 원고만 생성
     python3 run_ai_daily.py --ai 2 --shop 1 --celeb 3 --stagger 1200   # 실제 하루치

  자동 실행 plist는 [10]단계에서 이 맥 경로로 이미 만들어졌습니다(~/Library/LaunchAgents).
  등록을 미뤘다면:
     launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.edi.aiblog.plist
     launchctl enable gui/$(id -u)/com.edi.aiblog
  등록 확인:  launchctl print gui/$(id -u)/com.edi.aiblog | head -5

  ⚠️ 두 대에서 동시에 켜면 같은 블로그에 중복 발행됩니다.
     옮긴 뒤 예전 맥에서: launchctl bootout gui/$(id -u)/com.edi.aiblog
     (조회에 안 잡히는데도 돌면 plist를 com.edi.aiblog.plist.disabled 로 이름 변경 후 재로그인)
NEXT
