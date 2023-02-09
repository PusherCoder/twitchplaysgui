WHERE python >nul
IF %ERRORLEVEL% NEQ 0 python -m venv ./venv ELSE py -m venv ./venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe twitchplaysgui.py