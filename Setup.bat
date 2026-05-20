@echo off
chcp 65001 >nul
echo ================================
echo Starvell Cardinal - Setup
echo ================================
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не установлен!
    echo Скачайте Python с https://www.python.org/
    pause
    exit /b 1
)

echo Устанавливаю зависимости...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Ошибка при установке зависимостей!
    pause
    exit /b 1
)

echo.
echo ================================
echo Установка завершена!
echo ================================
echo.
echo Теперь запустите Start.bat
pause
