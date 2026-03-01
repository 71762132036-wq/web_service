@echo off
if "%~1"=="" (
    echo Usage: at ^<access_token^>
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0at.ps1" "%~1"
