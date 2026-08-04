@echo off
setlocal
py -3.11 -m venv .venv 2>nul || python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\validate_setup.py
pause
