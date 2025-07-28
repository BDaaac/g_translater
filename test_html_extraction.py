import re
import logging

# Настройка логирования для тестирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_body_content_from_html(html_content: str) -> str:
    """
    Извлекает содержимое <body> из HTML, удаляя CSS стили и оставляя только контент
    Решает проблему попадания CSS стилей в тело EPUB файла
    """
    if not html_content or not html_content.strip():
        return ""
    
    try:
        from bs4 import BeautifulSoup
        
        # Специальная обработка для случаев, где CSS стили попадают в начало файла
        # как текст с названием главы (например: "0002_Chapter_2_Bom__Spring_1 <br />body { font-family...")
        if '<br />body {' in html_content and 'font-family' in html_content:
            logger.info("🧹 Обнаружены CSS стили в тексте, выполняем специальную очистку...")
            
            # Разделяем по <br /> и ищем CSS блок
            parts = html_content.split('<br />')
            
            # Ищем часть с CSS стилями и удаляем её
            clean_parts = []
            css_block_started = False
            
            for part in parts:
                part_stripped = part.strip()
                
                # Проверяем, является ли эта часть CSS стилем
                if ('body {' in part_stripped or 
                    'font-family' in part_stripped or
                    'line-height' in part_stripped or
                    'margin:' in part_stripped or
                    'padding:' in part_stripped or
                    'color:' in part_stripped or
                    part_stripped.endswith('}') and any(css_prop in part_stripped for css_prop in ['font-size', 'border', 'background'])):
                    logger.info(f"   Удаляем CSS фрагмент: {part_stripped[:100]}...")
                    continue
                
                # Пропускаем пустые части
                if not part_stripped:
                    continue
                    
                clean_parts.append(part)
            
            # Соединяем очищенные части
            html_content = '<br />'.join(clean_parts)
            logger.info(f"✅ Специальная очистка завершена, осталось {len(clean_parts)} частей")
        
        # Парсим HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Находим тег <body>
        body_tag = soup.find('body')
        if body_tag:
            # Извлекаем содержимое body, убирая сам тег <body>
            body_content = ""
            for element in body_tag.contents:
                body_content += str(element)
            
            logger.info(f"✅ Извлечено содержимое body ({len(body_content)} символов)")
            return body_content.strip()
        else:
            # Если нет тега body, возвращаем весь контент, но убираем стили
            logger.warning("⚠️ Тег <body> не найден, используем весь контент")
            
            # Убираем теги <head>, <style>, <html>, и DOCTYPE
            content = re.sub(r'<!DOCTYPE[^>]*>', '', html_content, flags=re.IGNORECASE)
            content = re.sub(r'<html[^>]*>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'</html>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'<head[^>]*>.*?</head>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<\?xml[^>]*\?>', '', content, flags=re.IGNORECASE)
            
            # Дополнительная очистка от CSS стилей, которые могли попасть как текст
            content = re.sub(r'body\s*\{[^}]*\}', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'[a-zA-Z\-]+\s*\{[^}]*\}', '', content, flags=re.DOTALL)
            
            # Убираем множественные пустые строки и <br /> теги
            content = re.sub(r'<br\s*/?>(\s*<br\s*/?>\s*)+', '<br />', content, flags=re.IGNORECASE)
            content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
            
            return content.strip()
            
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения body контента: {e}")
        logger.info("   Возвращаем оригинальный контент")
        return html_content

# Тестируем с вашим HTML примером
test_html_content = """<p>В 21-м веке, с Республикой Корея в центре, по всему миру открылись врата, из которых начали высыпать монстры. В то же время начали появляться сверхлюди, вооруженные «Благословениями» и «Навыками».</p><p>В этот новый период времени, называемый Новой Эрой, Корея оказалась в более удачном положении. Здесь было больше подземелий с разумными видами и дьяволами, чем в других странах.</p><p>Доход от дьяволов и разумных видов был великолепен, и к Корее относились так же, как раньше к нефтедобывающим странам, и благодаря этому Корея в настоящее время входит в тройку ведущих стран мира по военной мощи.</p><p>И десять лет назад Корея начала собирать молодых охотников с выдающимся потенциалом в одном месте для обучения. Это было началом Города-Академии, «Логова».</p><p>«Джитаэ-сонбэ, привет!»</p><p>«Джитаэ тоже здесь? Мы вчера сл</p>"""

print("Исходный HTML контент:")
print(test_html_content[:200] + "..." if len(test_html_content) > 200 else test_html_content)
print("\n" + "="*50 + "\n")

cleaned_content = extract_body_content_from_html(test_html_content)

print("Очищенный Markdown контент:")
print(cleaned_content)
print(f"\nРазмер: {len(cleaned_content)} символов")
print(f"Содержит HTML теги: {'Да' if '<' in cleaned_content and '>' in cleaned_content else 'Нет'}")
