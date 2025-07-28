@echo off
chcp 65001 >nul
ececho.
echo 📥 Установка правильных зависимостей...
pip install python-telegram-bot==20.7
pip install google-generativeai==0.8.5
pip install python-docx
pip install beautifulsoup4
pip install lxml
pip install PyQt6
pip install ebooklib
pip install Pillow
pip install PySocks==============================================
echo    Настройка виртуального окружения для Telegram бота
echo ====================================================
echo.

cd /d "c:\Users\Димаш\Desktop\python\translater_bot"

echo 🔧 Создание виртуального окружения...
if exist "venv" (
    echo ℹ️  Виртуальное окружение уже существует
) else (
    python -m venv venv
    echo ✅ Виртуальное окружение создано
)

echo.
echo 🔥 Активация виртуального окружения...
call venv\Scripts\activate

echo.
echo 📦 Обновление pip...
python -m pip install --upgrade pip

echo.
echo �️  Удаление конфликтующих пакетов...
pip uninstall -y google-genai google-ai-generativelanguage
echo ✅ Конфликтующие пакеты удалены

echo.
echo �📥 Установка правильных зависимостей...
pip install python-telegram-bot==20.7
pip install google-generativeai==0.8.5
pip install python-docx
pip install beautifulsoup4
pip install lxml
pip install PyQt6
pip install ebooklib

echo.
echo 🧪 Проверка установки...
python -c "import telegram; import google.generativeai; from TransGemini import MODELS, Worker; print('✅ Все зависимости работают!')"

echo.
echo ✅ Все зависимости установлены!
echo.
echo ====================================================
echo    Настройка завершена!
echo ====================================================
echo.
echo 🚀 Для запуска бота:
echo 1. Активируйте окружение: venv\Scripts\activate
echo 2. Запустите бота: python telegram_bot.py
echo.
echo 📝 Или используйте: start_bot.bat
echo.

pause
