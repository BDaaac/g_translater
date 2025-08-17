#!/bin/bash

# Azure App Service startup script
echo "🔵 Запуск TransGemini Telegram Bot в Azure"

# Устанавливаем переменные окружения
export PYTHONPATH="/home/site/wwwroot:$PYTHONPATH"

# Запускаем бота
cd /home/site/wwwroot
python telegram_bot.py
