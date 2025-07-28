#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Установщик и запускальщик Telegram бота переводчика
"""

import os
import sys
import subprocess

def install_dependencies():
    """Устанавливает все необходимые зависимости"""
    dependencies = [
        "python-telegram-bot==20.7",
        "google-generativeai",
        "python-docx",
        "beautifulsoup4",
        "lxml"
    ]
    
    print("🔧 Устанавливаю зависимости...")
    for dep in dependencies:
        print(f"   Устанавливаю {dep}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
            print(f"   ✅ {dep} установлен")
        except subprocess.CalledProcessError:
            print(f"   ❌ Ошибка установки {dep}")
    
    print("✅ Установка зависимостей завершена!")

def get_bot_token():
    """Получает токен бота"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("\n🤖 Настройка Telegram бота")
        print("=" * 40)
        print("1. Откройте Telegram и найдите @BotFather")
        print("2. Отправьте команду /newbot")
        print("3. Следуйте инструкциям для создания бота")
        print("4. Скопируйте полученный токен")
        print("=" * 40)
        
        token = input("Введите токен вашего бота: ").strip()
        
        if not token:
            print("❌ Токен не введен!")
            return None
        
        # Сохраняем токен в переменную окружения для текущей сессии
        os.environ['TELEGRAM_BOT_TOKEN'] = token
    
    return token

def main():
    """Основная функция"""
    print("🚀 Запуск Telegram бота переводчика файлов")
    print("=" * 50)
    
    # Устанавливаем зависимости
    install_dependencies()
    
    # Получаем токен бота
    token = get_bot_token()
    if not token:
        print("❌ Не удалось получить токен бота. Выход.")
        sys.exit(1)
    
    print(f"\n✅ Токен получен: {token[:10]}...")
    print("\n🤖 Запуск бота...")
    print("Нажмите Ctrl+C для остановки")
    print("=" * 50)
    
    # Импортируем и запускаем бота
    try:
        from telegram_bot import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка запуска бота: {e}")
        print("Попробуйте запустить: python telegram_bot.py")

if __name__ == '__main__':
    main()
