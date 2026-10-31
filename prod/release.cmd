@echo off
rem Windows launcher for release.sh. Works from cmd, PowerShell or a double-click.
rem Always uses Git Bash, because a bare `bash` in PowerShell resolves to WSL, where Docker is not available.
rem   prod\release.cmd v1.0.1
rem   prod\release.cmd v1.0.1 --dry-run
set "GITBASH=C:\Program Files\Git\bin\bash.exe"
if not exist "%GITBASH%" (
  echo Git Bash not found at %GITBASH%
  exit /b 1
)
"%GITBASH%" "%~dp0release.sh" %*
