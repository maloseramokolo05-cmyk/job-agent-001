@echo off
for /f "tokens=2" %%p in ('tasklist /v /fo csv ^| findstr /i "Tumelo Job Agent"') do taskkill /PID %%~p /T /F >nul 2>&1
echo Tumelo Job Agent windows have been stopped.
