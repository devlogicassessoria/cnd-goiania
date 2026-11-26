@echo off
REM ============================================================
REM  Gera o CND_Goiania.exe  (rodar no Windows, na pasta do projeto)
REM  Requisitos: Python 3.10+ instalado e no PATH, Google Chrome
REM ============================================================
cd /d "%~dp0"
if not exist .venv (
    echo Criando ambiente virtual...
    python -m venv .venv || goto erro
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto erro

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name CND_Goiania ^
  --add-data "config.json;." --add-data "assets;assets" --icon "assets\icone.ico" ^
  --collect-all selenium ^
  app.py || goto erro

copy /Y config.json dist\config.json >nul
echo.
echo ============================================================
echo  Pronto!  dist\CND_Goiania.exe  (+ dist\config.json editavel)
echo ============================================================
pause
exit /b 0
:erro
echo.
echo *** Falhou. Veja as mensagens acima. ***
pause
exit /b 1
