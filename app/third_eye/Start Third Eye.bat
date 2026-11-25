@echo off
title Third Eye
cd /d "%~dp0"
echo Starting Third Eye... (keep this window open; close it or press Ctrl+C to quit)
py -3.12 main.py %*
if errorlevel 1 (
  echo.
  echo Third Eye stopped with an error. Read the message above.
  pause
)
