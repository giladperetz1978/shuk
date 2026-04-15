@echo off
setlocal

set "APP_NAME=FPI Trading Compare"
set "TARGET_DIR=%LocalAppData%\FPITradingCompare"
set "TARGET_EXE=%TARGET_DIR%\FPITradingCompare.exe"
set "DESKTOP_LINK=%UserProfile%\Desktop\FPI Trading Compare.lnk"

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

copy /Y "FPITradingCompare.exe" "%TARGET_EXE%" >nul
if errorlevel 1 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($env:DESKTOP_LINK); $shortcut.TargetPath = $env:TARGET_EXE; $shortcut.WorkingDirectory = $env:TARGET_DIR; $shortcut.IconLocation = $env:TARGET_EXE + ',0'; $shortcut.Save()"

start "" "%TARGET_EXE%"
exit /b 0