@echo off
chcp 65001 >nul
cd /d %~dp0
where claude >nul 2>nul
if not %errorlevel%==0 (
  echo [!] 클로드 코드가 아직 설치 안 됐습니다. 설치_윈도우.bat 를 먼저 실행하세요.
  pause
  exit /b 1
)
echo 클로드 코드를 시작합니다. 이렇게 말해보세요:
echo    "내 블로그에 맞게 자동화 고쳐줘"
echo    "댓글 달 블로그 찾아줘"
echo.
claude
