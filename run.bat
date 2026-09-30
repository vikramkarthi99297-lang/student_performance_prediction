@echo off
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
