@echo off
chcp 65001 >nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PainelDespesas.vbs" 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*servico_local.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Servico do painel parado e removido da inicializacao do Windows.
pause
