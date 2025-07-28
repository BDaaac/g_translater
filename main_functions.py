
def load_env_file():
    """Загружает переменные из .env файла"""
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def main():
    """Основная функция запуска бота"""
    print("🤖 Запуск Telegram бота переводчика файлов")
    print("🔧 Использует TransGemini.py для высококачественного перевода")
    print("=" * 60)
    
    # Загружаем .env файл если существует
    load_env_file()
    
    # Получаем токен бота из переменной окружения
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("❌ Ошибка: Не найден токен бота!")
        print("Создайте бота через @BotFather в Telegram и получите токен")
        print("=" * 40)
        
        # Попросим пользователя ввести токен
        bot_token = input("Введите токен бота: ").strip()
        if not bot_token:
            print("Токен не введен. Выход.")
            sys.exit(1)
    
    # Создаем приложение
    application = Application.builder().token(bot_token).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Обработчик файлов
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчик API ключа и ввода диапазона глав (текстовые сообщения)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Обработчики callback кнопок
    application.add_handler(CallbackQueryHandler(handle_format_selection, pattern=r"^format_"))
    application.add_handler(CallbackQueryHandler(handle_chapter_selection, pattern=r"^(chapters_|skip_chapters)"))
    application.add_handler(CallbackQueryHandler(handle_chapter_range_selection, pattern=r"^(range_|back_to_chapters)"))
    application.add_handler(CallbackQueryHandler(handle_translation_options, pattern=r"^(lang_|select_model$|model_|back_to_translation_options$|start_translation$)"))
    
    print(f"✅ Бот настроен с токеном: {bot_token[:10]}...")
    print("🚀 Бот запущен! Нажмите Ctrl+C для остановки.")
    print("🎯 Отправьте боту файл для начала перевода!")
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
