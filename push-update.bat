@echo off
REM Double-click to commit and push changes in this folder.
cd /d "%~dp0"
git add -A
git commit -m "Update SYS2 dashboard (%date% %time%)"
git pull --rebase
if errorlevel 1 (
  echo *** The rebase stopped. Tell Claude what this window says.
  pause
  exit /b 1
)
git push
echo Done.
pause
