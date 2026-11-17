@echo off
REM Gera "Forge AI.exe" neste computador (Windows). Precisa do Python instalado.
cd /d "%~dp0"
python -m pip install -r requirements-app.txt || goto erro
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Forge AI" --icon assets\forge.ico --add-data "ui;ui" --add-data "assets;assets" app.py || goto erro
echo.
echo Pronto! O app esta em: %~dp0dist\Forge AI.exe
explorer dist
pause
exit /b 0
:erro
echo Algo deu errado. Veja a mensagem acima.
pause
exit /b 1
