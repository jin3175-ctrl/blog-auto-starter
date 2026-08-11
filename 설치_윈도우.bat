@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   블로그 자동화 설치 (윈도우) - 1회만 실행
echo ============================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% --version >nul 2>nul
if not %errorlevel%==0 (
  echo [!] 파이썬이 없습니다. 마이크로소프트 스토어에서 "Python 3.12"를
  echo     설치한 뒤 이 파일을 다시 더블클릭하세요.
  pause
  exit /b 1
)
echo [1/4] 파이썬 확인 완료
echo [2/4] 필요한 부품 설치 중... (몇 분 걸립니다)
%PY% -m pip install --user playwright requests pillow
echo [3/4] 크롬 브라우저 부품 설치 중... (몇 분 걸립니다)
%PY% -m playwright install chromium
echo [4/4] 클로드 코드 설치 중... (이미 있으면 건너뜁니다)
where claude >nul 2>nul
if not %errorlevel%==0 (
  powershell -ExecutionPolicy Bypass -c "irm https://claude.ai/install.ps1 | iex"
)
echo.
echo ============================================
echo   설치 완료! 다음 순서:
echo   1. 메모장으로 "내정보.txt" 열어 내 블로그ID 넣기
echo   2. "블로그자동_시작_윈도우.bat" 더블클릭
echo   3. "네이버 로그인 시켜줘" 라고 말하기
echo ============================================
pause
