@echo off
chcp 65001 >nul
cd /d "c:\Users\Димаш\Desktop\python\translater_bot"

if not exist "venv" (
    echo ❌ Виртуальное окружение не найдено!
    echo Запустите сначала: setup_venv.bat
    pause
    exit /b 1
)

echo ====================================================
echo    🤖 TELEGRAM БОТ ПЕРЕВОДЧИК ФАЙЛОВ
echo ====================================================
echo.
echo 🔧 Использует TransGemini.py для качественного перевода
echo 📱 Интерфейс через Telegram
echo.

echo 🔍 Проверка токена бота...
if defined TELEGRAM_BOT_TOKEN (
    echo ✅ Токен найден в переменной окружения
) else (
    if exist ".env" (
        echo ℹ️  Найден .env файл
    ) else (
        echo ⚠️  Токен не найден - бот попросит ввести при запуске
    )
)
echo.

echo 🚀 Активация окружения и запуск бота...
call venv\Scripts\activate
python telegram_bot.py

pause
