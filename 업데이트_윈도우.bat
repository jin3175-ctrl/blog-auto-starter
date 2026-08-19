@echo off
chcp 949 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto USEPYTHON
py -3 "업데이트.py"
goto END
:USEPYTHON
python "업데이트.py"
:END
