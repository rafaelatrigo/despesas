@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Versao para o Agendador de Tarefas: sem pausas, grava log em atualizacao.log
echo ==== %date% %time% ==== >> atualizacao.log
python scripts\gerar_dados.py >> atualizacao.log 2>&1
if errorlevel 1 (echo ERRO ao gerar os dados >> atualizacao.log & exit /b 1)
git pull --quiet origin main >> atualizacao.log 2>&1
git add -A
git diff --cached --quiet
if not errorlevel 1 (echo Sem mudancas >> atualizacao.log & exit /b 0)
git commit -m "Atualiza dados do painel %date%" >> atualizacao.log 2>&1
git push -u origin HEAD:main >> atualizacao.log 2>&1
if errorlevel 1 (echo ERRO no push >> atualizacao.log & exit /b 1)
echo OK >> atualizacao.log
