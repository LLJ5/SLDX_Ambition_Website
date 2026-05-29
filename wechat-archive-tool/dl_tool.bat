@echo off
cd /d "%~dp0"
echo Starting WeChat Article Re-Download Tool...
echo.
python dl_tool.py --web
pause
