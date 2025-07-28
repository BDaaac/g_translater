#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram бот для перевода файлов с использованием TransGemini.py
"""

import os
import sys
import re
import tempfile
import asyncio
import logging
import subprocess
import zipfile
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

# Импортируем исключение для обработки ошибок Telegram
from telegram.error import BadRequest

# Устанавливаем зависимости если не установлены
def ensure_package(package_name, import_name=None):
    import_name = import_name or package_name
    try:
        __import__(import_name.split('.')[0])
    except ImportError:
        print(f"Устанавливаю {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

# Устанавливаем необходимые пакеты
ensure_package("python-telegram-bot==20.7")
ensure_package("google-generativeai", "google.generativeai")
ensure_package("python-docx", "docx")
ensure_package("beautifulsoup4", "bs4")
ensure_package("lxml")
ensure_package("PyQt6", "PyQt6")
ensure_package("ebooklib")

# Импортируем библиотеки Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# Импортируем функции из TransGemini.py
from TransGemini import (
    MODELS,
    OUTPUT_FORMATS,
    Worker,
    write_to_epub
)

# Импортируем Google API исключения для проверки ключа
try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
except ImportError:
    genai = None
    google_exceptions = None

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Поддерживаемые форматы файлов (соответствуют TransGemini.py)
SUPPORTED_FORMATS = {
    'txt': ['.txt'],
    'docx': ['.docx'], 
    'html': ['.html', '.htm'],
    'epub': ['.epub'],
    'xml': ['.xml'],
    'fb2': ['.fb2']
}

def get_possible_output_formats(input_format: str) -> list:
    """Возвращает возможные выходные форматы для данного входного формата"""
    # Используем OUTPUT_FORMATS из TransGemini.py
    available_formats = []
    for display_name, format_code in OUTPUT_FORMATS.items():
        # Теперь включаем EPUB для всех входных форматов с собственной реализацией
        if format_code in ['txt', 'docx', 'html', 'md', 'epub']:
            available_formats.append((display_name, format_code))
    return available_formats

def process_text_block_for_chapter_html(text_block: str) -> str:
    """Обрабатывает блок текста для HTML, сохраняя структуру как в TransGemini"""
    from html import escape
    import re
    
    # Защищаем амперсанды
    text_block_escaped_amp = text_block.replace('&', '&amp;')
    
    # Защищаем существующие <br/> теги
    text_block_br_protected = re.sub(r'<br\s*/?>', '__TEMP_BR_TAG__', text_block_escaped_amp, flags=re.IGNORECASE)
    
    # Экранируем < и >
    text_block_lt_gt_escaped = text_block_br_protected.replace('<', '&lt;').replace('>', '&gt;')
    
    # Обрабатываем простое markdown форматирование
    temp_md_text = text_block_lt_gt_escaped
    temp_md_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', temp_md_text, flags=re.DOTALL)
    temp_md_text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<em>\1</em>', temp_md_text, flags=re.DOTALL)
    temp_md_text = re.sub(r'`(.*?)`', r'<code>\1</code>', temp_md_text, flags=re.DOTALL)
    
    # Возвращаем защищенные теги
    final_text = temp_md_text.replace('__TEMP_BR_TAG__', '<br/>')
    
    return final_text

def create_chapter_html(chapter_title: str, content: str, chapter_num: int) -> str:
    """Создает HTML контент для главы в стиле TransGemini с сохранением структуры"""
    from html import escape
    import re
    
    # Экранируем заголовок
    title_escaped = escape(chapter_title)
    
    # Очищаем контент от мусорных фраз AI
    content = clean_ai_response(content)
    
    # Разделяем контент на строки (сохраняем оригинальную структуру)
    lines = content.splitlines()
    
    html_body_content = ""
    paragraph_buffer = []
    current_list_type = None
    in_code_block = False
    code_block_lines = []
    
    def flush_paragraph_buffer():
        """Очищает буфер абзаца и добавляет его в HTML"""
        nonlocal html_body_content, paragraph_buffer
        if paragraph_buffer:
            # Соединяем строки абзаца через <br/>
            para_content = process_text_block_for_chapter_html('<br/>'.join(paragraph_buffer))
            if para_content.strip():
                html_body_content += f"    <p>{para_content}</p>\n"
            paragraph_buffer = []
    
    def close_current_list():
        """Закрывает текущий список"""
        nonlocal html_body_content, current_list_type
        if current_list_type:
            html_body_content += f"    </{current_list_type}>\n"
            current_list_type = None
    
    for line in lines:
        stripped_line = line.strip()
        is_code_fence = stripped_line == '```'
        
        # Обработка блоков кода
        if is_code_fence:
            if not in_code_block:
                flush_paragraph_buffer()
                close_current_list()
                in_code_block = True
                code_block_lines = []
            else:
                in_code_block = False
                escaped_code = escape("\n".join(code_block_lines))
                html_body_content += f"    <pre><code>{escaped_code}</code></pre>\n"
            continue
        
        if in_code_block:
            code_block_lines.append(line)
            continue
        
        # Проверка на заголовки, списки и разделители
        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
        hr_match = stripped_line == '---'
        ul_match = re.match(r'^[\*\-]\s+(.*)', stripped_line)
        ol_match = re.match(r'^\d+\.\s+(.*)', stripped_line)
        
        # Закрываем список если нужно
        if current_list_type and not ((current_list_type == 'ul' and ul_match) or (current_list_type == 'ol' and ol_match)):
            close_current_list()
        
        # Очищаем буфер перед специальными элементами
        if paragraph_buffer and (heading_match or hr_match or ul_match or ol_match):
            flush_paragraph_buffer()
        
        if heading_match:
            # Заголовок
            level = len(heading_match.group(1))
            heading_text = process_text_block_for_chapter_html(heading_match.group(2).strip())
            if heading_text:
                html_body_content += f"    <h{level}>{heading_text}</h{level}>\n"
        elif hr_match:
            # Горизонтальная линия
            html_body_content += "    <hr/>\n"
        elif ul_match:
            # Неупорядоченный список
            if current_list_type != 'ul':
                html_body_content += "    <ul>\n"
                current_list_type = 'ul'
            list_text = process_text_block_for_chapter_html(ul_match.group(1).strip())
            html_body_content += f"      <li>{list_text}</li>\n"
        elif ol_match:
            # Упорядоченный список
            if current_list_type != 'ol':
                html_body_content += "    <ol>\n"
                current_list_type = 'ol'
            list_text = process_text_block_for_chapter_html(ol_match.group(1).strip())
            html_body_content += f"      <li>{list_text}</li>\n"
        elif line.strip():
            # Обычная строка - добавляем в буфер абзаца
            paragraph_buffer.append(line)
        elif not stripped_line and paragraph_buffer:
            # Пустая строка - завершаем текущий абзац
            flush_paragraph_buffer()
    
    # Завершаем оставшиеся элементы
    close_current_list()
    flush_paragraph_buffer()
    
    if in_code_block:
        escaped_code = escape("\n".join(code_block_lines))
        html_body_content += f"    <pre><code>{escaped_code}</code></pre>\n"
    
    # Если контент пустой, создаем минимальный абзац
    if not html_body_content.strip():
        processed_content = process_text_block_for_chapter_html(content.strip())
        html_body_content = f"    <p>{processed_content}</p>\n"
    
    # Создаем полный HTML в стиле TransGemini
    html_content = f'''<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{title_escaped}</title>
  <link rel="stylesheet" type="text/css" href="../style/default.css"/>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
</head>
<body>
  <h1>{title_escaped}</h1>
{html_body_content.rstrip()}
</body>
</html>'''
    
    return html_content

def clean_ai_response(content: str) -> str:
    """Очищает переведенный контент от служебных фраз AI"""
    try:
        # Список фраз, которые нужно удалить из начала текста
        ai_garbage_patterns = [
            r'^(?:конечно[,!]?\s*)?вот\s+перевод[:\s]*',
            r'^вот\s+переведенный\s+текст[:\s]*',
            r'^перевод[:\s]*',
            r'^переведенный\s+текст[:\s]*',
            r'^переведено[:\s]*',
            r'^результат\s+перевода[:\s]*',
            r'^переведенная\s+версия[:\s]*',
            r'^вот\s+результат[:\s]*',
            r'^конечно[,!]?\s*',
            r'^да[,!]?\s*вот\s*',
            r'^хорошо[,!]?\s*',
            r'^отлично[,!]?\s*',
            r'^готово[,!]?\s*',
            r'^вот\s+он[:\s]*',
            r'^смотри[,!]?\s*',
            r'^держи[,!]?\s*',
            r'^пожалуйста[,!]?\s*',
            r'^\*\*перевод\*\*[:\s]*',
            r'^\*\*переведенный\s+текст\*\*[:\s]*',
            r'^here\s+is\s+the\s+translation[:\s]*',
            r'^translation[:\s]*',
            r'^translated\s+text[:\s]*',
            r'^of\s+course[,!]?\s*here\s*',
            r'^sure[,!]?\s*here\s*',
            r'^here\s+you\s+go[:\s]*',
            r'^вот\s+и\s+всё[,!]?\s*',
            r'^готово[,!]?\s*вот\s*'
        ]
        
        # Применяем каждый паттерн для очистки начала
        cleaned_content = content.strip()
        for pattern in ai_garbage_patterns:
            cleaned_content = re.sub(pattern, '', cleaned_content, flags=re.IGNORECASE | re.MULTILINE)
            cleaned_content = cleaned_content.strip()
        
        # Удаляем пустые строки в начале
        while cleaned_content.startswith('\n'):
            cleaned_content = cleaned_content[1:]
        
        # Удаляем markdown форматирование в начале, если есть
        cleaned_content = re.sub(r'^```[a-z]*\n?', '', cleaned_content, flags=re.MULTILINE)
        cleaned_content = re.sub(r'\n?```$', '', cleaned_content, flags=re.MULTILINE)
        
        # Удаляем повторяющиеся переносы строк
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        
        # Удаляем лишние пробелы в начале строк
        cleaned_content = re.sub(r'^\s+', '', cleaned_content, flags=re.MULTILINE)
        
        if len(content) != len(cleaned_content):
            logger.info(f"🧹 Очищен контент: было {len(content)} символов, стало {len(cleaned_content)} символов")
        
        return cleaned_content.strip()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке AI ответа: {e}")
        return content

def smart_split_content(content: str, target_chapters: int) -> list:
    """Умно разделяет контент на главы, сохраняя структуру диалогов и абзацев"""
    try:
        logger.info(f"📝 Умное разделение контента ({len(content)} символов) на {target_chapters} глав")
        
        # Сначала пробуем разделить по явным маркерам глав
        chapter_patterns = [
            r'\n\s*(Глава|ГЛАВА|Chapter|CHAPTER)\s+\d+',
            r'\n\s*(Часть|ЧАСТЬ|Part|PART)\s+\d+',
            r'\n\s*\d+\.\s*[А-ЯA-Z]',
            r'\n\s*[IVX]+\.\s*[А-ЯA-Z]',
        ]
        
        for pattern in chapter_patterns:
            splits = re.split(pattern, content, flags=re.MULTILINE | re.IGNORECASE)
            if len(splits) > 1 and len(splits) <= target_chapters * 2:
                # Убираем пустые части и объединяем с заголовками
                chapters = []
                for i, part in enumerate(splits):
                    if part.strip():
                        chapters.append(part.strip())
                if len(chapters) >= 2:
                    logger.info(f"📖 Разделили контент по паттерну на {len(chapters)} частей")
                    return chapters
        
        # Если не получилось найти явные маркеры, разделяем по структурным границам
        # Сохраняем оригинальную структуру (переносы строк)
        
        # Ищем естественные границы (двойные переносы строк)
        sections = content.split('\n\n')
        
        if len(sections) <= target_chapters:
            # Слишком мало секций, возвращаем как есть
            return [content]
        
        # Группируем секции по размеру
        sections_per_chapter = max(1, len(sections) // target_chapters)
        chapters = []
        
        for i in range(0, len(sections), sections_per_chapter):
            chapter_sections = sections[i:i + sections_per_chapter]
            if chapter_sections:
                # Соединяем секции обратно двойными переносами для сохранения структуры
                chapter_content = '\n\n'.join(sec.strip() for sec in chapter_sections if sec.strip())
                if chapter_content:
                    chapters.append(chapter_content)
        
        # Если последняя глава получилась слишком короткой, объединяем с предыдущей
        if len(chapters) > 1 and len(chapters[-1]) < 200:  # Увеличили минимум
            chapters[-2] = chapters[-2] + '\n\n' + chapters[-1]
            chapters.pop()
        
        logger.info(f"📝 Разделили контент по структурным границам на {len(chapters)} глав")
        
        # Логируем структуру каждой главы
        for i, chapter in enumerate(chapters[:3]):  # Показываем первые 3
            lines_count = len(chapter.split('\n'))
            paragraphs_count = len([p for p in chapter.split('\n\n') if p.strip()])
            logger.info(f"  Глава {i+1}: {len(chapter)} символов, {lines_count} строк, {paragraphs_count} абзацев")
        
        return chapters
        
    except Exception as e:
        logger.error(f"❌ Ошибка при умном разделении контента: {e}")
        return [content]

def create_epub_from_original(original_epub_path: str, translated_content: str, output_path: str, title_override: str = None) -> bool:
    """
    Заглушка для создания EPUB - теперь TransGemini.py делает это сам
    """
    logger.info("create_epub_from_original: TransGemini.py теперь создает EPUB файлы напрямую")
    return False  # Не используется, так как TransGemini создает файлы сам
        
        from ebooklib import epub
        import uuid
        from html import escape
        from bs4 import BeautifulSoup
        import re
        
        # Создаем новую книгу
        book = epub.EpubBook()
        
        # Устанавливаем метаданные
        book_title = title_override or Path(original_epub_path).stem
        book.set_identifier(f'urn:uuid:{uuid.uuid4()}')
        book.set_title(book_title)
        book.set_language('ru')
        book.add_author('Translator')
        
        # Сначала попробуем прочитать оригинальную структуру EPUB
        original_chapters = []
        try:
            with zipfile.ZipFile(original_epub_path, 'r') as epub_zip:
                # Получаем все HTML файлы из оригинала (как в TransGemini)
                html_files = sorted([
                    name for name in epub_zip.namelist()
                    if name.lower().endswith(('.html', '.xhtml', '.htm'))
                    and not name.startswith(('__MACOSX', 'META-INF/'))
                ])
                
                # Применяем точную фильтрацию TransGemini для определения глав
                content_files = []
                TRANSLATED_SUFFIX = '_translated'
                
                for html_file in html_files:
                    filename_lower = Path(html_file).name.lower()
                    filename_base = Path(html_file).stem.split('.')[0].lower()
                    
                    # Списки из TransGemini
                    skip_indicators = ['toc', 'nav', 'ncx', 'cover', 'title', 'index', 'copyright', 'about', 'meta', 'opf',
                                      'masthead', 'colophon', 'imprint', 'acknowledgments', 'dedication',
                                      'glossary', 'bibliography', 'notes', 'annotations', 'epigraph', 'halftitle',
                                      'frontmatter', 'backmatter', 'preface', 'introduction', 'appendix', 'biography',
                                      'isbn', 'legal', 'notice', 'otherbooks', 'prelims', 'team', 'promo', 'bonus']
                    
                    content_indicators = ['chapter', 'part', 'section', 'content', 'text', 'page', 'body', 'main', 'article',
                                        'chp', 'chap', 'prt', 'sec', 'glava', 'prologue', 'epilogue']
                    
                    # Проверки как в TransGemini
                    is_likely_skip = any(skip in filename_base for skip in skip_indicators)
                    parent_dir_lower = str(Path(html_file).parent).lower()
                    is_likely_skip = is_likely_skip or any(skip in parent_dir_lower for skip in ['toc', 'nav', 'meta', 'frontmatter', 'backmatter', 'index', 'notes'])
                    is_likely_content = any(indicator in filename_base for indicator in content_indicators)
                    is_chapter_like = (re.fullmatch(r'(ch|gl|chap|chapter|part|section|sec|glava)[\d_-]+.*', filename_base) or 
                                      re.fullmatch(r'[\d]+', filename_base) or 
                                      re.match(r'^[ivxlcdm]+$', filename_base))
                    is_translated = filename_base.endswith(TRANSLATED_SUFFIX)
                    
                    # Размер файла
                    try:
                        file_info = epub_zip.getinfo(html_file)
                        file_size = file_info.file_size
                    except:
                        file_size = 0
                    
                    # Определяем, является ли файл главой (как в TransGemini)
                    if not is_likely_skip and not is_translated and file_size > 500:
                        if is_likely_content or is_chapter_like or ('text' in filename_base and file_size > 1000):
                            content_files.append({
                                'path': html_file,
                                'name': Path(html_file).name,
                                'title': Path(html_file).stem.split('.')[0],
                                'size': file_size,
                                'sort_key': html_file.lower()  # Для правильной сортировки
                            })
                
                # Сортируем файлы для правильного порядка глав (как в TransGemini)
                content_files.sort(key=lambda x: x['sort_key'])
                original_chapters = content_files
                
                logger.info(f"📖 Найдено {len(original_chapters)} оригинальных глав по логике TransGemini:")
                for i, ch in enumerate(original_chapters[:10]):  # Показываем первые 10
                    logger.info(f"  {i+1}. {ch['name']} ({ch['size']} bytes)")
                        
        except Exception as e:
            logger.warning(f"Не удалось проанализировать оригинальную структуру: {e}")
        
        # Разделяем переведенный контент на главы
        chapters = [ch.strip() for ch in translated_content.split('--- ГЛАВА ---') if ch.strip()]
        
        if not chapters:
            logger.warning("⚠️ Не найдено маркеров глав, используем умное разделение")
            # Используем умное разделение если есть информация об оригинале
            target_chapters = len(original_chapters) if original_chapters else 5
            chapters = smart_split_content(translated_content, target_chapters)
        
        if not chapters:
            logger.warning("⚠️ Умное разделение не удалось, создаем одну главу")
            chapters = [translated_content.strip()]
        
        logger.info(f"📚 Итого глав для создания EPUB: {len(chapters)}")
        
        # КРИТИЧЕСКИ ВАЖНО: Если у нас есть точная информация об оригинальной структуре,
        # убеждаемся что количество глав совпадает
        if original_chapters and len(original_chapters) > 0:
            if len(chapters) != len(original_chapters):
                logger.warning(f"⚠️ Несоответствие количества глав: переведено {len(chapters)}, оригинал {len(original_chapters)}")
                
                # Если у нас одна большая глава, а должно быть много
                if len(chapters) == 1 and len(original_chapters) > 1:
                    logger.info("📝 Разделяем единый переведенный текст согласно оригинальной структуре...")
                    chapters = smart_split_content(chapters[0], len(original_chapters))
                
                # Если количество глав близко, но не точно совпадает
                elif abs(len(chapters) - len(original_chapters)) <= 2:
                    logger.info(f"📝 Близкое количество глав, подгоняем под оригинал ({len(original_chapters)} глав)")
                    if len(chapters) > len(original_chapters):
                        # Объединяем лишние главы
                        while len(chapters) > len(original_chapters):
                            chapters[-2] = chapters[-2] + '\n\n' + chapters[-1]
                            chapters.pop()
                    elif len(chapters) < len(original_chapters):
                        # Разделяем большие главы
                        while len(chapters) < len(original_chapters) and len(chapters) > 0:
                            # Находим самую большую главу и разделяем её
                            max_idx = max(range(len(chapters)), key=lambda i: len(chapters[i]))
                            big_chapter = chapters[max_idx]
                            split_parts = smart_split_content(big_chapter, 2)
                            if len(split_parts) >= 2:
                                chapters[max_idx] = split_parts[0]
                                chapters.insert(max_idx + 1, split_parts[1])
                            else:
                                break
                
                logger.info(f"✅ Подогнали количество глав: {len(chapters)} глав")
        
        # Обеспечиваем минимум одну главу
        if not chapters:
            chapters = [translated_content.strip()]
        
        # Создаем CSS стили в стиле TransGemini с улучшенным отображением диалогов
        default_css = epub.EpubItem(
            uid="default",
            file_name="style/default.css",
            media_type="text/css",
            content="""
body {
    font-family: "Times New Roman", Times, serif;
    font-size: 1em;
    line-height: 1.6;
    margin: 1em;
    text-align: justify;
    color: #333;
    background-color: #fdfdfd;
}

h1, h2, h3, h4, h5, h6 {
    text-align: center;
    margin: 1.8em 0 1em 0;
    font-weight: bold;
    page-break-after: avoid;
    line-height: 1.3;
    color: #111;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.2em;
}

h1 { 
    font-size: 1.8em; 
    margin-bottom: 1.5em;
    border-bottom: 2px solid #333;
    padding-bottom: 0.5em;
}

h2 { font-size: 1.5em; }
h3 { font-size: 1.3em; }
h4 { font-size: 1.2em; }
h5 { font-size: 1.1em; }
h6 { font-size: 1em; }

p {
    margin: 0.5em 0 1em 0;
    text-indent: 0;
    orphans: 2;
    widows: 2;
    word-wrap: break-word;
}

/* Стиль для диалогов - каждая строка с отступом */
p br {
    line-height: 1.6;
}

/* Улучшенное отображение переносов строк */
br {
    display: block;
    margin: 0.2em 0;
    content: "";
}

.chapter-break {
    page-break-before: always;
}

blockquote {
    margin: 1em 2em;
    font-style: italic;
    border-left: 3px solid #ddd;
    padding-left: 1em;
}

em, i {
    font-style: italic;
}

strong, b {
    font-weight: bold;
}

code {
    background-color: #f0f0f0;
    padding: 0.1em 0.3em;
    border-radius: 3px;
    font-family: Consolas, Monaco, monospace;
    font-size: 0.9em;
}

pre {
    background-color: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 1em;
    overflow-x: auto;
    white-space: pre-wrap;
    margin: 1em 0;
}

pre code {
    background-color: transparent;
    padding: 0;
    border-radius: 0;
    font-size: 0.9em;
}

ul, ol {
    margin: 1em 0;
    padding-left: 2em;
}

li {
    margin-bottom: 0.4em;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 2.5em 0;
}

/* Специальные стили для сохранения структуры */
.dialogue {
    text-indent: 0;
    margin-left: 1em;
}

.narrative {
    text-indent: 1.5em;
}
            """.strip()
        )
        book.add_item(default_css)
        
        # Создаем главы
        epub_chapters = []
        
        for i, chapter_content in enumerate(chapters):
            if not chapter_content.strip():
                continue
                
            # Определяем заголовок главы - ВСЕГДА используем последовательную нумерацию
            chapter_title = f"Глава {i+1}"
            
            # Проверяем, что контент не пустой
            if not chapter_content.strip():
                logger.warning(f"⛔ Пропущена пустая глава: {chapter_title}")
                continue
            
            # Дополнительно очищаем контент каждой главы от остатков AI мусора
            chapter_content = clean_ai_response(chapter_content)
            
            # Создаем HTML контент для главы
            html_content = create_chapter_html(chapter_title, chapter_content, i+1)
            
            # Проверяем, что HTML контент не пустой
            if not html_content.strip():
                logger.warning(f"⛔ Пропущена глава с пустым HTML контентом: {chapter_title}")
                continue
            
            # Создаем EPUB главу
            chapter = epub.EpubHtml(
                title=chapter_title,
                file_name=f'chapter_{i+1:03d}.xhtml',
                lang='ru'
            )
            chapter.content = html_content.encode('utf-8')
            
            book.add_item(chapter)
            epub_chapters.append(chapter)
            
            logger.info(f"📄 Создана глава {i+1}: '{chapter_title}' ({len(chapter_content)} символов контента)")
        
        # Если не удалось создать ни одной главы
        if not epub_chapters:
            logger.error("❌ Не удалось создать ни одной главы из переведенного контента")
            return False
        
        # Устанавливаем структуру книги
        book.toc = epub_chapters
        book.spine = ['nav'] + epub_chapters
        
        # Добавляем навигацию
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Создаем директорию для выходного файла если не существует
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Сохраняем EPUB
        epub.write_epub(output_path, book, {})
        
        logger.info(f"✅ EPUB файл успешно создан: {output_path} ({len(epub_chapters)} глав)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания EPUB на основе оригинала: {e}", exc_info=True)
        return False


def create_epub_from_text(content: str, title: str, author: str, output_path: str, chapters_info: dict = None) -> bool:
    """
    Заглушка для создания EPUB - теперь TransGemini.py делает это сам
    """
    logger.info("create_epub_from_text: TransGemini.py теперь создает EPUB файлы напрямую")
    return False  # Не используется, так как TransGemini создает файлы сам

# Состояния пользователя
USER_STATES = {}

class UserState:
    def __init__(self):
        self.step = "waiting_file"  # waiting_file -> format_selection -> api_key -> chapter_selection -> translating
        self.file_path: Optional[str] = None
        self.file_name: Optional[str] = None
        self.file_format: Optional[str] = None
        self.output_format: Optional[str] = None
        self.api_key: Optional[str] = None
        self.target_language: str = "русский"
        self.model: str = list(MODELS.keys())[0] if MODELS else "Gemini 2.0 Flash"  # Используем первую доступную модель
        self.start_chapter: int = 1
        self.chapter_count: int = 0  # 0 = все главы
        self.total_chapters: int = 0  # Определяется при анализе файла
        self.chapters_info: Optional[Dict[str, Any]] = None  # Детальная информация о главах

def get_user_state(user_id: int) -> UserState:
    if user_id not in USER_STATES:
        USER_STATES[user_id] = UserState()
    return USER_STATES[user_id]

def reset_user_state(user_id: int):
    if user_id in USER_STATES:
        del USER_STATES[user_id]

def get_possible_output_formats_old(input_format: str) -> list:
    """Старая функция - заменена на версию с OUTPUT_FORMATS"""
    if input_format in ['txt', 'docx', 'html', 'xml']:
        return ['txt', 'docx', 'html']
    elif input_format == 'epub':
        return ['txt', 'docx', 'html', 'epub']
    else:
        return ['txt']

def determine_input_format(file_extension: str) -> str:
    """Определяет входной формат файла по расширению"""
    for fmt, extensions in SUPPORTED_FORMATS.items():
        if file_extension in extensions:
            return fmt
    return 'txt'  # fallback

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    reset_user_state(user_id)
    
    welcome_message = """
🤖 **Добро пожаловать в бот переводчика файлов!**

Я могу переводить различные форматы файлов используя Google Gemini AI.

**Поддерживаемые форматы:**
• TXT - текстовые файлы
• DOCX - документы Word
• HTML - веб-страницы
• EPUB - электронные книги
• XML - XML документы

**Как использовать:**
1. Отправьте файл для перевода
2. Выберите выходной формат
3. Введите API ключ Google Gemini
4. Получите переведенный файл

Отправьте файл чтобы начать! 📁
    """
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загруженных файлов"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state.step != "waiting_file":
        await update.message.reply_text("Пожалуйста, завершите текущий процесс или используйте /start для начала заново.")
        return
    
    document = update.message.document
    if not document:
        await update.message.reply_text("Пожалуйста, отправьте файл.")
        return
    
    # Проверяем размер файла (максимум 20MB для Telegram)
    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("Файл слишком большой. Максимальный размер: 20MB")
        return
    
    # Определяем формат файла по расширению
    file_name = document.file_name
    file_extension = Path(file_name).suffix.lower()
    
    # Проверяем поддерживаемые форматы
    supported_extensions = {'.txt', '.docx', '.html', '.htm', '.epub', '.xml'}
    if file_extension not in supported_extensions:
        await update.message.reply_text(
            f"Неподдерживаемый формат файла: {file_extension}\n"
            f"Поддерживаемые форматы: {', '.join(supported_extensions)}"
        )
        return
    
    try:
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        
        # Создаем temporary файл
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, file_name)
        
        await file.download_to_drive(file_path)
        
        # Определяем формат файла
        state.file_format = determine_input_format(file_extension)
        
        # Сохраняем информацию о файле
        state.file_path = file_path
        state.file_name = file_name
        state.step = "format_selection"
        
        # Показываем варианты выходного формата
        await show_format_selection(update, state)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await update.message.reply_text("Произошла ошибка при обработке файла. Попробуйте еще раз.")

async def show_format_selection(update: Update, state: UserState):
    """Показывает выбор выходного формата используя OUTPUT_FORMATS из TransGemini.py"""
    # Получаем возможные выходные форматы для данного входного формата
    possible_formats = get_possible_output_formats(state.file_format)
    
    keyboard = []
    for display_name, format_code in possible_formats:
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"format_{format_code}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📁 Файл получен: `{state.file_name}`\n\n"
        f"Выберите выходной формат:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора формата"""
    query = update.callback_query
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    if state.step != "format_selection":
        await query.answer("Неверный шаг процесса")
        return
    
    # Получаем выбранный формат
    callback_data = query.data
    if not callback_data.startswith("format_"):
        await query.answer("Неверные данные")
        return
    
    selected_format = callback_data.replace("format_", "")
    state.output_format = selected_format
    state.step = "api_key"
    
    await query.answer()
    try:
        await query.edit_message_text(
            f"✅ Выбран формат: **{selected_format.upper()}**\n\n"
            f"Теперь отправьте ваш API ключ Google Gemini.\n\n"
            f"**Как получить API ключ:**\n"
            f"1. Перейдите на https://aistudio.google.com/\n"
            f"2. Войдите в аккаунт Google\n"
            f"3. Создайте новый API ключ\n"
            f"4. Отправьте его мне\n\n"
            f"⚡ **Автоматическая проверка:** Ваш ключ будет проверен на действительность перед началом перевода.\n\n"
            f"🔐 Отправьте API ключ:",
            parse_mode=ParseMode.MARKDOWN
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state.step == "api_key":
        await handle_api_key(update, context)
    elif state.step == "chapter_input":
        await handle_chapter_input(update, context)
    else:
        # Неожиданное текстовое сообщение
        await update.message.reply_text(
            "🤔 Я не понимаю, что вы хотите сделать.\n"
            "Используйте /start для начала работы или /help для справки."
        )

async def validate_api_key(api_key: str) -> tuple[bool, str]:
    """Проверяет валидность API ключа через Google Gemini API"""
    try:
        if not genai or not google_exceptions:
            return False, "Google API библиотеки не установлены"
            
        # Настраиваем API
        genai.configure(api_key=api_key)
        
        # Пытаемся получить список моделей для проверки ключа
        models = genai.list_models()
        
        # Проверяем, есть ли доступные модели Gemini
        gemini_models = [m for m in models if m.name.startswith("models/")]
        
        if gemini_models:
            return True, "API ключ действителен."
        else:
            return False, "Ключ принят API, но не найдено доступных моделей Gemini."
            
    except google_exceptions.Unauthenticated as e:
        return False, f"Ошибка аутентификации (неверный ключ): {str(e)}"
    except Exception as e:
        return False, f"Ошибка проверки API ключа: {str(e)}"

async def handle_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик API ключа"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state.step != "api_key":
        return
    
    api_key = update.message.text.strip()
    
    # Базовая проверка API ключа
    if len(api_key) < 30 or not api_key.startswith('AI'):
        await update.message.reply_text(
            "❌ Неверный формат API ключа.\n"
            "API ключ должен начинаться с 'AI' и быть достаточно длинным.\n"
            "Попробуйте еще раз."
        )
        return
    
    # Отправляем сообщение о проверке ключа
    checking_message = await update.message.reply_text(
        "🔍 **Проверяю API ключ...**\n\n"
        "⏳ Выполняю тестовый запрос к Google Gemini API...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Проверяем валидность API ключа
    is_valid, validation_message = await validate_api_key(api_key)
    
    if is_valid:
        # Ключ действителен
        state.api_key = api_key
        state.step = "chapter_selection"
        
        await checking_message.edit_text(
            "✅ **API ключ действителен!**\n\n"
            "🔑 Ключ успешно проверен\n"
            "📝 Анализирую файл для определения глав...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Анализируем файл для определения количества глав
        await analyze_file_chapters(update, state)
        
    else:
        # Ключ недействителен
        await checking_message.edit_text(
            "❌ **API ключ недействителен**\n\n"
            f"🚫 {validation_message}\n\n"
            "**Как получить API ключ:**\n"
            "1. Перейдите на https://aistudio.google.com/\n"
            "2. Войдите в аккаунт Google\n"
            "3. Создайте новый API ключ\n"
            "4. Отправьте его мне\n\n"
            "🔐 Отправьте корректный API ключ:",
            parse_mode=ParseMode.MARKDOWN
        )

async def analyze_file_chapters(update: Update, state: UserState):
    """Анализирует файл для определения количества глав"""
    try:
        chapters_found = 0
        
        # Сначала пробуем использовать точную логику TransGemini
        if state.file_format == 'epub':
            transgemini_info = await get_transgemini_chapters_info(state.file_path, state.file_format)
            if transgemini_info['total_content'] > 0:
                chapters_found = transgemini_info['total_content']
                # Сохраняем детальную информацию в состоянии для дальнейшего использования
                state.chapters_info = transgemini_info
                logger.info(f"Использована точная логика TransGemini: найдено {chapters_found} глав")
            else:
                # Fallback к старой логике
                chapters_found = await count_chapters_in_file(state.file_path, state.file_format)
        else:
            # Для других форматов используем стандартную логику
            chapters_found = await count_chapters_in_file(state.file_path, state.file_format)
        
        state.total_chapters = max(1, chapters_found)
        
        # Показываем опции выбора глав
        await show_chapter_selection(update, state)
        
    except Exception as e:
        logger.error(f"Ошибка при анализе глав: {e}")
        # В случае ошибки - сразу к настройкам перевода
        state.step = "translating"
        await show_translation_options(update, state)

async def get_transgemini_chapters_info(file_path: str, file_format: str) -> dict:
    """Получает информацию о главах используя точную логику TransGemini"""
    try:
        if file_format == 'epub':
            with zipfile.ZipFile(file_path, 'r') as epub_zip:
                # Получаем все HTML файлы (как в TransGemini)
                html_files = sorted([
                    name for name in epub_zip.namelist()
                    if name.lower().endswith(('.html', '.xhtml', '.htm'))
                    and not name.startswith(('__MACOSX', 'META-INF/'))
                ])
                
                # Пытаемся найти NAV файл (как в TransGemini)
                nav_path = None
                for html_file in html_files:
                    if 'nav' in Path(html_file).name.lower():
                        nav_path = html_file
                        break
                
                chapters_info = {
                    'all_files': [],
                    'content_files': [],
                    'skip_files': [],
                    'nav_file': nav_path,
                    'total_all': len(html_files),
                    'total_content': 0,
                    'original_path': file_path  # Добавляем путь к оригинальному EPUB
                }
                
                TRANSLATED_SUFFIX = '_translated'  # Константа из TransGemini
                
                for file_path_in_epub in html_files:
                    try:
                        file_info = epub_zip.getinfo(file_path_in_epub)
                        file_size = file_info.file_size
                    except:
                        file_size = 0
                    
                    is_nav = (nav_path and file_path_in_epub == nav_path)
                    is_translated = Path(file_path_in_epub).stem.endswith(TRANSLATED_SUFFIX)
                    
                    file_data = {
                        'path': file_path_in_epub,
                        'name': Path(file_path_in_epub).name,
                        'size': file_size,
                        'is_nav': is_nav,
                        'is_translated': is_translated,
                        'is_selected': False,
                        'category': 'unknown'
                    }
                    
                    if is_nav:
                        file_data['category'] = 'nav'
                        file_data['is_selected'] = False
                        chapters_info['skip_files'].append(file_data)
                    else:
                        # Применяем точную логику TransGemini для определения типа файла
                        item_text_lower = file_path_in_epub.lower()
                        path = Path(item_text_lower)
                        filename_lower = path.name
                        filename_base = path.stem.split('.')[0]  # Get stem before first dot
                        
                        skip_indicators = ['toc', 'nav', 'ncx', 'cover', 'title', 'index', 'copyright', 'about', 'meta', 'opf',
                                          'masthead', 'colophon', 'imprint', 'acknowledgments', 'dedication',
                                          'glossary', 'bibliography', 'notes', 'annotations', 'epigraph', 'halftitle',
                                          'frontmatter', 'backmatter', 'preface', 'introduction', 'appendix', 'biography',
                                          'isbn', 'legal', 'notice', 'otherbooks', 'prelims', 'team', 'promo', 'bonus']
                        content_indicators = ['chapter', 'part', 'section', 'content', 'text', 'page', 'body', 'main', 'article',
                                            'chp', 'chap', 'prt', 'sec', 'glava', 'prologue', 'epilogue']
                        
                        is_likely_skip = any(skip in filename_base for skip in skip_indicators)
                        parent_dir_lower = str(path.parent).lower()
                        is_likely_skip = is_likely_skip or any(skip in parent_dir_lower for skip in ['toc', 'nav', 'meta', 'frontmatter', 'backmatter', 'index', 'notes'])
                        is_likely_content = any(indicator in filename_base for indicator in content_indicators)
                        is_chapter_like = (re.fullmatch(r'(ch|gl|chap|chapter|part|section|sec|glava)[\d_-]+.*', filename_base) or 
                                          re.fullmatch(r'[\d]+', filename_base) or 
                                          re.match(r'^[ivxlcdm]+$', filename_base))
                        
                        if not is_likely_skip and (is_likely_content or is_chapter_like):
                            file_data['category'] = 'content'
                            file_data['is_selected'] = True
                            chapters_info['content_files'].append(file_data)
                        else:
                            if not is_likely_skip and 'text' in filename_base:
                                file_data['category'] = 'text'
                                file_data['is_selected'] = True
                                chapters_info['content_files'].append(file_data)
                            else:
                                file_data['category'] = 'skip'
                                file_data['is_selected'] = False
                                chapters_info['skip_files'].append(file_data)
                    
                    chapters_info['all_files'].append(file_data)
                
                chapters_info['total_content'] = len(chapters_info['content_files'])
                logger.info(f"TransGemini анализ EPUB: {chapters_info['total_content']} глав из {chapters_info['total_all']} файлов")
                return chapters_info
                
        return {'total_all': 0, 'total_content': 0, 'all_files': [], 'content_files': [], 'skip_files': [], 'nav_file': None}
        
    except Exception as e:
        logger.error(f"Ошибка TransGemini анализа: {e}")
        return {'total_all': 0, 'total_content': 0, 'all_files': [], 'content_files': [], 'skip_files': [], 'nav_file': None}

async def get_chapters_info(file_path: str, file_format: str) -> dict:
    """Получает детальную информацию о главах в файле"""
    try:
        if file_format == 'epub':
            with zipfile.ZipFile(file_path, 'r') as epub_zip:
                # Получаем все HTML файлы
                all_html_files = sorted([
                    name for name in epub_zip.namelist()
                    if name.lower().endswith(('.html', '.xhtml', '.htm'))
                    and not name.startswith(('__MACOSX', 'META-INF/'))
                ])
                
                # Анализируем каждый файл
                chapters_info = {
                    'all_files': [],
                    'content_files': [],
                    'skip_files': [],
                    'total_all': len(all_html_files),
                    'total_content': 0,
                    'original_path': file_path  # Добавляем путь к оригинальному EPUB
                }
                
                skip_indicators = [
                    'toc', 'nav', 'ncx', 'cover', 'title', 'index', 'copyright', 'about', 'meta', 'opf',
                    'masthead', 'colophon', 'imprint', 'acknowledgments', 'dedication',
                    'glossary', 'bibliography', 'notes', 'annotations', 'epigraph', 'halftitle',
                    'frontmatter', 'backmatter', 'preface', 'introduction', 'appendix', 'biography',
                    'isbn', 'legal', 'notice', 'otherbooks', 'prelims', 'team', 'promo', 'bonus'
                ]
                
                for html_file in all_html_files:
                    filename_base = Path(html_file).stem.split('.')[0].lower()
                    
                    try:
                        file_info = epub_zip.getinfo(html_file)
                        file_size = file_info.file_size
                    except:
                        file_size = 0
                    
                    # Проверяем, является ли файл служебным
                    is_skip_file = any(skip_word in filename_base for skip_word in skip_indicators)
                    is_translated = filename_base.endswith('_translated')
                    
                    file_data = {
                        'path': html_file,
                        'name': Path(html_file).name,
                        'size': file_size,
                        'is_skip': is_skip_file,
                        'is_translated': is_translated
                    }
                    
                    chapters_info['all_files'].append(file_data)
                    
                    if not is_skip_file and not is_translated and file_size > 500:
                        chapters_info['content_files'].append(file_data)
                    else:
                        chapters_info['skip_files'].append(file_data)
                
                chapters_info['total_content'] = len(chapters_info['content_files'])
                return chapters_info
                
        return {'total_all': 0, 'total_content': 0, 'all_files': [], 'content_files': [], 'skip_files': []}
        
    except Exception as e:
        logger.error(f"Ошибка анализа глав: {e}")
        return {'total_all': 0, 'total_content': 0, 'all_files': [], 'content_files': [], 'skip_files': []}

async def count_chapters_in_file(file_path: str, file_format: str) -> int:
    """Подсчитывает количество глав в файле"""
    try:
        if file_format == 'txt':
            # Пробуем разные кодировки
            content = ""
            encodings = ['utf-8', 'cp1251', 'latin-1', 'cp866']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # Если ничего не помогло, читаем в бинарном режиме
                with open(file_path, 'rb') as f:
                    raw_content = f.read()
                    content = raw_content.decode('utf-8', errors='ignore')
            
            # Ищем заголовки глав
            import re
            patterns = [
                r'^\s*(Глава|Chapter|ГЛАВА|CHAPTER)\s+\d+',
                r'^\s*(Часть|Part|ЧАСТЬ|PART)\s+\d+',
                r'^\s*\d+\.\s*[А-ЯA-Z]',
                r'^#{1,3}\s+',  # Markdown заголовки
            ]
            
            total_matches = 0
            for pattern in patterns:
                matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
                total_matches = max(total_matches, len(matches))
            
            return max(1, total_matches)
                
        elif file_format == 'docx':
            # Для DOCX используем python-docx
            try:
                from docx import Document
                doc = Document(file_path)
                chapter_count = 0
                
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if text and (
                        text.lower().startswith(('глава', 'chapter', 'часть', 'part')) or
                        para.style.name.startswith('Heading')
                    ):
                        chapter_count += 1
                
                return max(1, chapter_count)
            except ImportError:
                return 5  # Fallback если docx не установлен
                
        elif file_format == 'html':
            # Пробуем разные кодировки для HTML
            content = ""
            encodings = ['utf-8', 'cp1251', 'latin-1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                with open(file_path, 'rb') as f:
                    raw_content = f.read()
                    content = raw_content.decode('utf-8', errors='ignore')
            
            import re
            # Ищем HTML заголовки
            headers = re.findall(r'<h[1-6][^>]*>(.*?)</h[1-6]>', content, re.IGNORECASE | re.DOTALL)
            return max(1, len(headers))
        
        elif file_format == 'epub':
            # Используем точную логику TransGemini.py для EPUB файлов
            try:
                chapter_count = 0
                with zipfile.ZipFile(file_path, 'r') as epub_zip:
                    # Получаем HTML файлы так же, как в TransGemini
                    html_files_in_epub = sorted([
                        name for name in epub_zip.namelist()
                        if name.lower().endswith(('.html', '.xhtml', '.htm'))
                        and not name.startswith(('__MACOSX', 'META-INF/'))  # Исключаем служебные папки
                    ])
                    
                    if not html_files_in_epub:
                        logger.warning(f"В EPUB файле не найдено HTML/XHTML файлов")
                        return 5
                    
                    logger.info(f"Всего HTML файлов в EPUB: {len(html_files_in_epub)}")
                    for html_file in html_files_in_epub:
                        logger.debug(f"HTML файл: {html_file}")
                    
                    # Фильтруем главы, исключая служебные файлы (как в TransGemini)
                    content_files = []
                    for file_path_in_epub in html_files_in_epub:
                        filename_lower = Path(file_path_in_epub).name.lower()
                        filename_base = Path(file_path_in_epub).stem.split('.')[0].lower()
                        
                        # Список служебных файлов (как в TransGemini)
                        skip_indicators = [
                            'toc', 'nav', 'ncx', 'cover', 'title', 'index', 'copyright', 'about', 'meta', 'opf',
                            'masthead', 'colophon', 'imprint', 'acknowledgments', 'dedication',
                            'glossary', 'bibliography', 'notes', 'annotations', 'epigraph', 'halftitle',
                            'frontmatter', 'backmatter', 'preface', 'introduction', 'appendix', 'biography',
                            'isbn', 'legal', 'notice', 'otherbooks', 'prelims', 'team', 'promo', 'bonus'
                        ]
                        
                        # Список индикаторов контента (главы)
                        content_indicators = [
                            'chapter', 'part', 'section', 'content', 'text', 'page', 'body', 'main', 'article',
                            'chp', 'chap', 'prt', 'sec', 'glava', 'prologue', 'epilogue'
                        ]
                        
                        # Проверяем, является ли файл служебным
                        is_skip_file = any(skip_word in filename_base for skip_word in skip_indicators)
                        is_content_file = any(content_word in filename_base for content_word in content_indicators)
                        
                        # Также проверяем файлы с суффиксом _translated
                        is_translated = filename_base.endswith('_translated')
                        
                        # Дополнительная проверка: исключаем очень короткие HTML файлы (менее 1KB)
                        try:
                            file_info = epub_zip.getinfo(file_path_in_epub)
                            file_size = file_info.file_size
                        except:
                            file_size = 0
                        
                        # Если файл не служебный и не переведенный, и имеет достаточный размер
                        if not is_skip_file and not is_translated and file_size > 1000:
                            content_files.append(file_path_in_epub)
                            logger.debug(f"Найдена глава: {file_path_in_epub} (размер: {file_size} байт)")
                        else:
                            logger.debug(f"Пропущен файл: {file_path_in_epub} (служебный: {is_skip_file}, переведенный: {is_translated}, размер: {file_size})")
                    
                    # Если после фильтрации осталось мало файлов, используем менее строгую фильтрацию
                    if len(content_files) < 3:
                        logger.info("Мало глав после строгой фильтрации, применяем более мягкие критерии")
                        content_files = []
                        for file_path_in_epub in html_files_in_epub:
                            filename_lower = Path(file_path_in_epub).name.lower()
                            filename_base = Path(file_path_in_epub).stem.split('.')[0].lower()
                            
                            # Более короткий список служебных файлов
                            skip_indicators_short = ['toc', 'nav', 'cover', 'title', 'copyright', 'meta', 'opf']
                            is_skip_file = any(skip_word in filename_base for skip_word in skip_indicators_short)
                            is_translated = filename_base.endswith('_translated')
                            
                            try:
                                file_info = epub_zip.getinfo(file_path_in_epub)
                                file_size = file_info.file_size
                            except:
                                file_size = 0
                            
                            if not is_skip_file and not is_translated and file_size > 500:
                                content_files.append(file_path_in_epub)
                    
                    chapter_count = len(content_files)
                    logger.info(f"EPUB анализ: найдено {chapter_count} глав из {len(html_files_in_epub)} HTML файлов")
                    
                    return max(1, chapter_count)
                    
            except Exception as e:
                logger.error(f"Ошибка анализа EPUB: {e}")
                # Fallback: пробуем прочитать как обычный файл
                try:
                    # Некоторые EPUB читаются как текст
                    encodings = ['utf-8', 'cp1251', 'latin-1']
                    for encoding in encodings:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                                patterns = [
                                    r'(?:chapter|глава|часть)\s*\d+',
                                    r'<h[1-6][^>]*>.*?</h[1-6]>',
                                ]
                                total_matches = 0
                                for pattern in patterns:
                                    matches = re.findall(pattern, content, re.IGNORECASE)
                                    total_matches = max(total_matches, len(matches))
                                if total_matches > 0:
                                    return total_matches
                            break
                        except UnicodeDecodeError:
                            continue
                except:
                    pass
                
                return 20  # Разумное значение по умолчанию для книг
        
        return 5  # Значение по умолчанию
        
    except Exception as e:
        logger.error(f"Ошибка при подсчете глав: {e}")
        return 5

async def show_chapter_selection(update: Update, state: UserState):
    """Показывает опции выбора глав"""
    keyboard = [
        [InlineKeyboardButton("📖 Все главы", callback_data="chapters_all")],
        [InlineKeyboardButton("🔢 Выбрать диапазон", callback_data="chapters_range")],
        [InlineKeyboardButton("📋 Показать все главы", callback_data="show_all_chapters")],
        [InlineKeyboardButton("▶️ Перейти к настройкам", callback_data="skip_chapters")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    chapter_info = ""
    if state.total_chapters > 1:
        chapter_info = f"📊 В файле обнаружено примерно **{state.total_chapters} глав/разделов**\n\n"
    
    await update.message.reply_text(
        f"📚 **Выбор глав для перевода**\n\n"
        f"{chapter_info}"
        f"📁 Файл: `{state.file_name}`\n"
        f"📄 Формат: `{state.output_format.upper()}`\n\n"
        f"Выберите опцию:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_all_chapters(update: Update, state: UserState):
    """Показывает все найденные главы в файле"""
    try:
        # Используем сохраненную информацию или получаем новую
        chapters_info = getattr(state, 'chapters_info', None)
        if not chapters_info:
            chapters_info = await get_transgemini_chapters_info(state.file_path, state.file_format)
            state.chapters_info = chapters_info
        
        if chapters_info['total_all'] == 0:
            try:
                await update.edit_message_text(
                    "❌ Не удалось проанализировать главы в файле.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_chapter_selection")]])
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise
            return
        
        # Формируем текст со списком глав
        message_text = f"📋 **Анализ глав (TransGemini логика)**\n\n"
        message_text += f"📁 Файл: `{state.file_name}`\n\n"
        message_text += f"📊 **Статистика:**\n"
        message_text += f"• Всего HTML файлов: `{chapters_info['total_all']}`\n"
        message_text += f"• Главы для перевода: `{chapters_info['total_content']}`\n"
        message_text += f"• Служебные файлы: `{len(chapters_info['skip_files'])}`\n"
        if chapters_info['nav_file']:
            message_text += f"• NAV файл (оглавление): `{Path(chapters_info['nav_file']).name}`\n"
        message_text += "\n"
        
        # Показываем главы содержания (те, что будут переведены)
        if chapters_info['content_files']:
            message_text += f"✅ **Главы для перевода ({len(chapters_info['content_files'])}):**\n"
            for i, file_data in enumerate(chapters_info['content_files'][:20], 1):  # Показываем первые 20
                size_kb = file_data['size'] // 1024 if file_data['size'] > 0 else 0
                category_emoji = {"content": "📖", "text": "📄"}.get(file_data['category'], "📄")
                message_text += f"{i}. {category_emoji} `{file_data['name']}` ({size_kb}KB)\n"
            
            if len(chapters_info['content_files']) > 20:
                message_text += f"... и еще {len(chapters_info['content_files']) - 20} глав\n"
        
        # Показываем служебные файлы (первые несколько)
        if chapters_info['skip_files']:
            message_text += f"\n🚫 **Служебные файлы ({len(chapters_info['skip_files'])}):**\n"
            for file_data in chapters_info['skip_files'][:8]:  # Показываем первые 8
                size_kb = file_data['size'] // 1024 if file_data['size'] > 0 else 0
                category_emoji = {"nav": "🧭", "skip": "⏭️"}.get(file_data['category'], "❓")
                reason = {"nav": "навигация", "skip": "служебный"}.get(file_data['category'], "неизвестно")
                message_text += f"• {category_emoji} `{file_data['name']}` ({size_kb}KB) - {reason}\n"
            
            if len(chapters_info['skip_files']) > 8:
                message_text += f"... и еще {len(chapters_info['skip_files']) - 8} файлов\n"
        
        # Обновляем точное количество глав в состоянии только для EPUB файлов
        # Для других форматов сохраняем первоначальное значение
        if state.file_format == 'epub' and chapters_info['total_content'] > 0:
            state.total_chapters = chapters_info['total_content']
        # Для не-EPUB файлов или если анализ EPUB не дал результатов, сохраняем исходное значение
        
        keyboard = [
            [InlineKeyboardButton(f"📖 Перевести все {chapters_info['total_content']} глав", callback_data="chapters_all")],
            [InlineKeyboardButton("🔢 Выбрать диапазон", callback_data="chapters_range")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_chapter_selection")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await update.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        
    except Exception as e:
        logger.error(f"Ошибка показа глав: {e}")
        try:
            await update.edit_message_text(
                f"❌ Ошибка при анализе глав: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_chapter_selection")]])
            )
        except BadRequest as e2:
            if "Message is not modified" not in str(e2):
                raise

async def handle_chapter_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора глав"""
    query = update.callback_query
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    if state.step != "chapter_selection":
        await query.answer("Неверный шаг процесса")
        return
    
    callback_data = query.data
    
    if callback_data == "chapters_all":
        state.start_chapter = 1
        state.chapter_count = 0  # 0 = все главы
        state.step = "translating"
        
        await query.answer("Выбраны все главы")
        await show_translation_options(query, state)
        
    elif callback_data == "chapters_range":
        await query.answer()
        await show_chapter_range_input(query, state)
        
    elif callback_data == "show_all_chapters":
        await query.answer()
        await show_all_chapters(query, state)
        
    elif callback_data == "skip_chapters":
        state.step = "translating"
        await query.answer()
        await show_translation_options(query, state)
        
    elif callback_data == "back_to_chapter_selection":
        await query.answer()
        await show_chapter_selection(query, state)

async def show_chapter_range_input(update: Update, state: UserState):
    """Показывает интерфейс для ввода диапазона глав"""
    keyboard = []
    
    # Быстрые варианты выбора
    if state.total_chapters >= 5:
        keyboard.extend([
            [
                InlineKeyboardButton("1-5 глав", callback_data="range_1_5"),
                InlineKeyboardButton("6-10 глав", callback_data="range_6_10")
            ],
            [
                InlineKeyboardButton("11-15 глав", callback_data="range_11_15"),
                InlineKeyboardButton("16-20 глав", callback_data="range_16_20")
            ]
        ])
    
    # Кнопки для ручного ввода
    keyboard.extend([
        [InlineKeyboardButton("✏️ Ввести вручную", callback_data="range_manual")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_chapters")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.edit_message_text(
        f"🔢 **Выбор диапазона глав**\n\n"
        f"📊 Всего глав в файле: `{state.total_chapters}`\n\n"
        f"Выберите диапазон или введите вручную:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_chapter_range_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора диапазона глав"""
    query = update.callback_query
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    callback_data = query.data
    
    if callback_data.startswith("range_"):
        if callback_data == "range_manual":
            state.step = "chapter_input"
            await query.answer()
            await query.edit_message_text(
                f"✏️ **Ручной ввод диапазона**\n\n"
                f"📊 Всего глав: `{state.total_chapters}`\n\n"
                f"Введите диапазон в одном из форматов:\n"
                f"• `5` - только 5-я глава\n"
                f"• `3-8` - главы с 3 по 8\n"
                f"• `10+5` - начиная с 10-й, всего 5 глав\n\n"
                f"Отправьте ваш выбор:",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        elif callback_data == "back_to_chapters":
            await query.answer()
            await show_chapter_selection(query, state)
            return
        
        # Обработка быстрых вариантов
        range_parts = callback_data.replace("range_", "").split("_")
        if len(range_parts) == 2:
            start_ch = int(range_parts[0])
            end_ch = int(range_parts[1])
            
            state.start_chapter = start_ch
            state.chapter_count = end_ch - start_ch + 1
            state.step = "translating"
            
            await query.answer(f"Выбраны главы {start_ch}-{end_ch}")
            await show_translation_options(query, state)

async def handle_chapter_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ручного ввода диапазона глав"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state.step != "chapter_input":
        return
    
    input_text = update.message.text.strip()
    
    try:
        # Парсим различные форматы ввода
        if "-" in input_text:
            # Формат "3-8"
            parts = input_text.split("-")
            start_ch = int(parts[0])
            end_ch = int(parts[1])
            
            if start_ch < 1 or end_ch > state.total_chapters or start_ch > end_ch:
                raise ValueError("Неверный диапазон")
                
            state.start_chapter = start_ch
            state.chapter_count = end_ch - start_ch + 1
            
        elif "+" in input_text:
            # Формат "10+5"
            parts = input_text.split("+")
            start_ch = int(parts[0])
            count = int(parts[1])
            
            if start_ch < 1 or start_ch > state.total_chapters or count < 1:
                raise ValueError("Неверный диапазон")
                
            state.start_chapter = start_ch
            state.chapter_count = min(count, state.total_chapters - start_ch + 1)
            
        else:
            # Формат "5" - одна глава
            chapter_num = int(input_text)
            
            if chapter_num < 1 or chapter_num > state.total_chapters:
                raise ValueError("Неверный номер главы")
                
            state.start_chapter = chapter_num
            state.chapter_count = 1
        
        state.step = "translating"
        
        # Показываем подтверждение
        end_chapter = min(state.start_chapter + state.chapter_count - 1, state.total_chapters)
        range_text = f"глава {state.start_chapter}" if state.chapter_count == 1 else f"главы {state.start_chapter}-{end_chapter}"
        
        await update.message.reply_text(
            f"✅ Выбран диапазон: **{range_text}**\n\n"
            f"Переходим к настройкам перевода...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await show_translation_options(update, state)
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            f"❌ Неверный формат ввода!\n\n"
            f"Используйте один из форматов:\n"
            f"• `5` - только 5-я глава\n"
            f"• `3-8` - главы с 3 по 8\n"
            f"• `10+5` - начиная с 10-й, всего 5 глав\n\n"
            f"Максимум глав в файле: `{state.total_chapters}`\n"
            f"Попробуйте еще раз:",
            parse_mode=ParseMode.MARKDOWN
        )

async def show_translation_options(update: Update, state: UserState):
    """Показывает дополнительные опции перевода"""
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_русский")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_английский")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_немецкий")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_французский")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_испанский")],
        [InlineKeyboardButton("🤖 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton("▶️ Начать перевод", callback_data="start_translation")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Информация о выбранных главах
    chapter_info = ""
    if hasattr(state, 'total_chapters') and state.total_chapters > 0:
        if state.chapter_count == 0:  # Все главы
            chapter_info = f"📖 Главы: все ({state.total_chapters})\n"
        elif state.chapter_count == 1:
            chapter_info = f"📖 Глава: {state.start_chapter}\n"
        else:
            end_chapter = min(state.start_chapter + state.chapter_count - 1, state.total_chapters)
            chapter_info = f"� Главы: {state.start_chapter}-{end_chapter}\n"
    
    try:
        # Проверяем тип объекта update и используем соответствующий метод
        if hasattr(update, 'edit_message_text'):
            # Это CallbackQuery
            await update.edit_message_text(
                f"🔧 **Настройки перевода**\n\n"
                f"📁 Файл: `{state.file_name}`\n"
                f"📄 Формат: `{state.output_format.upper()}`\n"
                f"{chapter_info}"
                f"🌍 Язык: `{state.target_language}`\n"
                f"🤖 Модель: `{state.model}`\n\n"
                f"Выберите язык перевода или начните перевод:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Это Update, отправляем новое сообщение
            await update.message.reply_text(
                f"🔧 **Настройки перевода**\n\n"
                f"📁 Файл: `{state.file_name}`\n"
                f"📄 Формат: `{state.output_format.upper()}`\n"
                f"{chapter_info}"
                f"🌍 Язык: `{state.target_language}`\n"
                f"🤖 Модель: `{state.model}`\n\n"
                f"Выберите язык перевода или начните перевод:",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        # Если не удалось обновить сообщение, отправляем новое
        if "Message is not modified" in str(e):
            logger.warning("Сообщение не изменилось, пропускаем обновление")
        else:
            logger.error(f"Ошибка обновления сообщения: {e}")
            # Определяем где отправить сообщение
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    f"🔧 **Настройки перевода**\n\n"
                    f"📁 Файл: `{state.file_name}`\n"
                    f"📄 Формат: `{state.output_format.upper()}`\n"
                    f"{chapter_info}"
                    f"🌍 Язык: `{state.target_language}`\n"
                    f"🤖 Модель: `{state.model}`\n\n"
                    f"Выберите язык перевода или начните перевод:",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif hasattr(update, 'from_user'):
                # Для CallbackQuery используем bot.send_message
                await update.get_bot().send_message(
                    chat_id=update.message.chat_id,
                    text=f"🔧 **Настройки перевода**\n\n"
                         f"📁 Файл: `{state.file_name}`\n"
                         f"📄 Формат: `{state.output_format.upper()}`\n"
                         f"{chapter_info}"
                         f"🌍 Язык: `{state.target_language}`\n"
                         f"🤖 Модель: `{state.model}`\n\n"
                         f"Выберите язык перевода или начните перевод:",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )

async def show_model_selection(update: Update, state: UserState):
    """Показывает выбор модели Gemini"""
    # Получаем доступные модели из TransGemini.py
    keyboard = []
    models_per_row = 1  # По одной модели в ряду для лучшей читаемости
    
    model_buttons = []
    for model_name in MODELS.keys():
        # Создаем короткие названия для кнопок
        short_name = model_name.replace("Gemini ", "").replace("gemma", "Gemma")
        if len(short_name) > 25:  # Обрезаем слишком длинные названия
            short_name = short_name[:22] + "..."
        
        model_buttons.append(InlineKeyboardButton(
            f"🤖 {short_name}", 
            callback_data=f"model_{model_name}"
        ))
    
    # Группируем кнопки по рядам
    for i in range(0, len(model_buttons), models_per_row):
        keyboard.append(model_buttons[i:i + models_per_row])
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton("⬅️ Назад к настройкам", callback_data="back_to_translation_options")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.edit_message_text(
        f"🤖 **Выбор модели Gemini**\n\n"
        f"📁 Файл: `{state.file_name}`\n"
        f"🎯 Текущая модель: `{state.model}`\n\n"
        f"**Доступные модели:**\n"
        f"• **Gemini 2.5** - Новейшие модели (рекомендуется)\n"
        f"• **Gemini 2.0** - Быстрые и эффективные\n"
        f"• **Gemini 1.5** - Проверенные временем\n\n"
        f"Выберите модель для перевода:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_translation_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик опций перевода"""
    query = update.callback_query
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    callback_data = query.data
    
    if callback_data.startswith("lang_"):
        # Изменение языка
        language = callback_data.replace("lang_", "")
        state.target_language = language
        
        await query.answer(f"Выбран язык: {language}")
        await show_translation_options(query, state)
        
    elif callback_data == "select_model":
        # Показать выбор модели
        await query.answer()
        await show_model_selection(query, state)
        
    elif callback_data.startswith("model_"):
        # Изменение модели
        model_name = callback_data.replace("model_", "")
        if model_name in MODELS:
            state.model = model_name
            await query.answer(f"Выбрана модель: {model_name}")
            await show_translation_options(query, state)
        else:
            await query.answer("Неизвестная модель")
            
    elif callback_data == "back_to_translation_options":
        # Вернуться к настройкам перевода
        await query.answer()
        await show_translation_options(query, state)
        
    elif callback_data == "start_translation":
        await query.answer()
        await start_translation(query, state)

async def start_translation(update: Update, state: UserState):
    import time
    start_time = time.time()
    logger.info(f"⏳ Перевод запущен в {time.strftime('%H:%M:%S', time.localtime(start_time))}")
    """Запускает процесс перевода используя TransGemini.py"""
    # Отправляем сообщение о начале перевода
    await update.edit_message_text(
        f"🔄 **Начинаю перевод...**\n\n"
        f"📁 Файл: `{state.file_name}`\n"
        f"🌍 Язык: `{state.target_language}`\n"
        f"📄 Формат: `{state.output_format.upper()}`\n\n"
        f"⏳ Это может занять несколько минут...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Создаем выходной файл
        input_path = Path(state.file_path)
        output_dir = input_path.parent
        output_name = f"{input_path.stem}_translated.{state.output_format}"
        output_path = output_dir / output_name
        
        logger.info(f"Начинаю перевод файла: {state.file_path}")
        logger.info(f"Выходной файл: {output_path}")
        logger.info(f"Формат входной: {state.file_format}, выходной: {state.output_format}")
        logger.info(f"Язык: {state.target_language}, Модель: {state.model}")
        logger.info(f"Главы: начиная с {getattr(state, 'start_chapter', 1)}, количество: {getattr(state, 'chapter_count', 0)}")
        
        # Запускаем перевод с использованием TransGemini.py
        success, error_message = await translate_file_with_transgemini(
            input_file=state.file_path,
            output_file=str(output_path),
            input_format=state.file_format,
            output_format=state.output_format,
            target_language=state.target_language,
            api_key=state.api_key,
            model_name=state.model,
            progress_callback=None,  # Отключаем прогресс-бар
            start_chapter=getattr(state, 'start_chapter', 1),
            chapter_count=getattr(state, 'chapter_count', 0),
            chapters_info=getattr(state, 'chapters_info', None)  # Передаем информацию о главах
        )
        
        end_time = time.time()
        duration = end_time - start_time
        if success and output_path.exists():
            logger.info(f"✅ Перевод успешно завершен, файл создан: {output_path}")
            logger.info(f"⏱️ Время перевода: {duration:.1f} сек. (завершено в {time.strftime('%H:%M:%S', time.localtime(end_time))})")
            await send_translated_file(update, state, str(output_path))
        else:
            # Добавляем детальную диагностику
            logger.error(f"❌ Проблема с результатом перевода:")
            logger.error(f"   success: {success}")
            logger.error(f"   output_path: {output_path}")
            logger.error(f"   output_path.exists(): {output_path.exists() if output_path else 'N/A'}")
            logger.error(f"   output_path.parent: {output_path.parent if output_path else 'N/A'}")
            logger.error(f"   error_message: {error_message}")
            
            # Проверяем, что находится в выходной папке
            if output_path and output_path.parent.exists():
                try:
                    files_in_output_dir = list(output_path.parent.iterdir())
                    logger.info(f"📁 Файлы в выходной директории {output_path.parent}:")
                    for file in files_in_output_dir:
                        logger.info(f"   - {file.name} (размер: {file.stat().st_size if file.is_file() else 'dir'})")
                except Exception as e:
                    logger.error(f"Ошибка при просмотре выходной директории: {e}")
            
            # Проверяем возможные альтернативные местоположения файла
            if output_path:
                possible_locations = [
                    output_path.parent / f"{output_path.stem}_translated{output_path.suffix}",
                    output_path.parent / f"{output_path.stem}.txt",
                    output_path.parent / f"{Path(state.file_name).stem}_translated.txt",
                ]
                
                logger.info("🔍 Проверяем возможные местоположения переведенного файла:")
                for possible_path in possible_locations:
                    exists = possible_path.exists()
                    logger.info(f"   {possible_path}: {'✅ НАЙДЕН' if exists else '❌ НЕТ'}")
                    if exists and possible_path.is_file():
                        logger.info(f"      Размер: {possible_path.stat().st_size} байт")
                        # Если нашли файл, попробуем его отправить
                        try:
                            await send_translated_file(update, state, str(possible_path))
                            return  # Успешно отправили файл
                        except Exception as send_error:
                            logger.error(f"Ошибка отправки найденного файла {possible_path}: {send_error}")
            
            error_text = "❌ **Ошибка при переводе**\n\n"
            if error_message and "успешно завершен" not in error_message.lower():
                error_text += f"Детали ошибки: `{error_message}`\n\n"
            else:
                error_text += "Перевод был завершен, но переведенный файл не найден.\n\n"
            
            error_text += "Возможные причины:\n"
            error_text += "• Worker создал файл в неожиданном месте\n"
            error_text += "• Проблема с правами доступа к файлу\n"
            error_text += "• Неверный API ключ Google Gemini\n"
            error_text += "• Превышен лимит запросов API\n"
            error_text += "• Проблемы с интернет-соединением\n"
            error_text += "• Файл слишком большой для обработки\n\n"
            error_text += "Попробуйте еще раз через несколько минут."
            
            await update.edit_message_text(
                error_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка при переводе: {e}", exc_info=True)
        await update.edit_message_text(
            f"❌ **Критическая ошибка при переводе**\n\n"
            f"Произошла неожиданная ошибка: `{str(e)}`\n\n"
            f"Обратитесь к разработчику или попробуйте еще раз позже.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Очищаем состояние пользователя
    user_id = update.from_user.id if hasattr(update, 'from_user') else update.effective_user.id
    reset_user_state(user_id)

async def translate_file_with_transgemini(input_file: str, output_file: str, 
                                        input_format: str, output_format: str,
                                        target_language: str, api_key: str, 
                                        model_name: str, progress_callback=None,
                                        start_chapter: int = 1, chapter_count: int = 0,
                                        chapters_info: dict = None) -> tuple[bool, str]:
    """
    Асинхронная обертка для TransGemini.py Worker класса
    Использует точно такую же логику как TransGemini для сохранения структуры файлов
    """
    import datetime
    
    logger.info(f"🚀 translate_file_with_transgemini: Начинаем перевод")
    logger.info(f"📁 Входной файл: {input_file}")
    logger.info(f"📄 Формат: {input_format} -> {output_format}")
    logger.info(f"🤖 Модель: {model_name}")
    
    start_time = datetime.datetime.now()
    
    def run_worker():
        """Запускает Worker в синхронном режиме"""
        try:
            # Импортируем необходимые компоненты из TransGemini
            from TransGemini import Worker, MODELS
            
            # Получаем конфигурацию модели
            model_config = MODELS.get(model_name, MODELS.get("Gemini 2.0 Flash", MODELS[list(MODELS.keys())[0]]))
            logger.info(f"🤖 Используем модель: {model_name} с конфигурацией: {model_config}")
            
            # Определяем prompt на основе целевого языка  
            if target_language.lower() in ['русский', 'russian', 'ru']:
                prompt_template = """Переведи следующий текст на русский язык. Сохрани исходное форматирование, структуру диалогов и разбивку на абзацы. Не добавляй никаких комментариев или пояснений к переводу.

{text}"""
            else:
                prompt_template = f"""Translate the following text to {target_language}. Preserve the original formatting, dialogue structure, and paragraph breaks. Do not add any comments or explanations to the translation.

{{text}}"""
            
            # Определяем выходную директорию
            output_dir = os.path.dirname(output_file)
            if not output_dir:
                output_dir = os.path.dirname(input_file)
            
            # Подготавливаем данные о файлах для обработки в формате TransGemini
            # TransGemini ожидает список кортежей: (input_type, filepath, epub_html_path_or_none)
            input_type = input_format.lower()
            if input_type == 'epub' and output_format.lower() != 'epub':
                # EPUB -> другой формат: TransGemini обработает все HTML файлы внутри
                files_to_process_data = [(input_type, input_file, None)]
            else:
                # Остальные случаи: прямая обработка файла
                files_to_process_data = [(input_type, input_file, None)]
            
            logger.info(f"📝 Подготовленные файлы для обработки: {files_to_process_data}")
            
            # Создаем Worker с теми же параметрами что и в TransGemini GUI
            worker = Worker(
                api_key=api_key,
                out_folder=output_dir,
                prompt_template=prompt_template,
                files_to_process_data=files_to_process_data,
                model_config=model_config,
                max_concurrent_requests=1,  # Последовательная обработка для стабильности Telegram бота
                output_format=output_format,  # Используем worker_output_format
                chunking_enabled_gui=True,
                chunk_limit=900000,  # Максимальный размер чанка
                chunk_window=500,
                temperature=0.1,
                chunk_delay_seconds=0.5,  # Уменьшенная задержка между чанками для быстрого перевода
                proxy_string=None
            )
            
            logger.info("Worker создан, запускаем обработку...")
            
            # Добавляем обработчик для захвата логов Worker'а
            worker_logs = []
            worker_errors = []
            
            def capture_worker_log(message):
                worker_logs.append(message)
                logger.info(f"Worker Log: {message}")
                # Логируем прогресс по API активности
                if any(word in message for word in ['[API START]', '[API CALL]', '[API RESPONSE]', 'Обработка', 'Начинаю обработку', 'Получен ответ', 'Отправляю запрос']):
                    logger.info(f"[PROGRESS] {message}")
                if any(keyword in message.lower() for keyword in ['error', 'failed', 'exception', 'ошибка']):
                    worker_errors.append(message)
            
            def extract_progress_info(log_message: str) -> str:
                """Извлекает информацию о прогрессе из лог-сообщения Worker'а"""
                try:
                    # Паттерны для различных этапов обработки
                    patterns = [
                        # API активность - новые паттерны
                        (r'\[API START\]\s*([^:]+):\s*Начинаем\s+API\s+запрос', 
                         lambda m: f"🔄 **{m.group(1)}**\n🚀 Начинаем API запрос..."),
                        
                        (r'\[API CALL\]\s*([^:]+):\s*Отправляем\s+запрос\s+к\s+API', 
                         lambda m: f"📡 **{m.group(1)}**\n🤖 Отправляем в Gemini API..."),
                        
                        (r'\[API RESPONSE\]\s*([^:]+):\s*Получен\s+ответ\s+от\s+API', 
                         lambda m: f"✅ **{m.group(1)}**\n📝 Получен ответ от API!"),
                        
                        # Обработка EPUB файлов
                        (r'\[INFO\]\s*([^:]+):\s*Обработка\s+(\d+)/(\d+)\s+чанков', 
                         lambda m: f"📄 **{m.group(1)}**\n⏳ Обрабатываю чанк {m.group(2)} из {m.group(3)}"),
                        
                        # Начало обработки файла
                        (r'\[INFO\]\s*([^:]+):\s*Начинаю\s+обработку', 
                         lambda m: f"🚀 **Начинаю обработку**\n📄 {m.group(1)}"),
                        
                        # Обработка HTML файлов из EPUB
                        (r'\[INFO\]\s*([^:]+):\s*Контент\s+\(([^)]+)\).*разделяем', 
                         lambda m: f"📖 **{m.group(1)}**\n🔄 Разделяю контент ({m.group(2)})"),
                        
                        # Отправка в API (старый формат)
                        (r'\[INFO\]\s*([^:]+):\s*Отправляю\s+запрос\s+в\s+API', 
                         lambda m: f"🤖 **{m.group(1)}**\n📡 Отправляю в Gemini API..."),
                        
                        # Успешный ответ API (старый формат)
                        (r'\[INFO\]\s*([^:]+):\s*Получен\s+ответ.*символов', 
                         lambda m: f"✅ **{m.group(1)}**\n📝 Получен перевод от Gemini"),
                        
                        # Задержка между запросами
                        (r'\[INFO\]\s*([^:]+):\s*Применяем\s+задержку\s+([\d.]+)\s+сек', 
                         lambda m: f"⏰ **{m.group(1)}**\n⏳ Ожидание {m.group(2)} сек..."),
                        
                        # Завершение обработки файла
                        (r'\[INFO\]\s*([^:]+):\s*Обработка\s+завершена', 
                         lambda m: f"✅ **{m.group(1)}**\n🎉 Обработка завершена!"),
                        
                        # Прогресс чанков
                        (r'Chunk\s+(\d+)/(\d+)', 
                         lambda m: f"📝 **Обработка чанка**\n🔢 {m.group(1)} из {m.group(2)}"),
                    ]
                    
                    for pattern, formatter in patterns:
                        match = re.search(pattern, log_message, re.IGNORECASE)
                        if match:
                            try:
                                return formatter(match)
                            except Exception as e:
                                logger.error(f"Ошибка форматирования прогресса: {e}")
                                return f"📋 {log_message}"
                    
                    return None
                    
                except Exception as e:
                    logger.error(f"Ошибка извлечения прогресса: {e}")
                    return None
            
            # Подключаем обработчик логов
            worker.log_message.connect(capture_worker_log)
            
            # Подключаем callback для прогресса если передан
            if progress_callback:
                def on_log_message(message):
                    progress_info = extract_progress_info(message)
                    if progress_info:
                        try:
                            # Запускаем callback асинхронно
                            asyncio.run_coroutine_threadsafe(
                                progress_callback(progress_info), 
                                asyncio.get_event_loop()
                            )
                        except Exception as e:
                            logger.error(f"Ошибка вызова progress_callback: {e}")
                
                worker.log_message.connect(on_log_message)
            
            # Запускаем обработку
            logger.info("🏃 Запускаем Worker.run()...")
            worker.run()
            
            # Проверяем результаты
            if worker_errors:
                error_msg = f"Обнаружены ошибки во время перевода: {'; '.join(worker_errors[:3])}"
                logger.error(f"❌ {error_msg}")
                return False, error_msg
            
            # Ищем созданный файл в выходной директории
            # Worker создает файлы с суффиксом _translated
            input_name = Path(input_file).stem
            expected_output_name = f"{input_name}_translated.{output_format}"
            expected_output_path = os.path.join(output_dir, expected_output_name)
            
            if os.path.exists(expected_output_path):
                # Если нужно переименовать файл
                if expected_output_path != output_file:
                    try:
                        # Создаем директорию для целевого файла
                        os.makedirs(os.path.dirname(output_file), exist_ok=True)
                        # Перемещаем файл
                        import shutil
                        shutil.move(expected_output_path, output_file)
                        logger.info(f"✅ Файл перемещен с {expected_output_path} на {output_file}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось переместить файл: {e}, используем оригинальный путь")
                        output_file = expected_output_path
                
                file_size = os.path.getsize(output_file)
                end_time = datetime.datetime.now()
                duration = end_time - start_time
                
                logger.info(f"✅ Перевод завершен успешно!")
                logger.info(f"📁 Выходной файл: {output_file}")
                logger.info(f"📊 Размер файла: {file_size} байт")
                logger.info(f"⏱️ Время выполнения: {duration}")
                
                return True, f"Перевод завершен. Файл сохранен: {os.path.basename(output_file)} ({file_size} байт)"
            else:
                # Ищем любые созданные файлы с _translated
                created_files = []
                for file in os.listdir(output_dir):
                    if '_translated' in file and file.endswith(f'.{output_format}'):
                        created_files.append(os.path.join(output_dir, file))
                
                if created_files:
                    # Берем первый найденный файл
                    actual_output = created_files[0]
                    logger.info(f"✅ Найден созданный файл: {actual_output}")
                    
                    # Перемещаем к нужному имени
                    try:
                        import shutil
                        shutil.move(actual_output, output_file)
                        logger.info(f"✅ Файл перемещен на {output_file}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось переместить файл: {e}")
                        output_file = actual_output
                    
                    file_size = os.path.getsize(output_file)
                    return True, f"Перевод завершен. Файл сохранен: {os.path.basename(output_file)} ({file_size} байт)"
                else:
                    error_msg = f"Файл не был создан. Ожидался: {expected_output_path}"
                    logger.error(f"❌ {error_msg}")
                    return False, error_msg
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске Worker: {e}", exc_info=True)
            return False, f"Ошибка обработки: {str(e)}"
    
    # Запускаем Worker в отдельном потоке
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_worker)
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения: {e}", exc_info=True)
        return False, f"Ошибка выполнения: {str(e)}"


def main():
                                try:
                                    with epub_zip.open(html_file) as f:
                                        html_content = f.read().decode('utf-8', errors='ignore')
                                        
                                        # Убираем HTML теги и извлекаем текст
                                        # Убираем CSS и скрипты
                                        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                                        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                                        
                                        # Извлекаем текст из HTML
                                        text_content = re.sub(r'<[^>]+>', '', html_content)
                                        text_content = re.sub(r'\s+', ' ', text_content).strip()
                                        
                                        if text_content and len(text_content) > 100:  # Игнорируем слишком короткие файлы
                                            chapters_content.append(text_content)
                                except:
                                    continue
                    
                    if chapters_content:
                        content = '\n\n--- ГЛАВА ---\n\n'.join(chapters_content)
                        logger.info(f"EPUB обработан: извлечено {len(chapters_content)} глав, общий размер: {len(content)} символов")
                    else:
                        # Fallback: читаем как обычный файл
                        logger.warning("Не удалось извлечь главы из EPUB, используем fallback")
                        with open(file_path, 'rb') as f:
                            raw_content = f.read()
                            content = raw_content.decode('utf-8', errors='ignore')
                            
                except Exception as e:
                    logger.error(f"Ошибка чтения EPUB: {e}")
                    # Fallback: читаем как обычный файл
                    with open(file_path, 'rb') as f:
                        raw_content = f.read()
                        content = raw_content.decode('utf-8', errors='ignore')
                        
            elif file_format.lower() in ['html', 'xml']:
                encodings = ['utf-8', 'cp1251', 'latin-1']
                for encoding in encodings:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    with open(file_path, 'rb') as f:
                        raw_content = f.read()
                        content = raw_content.decode('utf-8', errors='ignore')
            else:
                # Для других форматов читаем как текст с обработкой ошибок
                encodings = ['utf-8', 'cp1251', 'latin-1']
                for encoding in encodings:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    with open(file_path, 'rb') as f:
                        raw_content = f.read()
                        content = raw_content.decode('utf-8', errors='ignore')
            
            # Если нужны все главы (count = 0), возвращаем весь контент
            if count == 0:
                return content
            
            # Ищем главы в зависимости от формата
            if file_format.lower() == 'txt':
                chapter_pattern = r'(?:^|\n)(?:ГЛАВА|Глава|Chapter|CHAPTER)\s*(?:\d+|[IVXLCDM]+|[А-Я]{1,3})\b[^\n]*(?:\n|$)'
            elif file_format.lower() == 'docx':
                chapter_pattern = r'(?:^|\n)(?:ГЛАВА|Глава|Chapter|CHAPTER)\s*(?:\d+|[IVXLCDM]+|[А-Я]{1,3})\b[^\n]*(?:\n|$)'
            elif file_format.lower() == 'epub':
                # Для EPUB используем разделители, которые мы добавили при чтении
                chapter_pattern = r'\n\n--- ГЛАВА ---\n\n'
            elif file_format.lower() == 'html':
                chapter_pattern = r'<h[1-6][^>]*>(?:ГЛАВА|Глава|Chapter|CHAPTER)\s*(?:\d+|[IVXLCDM]+|[А-Я]{1,3})\b[^<]*</h[1-6]>'
            else:
                chapter_pattern = r'(?:^|\n)(?:ГЛАВА|Глава|Chapter|CHAPTER)\s*(?:\d+|[IVXLCDM]+|[А-Я]{1,3})\b[^\n]*(?:\n|$)'
            
            chapters = re.split(chapter_pattern, content, flags=re.MULTILINE | re.IGNORECASE)
            chapter_headers = re.findall(chapter_pattern, content, flags=re.MULTILINE | re.IGNORECASE)
            
            # Специальная обработка для EPUB
            if file_format.lower() == 'epub' and '--- ГЛАВА ---' in content:
                chapters = content.split('\n\n--- ГЛАВА ---\n\n')
                # Создаем заголовки для глав
                chapter_headers = [f"Глава {i+1}" for i in range(len(chapters)-1)]
                
                # Убираем пустые главы
                filtered_chapters = []
                filtered_headers = []
                for i, chapter in enumerate(chapters):
                    if chapter.strip() and len(chapter.strip()) > 100:
                        filtered_chapters.append(chapter)
                        if i > 0:  # Пропускаем первую "главу" (до первого разделителя)
                            filtered_headers.append(f"Глава {len(filtered_chapters)}")
                
                chapters = filtered_chapters
                chapter_headers = filtered_headers
            
            if len(chapters) <= 1:
                # Главы не найдены, возвращаем часть текста
                lines = content.split('\n')
async def update_progress_message(message, progress_text: str):
    """Обновляет сообщение с прогрессом"""
    try:
        await message.edit_text(
            f"🔄 **Перевод в процессе...**\n\n"
            f"{progress_text}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass  # Игнорируем ошибки обновления прогресса (включая timeout)

def update_progress_message_async(message, progress_text: str):
    """Синхронная обертка для обновления прогресса из Worker'а"""
    try:
        # Создаем новый event loop если его нет
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Запускаем обновление сообщения
        if loop.is_running():
            # Если loop уже запущен, создаем task
            asyncio.create_task(update_progress_message(message, progress_text))
        else:
            # Если loop не запущен, запускаем синхронно
            loop.run_until_complete(update_progress_message(message, progress_text))
    except Exception as e:
        # Игнорируем ошибки обновления прогресса
        logger.debug(f"Ошибка обновления прогресса: {e}")
        pass

async def send_translated_file(update: Update, state: UserState, output_path: str):
    """Отправляет переведенный файл пользователю"""
    try:
        # Проверяем размер файла
        file_size = os.path.getsize(output_path)
        if file_size > 50 * 1024 * 1024:  # 50MB лимит Telegram
            await update.edit_message_text(
                "❌ **Файл слишком большой**\n\n"
                "Переведенный файл превышает 50MB и не может быть отправлен через Telegram.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Отправляем файл
        with open(output_path, 'rb') as file:
            # Определяем chat_id в зависимости от типа update
            if hasattr(update, 'effective_chat'):
                chat_id = update.effective_chat.id
            elif hasattr(update, 'message') and update.message:
                chat_id = update.message.chat.id
            else:
                chat_id = update.from_user.id  # Fallback для CallbackQuery
                
            await update.get_bot().send_document(
                chat_id=chat_id,
                document=file,
                filename=Path(output_path).name,
                caption=f"✅ **Перевод завершен!**\n\n"
                       f"📁 Исходный файл: `{state.file_name}`\n"
                       f"🌍 Язык: `{state.target_language}`\n"
                       f"📄 Формат: `{state.output_format.upper()}`\n"
                       f"📊 Размер: `{file_size / 1024:.1f} KB`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Удаляем сообщение о прогрессе
        try:
            if hasattr(update, 'delete_message'):
                await update.delete_message()
            elif hasattr(update, 'message') and update.message:
                await update.message.delete()
        except Exception:
            pass  # Игнорируем ошибки удаления сообщения
        
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        try:
            if hasattr(update, 'edit_message_text'):
                await update.edit_message_text(
                    f"❌ **Ошибка при отправке файла**\n\n"
                    f"Перевод выполнен, но произошла ошибка при отправке: `{str(e)}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    f"❌ **Ошибка при отправке файла**\n\n"
                    f"Перевод выполнен, но произошла ошибка при отправке: `{str(e)}`",
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception:
            pass
    
    finally:
        # Очищаем временные файлы
        try:
            if os.path.exists(state.file_path):
                os.remove(state.file_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
🤖 **Помощь по боту переводчика**

**Команды:**
• /start - Начать работу
• /help - Показать эту справку
• /cancel - Отменить текущий процесс

**Поддерживаемые форматы:**
• TXT - текстовые файлы
• DOCX - документы Word  
• HTML - веб-страницы
• EPUB - электронные книги
• XML - XML документы

**Процесс перевода:**
1. Отправьте файл боту
2. Выберите выходной формат
3. Введите API ключ Google Gemini
4. Выберите язык перевода
5. Получите переведенный файл

**Получение API ключа:**
1. Откройте https://aistudio.google.com/
2. Войдите в Google аккаунт
3. Создайте новый API ключ
4. Отправьте его боту

**Ограничения:**
• Максимальный размер файла: 20MB
• Максимальный размер результата: 50MB
    """
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    user_id = update.effective_user.id
    reset_user_state(user_id)
    
    await update.message.reply_text(
        "❌ **Процесс отменен**\n\n"
        "Используйте /start чтобы начать заново.",
        parse_mode=ParseMode.MARKDOWN
    )

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
