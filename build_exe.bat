@echo off
REM Builds dist\STA2e_Combat_Helper.exe - run this from the project folder on Windows.
python -m pip install --upgrade pyinstaller || goto :error
python -m PyInstaller --onefile --windowed --name STA2e_Combat_Helper main.py || goto :error
echo.
echo Done: dist\STA2e_Combat_Helper.exe
goto :eof

:error
echo Build failed.
exit /b 1
