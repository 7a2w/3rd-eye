@echo off
title Third Eye - AI key
echo Paste your Gemini key (from aistudio.google.com) and press Enter.
echo For a Claude key instead, type "claude" first and press Enter.
echo.
set /p KEY=Key:
if /i "%KEY%"=="claude" (
  set /p KEY=Claude key:
  setx ANTHROPIC_API_KEY "%KEY%" >nul
  echo Saved your Claude key.
) else (
  setx GEMINI_API_KEY "%KEY%" >nul
  echo Saved your Gemini key.
)
echo Restart Third Eye to use it.
pause
