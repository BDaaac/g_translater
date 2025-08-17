# Azure-специфичная конфигурация
import os

# Azure App Service configuration
AZURE_WEBAPP_NAME = os.getenv('WEBSITE_SITE_NAME', '')
AZURE_WEBHOOK_URL = f"https://{AZURE_WEBAPP_NAME}.azurewebsites.net" if AZURE_WEBAPP_NAME else None

def is_azure_environment():
    """Проверяет, запущен ли бот в Azure"""
    return bool(AZURE_WEBAPP_NAME)

def get_webhook_url():
    """Возвращает URL для webhook в Azure"""
    if is_azure_environment():
        return f"{AZURE_WEBHOOK_URL}/webhook"
    return None
