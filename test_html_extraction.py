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

# Тестируем с вашим примером
test_content = """0002_Chapter_2_Bom__Spring_1 
<br />body { font-family: sans-serif; line-height: 1.6; margin: 2em auto; max-width: 800px; padding: 0 1em; color: #333; background-color: #fdfdfd; }<br />p { margin-top: 0; margin-bottom: 1em; text-align: justify; }<br />h1, h2, h3, h4, h5, h6 { margin-top: 1.8em; margin-bottom: 0.6em; line-height: 1.3; font-weight: normal; color: #111; border-bottom: 1px solid #eee; padding-bottom: 0.2em;}<br />h1 { font-size: 2em; } h2 { font-size: 1.7em; } h3 { font-size: 1.4em; }<br />img { max-width: 100%; height: auto; display: block; margin: 1.5em auto; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }<br />hr { border: none; border-top: 1px solid #ccc; margin: 2.5em 0; }<br />ul, ol { margin-left: 1.5em; margin-bottom: 1em; padding-left: 1.5em; }<br />li { margin-bottom: 0.4em; }<br />strong { font-weight: bold; }<br />em { font-style: italic; }<br />a { color: #007bff; text-decoration: none; } a:hover { text-decoration: underline; }<br />code { background-color: #f0f0f0; padding: 0.1em 0.3em; border-radius: 3px; font-family: Consolas, monospace; font-size: 0.9em; }<br />pre { background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 1em; overflow-x: auto; white-space: pre; }<br />pre code { background-color: transparent; padding: 0; border-radius: 0; font-size: 0.9em; }<br /> 
Глава 2: Бом / Весна (1) 
Ю Джитаэ достал из шкафа униформу, надел"""

print("Исходный контент:")
print(test_content[:200] + "..." if len(test_content) > 200 else test_content)
print("\n" + "="*50 + "\n")

cleaned_content = extract_body_content_from_html(test_content)

print("Очищенный контент:")
print(cleaned_content)
