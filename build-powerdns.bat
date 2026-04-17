@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building PowerDNS Updater executable...
pyinstaller --onefile --windowed --name PowerDNSUpdater --icon=icon.ico dynamicdns.py 2>nul || ^
pyinstaller --onefile --windowed --name PowerDNSUpdater dynamicdns.py

echo.
echo Done! Executable is in the dist\ folder.
pause
