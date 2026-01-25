@echo off
cd /d "C:\Users\Aaron Clarkson\Documents\boz-ripper\agent"
call .venv\Scripts\activate
python -m boz_agent run
pause
