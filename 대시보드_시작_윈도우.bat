@echo off
chcp 949 >nul
cd /d "%~dp0"
echo.
echo   대시보드를 엽니다. 브라우저가 자동으로 열립니다.
echo   이 창은 닫지 마세요.
echo.
where py >nul 2>nul
if errorlevel 1 goto USEPYTHON
py -3 "대시보드.py"
goto END
:USEPYTHON
python "대시보드.py"
:END
pause
