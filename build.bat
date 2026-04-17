@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building executable...
pyinstaller --onefile --windowed --name DynDNSUpdater --icon=icon.ico dynamicdns.py 2>nul || ^
pyinstaller --onefile --windowed --name DynDNSUpdater dynamicdns.py

echo.
echo Done! Executable is in the dist\ folder.
pause
