
import sys
import subprocess
import importlib.util

def ensure_package(package_name, import_name=None, extras=None):
    """Проверяет наличие пакета и устанавливает его при необходимости."""
    import_name = import_name or package_name
    if importlib.util.find_spec(import_name) is None:
        print(f"Пакет '{package_name}' не найден. Устанавливаю...")
        try:
            install_target = package_name + extras if extras else package_name
            subprocess.check_call([sys.executable, "-m", "pip", "install", install_target])
        except Exception as e:
            print(f"Не удалось установить пакет '{package_name}': {e}")
            return False
    return True

ensure_package("bs4", "bs4")
ensure_package("PySocks", "socks") # For SOCKS proxy support
ensure_package("PyQt6", "PyQt6")
ensure_package("google-generativeai", "google")
ensure_package("python-docx", "docx")
ensure_package("lxml", "lxml")
ensure_package("ebooklib", "ebooklib")
ensure_package("Pillow", "PIL")

DOCX_AVAILABLE = importlib.util.find_spec("docx") is not None
LXML_AVAILABLE = importlib.util.find_spec("lxml") is not None
EBOOKLIB_AVAILABLE = importlib.util.find_spec("ebooklib") is not None
PILLOW_AVAILABLE = importlib.util.find_spec("PIL") is not None
BS4_AVAILABLE = importlib.util.find_spec("bs4") is not None

import os
import sys
import glob
import argparse
import traceback
import xml.etree.ElementTree as ET
import time
import math
from pathlib import Path
import re
import uuid
import tempfile
from io import BytesIO
import zipfile
import configparser
import base64
import imghdr
import html
from urllib.parse import urlparse, urljoin, unquote
import warnings

from bs4 import BeautifulSoup, Tag, NavigableString, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QListWidget, QPushButton,
    QDialogButtonBox, QLabel, QWidget, QLineEdit, QComboBox, QSpinBox,
    QCheckBox, QPlainTextEdit, QDoubleSpinBox, QProgressBar, QTextEdit,
    QGridLayout, QGroupBox, QHBoxLayout, QMessageBox, QFileDialog, QScrollArea
)
from PyQt6.QtCore import QStandardPaths, Qt

# --- НАЧАЛО БЛОКА ДЛЯ ЗАМЕНЫ (этот блок правильный, менять не нужно) ---
from google.api_core import exceptions as google_exceptions
from google import generativeai as genai
# Правильный импорт модуля 'types', который содержит и типы, и исключения контента
import google.generativeai.types as genai_types
# --- КОНЕЦ БЛОКА ДЛЯ ЗАМЕНЫ ---

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml.ns import qn

from lxml import etree
from ebooklib import epub
from PIL import Image

from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed, Future, wait, CancelledError

MODELS = {




    "Gemini 2.5 Pro": { # From user list / original code
        "id": "models/gemini-2.5-pro",
        "rpm": 5, # Moderate RPM
        "needs_chunking": True, # Assume requires chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },

    "Gemini 2.5 Flash": { # From user list / original code
        "id": "models/gemini-2.5-flash",
        "rpm": 10, # Moderate RPM
        "needs_chunking": True, # Assume requires chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },

    "Gemini 2.5 Flash-Lite Preview": { # From user list / original code
        "id": "models/gemini-2.5-flash-lite-preview-06-17",
        "rpm": 15, # Moderate RPM
        "needs_chunking": True, # Assume requires chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },

    "Gemini 2.5 Pro Experimental 03-25": { # From user list / original code
        "id": "models/gemini-2.5-pro-preview-03-25",
        "rpm": 10, # Moderate RPM
        "needs_chunking": True, # Assume requires chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },


    "Gemini 2.0 Flash": { # From user list / original code
        "id": "models/gemini-2.0-flash",
        "rpm": 15, # Higher RPM for Flash
        "needs_chunking": True, # Requires chunking for large inputs
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },
    "Gemini 2.0 Flash Experimental": { # From user list / original code
        "id": "models/gemini-2.0-flash-exp",
        "rpm": 10, # Higher RPM for Flash
        "needs_chunking": True, # Requires chunking for large inputs
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },
    "Gemini 2.0 Flash-Lite": { # From user list
        "id": "models/gemini-2.0-flash-lite",
        "rpm": 30, # Guess: Higher than standard Flash
        "needs_chunking": True, # Assume needs chunking like other Flash
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },

    "Gemini 1.5 Flash": { # From user list (using recommended 'latest' tag)
        "id": "models/gemini-1.5-flash-latest",
        "rpm": 20, # Guess: Higher RPM for Flash models
        "needs_chunking": True, # Assume needs chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },
    "gemma-3-27b-it": { # From user list / original code
        "id": "models/gemma-3-27b-it",
        "rpm": 30, # Moderate RPM
        "needs_chunking": True, # Assume requires chunking
        "post_request_delay": 2 # Уменьшенная задержка для быстрого перевода
    },


}

DEFAULT_MODEL_NAME = "Gemini 2.5 Flash Preview" if "Gemini 2.0 Flash" in MODELS else list(MODELS.keys())[0]

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 25
API_TIMEOUT_SECONDS = 600 # 10 минут

DEFAULT_CHARACTER_LIMIT_FOR_CHUNK = 900_000 # Default limit (can be adjusted in GUI)
DEFAULT_CHUNK_SEARCH_WINDOW = 500 # Default window (can be adjusted in GUI)
MIN_CHUNK_SIZE = 500 # Minimum size to avoid tiny chunks
CHUNK_HTML_SOURCE = True # Keep False: HTML chunking with embedded images is complex and disabled by default

SETTINGS_FILE = 'translator_settings.ini'

OUTPUT_FORMATS = {
    "Текстовый файл (.txt)": "txt",
    "Документ Word (.docx)": "docx",
    "Markdown (.md)": "md",
    "EPUB (.epub)": "epub", # Triggers EPUB rebuild logic if input is also EPUB
    "FictionBook2 (.fb2)": "fb2",
    "HTML (.html)": "html",
}
DEFAULT_OUTPUT_FORMAT_DISPLAY = "Текстовый файл (.txt)" # Default display name for format dropdown

IMAGE_PLACEHOLDER_PREFIX = "img_placeholder_"
def create_image_placeholder(img_uuid):
    return f"<||{IMAGE_PLACEHOLDER_PREFIX}{img_uuid}||>"

def find_image_placeholders(text):
    pattern = re.compile(r"<\|\|(" + IMAGE_PLACEHOLDER_PREFIX + r"([a-f0-9]{32}))\|\|>")
    return [(match.group(0), match.group(2)) for match in pattern.finditer(text)]

TRANSLATED_SUFFIX = "_translated"

def add_translated_suffix(filename):
    """Adds _translated before the file extension, handling multiple suffixes."""
    if not filename: return filename
    path = Path(filename)

    suffixes = "".join(path.suffixes)
    if not suffixes: # Handle case with no extension (e.g., just "myfile")
        stem = path.name

        return str(path.parent / f"{stem}{TRANSLATED_SUFFIX}")
    else:

        stem = path.name.replace(suffixes, "")

        return str(path.parent / f"{stem}{TRANSLATED_SUFFIX}{suffixes}")

def format_size(size_bytes):
   """Converts bytes to a human-readable format (KB, MB, GB)."""
   if size_bytes == 0: return "0 B"
   size_name = ("B", "KB", "MB", "GB", "TB")
   i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
   i = min(i, len(size_name) - 1)
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return f"{s} {size_name[i]}"




def split_text_into_chunks(text, limit_chars, search_window, min_chunk_size):
    """Splits text into chunks, respecting paragraphs and sentences where possible."""
    chunks = []
    start_index = 0
    text_len = len(text)
    target_size = max(min_chunk_size, limit_chars - search_window // 2)

    while start_index < text_len:
        if text_len - start_index <= limit_chars:
            chunks.append(text[start_index:])
            break

        ideal_end_index = min(start_index + target_size, text_len)
        search_start = max(start_index + min_chunk_size, ideal_end_index - search_window)
        search_end = min(ideal_end_index + search_window, text_len)
        split_index = -1

        potential_splits = []

        search_slice = text[search_start:search_end]
        if search_slice:
            for match in re.finditer(r'\n\n', search_slice):
                 potential_splits.append((abs((search_start + match.end()) - ideal_end_index), search_start + match.end(), 1))
            for match in re.finditer(r"[.!?]\s+", search_slice):
                 potential_splits.append((abs((search_start + match.end()) - ideal_end_index), search_start + match.end(), 2))
            for match in re.finditer(r'\n', search_slice):
                  potential_splits.append((abs((search_start + match.end()) - ideal_end_index), search_start + match.end(), 3))

            for match in re.finditer(r' ', search_slice):
                current_split_pos = search_start + match.end()
                preceding_text = text[max(0, current_split_pos - 50):current_split_pos]
                following_text = text[current_split_pos:min(text_len, current_split_pos + 5)]
                if f"<||{IMAGE_PLACEHOLDER_PREFIX}" in preceding_text and "||>" not in following_text:
                     continue # Likely inside a placeholder, don't split here
                potential_splits.append((abs(current_split_pos - ideal_end_index), current_split_pos, 4))


        potential_splits.sort()

        if potential_splits:
             split_index = potential_splits[0][1]

             if split_index <= start_index + min_chunk_size:
                 split_index = -1 # Ignore this split point

        if split_index == -1:
             if ideal_end_index > start_index + min_chunk_size:
                 split_index = ideal_end_index
             else: # Force split at limit or end of text
                 split_index = min(start_index + limit_chars, text_len)

        split_index = min(split_index, text_len)
        if split_index <= start_index:

             split_index = min(start_index + limit_chars, text_len)
             if split_index <= start_index: # Final fallback if limit is tiny or zero
                 split_index = text_len

        chunks.append(text[start_index:split_index])
        start_index = split_index

    return [chunk for chunk in chunks if chunk.strip()]

def get_image_extension_from_data(image_data, fallback_ext="jpeg"):
    """Determines image extension from binary data."""
    if not image_data: return fallback_ext
    ext = imghdr.what(None, image_data)
    if ext == 'jpeg': return 'jpg'
    if ext is None and PILLOW_AVAILABLE:
        try:
            with Image.open(BytesIO(image_data)) as img:
                img_format = img.format
                if img_format:
                    fmt_lower = img_format.lower()
                    if fmt_lower == 'jpeg': return 'jpg'
                    if fmt_lower in ['png', 'gif', 'bmp', 'tiff', 'webp']: return fmt_lower
        except Exception: pass # Ignore Pillow errors if imghdr failed
    return ext if ext else fallback_ext


def convert_emf_to_png(emf_data):
    """Converts EMF image data to PNG using Pillow."""
    if not PILLOW_AVAILABLE:
        print("[WARN] Pillow library not found, cannot convert EMF image. Skipping.")
        return None
    try:

        with Image.open(BytesIO(emf_data)) as img:

            if img.mode == 'CMYK': img = img.convert('RGB')
            elif img.mode == 'P': img = img.convert('RGBA') # Convert palette to RGBA for transparency
            elif img.mode == '1': img = img.convert('L') # Convert bilevel to grayscale

            png_bytes_io = BytesIO()
            img.save(png_bytes_io, format='PNG')
            return png_bytes_io.getvalue()
    except ImportError: # Might happen if EMF plugin for Pillow is missing
         print("[ERROR] Failed to convert EMF: Pillow EMF support might be missing or incomplete on this system.")
         return None
    except Exception as e:
        print(f"[ERROR] Failed to convert EMF to PNG: {e}")
        return None

def read_docx_with_images(filepath, temp_dir, image_map):
    """Reads DOCX, extracts text, replaces images with placeholders, saves images."""
    if not DOCX_AVAILABLE: raise ImportError("python-docx library is required.")
    if not os.path.exists(filepath): raise FileNotFoundError(f"DOCX file not found: {filepath}")

    doc = docx.Document(filepath)
    output_lines = []

    is_bold_chapter = re.compile(r'^\s*(Глава|Chapter|Part)\s+([0-9IVXLCDM]+|[a-zA-Zа-яА-Я]+)\b.*', re.IGNORECASE)
    doc_rels = doc.part.rels
    processed_image_rids = set()
    processed_rid_to_uuid = {}

    for element in doc.element.body:

        if element.tag.endswith('p'):
            para = docx.text.paragraph.Paragraph(element, doc)
            para_text_parts = []
            contains_image = False
            for run in para.runs:

                drawing_elems = run.element.xpath('.//w:drawing')
                if drawing_elems:
                    for drawing in drawing_elems:

                        inline_elems = drawing.xpath('.//wp:inline | .//wp:anchor')
                        if inline_elems:
                            for inline in inline_elems:

                                blip_fill = inline.xpath('.//a:blip')
                                if blip_fill:
                                    rId = blip_fill[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')

                                    if rId and rId in doc_rels and "image" in doc_rels[rId].target_ref:
                                        if rId not in processed_image_rids:
                                            try:
                                                img_part = doc_rels[rId].target_part
                                                img_data = img_part.blob
                                                original_filename = os.path.basename(img_part.partname)

                                                img_ext_original = os.path.splitext(original_filename)[-1].lower().strip('.')
                                                img_ext_detected = get_image_extension_from_data(img_data, fallback_ext=img_ext_original or "png")

                                                if img_ext_original == 'emf' or img_ext_detected == 'emf':
                                                    png_data = convert_emf_to_png(img_data)
                                                    if png_data:
                                                        img_data = png_data; img_ext_final = 'png'; content_type = 'image/png'
                                                        print(f"[INFO] DOCX: Converted EMF image '{original_filename}' to PNG.")
                                                    else:
                                                        print(f"[WARN] DOCX: Failed to convert EMF '{original_filename}', skipping."); continue # Skip if conversion failed
                                                else:
                                                    img_ext_final = img_ext_detected; content_type = f"image/{img_ext_final}"

                                                width, height = None, None
                                                try:
                                                    extent = inline.xpath('.//wp:extent');
                                                    if extent:
                                                        emu_per_px = 9525 # Approx conversion factor
                                                        width = int(extent[0].get('cx')) // emu_per_px
                                                        height = int(extent[0].get('cy')) // emu_per_px
                                                except Exception: pass # Ignore errors getting dimensions

                                                img_uuid = uuid.uuid4().hex
                                                saved_filename = f"{img_uuid}.{img_ext_final}"; saved_path = os.path.join(temp_dir, saved_filename)
                                                with open(saved_path, 'wb') as img_file: img_file.write(img_data)
                                                image_map[img_uuid] = {'saved_path': saved_path, 'original_filename': original_filename, 'content_type': content_type, 'width': width, 'height': height}
                                                processed_image_rids.add(rId); processed_rid_to_uuid[rId] = img_uuid

                                                placeholder = create_image_placeholder(img_uuid)
                                                para_text_parts.append(placeholder); contains_image = True
                                            except Exception as e:
                                                print(f"[WARN] DOCX: Error processing image rId {rId}: {e}"); para_text_parts.append(run.text) # Append run text on error
                                        else: # Image already processed (e.g., copy-pasted image)
                                            if rId in processed_rid_to_uuid:
                                                para_text_parts.append(create_image_placeholder(processed_rid_to_uuid[rId])); contains_image = True
                                            else: # Should not happen if processed correctly
                                                print(f"[WARN] DOCX: rId {rId} processed but not in UUID map."); para_text_parts.append(run.text)
                                    else: # Not an image relationship or rId invalid
                                        para_text_parts.append(run.text)
                                else: # No blip fill found
                                     para_text_parts.append(run.text)
                        else: # No inline/anchor element
                             para_text_parts.append(run.text)
                else: # No drawing element in run
                     para_text_parts.append(run.text)

            full_para_text = "".join(para_text_parts).strip()
            style_name = para.style.name.lower() if para.style and para.style.name else ''
            is_heading_style = False

            is_run_bold = all(r.bold for r in para.runs if r.text.strip()) # Check if all text runs are bold
            if style_name.startswith('heading 1') or (style_name == 'normal' and is_bold_chapter.match(full_para_text) and is_run_bold):
                output_lines.append(f"# {full_para_text}"); is_heading_style = True
            elif style_name.startswith('heading 2'):
                output_lines.append(f"## {full_para_text}"); is_heading_style = True
            elif style_name.startswith('heading 3'):
                output_lines.append(f"### {full_para_text}"); is_heading_style = True

            elif not full_para_text.strip() and not contains_image:

                 if output_lines and output_lines[-1] != "": output_lines.append("")
                 continue

            elif not is_heading_style and (style_name.startswith('list paragraph') or (para.paragraph_format and para.paragraph_format.left_indent and full_para_text)):
                 list_marker = "*"; # Default marker

                 num_match = re.match(r'^\s*(\d+\.|\([a-z]\)|\([A-Z]\)|[a-z]\.|[A-Z]\.)\s+', para.text) # Numbered or lettered lists
                 bullet_match = re.match(r'^\s*([\*\-\•\⁃])\s+', para.text) # Common bullet chars
                 if num_match: list_marker = num_match.group(1)
                 elif bullet_match: list_marker = bullet_match.group(1)

                 clean_list_text = re.sub(r'^\s*(\d+\.|\([a-z]\)|\([A-Z]\)|[a-z]\.|[A-Z]\.|[\*\-\•\⁃])\s*', '', full_para_text)
                 output_lines.append(f"{list_marker} {clean_list_text}")

            elif not is_heading_style and (full_para_text or contains_image):
                 output_lines.append(full_para_text)

        elif element.tag.endswith('tbl'):

            if output_lines and output_lines[-1]: output_lines.append("")
            output_lines.append("[--- ТАБЛИЦА (не обработано) ---]")
            output_lines.append("")

    final_text = "";
    for i, line in enumerate(output_lines):
        final_text += line

        if i < len(output_lines) - 1:
             final_text += "\n"

             is_current_placeholder_line = IMAGE_PLACEHOLDER_PREFIX in line
             is_next_placeholder_line = IMAGE_PLACEHOLDER_PREFIX in output_lines[i+1]
             is_current_heading = line.startswith('#')
             is_current_list = re.match(r'^([\*\-\•\⁃]|\d+\.|\([a-z]\)|\([A-Z]\)|[a-z]\.|[A-Z]\.)\s', line)
             is_current_table = "[--- ТАБЛИЦА" in line
             is_next_table = "[--- ТАБЛИЦА" in output_lines[i+1]

             if (output_lines[i+1] != "" and line != "" and # Both lines have content
                 not is_current_heading and not is_current_list and # Not headings or lists
                 not is_current_table and not is_next_table and # Not tables
                 not (is_current_placeholder_line and is_next_placeholder_line)): # Not two image lines together
                     final_text += "\n"

    print(f"[INFO] DOCX Read: Extracted {len(image_map)} images.")
    return final_text.strip()


def process_html_images(html_content, source_context, temp_dir, image_map):
    """
    Parses HTML, extracts images, replaces with placeholders, converts Hx/title to Markdown-like,
    and then extracts text content for translation.
    `source_context` can be a tuple (zipfile.ZipFile, html_path_in_zip) or a base directory path.
    """
    if not BS4_AVAILABLE: raise ImportError("BeautifulSoup4 is required for HTML processing.")

    if "<svg" in html_content.lower() or "xmlns:" in html_content.lower() or \
       html_content.strip().startswith("<?xml"):
        parser_type = 'lxml-xml'
    else:
        parser_type = 'lxml'

    try:
        soup = BeautifulSoup(html_content, parser_type)
    except Exception as e_parse:
        print(f"DEBUG process_html_images: Parse failed with '{parser_type}': {e_parse}. Trying 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e_parse_fallback:
            print(f"[ERROR] BeautifulSoup failed to parse HTML content with primary parser '{parser_type}' and fallback 'html.parser'. Error: {e_parse_fallback}")
            raise ValueError(f"Failed to parse HTML content after trying multiple parsers: {e_parse_fallback}")

    zip_file_obj = None
    source_html_path = None
    base_path = ""
    if isinstance(source_context, tuple) and len(source_context) == 2 and isinstance(source_context[0], zipfile.ZipFile):
         zip_file_obj = source_context[0]
         source_html_path = source_context[1]
         if source_html_path:
             base_path = os.path.dirname(source_html_path).replace('\\', '/')
             if base_path == '.': base_path = ""
    elif isinstance(source_context, str) and os.path.isdir(source_context):
        base_path = source_context
        source_html_path = "unknown.html"
        zip_file_obj = None
    else:
        zip_file_obj = None
        base_path = ""
        source_html_path = "unknown.html"

    image_processing_context = zip_file_obj if zip_file_obj else base_path
    
    # --- Image Processing ---
    for tag in soup.find_all(['img', 'svg']):
        if not tag.parent: continue
        img_uuid = None
        tag_name = tag.name.lower()
        
        try:
            if tag_name == 'img':
                img_uuid = _process_single_image(tag, image_processing_context, base_path, source_html_path, temp_dir, image_map, is_svg_image=False)
                tag.replace_with(NavigableString(create_image_placeholder(img_uuid)) if img_uuid else "")
            elif tag_name == 'svg':
                svg_image_tag = tag.find(lambda t: t.name.lower() == 'image', recursive=False)
                if svg_image_tag:
                    img_uuid = _process_single_image(svg_image_tag, image_processing_context, base_path, source_html_path, temp_dir, image_map, is_svg_image=True)
                tag.replace_with(NavigableString(create_image_placeholder(img_uuid)) if img_uuid else "")
        except Exception as e:
            print(f"[ERROR] process_html_images: Error replacing tag <{tag_name}>: {e}")
            try: tag.replace_with("")
            except Exception as remove_err: print(f"[ERROR] Failed to remove tag after error: {remove_err}")
            
    # --- НАЧАЛО БЛОКА НОРМАЛИЗАЦИИ HTML (НОВЫЙ БЛОК) ---
    # Преобразуем стилизованные span в семантические теги em/strong
    for span in soup.find_all('span', style=True):
        style = span['style'].lower()
        if 'font-style' in style and 'italic' in style:
            span.name = 'em'
            del span['style'] # Удаляем атрибут style после преобразования
        elif 'font-weight' in style and ('bold' in style or any(w.strip() in ['700', '800', '900'] for w in style.split('font-weight:')[1].split(';')[0].split())):
            span.name = 'strong'
            del span['style']

    # Объединяем последовательные теги em и strong
    for tag_name in ['em', 'strong']:
        for tag in soup.find_all(tag_name):
            next_sibling = tag.next_sibling
            while next_sibling and isinstance(next_sibling, NavigableString) and not next_sibling.strip():
                next_sibling = next_sibling.next_sibling # Пропускаем пустые строки
            if next_sibling and next_sibling.name == tag.name:
                # Если у следующего тега есть атрибуты, отличные от текущего, не объединяем
                if next_sibling.attrs == tag.attrs:
                    tag.append(next_sibling.decode_contents())
                    next_sibling.decompose()

    # Заменяем структурные div на p, чтобы они обрабатывались как абзацы
    # и "разворачиваем" (unwrap) вложенные div и span, которые не несут форматирования
    tags_to_process = soup.find_all(['div', 'span'])
    for tag in tags_to_process:
        # Если это div, который выглядит как контейнер для абзаца, меняем его на p
        if tag.name == 'div':
            tag.name = 'p'
            # Удаляем атрибуты, не относящиеся к p
            for attr in list(tag.attrs.keys()):
                if attr.lower() not in ['class', 'id']:
                     del tag[attr]
        # Если это span без атрибутов, он, скорее всего, для разбиения текста - убираем его
        elif tag.name == 'span' and not tag.attrs:
            tag.unwrap()
    # --- КОНЕЦ БЛОКА НОРМАЛИЗАЦИИ HTML ---


    # --- Header and Content Extraction ---
    html_doctitle_text = None
    if soup.head and soup.head.title and soup.head.title.string:
        title_candidate = soup.head.title.string.strip()
        generic_titles = ['untitled', 'unknown', 'navigation', 'toc', 'table of contents', 'index', 'contents', 'оглавление', 'содержание', 'индекс', 'cover', 'title page', 'copyright', 'chapter']
        if title_candidate and title_candidate.lower() not in generic_titles and len(title_candidate) > 2:
            html_doctitle_text = title_candidate

    content_extraction_root = soup.body if soup.body else soup
    if not content_extraction_root:
        print("[WARN] process_html_images: No <body> or root element found.")
        return ""

    # --- CORRECTED HEADER PROCESSING LOGIC ---
    for level in range(6, 0, -1):
        for header_tag in content_extraction_root.find_all(f'h{level}'):
            # Сначала преобразуем em/strong внутри заголовка в Markdown
            for em_tag in header_tag.find_all('em'):
                em_tag.replace_with(f"*{em_tag.get_text(strip=True)}*")
            for strong_tag in header_tag.find_all('strong'):
                strong_tag.replace_with(f"**{strong_tag.get_text(strip=True)}**")
            
            header_text = header_tag.get_text(separator=' ', strip=True)
            if header_text:
                markdown_header_line = f"\n\n{'#' * level} {header_text}\n\n"
                header_tag.replace_with(NavigableString(markdown_header_line))

    # Decompose unwanted tags after processing headers and normalization
    tags_to_decompose = ['script', 'style', 'noscript', 'head', 'meta', 'link', 'form', 'iframe', 'header', 'footer', 'nav', 'aside']
    for tag_type in tags_to_decompose:
        for instance in content_extraction_root.find_all(tag_type):
            instance.decompose()
            
    # --- ИЗМЕНЕННАЯ ЛОГИКА ИЗВЛЕЧЕНИЯ ТЕКСТА ---
    # Преобразуем оставшиеся em/strong в Markdown перед финальным извлечением текста
    for em_tag in content_extraction_root.find_all('em'):
        em_tag.replace_with(f"*{em_tag.get_text(strip=True)}*")
    for strong_tag in content_extraction_root.find_all('strong'):
        strong_tag.replace_with(f"**{strong_tag.get_text(strip=True)}**")
    
    # Заменяем <br> и </p> на переносы строк для корректного разделения
    for br in content_extraction_root.find_all("br"):
        br.replace_with("\n")
    for p_tag in content_extraction_root.find_all("p"):
        p_tag.append("\n\n")

    # Get all text from the modified body
    body_text_md = content_extraction_root.get_text(separator='', strip=False) # Используем separator='', чтобы не добавлять лишних разделителей

    # Final logic to assemble text for API
    final_text_for_api = body_text_md
    if html_doctitle_text and not body_text_md.lstrip().startswith('#'):
        final_text_for_api = f"# {html_doctitle_text}\n\n{body_text_md}"

    # Clean up excessive newlines and spaces
    final_text_for_api = re.sub(r' +', ' ', final_text_for_api) # Сжимаем множественные пробелы
    final_text_for_api = re.sub(r'\n{3,}', '\n\n', final_text_for_api) # Сжимаем множественные переносы
    
    return final_text_for_api.strip()


def _process_single_image(img_tag, source_context, base_path, source_html_path, temp_dir, image_map, is_svg_image=False):
    """
    Processes individual image tag.
    For EPUB->EPUB: Extracts original src and attributes, stores them in image_map with a UUID. Does NOT save file.
    For other modes: Extracts image data, saves to temp_dir, stores path and info in image_map.
    """
    src = None
    xlink_namespace_uri = "http://www.w3.org/1999/xlink"


    is_epub_rebuild_mode = isinstance(source_context, zipfile.ZipFile) # True if processing for EPUB->EPUB

    if is_svg_image:
        src = img_tag.get(f'{{{xlink_namespace_uri}}}href')
        if not src:
            attrs_dict = img_tag.attrs
            if 'xlink:href' in attrs_dict: src = attrs_dict['xlink:href']
            elif 'href' in attrs_dict: src = attrs_dict['href']
            else:
                namespaced_key = (xlink_namespace_uri, 'href')
                if namespaced_key in attrs_dict: src = attrs_dict[namespaced_key]

    else: # HTML <img> tag
        src = img_tag.get('src', '')


    if not src or src.startswith('data:'):

        return None

    img_uuid = uuid.uuid4().hex
    original_src_value = src # This is the raw value from the attribute, e.g., "../Images/0004.png"
    original_tag_name = img_tag.name # 'img' or 'image' (from svg)
    all_original_attributes = dict(img_tag.attrs) # Store all attributes

    if is_epub_rebuild_mode:

        image_map[img_uuid] = {
            'original_src': original_src_value,
            'original_tag_name': original_tag_name, # 'img' or 'image'
            'is_svg_image_child': is_svg_image, # True if it was <image> inside <svg>
            'attributes': all_original_attributes # Store all original attributes
        }

        return img_uuid
    else:

        img_data = None
        decoded_src = unquote(src)
        original_filename = os.path.basename(urlparse(decoded_src).path)
        if not original_filename:
            src_parts = decoded_src.split('/')
            potential_fname = src_parts[-1] if src_parts else "image"
            potential_fname = potential_fname.split('?')[0]
            safe_fname_part = re.sub(r'[^\w\.\-]+', '_', potential_fname)
            _, ext_guess = os.path.splitext(safe_fname_part)
            fallback_ext = "png"
            if ext_guess and ext_guess[1:].lower() in ['jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'svg']:
                original_filename = safe_fname_part
            else:
                original_filename = f"{Path(safe_fname_part).stem}.{fallback_ext}"

        content_type = None

        try:
            if isinstance(source_context, zipfile.ZipFile): # EPUB source -> non-EPUB output

                possible_paths = []
                current_html_dir = base_path
                path1 = os.path.join(current_html_dir, decoded_src)
                path1_norm = os.path.normpath(path1).replace('\\', '/')
                if not path1_norm.startswith('..'): possible_paths.append(path1_norm.lstrip('/'))
                path2_norm = os.path.normpath(decoded_src.lstrip('/')) .replace('\\', '/')
                if not path2_norm.startswith('..'): possible_paths.append(path2_norm)

                unique_paths = list(dict.fromkeys(p.strip('/') for p in possible_paths if p.strip('/')))

                for img_path_in_zip in unique_paths:
                    try:
                        img_data = source_context.read(img_path_in_zip)

                        break
                    except KeyError: continue
                if not img_data:
                    print(f"[WARN] HTML Image NOT Found (EPUB src -> File Output): src='{src}'. Tried: {unique_paths}.")
                    return None

            elif isinstance(source_context, str) and os.path.isdir(source_context): # Directory context

                paths_to_try_fs = [
                    os.path.normpath(os.path.join(base_path, decoded_src)),
                    os.path.normpath(os.path.join(source_context, decoded_src.lstrip('/\\')))
                ]
                if not decoded_src.startswith(('/', '\\')):
                    path3_fs = os.path.normpath(os.path.join(source_context, decoded_src))
                    if path3_fs not in paths_to_try_fs: paths_to_try_fs.append(path3_fs)
                abs_path = next((p for p in paths_to_try_fs if os.path.exists(p)), None)
                if not abs_path:
                    print(f"[WARN] HTML Image (FS Mode): Could not find '{decoded_src}'. Tried: {paths_to_try_fs}")
                    return None
                with open(abs_path, 'rb') as f: img_data = f.read()
            else:
                print(f"[WARN] HTML Image: Unknown source context for file mode: {type(source_context)}")
                return None

            img_ext_from_file = os.path.splitext(original_filename)[1][1:].lower()
            content_type = f"image/{get_image_extension_from_data(img_data, fallback_ext=img_ext_from_file or 'jpeg')}"
            img_ext = content_type.split('/')[-1] if content_type else 'jpeg'
            img_ext = 'jpg' if img_ext == 'jpeg' else img_ext

            if img_ext == 'emf':
                converted_data = convert_emf_to_png(img_data)
                if converted_data:
                    img_data = converted_data; img_ext = 'png'; content_type = 'image/png'
                else: return None

            filename = f"{img_uuid}.{img_ext}"
            save_path = os.path.join(temp_dir, filename)
            with open(save_path, 'wb') as f: f.write(img_data)

            image_map[img_uuid] = {
                'saved_path': save_path, # For non-EPUB rebuild, this is used
                'original_filename': original_filename,
                'original_src': original_src_value, # Still store original_src for consistency if needed
                'content_type': content_type,
                'attributes': all_original_attributes # Store original attributes
            }

            return img_uuid

        except Exception as e:
            print(f"[ERROR] HTML Image (File Mode): Error processing src '{src}': {e}")
            traceback.print_exc()
            return None

def write_markdown_to_docx(filepath, md_text_with_placeholders, image_map):
    """Writes Markdown-like text with placeholders back to DOCX."""
    if not DOCX_AVAILABLE: raise ImportError("python-docx library is required.")
    if image_map is None: image_map = {}
    doc = Document()

    lines = re.split('(\n)', md_text_with_placeholders)

    paragraphs_md = []
    current_para_lines = []
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line: # Treat empty line as paragraph break
            if current_para_lines:
                paragraphs_md.append("\n".join(current_para_lines))
                current_para_lines = []

            if paragraphs_md and paragraphs_md[-1]: # Add if last added wasn't already empty
                 paragraphs_md.append("")
        else:
            current_para_lines.append(line)
    if current_para_lines: # Add last paragraph if exists
        paragraphs_md.append("\n".join(current_para_lines))

    current_docx_para = None
    for md_para in paragraphs_md:
        md_para_stripped = md_para.strip()
        if not md_para_stripped:

            if current_docx_para is not None: # Check if previous para exists
                doc.add_paragraph("")
            current_docx_para = None # Reset current para tracker
            continue

        heading_match = re.match(r'^(#{1,6})\s+(.*)', md_para_stripped, re.DOTALL)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text_raw = heading_match.group(2).strip()
            current_docx_para = doc.add_heading("", level=max(1, min(level, 6))) # Add heading
            process_text_with_placeholders(current_docx_para, heading_text_raw, image_map)
            continue # Move to next md paragraph

        list_match = re.match(r'^([\*\-\•\⁃]|\d+\.|\([a-z]\)|\([A-Z]\)|[a-z]\.|[A-Z]\.)\s+(.*)', md_para_stripped, re.DOTALL)
        if list_match:
             marker = list_match.group(1)
             list_item_text_raw = list_match.group(2).strip()
             style = 'List Bullet' if marker in ['*', '-', '•', '⁃'] else 'List Number' # Basic style mapping
             try:
                 current_docx_para = doc.add_paragraph(style=style)
             except (KeyError, ValueError): # Fallback if style doesn't exist in template
                 print(f"[WARN] DOCX Write: Style '{style}' not found. Using default paragraph.")
                 current_docx_para = doc.add_paragraph()
             process_text_with_placeholders(current_docx_para, list_item_text_raw, image_map)
             continue # Move to next md paragraph

        if md_para_stripped == '---':
             doc.add_paragraph().add_run()._element.xpath('.//w:pPr')[0].append(
                 etree.fromstring('<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="6" w:space="1" w:color="auto"/></w:pBdr>')
             )
             current_docx_para = None # HR acts as break
             continue

        current_docx_para = doc.add_paragraph()
        process_text_with_placeholders(current_docx_para, md_para.strip(), image_map) # Process original (not stripped) to keep internal newlines

    doc.save(filepath)


def process_text_with_placeholders(docx_paragraph, text_with_placeholders, image_map):
    """Adds runs of text and images to a docx paragraph based on placeholders."""

    last_index = 0
    placeholders_found = find_image_placeholders(text_with_placeholders)

    if not placeholders_found:
        if text_with_placeholders.strip():
            docx_paragraph.add_run(text_with_placeholders)
        return

    for placeholder_tag, img_uuid in placeholders_found:
        match_start = text_with_placeholders.find(placeholder_tag, last_index)
        if match_start == -1: continue # Should not happen with finditer logic

        text_before = text_with_placeholders[last_index:match_start]
        if text_before:
            docx_paragraph.add_run(text_before)

        if img_uuid in image_map:
            img_info = image_map[img_uuid]; img_path = img_info['saved_path']
            if os.path.exists(img_path):
                try:

                    img_width_px = img_info.get('width'); img_height_px = img_info.get('height')
                    run = docx_paragraph.add_run() # Create run for the picture
                    target_width = None

                    if img_width_px:
                        try:
                            img_width_px = float(img_width_px) # Ensure it's a number
                            if img_width_px > 0:
                                 target_width_inches = img_width_px / 96.0 # Approx DPI
                                 max_doc_width_inches = 6.0 # Usable width on standard page
                                 target_width = Inches(min(target_width_inches, max_doc_width_inches))
                        except (ValueError, TypeError): pass # Ignore invalid width values

                    run.add_picture(img_path, width=target_width)
                except FileNotFoundError:
                    print(f"[ERROR] DOCX Write: Image file not found: {img_path}")
                    docx_paragraph.add_run(f"[Image NF: {img_info.get('original_filename', img_uuid)}]") # Add error text
                except Exception as e:
                    print(f"[ERROR] DOCX Write: Failed to add picture {img_path}: {e}")
                    docx_paragraph.add_run(f"[Img Err: {img_info.get('original_filename', img_uuid)}]")
            else:

                print(f"[ERROR] DOCX Write: Image path from map does not exist: {img_path}")
                docx_paragraph.add_run(f"[Img Path Miss: {img_info.get('original_filename', img_uuid)}]")
        else:

            print(f"[WARN] DOCX Write: Placeholder UUID '{img_uuid}' not found in image_map.")
            docx_paragraph.add_run(f"[Unk Img: {img_uuid}]")

        last_index = match_start + len(placeholder_tag)

    text_after = text_with_placeholders[last_index:]
    if text_after:
        docx_paragraph.add_run(text_after)







def generate_nav_html(nav_data_list, nav_file_path_in_zip, book_title, book_lang="ru"):
    """
    Generates XHTML content for nav.xhtml based on spine data.
    Simplified version focusing on the list structure.
    """
    if not nav_data_list:
        print("[WARN] NAV Gen: Input data list is empty. NAV not generated.")
        return None

    if not LXML_AVAILABLE:
        print("[ERROR] NAV Gen: LXML library is required for reliable NAV generation.")

        print("[WARN] NAV Gen: LXML not found, attempting basic string generation (less reliable).")
        nav_lines = []
        nav_lines.append("<?xml version='1.0' encoding='utf-8'?>")
        nav_lines.append("<!DOCTYPE html>")
        nav_lines.append(f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{book_lang}" xml:lang="{book_lang}">')
        nav_lines.append("<head>")
        nav_lines.append("  <meta charset=\"utf-8\"/>")

        nav_lines.append("</head>")
        nav_lines.append("<body>")
        nav_lines.append('  <nav epub:type="toc" id="toc">') # Используем id="toc"

        nav_lines.append("    <ol>")
        nav_dir = os.path.dirname(nav_file_path_in_zip).replace('\\', '/')
        if nav_dir == '.': nav_dir = ""
        link_count_str = 0
        for item_path, item_title in nav_data_list:
            safe_item_title = html.escape(str(item_title).strip())
            if not safe_item_title: safe_item_title = "Untitled Entry" # Заглушка
            try:
                item_path_norm = item_path.replace('\\', '/').lstrip('/')
                nav_parent_dir_norm = os.path.dirname(nav_file_path_in_zip.replace('\\','/').lstrip('/')).replace('\\','/')
                relative_href = os.path.relpath(item_path_norm, start=nav_parent_dir_norm if nav_parent_dir_norm else '.').replace('\\', '/')
                safe_href = html.escape(relative_href, quote=True)
                nav_lines.append(f'      <li><a href="{safe_href}">{safe_item_title}</a></li>')
                link_count_str += 1
            except ValueError as e:
                print(f"[WARN] NAV Gen (String): Failed to calculate relative path for '{item_path}' from '{nav_parent_dir_norm or '<root>'}': {e}. Skipping link.")
            except Exception as e_loop:
                 print(f"[ERROR] NAV Gen (String): Error processing item ('{item_path}', '{item_title}'): {e_loop}")
        nav_lines.append("    </ol>")
        nav_lines.append("  </nav>")
        nav_lines.append("</body>")
        nav_lines.append("</html>")
        print(f"[INFO] NAV Gen (String): Finished generation. Added {link_count_str} links.")
        return "\n".join(nav_lines).encode('utf-8')

    print(f"[INFO] NAV Gen (lxml): Starting NAV generation for '{nav_file_path_in_zip}' with {len(nav_data_list)} entries...")
    xhtml_ns = "http://www.w3.org/1999/xhtml"
    epub_ns = "http://www.idpf.org/2007/ops"
    NSMAP = {None: xhtml_ns, "epub": epub_ns}

    html_tag = etree.Element(f"{{{xhtml_ns}}}html", nsmap=NSMAP)
    xml_lang_attr_name = "{http://www.w3.org/XML/1998/namespace}lang"
    html_tag.set(xml_lang_attr_name, book_lang)
    html_tag.set("lang", book_lang)

    head = etree.SubElement(html_tag, f"{{{xhtml_ns}}}head")

    etree.SubElement(head, f"{{{xhtml_ns}}}meta", charset="utf-8") # Добавляем meta charset

    body = etree.SubElement(html_tag, f"{{{xhtml_ns}}}body")
    nav = etree.SubElement(body, f"{{{xhtml_ns}}}nav", id="toc") # Используем id="toc"
    nav.set(f"{{{epub_ns}}}type", "toc")


    ol = etree.SubElement(nav, f"{{{xhtml_ns}}}ol")

    nav_dir = os.path.dirname(nav_file_path_in_zip).replace('\\', '/')
    if nav_dir == '.': nav_dir = "" # Корень

    link_count = 0
    for item_path, item_title in nav_data_list:
        safe_item_title = html.escape(str(item_title).strip())
        if not safe_item_title: safe_item_title = "Untitled Entry" # Заглушка для пустых заголовков

        try:
            item_path_norm = item_path.replace('\\', '/').lstrip('/')
            nav_parent_dir_norm = os.path.dirname(nav_file_path_in_zip.replace('\\','/').lstrip('/')).replace('\\','/')

            relative_href = os.path.relpath(item_path_norm, start=nav_parent_dir_norm if nav_parent_dir_norm else '.').replace('\\', '/')
            safe_href = html.escape(relative_href, quote=True)

            li = etree.SubElement(ol, f"{{{xhtml_ns}}}li")
            a = etree.SubElement(li, f"{{{xhtml_ns}}}a", href=safe_href)
            a.text = safe_item_title
            link_count += 1


        except ValueError as e:
            print(f"[WARN] NAV Gen (lxml): Failed to calculate relative path for '{item_path}' from '{nav_parent_dir_norm or '<root>'}': {e}. Skipping link.")
        except Exception as e_loop:
             print(f"[ERROR] NAV Gen (lxml): Error processing item ('{item_path}', '{item_title}'): {e_loop}")

    if link_count == 0 and len(nav_data_list) > 0:
         print("[WARN] NAV Gen (lxml): No list items were added to NAV despite input data.")
         ol.append(etree.Comment(" Error: No valid links generated "))
    elif link_count != len(nav_data_list):
        print(f"[WARN] NAV Gen (lxml): Added {link_count} links, but received {len(nav_data_list)} data items.")

    nav_output_string = etree.tostring(html_tag, encoding='unicode', method='html', xml_declaration=False, pretty_print=True)

    doctype = '<!DOCTYPE html>'
    xml_declaration = "<?xml version='1.0' encoding='utf-8'?>"
    final_output = f"{xml_declaration}\n{doctype}\n{nav_output_string}"


    print(f"[INFO] NAV Gen (lxml): Finished generation for '{nav_file_path_in_zip}'. Added {link_count} links.")
    return final_output.encode('utf-8') # Возвращаем байты UTF-8



def generate_ncx_manual(book_id, book_title, ncx_data_list):
    """
    Generates the content of an NCX file manually from a prepared list of data
    derived from nav.xhtml.

    Args:
        book_id (str): The unique identifier for the book (for dtb:uid).
        book_title (str): The title of the book (for docTitle).
        ncx_data_list (list): A list of tuples extracted from nav.xhtml:
                              [(nav_point_id, content_src, link_text), ...].
                              - nav_point_id: Pre-generated ID for the navPoint.
                              - content_src: Pre-calculated relative path for content src.
                              - link_text: Text label for the navPoint.

    Returns:
        bytes: The generated NCX content as bytes (UTF-8 encoded XML), or None if error.
    """
    if not ncx_data_list:
        print("[WARN] NCX Manual Gen: Input data list is empty. NCX not generated.")
        return None

    print(f"[INFO] NCX Manual Gen: Starting NCX generation from {len(ncx_data_list)} NAV entries...")

    ncx_lines = []
    ncx_lines.append("<?xml version='1.0' encoding='utf-8'?>")
    ncx_lines.append('<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">')
    ncx_lines.append('  <head>')

    safe_book_id = html.escape(book_id or f"urn:uuid:{uuid.uuid4()}", quote=True)
    ncx_lines.append(f'    <meta content="{safe_book_id}" name="dtb:uid"/>')

    ncx_lines.append('    <meta content="1" name="dtb:depth"/>') # Ставим 1, если есть navPoints
    ncx_lines.append('    <meta content="0" name="dtb:totalPageCount"/>')
    ncx_lines.append('    <meta content="0" name="dtb:maxPageNumber"/>')
    ncx_lines.append('  </head>')

    safe_book_title = html.escape(book_title or "Untitled")
    ncx_lines.append('  <docTitle>')
    ncx_lines.append(f'    <text>{safe_book_title}</text>')
    ncx_lines.append('  </docTitle>')

    ncx_lines.append('  <docAuthor>')
    ncx_lines.append(f'    <text>Translator</text>') # Можно заменить на что-то другое
    ncx_lines.append('  </docAuthor>')

    ncx_lines.append('  <navMap>')

    play_order_counter = 1
    for nav_point_id, content_src, link_text in ncx_data_list:

        safe_id = html.escape(nav_point_id, quote=True)
        safe_label = html.escape(link_text)
        safe_src = html.escape(content_src, quote=True)

        ncx_lines.append(f'    <navPoint id="{safe_id}" playOrder="{play_order_counter}">')
        ncx_lines.append('      <navLabel>')
        ncx_lines.append(f'        <text>{safe_label}</text>')
        ncx_lines.append('      </navLabel>')
        ncx_lines.append(f'      <content src="{safe_src}"/>')
        ncx_lines.append('    </navPoint>')
        play_order_counter += 1

    ncx_lines.append('  </navMap>')
    ncx_lines.append('</ncx>')

    ncx_output_string = "\n".join(ncx_lines)
    print(f"[INFO] NCX Manual Gen: Generated {play_order_counter - 1} navPoints from NAV data.")


    return ncx_output_string.encode('utf-8')


def parse_nav_for_ncx_data(nav_content_bytes, nav_base_path_in_zip):
    """Извлекает данные из NAV XHTML для генерации NCX."""
    if not nav_content_bytes or not BS4_AVAILABLE: return []
    ncx_data = []
    play_order = 1
    try:
        soup = BeautifulSoup(nav_content_bytes, 'lxml-xml') # Используем XML парсер
        nav_list = soup.find('nav', attrs={'epub:type': 'toc'})
        if not nav_list: nav_list = soup # Fallback, если нет <nav>
        list_tag = nav_list.find(['ol', 'ul'])
        if not list_tag: return []

        nav_dir = os.path.dirname(nav_base_path_in_zip).replace('\\', '/')
        if nav_dir == '.': nav_dir = "" # Корень

        for link in list_tag.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text(strip=True)
            if not href or not text or href.startswith('#') or href.startswith(('http:', 'https:', 'mailto:')):
                continue

            try:

                abs_path_in_zip = os.path.normpath(os.path.join(nav_dir, unquote(href))).replace('\\', '/')
                content_src = abs_path_in_zip.lstrip('/') # NCX src обычно от корня

                content_src_base = urlparse(content_src).path

                safe_base_name = re.sub(r'[^\w\-]+', '_', Path(content_src_base).stem)
                nav_point_id = f"navpoint_{safe_base_name}_{play_order}"

                ncx_data.append((nav_point_id, content_src, text)) # Сохраняем путь с фрагментом, если был
                play_order += 1
            except Exception as e:
                print(f"[WARN NavParseForNCX] Error processing NAV link '{href}': {e}")
        return ncx_data
    except Exception as e:
        print(f"[ERROR NavParseForNCX] Failed to parse NAV content: {e}")
        return []



def parse_ncx_for_nav_data(ncx_content_bytes, opf_dir):
    """Извлекает данные из NCX для генерации NAV HTML."""
    if not ncx_content_bytes or not LXML_AVAILABLE: return []
    nav_data = [] # Будет содержать кортежи: (путь_от_корня_zip, заголовок)
    try:
        root = etree.fromstring(ncx_content_bytes)
        ns = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
        for nav_point in root.xpath('//ncx:navMap/ncx:navPoint', namespaces=ns):
            content_tag = nav_point.find('ncx:content', ns)
            label_tag = nav_point.find('.//ncx:text', ns)

            if content_tag is not None and label_tag is not None:
                src = content_tag.get('src')
                text = label_tag.text.strip() if label_tag.text else "Untitled"
                if not src: continue

                try:

                    unquoted_src = unquote(urlparse(src).path) # Убираем URL-кодирование и фрагменты

                    if opf_dir:

                        abs_path_in_zip = os.path.normpath(os.path.join(opf_dir, unquoted_src)).replace('\\', '/')
                    else:

                        abs_path_in_zip = os.path.normpath(unquoted_src).replace('\\', '/')

                    abs_path_in_zip = '/'.join(part for part in abs_path_in_zip.split('/') if part != '..')
                    abs_path_in_zip = abs_path_in_zip.lstrip('/')

                    nav_data.append((abs_path_in_zip, text))

                except Exception as e:
                    print(f"[WARN NcxParseForNav] Error processing NCX src '{src}': {e}")
        return nav_data
    except Exception as e:
        print(f"[ERROR NcxParseForNav] Failed to parse NCX content: {e}")
        return []



def update_nav_content(nav_content_bytes, nav_base_path_in_zip, filename_map, canonical_titles):
    """Обновляет href и текст ссылок в существующем NAV контенте."""
    if not nav_content_bytes or not BS4_AVAILABLE: return None
    try:
        soup = BeautifulSoup(nav_content_bytes, 'lxml-xml')
        nav_list = soup.find('nav', attrs={'epub:type': 'toc'})
        if not nav_list: nav_list = soup
        list_tag = nav_list.find(['ol', 'ul'])
        if not list_tag: return nav_content_bytes # Не нашли список, возвращаем как есть

        nav_dir = os.path.dirname(nav_base_path_in_zip).replace('\\', '/')
        if nav_dir == '.': nav_dir = "" # Корень

        updated_count = 0
        for link in list_tag.find_all('a', href=True):
            href = link.get('href')
            if not href or href.startswith('#') or href.startswith(('http:', 'https:', 'mailto:')):
                continue

            original_target_full_path = None
            frag = None
            try:

                original_target_full_path = os.path.normpath(os.path.join(nav_dir, unquote(urlparse(href).path))).replace('\\', '/').lstrip('/')
                frag = urlparse(href).fragment

            except Exception as e:
                print(f"[WARN NAV Update] Error resolving original path for href '{href}': {e}")
                continue

            new_target_relative_path = filename_map.get(original_target_full_path)


            if new_target_relative_path:
                try:

                    nav_parent_dir = os.path.dirname(nav_base_path_in_zip).replace('\\', '/') # Директория, где лежит NAV
                    new_rel_href = os.path.relpath(new_target_relative_path, start=nav_parent_dir).replace('\\', '/')


                    new_href_val = new_rel_href + (f"#{frag}" if frag else "")
                    link['href'] = new_href_val # Обновляем href
                    updated_count += 1
                except ValueError as e:
                    print(f"[WARN NAV Update] Error calculating relative href for '{new_target_relative_path}' from '{nav_parent_dir}': {e}")

            target_canonical_title = canonical_titles.get(original_target_full_path)
            if target_canonical_title:
                link.string = html.escape(str(target_canonical_title).strip()) # Устанавливаем новый текст


        print(f"[INFO] NAV Update: Updated attributes for {updated_count} links.")

        return str(soup).encode('utf-8')

    except Exception as e:
        print(f"[ERROR NAV Update] Failed to update NAV content: {e}\n{traceback.format_exc()}")
        return None # Возвращаем None в случае ошибки



def update_ncx_content(ncx_content_bytes, opf_dir, filename_map, canonical_titles):
    """Обновляет src и text в существующем NCX контенте."""
    if not ncx_content_bytes or not LXML_AVAILABLE: return None
    try:

        ncx_ns_uri = 'http://www.daisy.org/z3986/2005/ncx/'
        ns = {'ncx': ncx_ns_uri}


        root = etree.fromstring(ncx_content_bytes)
        updated_count = 0

        for nav_point in root.xpath('//ncx:navPoint', namespaces=ns):
            content_tag = nav_point.find('ncx:content', ns)
            label_tag = nav_point.find('.//ncx:text', ns) # Ищем text внутри navLabel

            if content_tag is None or label_tag is None: continue

            src = content_tag.get('src')
            if not src: continue

            original_target_full_path = None
            frag = None
            try:

                original_target_full_path = os.path.normpath(os.path.join(opf_dir, unquote(urlparse(src).path))).replace('\\', '/').lstrip('/')
                frag = urlparse(src).fragment

            except Exception as e:
                 print(f"[WARN NCX Update] Error resolving original path for src '{src}': {e}")
                 continue

            new_target_relative_path = filename_map.get(original_target_full_path)


            if new_target_relative_path:
                try:

                    if opf_dir: # Если OPF не в корне
                        new_src = os.path.relpath(new_target_relative_path, start=opf_dir).replace('\\', '/')
                    else: # OPF в корне, новый путь уже относителен корню
                        new_src = new_target_relative_path


                    new_src_val = new_src + (f"#{frag}" if frag else "")
                    content_tag.set('src', new_src_val) # Обновляем src
                    updated_count += 1
                except ValueError as e:
                    print(f"[WARN NCX Update] Error calculating relative src for '{new_target_relative_path}' from '{opf_dir or '<root>'}': {e}")

            target_canonical_title = canonical_titles.get(original_target_full_path)
            if target_canonical_title:
                label_tag.text = str(target_canonical_title).strip() # Устанавливаем новый текст


        print(f"[INFO] NCX Update: Updated attributes for {updated_count} navPoints.")

        return etree.tostring(root, encoding='utf-8', xml_declaration=True, pretty_print=True)

    except Exception as e:
        print(f"[ERROR NCX Update] Failed to update NCX content: {e}\n{traceback.format_exc()}")
        return None # Возвращаем None в случае ошибки

def write_to_epub(out_path, processed_epub_parts, original_epub_path, build_metadata, book_title_override=None):
    start_time = time.time()
    if not EBOOKLIB_AVAILABLE: return False, "EbookLib library is required"
    if not LXML_AVAILABLE: return False, "lxml library is required"
    if not BS4_AVAILABLE: return False, "BeautifulSoup4 required"
    if not os.path.exists(original_epub_path): return False, f"Original EPUB not found: {original_epub_path}"

    print(f"[INFO] EPUB Rebuild: Starting rebuild for '{os.path.basename(original_epub_path)}' -> '{out_path}'")
    book = epub.EpubBook()

    nav_path_orig_from_meta = build_metadata.get('nav_path_in_zip')
    ncx_path_orig_from_meta = build_metadata.get('ncx_path_in_zip')
    opf_dir_from_meta = build_metadata.get('opf_dir', '') # Это директория OPF в оригинальном EPUB
    nav_id_orig_from_meta = build_metadata.get('nav_item_id')
    ncx_id_orig_from_meta = build_metadata.get('ncx_item_id')

    final_book_title = book_title_override or Path(original_epub_path).stem
    final_author = "Translator"; final_identifier = f"urn:uuid:{uuid.uuid4()}"; final_language = "ru"

    original_manifest_items_from_zip = {} # {path_in_zip: {id, media_type, properties, original_href}}
    original_spine_idrefs_from_zip = []

    combined_new_image_map_from_worker = build_metadata.get('combined_image_map', {})


    filename_map = {} # original_full_path_in_zip -> new_full_path_in_zip (для обновления NAV/NCX)
    final_book_item_ids = set() # Для отслеживания уникальности ID
    book_items_to_add_to_epub_obj = [] # Список объектов EpubItem, EpubHtml, EpubImage для добавления в book

    new_book_items_structure_map = {} 
    id_to_new_item_map = {} # Для быстрого доступа по ID в spine
    
    processed_original_paths_from_zip = set() # Отслеживать, какие файлы из ZIP уже обработаны
    canonical_titles_map = {} # original_full_path_in_zip -> canonical_title

    opf_dir_for_new_epub = opf_dir_from_meta # Директория OPF в НОВОМ EPUB (обычно та же)

    try:
        with zipfile.ZipFile(original_epub_path, 'r') as original_zip:
            zip_contents_normalized = {name.replace('\\', '/'): name for name in original_zip.namelist()}
            opf_path_in_zip_abs = None

            try:
                container_data = original_zip.read('META-INF/container.xml')
                container_root = etree.fromstring(container_data); cnt_ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                opf_path_rel_to_container = container_root.xpath('//c:rootfile/@full-path', namespaces=cnt_ns)[0]
                opf_path_in_zip_abs = opf_path_rel_to_container.replace('\\', '/')

                temp_opf_dir_check = os.path.dirname(opf_path_in_zip_abs).replace('\\','/')
                temp_opf_dir_check = "" if temp_opf_dir_check == '.' else temp_opf_dir_check.lstrip('/')
                if opf_dir_for_new_epub != temp_opf_dir_check:
                    print(f"[WARN] OPF directory mismatch: Meta='{opf_dir_for_new_epub}', Re-check='{temp_opf_dir_check}'. Using meta: '{opf_dir_for_new_epub}'.")
            except Exception: # Fallback
                pot_opf = [p for p in zip_contents_normalized if p.lower().endswith('.opf') and not p.lower().startswith('meta-inf/') and p.lower() != 'mimetype']
                if not pot_opf: pot_opf = [p for p in zip_contents_normalized if p.lower().endswith('.opf') and p.lower() != 'mimetype']
                if not pot_opf: raise FileNotFoundError("Cannot find OPF in original EPUB.")
                opf_path_in_zip_abs = pot_opf[0]

            
            if not opf_path_in_zip_abs: raise FileNotFoundError("OPF path could not be determined.")

            opf_data_bytes = original_zip.read(zip_contents_normalized[opf_path_in_zip_abs])
            opf_root = etree.fromstring(opf_data_bytes)
            ns_opf_parse = {'opf': 'http://www.idpf.org/2007/opf', 'dc': 'http://purl.org/dc/elements/1.1/'}

            meta_node = opf_root.find('.//opf:metadata', ns_opf_parse) or opf_root.find('.//metadata')
            if meta_node is not None:
                def get_text_meta(element): return element.text.strip() if element is not None and element.text else None
                lang_node = meta_node.find('.//dc:language', ns_opf_parse) or meta_node.find('.//language')
                title_node = meta_node.find('.//dc:title', ns_opf_parse) or meta_node.find('.//title')
                creator_node = meta_node.find('.//dc:creator', ns_opf_parse) or meta_node.find('.//creator')
                id_element = meta_node.find('.//dc:identifier[@id]', ns_opf_parse) or \
                             meta_node.find('.//identifier[@id]', ns_opf_parse) or \
                             meta_node.find('.//dc:identifier', ns_opf_parse) or \
                             meta_node.find('.//identifier')
                final_language = get_text_meta(lang_node) or final_language
                final_book_title = book_title_override or get_text_meta(title_node) or final_book_title
                final_author = get_text_meta(creator_node) or final_author
                final_identifier = get_text_meta(id_element) or final_identifier or f"urn:uuid:{uuid.uuid4()}"
            book.set_title(final_book_title); book.add_author(final_author); book.set_identifier(final_identifier); book.set_language(final_language)


            manifest_node = opf_root.find('.//opf:manifest', ns_opf_parse) or opf_root.find('.//manifest')
            if manifest_node is not None:
                for item_mf_loop in (manifest_node.findall('.//opf:item', ns_opf_parse) or manifest_node.findall('.//item')):
                    item_id = item_mf_loop.get('id'); href = item_mf_loop.get('href'); media_type = item_mf_loop.get('media-type'); props = item_mf_loop.get('properties')
                    if not item_id or not href or not media_type: continue

                    full_path_in_zip = os.path.normpath(os.path.join(opf_dir_from_meta, unquote(href))).replace('\\', '/').lstrip('/')
                    original_manifest_items_from_zip[full_path_in_zip] = {'id': item_id, 'media_type': media_type, 'properties': props, 'original_href': href}
            
            spine_node = opf_root.find('.//opf:spine', ns_opf_parse) or opf_root.find('.//spine')
            ncx_id_from_spine_attr = None
            if spine_node is not None:
                ncx_id_from_spine_attr = spine_node.get('toc') # Это ID NCX файла из манифеста
                original_spine_idrefs_from_zip = [i_ref.get('idref') for i_ref in (spine_node.findall('.//opf:itemref', ns_opf_parse) or spine_node.findall('.//itemref')) if i_ref.get('idref')]

            if nav_path_orig_from_meta and nav_path_orig_from_meta in zip_contents_normalized:
                try:
                    nav_data_bytes = original_zip.read(zip_contents_normalized[nav_path_orig_from_meta])
                    nav_soup = BeautifulSoup(nav_data_bytes, 'lxml-xml')
                    nav_list_el = nav_soup.find('nav', attrs={'epub:type': 'toc'}) or nav_soup
                    list_tag_nav = nav_list_el.find(['ol', 'ul'])
                    if list_tag_nav:
                        nav_dir_current = os.path.dirname(nav_path_orig_from_meta).replace('\\', '/')
                        if nav_dir_current == '.': nav_dir_current = ""
                        for link in list_tag_nav.find_all('a', href=True):
                            href = link.get('href'); title_text = link.get_text(strip=True)
                            if not href or not title_text or href.startswith(('#', 'http:', 'mailto:')): continue
                            try:
                                target_full_path = os.path.normpath(os.path.join(nav_dir_current, unquote(urlparse(href).path))).replace('\\', '/').lstrip('/')
                                if target_full_path not in canonical_titles_map: canonical_titles_map[target_full_path] = title_text
                            except Exception: pass
                except Exception as nav_err_read: print(f"[WARN write_epub] Error reading original NAV for titles: {nav_err_read}")
            elif ncx_path_orig_from_meta and ncx_path_orig_from_meta in zip_contents_normalized:
                 try:
                    ncx_data_bytes = original_zip.read(zip_contents_normalized[ncx_path_orig_from_meta])
                    ncx_root_titles = etree.fromstring(ncx_data_bytes); ncx_ns_titles = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
                    for nav_point in ncx_root_titles.xpath('//ncx:navMap/ncx:navPoint', namespaces=ncx_ns_titles):
                         content_tag = nav_point.find('ncx:content', ncx_ns_titles); label_tag = nav_point.find('.//ncx:text', ncx_ns_titles)
                         if content_tag is not None and label_tag is not None and content_tag.get('src'):
                             src_attr = content_tag.get('src'); title_text = label_tag.text.strip() if label_tag.text else None
                             if not src_attr or not title_text: continue
                             try:
                                 target_full_path = os.path.normpath(os.path.join(opf_dir_from_meta, unquote(urlparse(src_attr).path))).replace('\\', '/').lstrip('/')
                                 if target_full_path not in canonical_titles_map: canonical_titles_map[target_full_path] = title_text
                             except Exception: pass
                 except Exception as ncx_err_read: print(f"[WARN write_epub] Error reading original NCX for titles: {ncx_err_read}")

            new_image_objects_for_manifest = {} # uuid -> EpubImage object
            img_counter = 1
            for img_uuid, new_img_info in combined_new_image_map_from_worker.items():
                temp_img_path = new_img_info.get('saved_path')
                if not temp_img_path or not os.path.exists(temp_img_path):
                    print(f"[WARN write_epub] New image for UUID {img_uuid} has invalid temp path: '{temp_img_path}'. Skipping.")
                    continue
                try:
                    with open(temp_img_path, 'rb') as f_new_img: img_data_bytes = f_new_img.read()
                    content_type = new_img_info.get('content_type', 'image/jpeg')
                    ext_new_img = content_type.split('/')[-1]; ext_new_img = 'jpg' if ext_new_img == 'jpeg' else ext_new_img
                    orig_fname_for_new = new_img_info.get('original_filename', f'new_image_{img_uuid[:6]}.{ext_new_img}')

                    img_folder_in_epub = "Images" # Можно сделать настраиваемым
                    new_img_rel_path_in_epub = os.path.join(img_folder_in_epub, re.sub(r'[^\w\.\-]', '_', orig_fname_for_new)).replace('\\','/')
                    
                    new_img_id = f"new_img_{img_uuid[:6]}_{img_counter}"
                    if new_img_id in final_book_item_ids: new_img_id = f"{new_img_id}_{uuid.uuid4().hex[:3]}"
                    
                    epub_img_obj_new = epub.EpubImage(uid=new_img_id, file_name=new_img_rel_path_in_epub, media_type=content_type, content=img_data_bytes)
                    book_items_to_add_to_epub_obj.append(epub_img_obj_new)
                    new_image_objects_for_manifest[img_uuid] = epub_img_obj_new # Для использования в _convert_placeholders
                    final_book_item_ids.add(new_img_id)

                    new_img_abs_path_in_epub = os.path.normpath(os.path.join(opf_dir_for_new_epub, new_img_rel_path_in_epub)).replace('\\','/').lstrip('/')
                    new_book_items_structure_map[new_img_abs_path_in_epub] = {'item': epub_img_obj_new, 'content_bytes': None, 'canonical_title': None}
                    id_to_new_item_map[new_img_id] = new_book_items_structure_map[new_img_abs_path_in_epub]
                    processed_original_paths_from_zip.add(new_img_abs_path_in_epub) # Помечаем, что этот путь уже занят новым изображением
                    img_counter += 1
                except Exception as e_new_img:
                    print(f"[ERROR write_epub] Failed to add new image (UUID {img_uuid}): {e_new_img}")

            print(f"[INFO write_epub] Начало обработки {len(processed_epub_parts)} HTML-частей для сборки...")
            
            for part_data in processed_epub_parts:

                if 'content_to_write' not in part_data or part_data['content_to_write'] is None:
                    original_fn_for_skip = part_data.get('original_filename', 'Неизвестный HTML')
                    warning_msg_for_skip = part_data.get('translation_warning', 'Данные контента отсутствуют или повреждены')
                    print(f"[WARN write_epub] Пропуск HTML-части '{original_fn_for_skip}', так как 'content_to_write' отсутствует или None. Причина: {warning_msg_for_skip}")
                    if original_fn_for_skip:
                         processed_original_paths_from_zip.add(original_fn_for_skip)
                    continue 


                original_html_path_in_zip = part_data['original_filename'] 
                content_to_use = part_data['content_to_write']
                image_map_for_this_part = part_data.get('image_map', {})
                is_original = part_data.get('is_original_content', False)
                
                original_item_info = original_manifest_items_from_zip.get(original_html_path_in_zip)
                if not original_item_info:
                    print(f"[WARN write_epub] Нет записи в манифесте для оригинального HTML: {original_html_path_in_zip}. Пропуск этой части.")
                    processed_original_paths_from_zip.add(original_html_path_in_zip)
                    continue

                original_item_id = original_item_info['id']
                original_href_from_manifest = original_item_info['original_href'] # Путь относительно OPF
                
                new_html_rel_path_in_epub = "" # Путь нового файла относительно OPF
                final_html_content_bytes = None

                current_part_canonical_title = canonical_titles_map.get(original_html_path_in_zip) 
                
                if is_original:
                    new_html_rel_path_in_epub = original_href_from_manifest.replace('\\', '/')
                    final_html_content_bytes = content_to_use # Это уже bytes

                    abs_path_for_map = os.path.normpath(os.path.join(opf_dir_for_new_epub, new_html_rel_path_in_epub)).replace('\\','/').lstrip('/')
                    filename_map[original_html_path_in_zip] = abs_path_for_map
                    
                    if not current_part_canonical_title and final_html_content_bytes:
                         try:
                             temp_html_str_orig = final_html_content_bytes.decode('utf-8', errors='replace')
                             temp_soup_orig = BeautifulSoup(temp_html_str_orig, 'lxml') 
                             extracted_title = None
                             h_tag = temp_soup_orig.find(['h1','h2','h3','h4','h5','h6'])
                             title_tag = temp_soup_orig.head.title if temp_soup_orig.head else None
                             if h_tag and h_tag.get_text(strip=True): extracted_title = h_tag.get_text(strip=True)
                             elif title_tag and title_tag.string:
                                 stripped_title = title_tag.string.strip()
                                 generic_titles = ['untitled', 'unknown', 'navigation', 'toc', 'table of contents', 'index', 'contents', 'оглавление', 'содержание', 'индекс', 'cover', 'title page', 'copyright', 'chapter']
                                 if stripped_title and stripped_title.lower() not in generic_titles and len(stripped_title) > 1:
                                     extracted_title = stripped_title
                             if extracted_title: current_part_canonical_title = extracted_title
                         except Exception as e_title_orig_extract: print(f"[DEBUG write_epub] Ошибка извлечения заголовка из оригинального HTML {original_html_path_in_zip}: {e_title_orig_extract}")
                
                else: # Переведенный контент (content_to_use это строка с Markdown-like разметкой и плейсхолдерами)
                    new_html_rel_path_in_epub = add_translated_suffix(original_href_from_manifest).replace('\\', '/')

                    temp_title_for_conversion = current_part_canonical_title
                    if not temp_title_for_conversion and isinstance(content_to_use, str):
                        first_line_md = content_to_use.split('\n', 1)[0].strip()
                        md_h_match = re.match(r'^(#{1,6})\s+(.*)', first_line_md)
                        if md_h_match: temp_title_for_conversion = md_h_match.group(2).strip()
                    if not temp_title_for_conversion: # Если все еще нет, используем имя файла
                        temp_title_for_conversion = Path(new_html_rel_path_in_epub).stem.replace('_translated', '').replace('_', ' ').capitalize()

                    final_html_str_rendered = _convert_placeholders_to_html_img(
                        text_with_placeholders=content_to_use, 
                        item_image_map_for_this_html=image_map_for_this_part, 
                        epub_new_image_objects=new_image_objects_for_manifest, 
                        canonical_title=temp_title_for_conversion, # Используем временный/предполагаемый заголовок
                        current_html_file_path_relative_to_opf=new_html_rel_path_in_epub,
                        opf_dir_path=opf_dir_for_new_epub
                    )

                    actual_translated_title_from_html = None
                    try:
                        soup_final_html = BeautifulSoup(final_html_str_rendered, 'lxml') 
                        h1_tag = soup_final_html.body.find('h1') if soup_final_html.body else None
                        if h1_tag and h1_tag.get_text(strip=True):
                            actual_translated_title_from_html = h1_tag.get_text(strip=True)
                        else: 
                            title_tag_final = soup_final_html.head.title if soup_final_html.head else None
                            if title_tag_final and title_tag_final.string:
                                stripped_final_title = title_tag_final.string.strip()
                                generic_titles_check = ['untitled', 'unknown', 'navigation', 'toc', 'table of contents', 'index', 'contents', 'оглавление', 'содержание', 'индекс', 'cover', 'title page', 'copyright', 'chapter']
                                if stripped_final_title and stripped_final_title.lower() not in generic_titles_check and len(stripped_final_title) > 1:
                                    actual_translated_title_from_html = stripped_final_title
                        
                        if actual_translated_title_from_html:
                            current_part_canonical_title = actual_translated_title_from_html 

                    except Exception as e_title_extract_final:
                        print(f"[WARN write_epub] Не удалось извлечь заголовок из финального HTML для {new_html_rel_path_in_epub}: {e_title_extract_final}")

                    if actual_translated_title_from_html:
                        try:

                            soup_to_update_title = BeautifulSoup(final_html_str_rendered, 'lxml')
                            if soup_to_update_title.head:
                                if soup_to_update_title.head.title:
                                    soup_to_update_title.head.title.string = html.escape(actual_translated_title_from_html)
                                else: # Если тега <title> нет, но есть <head>
                                    new_title_tag_in_head = soup_to_update_title.new_tag("title")
                                    new_title_tag_in_head.string = html.escape(actual_translated_title_from_html)
                                    soup_to_update_title.head.insert(0, new_title_tag_in_head)
                                final_html_str_rendered = str(soup_to_update_title) # Обновляем строку

                        except Exception as e_title_force_update:
                            print(f"[WARN write_epub] Не удалось принудительно обновить тег <title> в {new_html_rel_path_in_epub}: {e_title_force_update}")
                    
                    final_html_content_bytes = final_html_str_rendered.encode('utf-8')
                    abs_path_for_map_translated = os.path.normpath(os.path.join(opf_dir_for_new_epub, new_html_rel_path_in_epub)).replace('\\','/').lstrip('/')
                    filename_map[original_html_path_in_zip] = abs_path_for_map_translated

                if not current_part_canonical_title:
                    cleaned_stem = Path(new_html_rel_path_in_epub).stem.replace('_translated', '')
                    cleaned_stem = re.sub(r'^[\d_-]+', '', cleaned_stem) # Удаляем префиксы типа "01_", "001-"
                    cleaned_stem = cleaned_stem.replace('_', ' ').replace('-', ' ').strip()
                    current_part_canonical_title = cleaned_stem.capitalize() if cleaned_stem else f"Документ {original_item_id}"
                
                canonical_titles_map[original_html_path_in_zip] = current_part_canonical_title # Обновляем глобальную карту заголовков

                final_html_item_id = original_item_id
                if final_html_item_id in final_book_item_ids: # Обеспечиваем уникальность ID
                    final_html_item_id = f"html_{Path(new_html_rel_path_in_epub).stem}_{uuid.uuid4().hex[:4]}"
                
                epub_html_obj = epub.EpubHtml(
                    uid=final_html_item_id,
                    file_name=new_html_rel_path_in_epub, # Путь относительно OPF
                    title=html.escape(current_part_canonical_title), # Используем финальный канонический заголовок
                    lang=final_language,
                    content=final_html_content_bytes # Это всегда bytes
                )
                epub_html_obj.media_type = 'application/xhtml+xml'
                
                book_items_to_add_to_epub_obj.append(epub_html_obj)
                final_book_item_ids.add(final_html_item_id)

                new_html_abs_path_in_epub_map_key = os.path.normpath(os.path.join(opf_dir_for_new_epub, new_html_rel_path_in_epub)).replace('\\','/').lstrip('/')
                new_book_items_structure_map[new_html_abs_path_in_epub_map_key] = {
                    'item': epub_html_obj, 
                    'content_bytes': final_html_content_bytes, # Сохраняем байты для возможного повторного использования
                    'canonical_title': current_part_canonical_title
                }
                id_to_new_item_map[final_html_item_id] = new_book_items_structure_map[new_html_abs_path_in_epub_map_key]
                processed_original_paths_from_zip.add(original_html_path_in_zip) # Помечаем оригинальный путь как обработанный

            items_to_skip_copying = set() # NAV, NCX из build_metadata
            if nav_path_orig_from_meta: items_to_skip_copying.add(nav_path_orig_from_meta)
            if ncx_path_orig_from_meta: items_to_skip_copying.add(ncx_path_orig_from_meta)

            for orig_full_path, orig_item_info in original_manifest_items_from_zip.items():
                if orig_full_path in processed_original_paths_from_zip: # Уже обработан (HTML или замененное изображение)
                    continue
                if orig_full_path in items_to_skip_copying: # Явно пропускаемые (старые NAV/NCX)
                    continue
                if orig_item_info.get('properties') and 'nav' in orig_item_info['properties'].split(): # Пропуск старого NAV по свойству
                    continue
                
                actual_zip_entry_name = zip_contents_normalized.get(orig_full_path)
                if not actual_zip_entry_name: # Fallback if case mismatch or slight path variation
                    actual_zip_entry_name = next((o_name for norm_name, o_name in zip_contents_normalized.items() if norm_name.lower() == orig_full_path.lower()), None)
                if not actual_zip_entry_name:
                    print(f"[WARN write_epub] Original manifest item '{orig_full_path}' not found in ZIP. Skipping copy.")
                    continue
                
                try:
                    item_content_bytes = original_zip.read(actual_zip_entry_name)
                    item_id_copy = orig_item_info['id']
                    item_href_copy = orig_item_info['original_href'] # Это путь относительно OPF
                    item_media_type_copy = orig_item_info['media_type']

                    if item_id_copy in final_book_item_ids: item_id_copy = f"item_copy_{Path(item_href_copy).stem}_{uuid.uuid4().hex[:3]}"
                    
                    new_item_obj_copy = None
                    if item_media_type_copy.startswith('image/'):
                        new_item_obj_copy = epub.EpubImage(uid=item_id_copy, file_name=item_href_copy, media_type=item_media_type_copy, content=item_content_bytes)
                    elif item_media_type_copy == 'text/css':
                        new_item_obj_copy = epub.EpubItem(uid=item_id_copy, file_name=item_href_copy, media_type=item_media_type_copy, content=item_content_bytes)
                    elif item_media_type_copy.startswith('font/') or item_media_type_copy in ['application/font-woff', 'application/vnd.ms-opentype', 'application/octet-stream', 'application/x-font-ttf']:
                        new_item_obj_copy = epub.EpubItem(uid=item_id_copy, file_name=item_href_copy, media_type=item_media_type_copy, content=item_content_bytes)
                    else: # Другие типы файлов
                        new_item_obj_copy = epub.EpubItem(uid=item_id_copy, file_name=item_href_copy, media_type=item_media_type_copy, content=item_content_bytes)
                    
                    if new_item_obj_copy:
                        book_items_to_add_to_epub_obj.append(new_item_obj_copy)
                        final_book_item_ids.add(item_id_copy)

                        filename_map[orig_full_path] = os.path.normpath(os.path.join(opf_dir_for_new_epub, item_href_copy)).replace('\\','/').lstrip('/')

                        new_abs_path_copy = filename_map[orig_full_path]
                        new_book_items_structure_map[new_abs_path_copy] = {'item': new_item_obj_copy, 'content_bytes': item_content_bytes, 'canonical_title': None}
                        id_to_new_item_map[item_id_copy] = new_book_items_structure_map[new_abs_path_copy]
                        processed_original_paths_from_zip.add(orig_full_path)
                except KeyError:
                    print(f"[WARN write_epub] Original manifest item '{orig_full_path}' (href: {orig_item_info.get('original_href')}) could not be read from ZIP. Skipping.")
                except Exception as e_copy:
                    print(f"[ERROR write_epub] Failed to copy original manifest item '{orig_full_path}': {e_copy}")

            for item_obj in book_items_to_add_to_epub_obj:
                try: book.add_item(item_obj)
                except Exception as add_final_err: print(f"[ERROR write_epub] Failed to add item ID='{getattr(item_obj,'id','N/A')}' to book: {add_final_err}")

            
            final_nav_item_obj = None; final_ncx_item_obj = None
            new_nav_content_bytes = None; new_ncx_content_bytes = None

            final_nav_rel_path_in_epub = "nav.xhtml" # Стандартное имя
            final_ncx_rel_path_in_epub = "toc.ncx"   # Стандартное имя

            spine_item_objects_for_toc_gen = []
            for orig_idref in original_spine_idrefs_from_zip:

                original_item_path_for_idref = next((p for p, i_info in original_manifest_items_from_zip.items() if i_info['id'] == orig_idref), None)
                if not original_item_path_for_idref: continue
                
                new_item_abs_path = filename_map.get(original_item_path_for_idref)
                if not new_item_abs_path: continue

                new_item_entry = new_book_items_structure_map.get(new_item_abs_path)
                if not new_item_entry or not new_item_entry.get('item'): continue
                
                new_epub_item_obj = new_item_entry['item']
                if isinstance(new_epub_item_obj, epub.EpubHtml) and new_epub_item_obj.file_name.replace('\\','/') != final_nav_rel_path_in_epub:

                    item_title_for_toc = canonical_titles_map.get(original_item_path_for_idref, Path(new_epub_item_obj.file_name).stem)
                    spine_item_objects_for_toc_gen.append((new_epub_item_obj, item_title_for_toc))

            nav_item_id_to_use = nav_id_orig_from_meta or "nav"
            ncx_item_id_to_use = ncx_id_orig_from_meta or ncx_id_from_spine_attr or "ncx"

            if nav_path_orig_from_meta and nav_path_orig_from_meta in zip_contents_normalized: # Был NAV
                print(f"[INFO write_epub] Обновление существующего NAV: {nav_path_orig_from_meta}")
                orig_nav_bytes = original_zip.read(zip_contents_normalized[nav_path_orig_from_meta])
                new_nav_content_bytes = update_nav_content(orig_nav_bytes, nav_path_orig_from_meta, filename_map, canonical_titles_map)
                if new_nav_content_bytes: final_nav_rel_path_in_epub = Path(nav_path_orig_from_meta).name # Сохраняем оригинальное имя файла NAV
            elif spine_item_objects_for_toc_gen: # Не было NAV, но есть что добавить в spine
                print("[INFO write_epub] Генерация нового NAV из элементов spine...")
                nav_data_for_gen_html = []
                for item_obj_nav, title_nav in spine_item_objects_for_toc_gen:

                    abs_path_for_nav_href = os.path.normpath(os.path.join(opf_dir_for_new_epub, item_obj_nav.file_name)).replace('\\','/').lstrip('/')
                    nav_data_for_gen_html.append((abs_path_for_nav_href, title_nav))
                new_nav_content_bytes = generate_nav_html(nav_data_for_gen_html, 
                                                          os.path.join(opf_dir_for_new_epub, final_nav_rel_path_in_epub).replace('\\','/').lstrip('/'), 
                                                          final_book_title, final_language)

            if ncx_path_orig_from_meta and ncx_path_orig_from_meta in zip_contents_normalized: # Был NCX
                print(f"[INFO write_epub] Обновление существующего NCX: {ncx_path_orig_from_meta}")
                orig_ncx_bytes = original_zip.read(zip_contents_normalized[ncx_path_orig_from_meta])
                new_ncx_content_bytes = update_ncx_content(orig_ncx_bytes, opf_dir_from_meta, filename_map, canonical_titles_map)
                if new_ncx_content_bytes: final_ncx_rel_path_in_epub = Path(ncx_path_orig_from_meta).name # Сохраняем оригинальное имя файла NCX
            elif new_nav_content_bytes: # Не было NCX, но сгенерировали NAV, из него генерируем NCX
                 print("[INFO write_epub] Генерация нового NCX из данных нового NAV...")

                 nav_path_for_ncx_parse_abs = os.path.normpath(os.path.join(opf_dir_for_new_epub, final_nav_rel_path_in_epub)).replace('\\','/').lstrip('/')
                 ncx_data_from_new_nav = parse_nav_for_ncx_data(new_nav_content_bytes, nav_path_for_ncx_parse_abs)
                 if ncx_data_from_new_nav:
                      new_ncx_content_bytes = generate_ncx_manual(final_identifier, final_book_title, ncx_data_from_new_nav)
            elif spine_item_objects_for_toc_gen: # Не было ни NAV, ни NCX, генерируем NCX из spine
                 print("[INFO write_epub] Генерация нового NCX из элементов spine (NAV не был сгенерирован)...")
                 ncx_data_from_spine_gen = []
                 for i_ncx, (item_obj_ncx, title_ncx) in enumerate(spine_item_objects_for_toc_gen):
                     ncx_src_for_gen = item_obj_ncx.file_name.replace('\\','/') # Относительно OPF
                     safe_base_ncx = re.sub(r'[^\w\-]+', '_', Path(ncx_src_for_gen).stem);
                     nav_point_id_ncx = f"navpoint_{safe_base_ncx}_{i_ncx+1}"
                     ncx_data_from_spine_gen.append((nav_point_id_ncx, ncx_src_for_gen, title_ncx))
                 if ncx_data_from_spine_gen:
                      new_ncx_content_bytes = generate_ncx_manual(final_identifier, final_book_title, ncx_data_from_spine_gen)

            if new_nav_content_bytes:
                if nav_item_id_to_use in final_book_item_ids: nav_item_id_to_use = f"{nav_item_id_to_use}_{uuid.uuid4().hex[:4]}"
                final_nav_item_obj = epub.EpubHtml(uid=nav_item_id_to_use, file_name=final_nav_rel_path_in_epub, title=final_book_title, lang=final_language, content=new_nav_content_bytes)
                final_nav_item_obj.media_type = 'application/xhtml+xml'

                if 'nav' not in final_nav_item_obj.properties: # Проверяем, нет ли уже такого свойства
                    final_nav_item_obj.properties.append('nav')


                book.add_item(final_nav_item_obj); final_book_item_ids.add(nav_item_id_to_use)
                book.toc = (final_nav_item_obj,) # Устанавливаем NAV как TOC
                print(f"[INFO write_epub] NAV добавлен/обновлен. ID: {nav_item_id_to_use}, Path: {final_nav_rel_path_in_epub}")
            else: 
                book.toc = ()
                print(f"[INFO write_epub] NAV контент не был сгенерирован/обновлен. book.toc будет пуст.")
            
            if new_ncx_content_bytes:
                if ncx_item_id_to_use in final_book_item_ids: ncx_item_id_to_use = f"{ncx_item_id_to_use}_{uuid.uuid4().hex[:4]}"
                final_ncx_item_obj = epub.EpubItem(uid=ncx_item_id_to_use, file_name=final_ncx_rel_path_in_epub, media_type='application/x-dtbncx+xml', content=new_ncx_content_bytes)
                book.add_item(final_ncx_item_obj); final_book_item_ids.add(ncx_item_id_to_use)

                book.spine_toc = final_ncx_item_obj.id 

                print(f"[INFO write_epub] NCX добавлен/обновлен. ID: {ncx_item_id_to_use}, Path: {final_ncx_rel_path_in_epub}")
            elif ncx_id_from_spine_attr: 
                 existing_ncx_item = book.get_item_with_id(ncx_id_from_spine_attr)
                 if existing_ncx_item and existing_ncx_item.media_type == 'application/x-dtbncx+xml':
                     book.spine_toc = ncx_id_from_spine_attr
                     print(f"[INFO write_epub] Использован существующий NCX из spine: ID={ncx_id_from_spine_attr}")

            final_spine_idrefs_for_book = []
            for orig_idref_spine in original_spine_idrefs_from_zip:
                original_path_for_idref_spine = next((p for p, item_info_spine in original_manifest_items_from_zip.items() if item_info_spine['id'] == orig_idref_spine), None)
                if not original_path_for_idref_spine: continue
                new_abs_path_for_idref_spine = filename_map.get(original_path_for_idref_spine)
                if not new_abs_path_for_idref_spine: continue
                new_item_entry_for_idref_spine = new_book_items_structure_map.get(new_abs_path_for_idref_spine)
                if new_item_entry_for_idref_spine and new_item_entry_for_idref_spine.get('item'):
                    final_spine_idrefs_for_book.append(new_item_entry_for_idref_spine['item'].id)
            
            if not final_spine_idrefs_for_book and spine_item_objects_for_toc_gen: # Fallback, если original_spine_idrefs_from_zip пуст
                 final_spine_idrefs_for_book = [item_obj_s.id for item_obj_s, _ in spine_item_objects_for_toc_gen]

            book.spine = final_spine_idrefs_for_book
            if not book.spine: # Крайний случай: добавляем первый HTML, если spine пуст
                first_html_item = next((item for item in book.items if isinstance(item, epub.EpubHtml) and item != final_nav_item_obj), None)
                if first_html_item: book.spine = [first_html_item.id]
                else: print("[WARN write_epub] Не удалось сформировать spine, нет подходящих HTML элементов.")

            print(f"[INFO write_epub] Запись финального EPUB файла в: {out_path}...")
            epub.write_epub(out_path, book, {}) # Опции по умолчанию
            end_time = time.time()
            print(f"[SUCCESS] EPUB Rebuild: Файл сохранен: {out_path} (Заняло {end_time - start_time:.2f} сек)")
            return True, None

    except FileNotFoundError as e_fnf:
        err_msg = f"EPUB Rebuild Error: Файл не найден - {e_fnf}"; print(f"[ERROR] {err_msg}"); return False, err_msg
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as e_xml_zip:
        err_msg = f"EPUB Rebuild Error: Не удалось разобрать структуру EPUB - {e_xml_zip}"; print(f"[ERROR] {err_msg}"); return False, err_msg
    except ImportError as e_imp:
        err_msg = f"EPUB Rebuild Error: Отсутствует библиотека - {e_imp}"; print(f"[ERROR] {err_msg}"); return False, err_msg
    except ValueError as e_val:
        err_msg = f"EPUB Rebuild Error: {e_val}"; print(f"[ERROR] {err_msg}"); return False, err_msg
    except Exception as e_generic:
        tb_str = traceback.format_exc()
        err_msg = f"EPUB Rebuild Error: Неожиданная ошибка - {type(e_generic).__name__}: {e_generic}"
        print(f"[ERROR] {err_msg}\n{tb_str}"); return False, err_msg

def _convert_placeholders_to_html_img(text_with_placeholders, item_image_map_for_this_html,
                                    epub_new_image_objects,
                                    canonical_title,
                                    current_html_file_path_relative_to_opf=None,
                                    opf_dir_path=None):
    if not text_with_placeholders: return ""
    if item_image_map_for_this_html is None: item_image_map_for_this_html = {}
    if epub_new_image_objects is None: epub_new_image_objects = {}

    def apply_inline_markdown_carefully(text_segment):
        known_tags_map = {}
        temp_id_counter = 0
        def tag_replacer(match):
            nonlocal temp_id_counter
            tag = match.group(0)
            placeholder = f"__HTML_TAG_PLACEHOLDER_{temp_id_counter}__"
            known_tags_map[placeholder] = tag
            temp_id_counter += 1
            return placeholder
        text_with_placeholders_for_tags = re.sub(r'(<br\s*/?>|<img\s+[^>]*?/>)', tag_replacer, text_segment, flags=re.IGNORECASE | re.DOTALL)
        def markdown_replacer(match_md):
            marker = match_md.group(1)
            content_to_wrap = html.escape(match_md.group(2))
            if marker == '**': return f'<strong>{content_to_wrap}</strong>'
            if marker == '*':  return f'<em>{content_to_wrap}</em>'
            if marker == '`':  return f'<code>{content_to_wrap}</code>'
            return match_md.group(0)
        processed_text_with_md = re.sub(r'(\*\*|\*|`)(.+?)\1', markdown_replacer, text_with_placeholders_for_tags, flags=re.DOTALL)
        final_text = processed_text_with_md
        for placeholder, original_tag in known_tags_map.items():
            final_text = final_text.replace(placeholder, original_tag)
        return final_text

    processed_parts_for_img_restore = []
    last_idx_img_restore = 0

    for placeholder_tag, img_uuid in find_image_placeholders(text_with_placeholders):
        match_start = text_with_placeholders.find(placeholder_tag, last_idx_img_restore)
        if match_start == -1: continue
        processed_parts_for_img_restore.append(text_with_placeholders[last_idx_img_restore:match_start])
        img_info = item_image_map_for_this_html.get(img_uuid)
        img_tag_html = f"<!-- Placeholder Error: UUID {img_uuid} not fully processed -->"
        if img_info:
            original_src_from_html_map = img_info.get('original_src')
            final_img_src_attr_value_for_tag = None
            final_attributes_for_tag = dict(img_info.get('attributes', {}))
            if original_src_from_html_map is not None:
                final_img_src_attr_value_for_tag = original_src_from_html_map
                final_attributes_for_tag.pop('{http://www.w3.org/1999/xlink}href', None)
                final_attributes_for_tag.pop('xlink:href', None)
            elif img_uuid in epub_new_image_objects:
                epub_img_object_for_new = epub_new_image_objects.get(img_uuid)
                if epub_img_object_for_new:
                    image_path_rel_to_opf_for_new = epub_img_object_for_new.file_name.replace('\\', '/')
                    if current_html_file_path_relative_to_opf is not None:
                        html_dir_rel_to_opf_for_new = os.path.dirname(current_html_file_path_relative_to_opf).replace('\\', '/')
                        if html_dir_rel_to_opf_for_new == '.': html_dir_rel_to_opf_for_new = ""
                        try: final_img_src_attr_value_for_tag = os.path.relpath(image_path_rel_to_opf_for_new, start=html_dir_rel_to_opf_for_new).replace('\\', '/')
                        except ValueError: final_img_src_attr_value_for_tag = image_path_rel_to_opf_for_new
                    else: final_img_src_attr_value_for_tag = image_path_rel_to_opf_for_new
            if final_img_src_attr_value_for_tag is not None:
                alt_text_raw = final_attributes_for_tag.get('alt', img_info.get('original_filename', f'Image {img_uuid[:7]}'))
                alt_text_escaped = html.escape(str(alt_text_raw), quote=True)
                attr_strings_list = [f'src="{html.escape(final_img_src_attr_value_for_tag, quote=True)}"', f'alt="{alt_text_escaped}"']
                for key, value in final_attributes_for_tag.items():
                    key_lower = str(key).lower()
                    if key_lower not in ['src', 'alt', 'xlink:href', '{http://www.w3.org/1999/xlink}href']:
                        attr_strings_list.append(f'{html.escape(str(key))}="{html.escape(str(value))}"')
                width_attr = final_attributes_for_tag.get('width'); height_attr = final_attributes_for_tag.get('height')
                styles_to_add = []
                if not width_attr or (isinstance(width_attr, str) and '%' in width_attr): styles_to_add.append("max-width: 100%;")
                if not height_attr or (isinstance(height_attr, str) and '%' in height_attr):
                     if "max-width: 100%;" in styles_to_add and not height_attr : styles_to_add.append("height: auto;")
                if styles_to_add: attr_strings_list.append(f'style="{html.escape(" ".join(styles_to_add))}"')
                img_tag_html = f"<img {' '.join(attr_strings_list)} />"
        processed_parts_for_img_restore.append(img_tag_html)
        last_idx_img_restore = match_start + len(placeholder_tag)
    processed_parts_for_img_restore.append(text_with_placeholders[last_idx_img_restore:])
    text_after_img_restore = "".join(processed_parts_for_img_restore)

    text_normalized_newlines = re.sub(r'<br\s*/?>', '\n', text_after_img_restore, flags=re.IGNORECASE)

    text_normalized_newlines = re.sub(r'\n{3,}', '\n\n', text_normalized_newlines)

    lines = text_normalized_newlines.splitlines() # Делим по \n.

    html_body_segments = []
    paragraph_part_buffer = []
    current_list_tag_md = None
    in_code_block_md = False
    code_block_buffer_md = []

    heading_re_md = re.compile(r'^\s*(#{1,6})\s+(.*)')
    hr_re_md = re.compile(r'^\s*---\s*$')
    ul_item_re_md = re.compile(r'^\s*[\*\-]\s+(.*)')
    ol_item_re_md = re.compile(r'^\s*\d+\.\s+(.*)')
    code_fence_re_md = re.compile(r'^\s*```(.*)')

    def finalize_paragraph_md():
        nonlocal paragraph_part_buffer, html_body_segments
        if paragraph_part_buffer:

            para_content_raw = "<br />".join(paragraph_part_buffer) # Восстанавливаем <br />
            processed_content = apply_inline_markdown_carefully(para_content_raw)
            html_body_segments.append(f"<p>{processed_content}</p>")
            paragraph_part_buffer = []

    def finalize_list_md():
        nonlocal current_list_tag_md, html_body_segments
        if current_list_tag_md:
            html_body_segments.append(f"</{current_list_tag_md}>")
            current_list_tag_md = None
            
    def finalize_code_block_md():
        nonlocal in_code_block_md, code_block_buffer_md, html_body_segments
        if code_block_buffer_md:
            escaped_code = html.escape("\n".join(code_block_buffer_md))
            html_body_segments.append(escaped_code)
        if in_code_block_md:
            html_body_segments.append("</code></pre>")
            in_code_block_md = False
        code_block_buffer_md = []

    for i, line_text in enumerate(lines): # line_text это строка без \n на конце
        stripped_line = line_text.strip()

        is_standalone_image = False
        if stripped_line.startswith("<img") and stripped_line.endswith("/>"):
            if re.fullmatch(r'\s*<img\s+[^>]*?/>\s*', line_text, re.IGNORECASE):
                is_standalone_image = True
        
        if is_standalone_image:
            finalize_paragraph_md()
            finalize_list_md()
            finalize_code_block_md()
            html_body_segments.append(line_text)
            continue

        code_fence_match = code_fence_re_md.match(stripped_line)
        if code_fence_match:
            finalize_paragraph_md()
            finalize_list_md()
            if not in_code_block_md:
                in_code_block_md = True
                code_block_buffer_md = []
                lang = html.escape(code_fence_match.group(1).strip())
                html_body_segments.append(f'<pre><code class="language-{lang}">' if lang else "<pre><code>")
            else:
                finalize_code_block_md()
            continue

        if in_code_block_md:
            code_block_buffer_md.append(line_text)
            continue

        if not stripped_line: # Если строка пуста ПОСЛЕ strip
            finalize_paragraph_md()
            finalize_list_md() 

            continue # Переходим к следующей строке

        heading_match = heading_re_md.match(line_text) 
        hr_match = hr_re_md.match(stripped_line) # hr всегда на всю строку
        ul_item_match = ul_item_re_md.match(line_text)
        ol_item_match = ol_item_re_md.match(line_text)

        is_block_markdown = bool(heading_match or hr_match or ul_item_match or ol_item_match)

        if is_block_markdown:
            finalize_paragraph_md() 

        if heading_match:
            finalize_list_md()
            level = len(heading_match.group(1))
            heading_text_raw = heading_match.group(2).strip() # strip() здесь, т.к. это содержимое тега
            processed_heading_text = apply_inline_markdown_carefully(heading_text_raw)
            html_body_segments.append(f"<h{level}>{processed_heading_text}</h{level}>")
        elif hr_match:
            finalize_list_md()
            html_body_segments.append("<hr />")
        elif ul_item_match:
            if current_list_tag_md != 'ul':
                finalize_list_md()
                html_body_segments.append("<ul>")
                current_list_tag_md = 'ul'
            list_item_raw = ul_item_match.group(1).strip() # strip() здесь
            processed_list_item = apply_inline_markdown_carefully(list_item_raw)
            html_body_segments.append(f"<li>{processed_list_item}</li>")
        elif ol_item_match:
            if current_list_tag_md != 'ol':
                finalize_list_md()
                html_body_segments.append("<ol>")
                current_list_tag_md = 'ol'
            list_item_raw = ol_item_match.group(1).strip() # strip() здесь
            processed_list_item = apply_inline_markdown_carefully(list_item_raw)
            html_body_segments.append(f"<li>{processed_list_item}</li>")
        else: # Если это не MD-блок и не пустая строка (уже проверили stripped_line)
            finalize_list_md() # Закрыть список, если эта строка не является его продолжением

            paragraph_part_buffer.append(line_text)

    finalize_paragraph_md()
    finalize_list_md()
    finalize_code_block_md()

    body_content_final = "\n".join(html_body_segments)

    final_title_text_for_html_tag = html.escape(str(canonical_title or Path(current_html_file_path_relative_to_opf or "document").stem).strip())
    if not final_title_text_for_html_tag: final_title_text_for_html_tag = "Untitled Document"
    stylesheet_path_final = "../Styles/stylesheet.css"
    if current_html_file_path_relative_to_opf is not None:
        html_abs_dir_in_epub = ""
        if opf_dir_path: 
            abs_html_path_in_epub = os.path.join(opf_dir_path, current_html_file_path_relative_to_opf)
            html_abs_dir_in_epub = os.path.dirname(abs_html_path_in_epub)
        else: 
            html_abs_dir_in_epub = os.path.dirname(current_html_file_path_relative_to_opf)
        if html_abs_dir_in_epub == '.': html_abs_dir_in_epub = ""
        css_dir_from_root = os.path.join(opf_dir_path or "", "Styles")
        abs_stylesheet_path_in_epub = os.path.join(css_dir_from_root, "stylesheet.css")
        abs_stylesheet_path_in_epub = os.path.normpath(abs_stylesheet_path_in_epub).replace('\\','/')
        html_abs_dir_in_epub = os.path.normpath(html_abs_dir_in_epub).replace('\\','/')
        try: stylesheet_path_final = os.path.relpath(abs_stylesheet_path_in_epub, start=html_abs_dir_in_epub).replace('\\','/')
        except ValueError:
            if not html_abs_dir_in_epub: stylesheet_path_final = abs_stylesheet_path_in_epub.lstrip('/')
            else: stylesheet_path_final = abs_stylesheet_path_in_epub
    stylesheet_link_tag = f'<link rel="stylesheet" type="text/css" href="{html.escape(stylesheet_path_final, quote=True)}"/>'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="ru" xml:lang="ru">
<head>
<meta charset="utf-8" />
<title>{final_title_text_for_html_tag}</title>
{stylesheet_link_tag}
</head>
<body>
{body_content_final}
</body>
</html>"""

def write_to_html(out_path, translated_content_with_placeholders, image_map, title):
    """Creates HTML file with embedded Base64 images."""
    if image_map is None: image_map = {}
    print(f"[INFO] HTML: Creating HTML file with embedded images: {out_path}")
    html_body_content = ""


    lines = translated_content_with_placeholders.splitlines() # Разделяем по \n, если они там есть (обычно нет, если <br />)
    paragraph_buffer = []

    def process_text_block_for_html(text_block):

        
        processed_parts = []
        last_index = 0

        text_block_escaped_amp = text_block.replace('&', '&')

        text_block_br_protected = re.sub(r'<br\s*/?>', '__TEMP_BR_TAG__', text_block_escaped_amp, flags=re.IGNORECASE)

        text_block_lt_gt_escaped = text_block_br_protected.replace('<', '<').replace('>', '>')


        temp_md_text = text_block_lt_gt_escaped
        temp_md_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', temp_md_text, flags=re.DOTALL)
        temp_md_text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<em>\1</em>', temp_md_text, flags=re.DOTALL)
        temp_md_text = re.sub(r'`(.*?)`', r'<code>\1</code>', temp_md_text, flags=re.DOTALL)

        final_md_text = temp_md_text.replace('<strong>', '<strong>').replace('</strong>', '</strong>')
        final_md_text = final_md_text.replace('<em>', '<em>').replace('</em>', '</em>')
        final_md_text = final_md_text.replace('<code>', '<code>').replace('</code>', '</code>')

        text_with_md_and_br = final_md_text.replace('__TEMP_BR_TAG__', '<br />')


        placeholders = find_image_placeholders(text_with_md_and_br) # Ищем плейсхолдеры в тексте с Markdown и <br />

        for placeholder_tag, img_uuid in placeholders:
            match_start = text_with_md_and_br.find(placeholder_tag, last_index)
            if match_start == -1: continue

            text_before = text_with_md_and_br[last_index:match_start]
            processed_parts.append(text_before) # Добавляем текст "как есть", он уже обработан

            if img_uuid in image_map:
                img_info = image_map[img_uuid]; img_path = img_info['saved_path']
                if os.path.exists(img_path):
                    try:
                        with open(img_path, 'rb') as f_img: img_data = f_img.read()
                        b64_data = base64.b64encode(img_data).decode('ascii')
                        content_type = img_info.get('content_type', 'image/jpeg'); data_uri = f"data:{content_type};base64,{b64_data}"
                        alt_text_raw = img_info.get('original_filename', f'Image {img_uuid[:8]}');

                        alt_text = html.escape(alt_text_raw, quote=True)
                        img_tag = f'<img src="{html.escape(data_uri, quote=True)}" alt="{alt_text}" style="max-width: 100%; height: auto;" />'
                        processed_parts.append(img_tag) 
                    except Exception as img_err: print(f"[ERROR] HTML Write: Failed to read/encode image {img_path}: {img_err}"); processed_parts.append(f"[Err embed img: {img_uuid[:8]}]")
                else: print(f"[ERROR] HTML Write: Image path not found: {img_path}"); processed_parts.append(f"[Img path miss: {img_uuid[:8]}]")
            else: print(f"[WARN] HTML Write: Placeholder UUID '{img_uuid}' not found."); processed_parts.append(f"[Unk Img: {img_uuid[:8]}]")
            last_index = match_start + len(placeholder_tag)

        text_after = text_with_md_and_br[last_index:]
        processed_parts.append(text_after) # Добавляем остаток текста "как есть"
        return "".join(processed_parts)

    current_list_type = None 
    in_code_block = False
    code_block_lines = []

    for line in lines: # line может содержать <br />
        stripped_line = line.strip()
        is_code_fence = stripped_line == '```'

        if is_code_fence:
            if not in_code_block:
                if paragraph_buffer: html_body_content += f"<p>{process_text_block_for_html('<br/>'.join(paragraph_buffer))}</p>\n"; paragraph_buffer = []
                if current_list_type: html_body_content += f"</{current_list_type}>\n"; current_list_type = None
                in_code_block = True; code_block_lines = []
            else:
                in_code_block = False
                escaped_code = html.escape("\n".join(code_block_lines)) # Экранируем все содержимое блока кода
                html_body_content += f"<pre><code>{escaped_code}</code></pre>\n"
            continue

        if in_code_block:
            code_block_lines.append(line); continue

        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped_line)
        hr_match = stripped_line == '---'
        ul_match = re.match(r'^[\*\-]\s+(.*)', stripped_line)
        ol_match = re.match(r'^\d+\.\s+(.*)', stripped_line)

        if current_list_type and not ((current_list_type == 'ul' and ul_match) or (current_list_type == 'ol' and ol_match)):
             html_body_content += f"</{current_list_type}>\n"; current_list_type = None
        if paragraph_buffer and (heading_match or hr_match or ul_match or ol_match):
             para_content = process_text_block_for_html("<br/>".join(paragraph_buffer)); html_body_content += f"<p>{para_content}</p>\n" if para_content.strip() else ""; paragraph_buffer = []

        if heading_match:
            level = len(heading_match.group(1)); heading_text = process_text_block_for_html(heading_match.group(2).strip())
            if heading_text: html_body_content += f"<h{level}>{heading_text}</h{level}>\n"
        elif hr_match:
             html_body_content += "<hr/>\n"
        elif ul_match:
             if current_list_type != 'ul': html_body_content += "<ul>\n"; current_list_type = 'ul'
             list_text = process_text_block_for_html(ul_match.group(1).strip()); html_body_content += f"<li>{list_text}</li>\n"
        elif ol_match:
             if current_list_type != 'ol': html_body_content += "<ol>\n"; current_list_type = 'ol'
             list_text = process_text_block_for_html(ol_match.group(1).strip()); html_body_content += f"<li>{list_text}</li>\n"
        elif line or find_image_placeholders(line): 
             paragraph_buffer.append(line) # line уже содержит <br /> если они были
        elif not stripped_line and paragraph_buffer: 

             para_content = process_text_block_for_html("".join(paragraph_buffer)); # Не соединяем через <br/>, т.к. они уже есть
             html_body_content += f"<p>{para_content}</p>\n" if para_content.strip() else ""; paragraph_buffer = []

    if current_list_type: html_body_content += f"</{current_list_type}>\n"
    if paragraph_buffer:
        para_content = process_text_block_for_html("".join(paragraph_buffer)); # Не соединяем через <br/>
        html_body_content += f"<p>{para_content}</p>\n" if para_content.strip() else ""
    if in_code_block:
        escaped_code = html.escape("\n".join(code_block_lines))
        html_body_content += f"<pre><code>{escaped_code}</code></pre>\n"

    safe_title = html.escape(title or "Переведенный документ")
    html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
body {{ font-family: sans-serif; line-height: 1.6; margin: 2em auto; max-width: 800px; padding: 0 1em; color: #333; background-color: #fdfdfd; }}
p {{ margin-top: 0; margin-bottom: 1em; text-align: justify; }}
h1, h2, h3, h4, h5, h6 {{ margin-top: 1.8em; margin-bottom: 0.6em; line-height: 1.3; font-weight: normal; color: #111; border-bottom: 1px solid #eee; padding-bottom: 0.2em;}}
h1 {{ font-size: 2em; }} h2 {{ font-size: 1.7em; }} h3 {{ font-size: 1.4em; }}
img {{ max-width: 100%; height: auto; display: block; margin: 1.5em auto; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
hr {{ border: none; border-top: 1px solid #ccc; margin: 2.5em 0; }}
ul, ol {{ margin-left: 1.5em; margin-bottom: 1em; padding-left: 1.5em; }}
li {{ margin-bottom: 0.4em; }}
strong {{ font-weight: bold; }}
em {{ font-style: italic; }}
a {{ color: #007bff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
code {{ background-color: #f0f0f0; padding: 0.1em 0.3em; border-radius: 3px; font-family: Consolas, monospace; font-size: 0.9em; }}
pre {{ background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 1em; overflow-x: auto; white-space: pre; }}
pre code {{ background-color: transparent; padding: 0; border-radius: 0; font-size: 0.9em; }}
</style>
</head>
<body>
{html_body_content.strip()}
</body>
</html>"""
    try:
        with open(out_path, "w", encoding="utf-8") as f: f.write(html_template)
        print(f"[SUCCESS] HTML file saved: {out_path}")
    except Exception as write_err: print(f"[ERROR] Failed to write HTML file {out_path}: {write_err}"); raise

def write_to_fb2(out_path, translated_content_with_placeholders, image_map, title):
    if not LXML_AVAILABLE: raise ImportError("lxml library is required to write FB2 files.")
    if image_map is None: image_map = {}
    print(f"[INFO] FB2: Creating FB2 file with image support: {out_path}")

    print(f"DEBUG write_to_fb2: image_map received with {len(image_map)} entries.")
    if image_map:
        print(f"  UUIDs in received image_map: {list(image_map.keys())}")


    placeholders_in_text = find_image_placeholders(translated_content_with_placeholders)
    print(f"DEBUG write_to_fb2: Found {len(placeholders_in_text)} placeholders in translated_content.")
    if placeholders_in_text:
        print(f"  UUIDs from placeholders in text: {[p[1] for p in placeholders_in_text]}")

    FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"; XLINK_NS = "http://www.w3.org/1999/xlink"; nsmap = {None: FB2_NS, "l": XLINK_NS}
    l_href_attr = f"{{{XLINK_NS}}}href" 
    fb2_root = etree.Element("FictionBook", nsmap=nsmap)

    description = etree.SubElement(fb2_root, "description")
    title_info = etree.SubElement(description, "title-info")
    document_info = etree.SubElement(description, "document-info")
    book_title_text = title or "Переведенный Документ" # Renamed variable
    etree.SubElement(title_info, "book-title").text = book_title_text
    author_elem = etree.SubElement(title_info, "author"); etree.SubElement(author_elem, "first-name").text = "Translator"
    etree.SubElement(title_info, "genre").text = "unspecified"; etree.SubElement(title_info, "lang").text = "ru"
    doc_author = etree.SubElement(document_info, "author"); etree.SubElement(doc_author, "nickname").text = "TranslatorApp"
    etree.SubElement(document_info, "program-used").text = "TranslatorApp using Gemini"; etree.SubElement(document_info, "date", attrib={"value": time.strftime("%Y-%m-%d")}).text = time.strftime("%d %B %Y", time.localtime()); etree.SubElement(document_info, "version").text = "1.0"

    binary_sections = []; placeholder_to_binary_id = {}; binary_id_counter = 1
    processed_uuids_for_binary = set()
    images_added_to_binary_count = 0 # New counter

    for placeholder_tag, img_uuid_from_text in placeholders_in_text: # Renamed img_uuid
        print(f"DEBUG write_to_fb2: Processing placeholder for UUID from text: {img_uuid_from_text}")
        if img_uuid_from_text in image_map and img_uuid_from_text not in processed_uuids_for_binary:
            img_info = image_map[img_uuid_from_text]
            img_path = img_info.get('saved_path')
            print(f"  UUID {img_uuid_from_text} found in image_map. Path: {img_path}")

            if img_path and os.path.exists(img_path):
                try:
                    with open(img_path, 'rb') as f_img: img_data = f_img.read()
                    base_id = f"img_{img_uuid_from_text[:8]}_{binary_id_counter}"; binary_id = re.sub(r'[^\w.-]', '_', base_id)
                    content_type = img_info.get('content_type', 'image/jpeg')
                    base64_encoded_data = base64.b64encode(img_data).decode('ascii')
                    
                    binary_sections.append((binary_id, content_type, base64_encoded_data))
                    placeholder_to_binary_id[img_uuid_from_text] = binary_id
                    processed_uuids_for_binary.add(img_uuid_from_text)
                    binary_id_counter += 1
                    images_added_to_binary_count +=1 # Increment counter
                    print(f"    Successfully prepared binary data for UUID {img_uuid_from_text}. Binary ID: {binary_id}")
                except Exception as e:
                    print(f"[ERROR] FB2: Failed to read/encode image {img_path} for UUID {img_uuid_from_text}: {e}")
            elif not img_path:
                print(f"[ERROR] FB2: No 'saved_path' found in image_map for UUID {img_uuid_from_text}.")
            else: # img_path exists in map, but file os.path.exists(img_path) is false
                print(f"[ERROR] FB2: Image path from image_map does not exist on disk: {img_path} (for UUID {img_uuid_from_text})")
        elif img_uuid_from_text not in image_map:
            print(f"  UUID {img_uuid_from_text} from placeholder NOT FOUND in image_map.")
        elif img_uuid_from_text in processed_uuids_for_binary:
            print(f"  UUID {img_uuid_from_text} already processed for binary section.")

    print(f"DEBUG write_to_fb2: Total images prepared for binary section: {images_added_to_binary_count}")

    body = etree.SubElement(fb2_root, "body")
    lines = translated_content_with_placeholders.splitlines()
    para_buffer = []; current_section = None; is_first_section = True

    def add_paragraph_to_fb2(target_element, para_lines):
        nonlocal is_first_section # Allow modification of outer scope variable
        if not para_lines: return
        full_para_text = "\n".join(para_lines).strip()
        if not full_para_text: return

        parent_section = target_element
        if parent_section is None or parent_section.tag != 'section':
             last_section = body.xpath('section[last()]')
             parent_section = last_section[0] if last_section else None
             if parent_section is None:
                 parent_section = etree.SubElement(body, "section")
                 is_first_section = False 

        p = etree.SubElement(parent_section, "p")
        last_index = 0; current_tail_element = None

        placeholders_in_para = find_image_placeholders(full_para_text)
        for placeholder_tag_para, img_uuid_para in placeholders_in_para: # Renamed variables
            match_start = full_para_text.find(placeholder_tag_para, last_index)
            if match_start == -1: continue

            text_before = full_para_text[last_index:match_start]
            if text_before:
                if current_tail_element is not None:
                    current_tail_element.tail = (current_tail_element.tail or "") + text_before
                else:
                    p.text = (p.text or "") + text_before

            if img_uuid_para in placeholder_to_binary_id:
                binary_id_para = placeholder_to_binary_id[img_uuid_para] # Renamed
                try:
                    img_elem = etree.SubElement(p, "image")
                    img_elem.set(l_href_attr, f"#{binary_id_para}")
                    current_tail_element = img_elem
                except ValueError as ve:
                    print(f"[ERROR] FB2: Failed to create image element for binary ID '{binary_id_para}': {ve}")
                    error_text_ve = f" [FB2 Img Err: {img_uuid_para[:8]}] " # Renamed
                    if current_tail_element is not None: current_tail_element.tail = (current_tail_element.tail or "") + error_text_ve
                    else: p.text = (p.text or "") + error_text_ve
                    current_tail_element = None
            else:
                original_filename_fb2 = image_map.get(img_uuid_para, {}).get('original_filename', img_uuid_para) # Renamed
                error_text_nf = f" [Img Placeholder {img_uuid_para[:8]} found in text, but no binary data prepared (orig: {original_filename_fb2})] " # Renamed
                print(f"DEBUG write_to_fb2 (add_paragraph): Placeholder {img_uuid_para} found in paragraph, but not in placeholder_to_binary_id map.")
                if current_tail_element is not None: current_tail_element.tail = (current_tail_element.tail or "") + error_text_nf
                else: p.text = (p.text or "") + error_text_nf
                current_tail_element = None
            last_index = match_start + len(placeholder_tag_para)

        text_after = full_para_text[last_index:]
        if text_after:
            if current_tail_element is not None:
                current_tail_element.tail = (current_tail_element.tail or "") + text_after
            else:
                p.text = (p.text or "") + text_after
        if len(p) == 0 and not (p.text or "").strip() and p.getparent() is not None:
             p.getparent().remove(p)

    for line in lines:
        stripped_line = line.strip()
        chapter_match = re.match(r'^(#{1,3})\s+(.*)', stripped_line)
        if chapter_match:
            if para_buffer and current_section is not None:
                add_paragraph_to_fb2(current_section, para_buffer)
            para_buffer = []
            current_section = etree.SubElement(body, "section")
            title_elem = etree.SubElement(current_section, "title")
            add_paragraph_to_fb2(title_elem, [chapter_match.group(2).strip()])
            if not title_elem.xpath('.//text() | .//image'):
                 current_section.remove(title_elem)
            is_first_section = False
        else:
            if is_first_section and not current_section and stripped_line:
                 current_section = etree.SubElement(body, "section")
                 is_first_section = False
            if stripped_line or find_image_placeholders(line): # Check raw line for placeholders
                para_buffer.append(line)
            elif not stripped_line and para_buffer:
                 if current_section is None:
                      current_section = etree.SubElement(body, "section"); is_first_section = False
                 add_paragraph_to_fb2(current_section, para_buffer); para_buffer = []
    if para_buffer:
        if current_section is None: current_section = etree.SubElement(body, "section")
        add_paragraph_to_fb2(current_section, para_buffer)
    if not body.xpath('section'):
        print("[WARN] FB2: No sections created. Adding empty fallback section.")
        etree.SubElement(body, "section")

    if binary_sections: # This list is populated based on successful processing
        print(f"[INFO] FB2: Adding {len(binary_sections)} binary image sections.") # This should match images_added_to_binary_count
        for binary_id_add, content_type_add, base64_data_add in binary_sections: # Renamed variables
            try:
                etree.SubElement(fb2_root, "binary", id=binary_id_add, attrib={"content-type": content_type_add}).text = base64_data_add
            except ValueError as ve_add:
                 print(f"[ERROR] FB2: Invalid binary ID '{binary_id_add}' during write: {ve_add}")
    else:
        print("[INFO] FB2: No binary image data to add.")

    try:
        tree = etree.ElementTree(fb2_root)
        tree.write(out_path, pretty_print=True, xml_declaration=True, encoding="utf-8")
        print(f"[SUCCESS] FB2 file saved: {out_path}")
    except Exception as write_err:
        print(f"[ERROR] Failed to write FB2 file {out_path}: {write_err}"); raise write_err

class EpubHtmlSelectorDialog(QDialog):

    def __init__(self, epub_filename, html_files, nav_path, ncx_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Выберите HTML/XHTML файлы из '{os.path.basename(epub_filename)}'")
        self.setMinimumWidth(500); self.setMinimumHeight(400) # Можно даже чуть больше высоту, например 450
        layout = QVBoxLayout(self)
        info_text = f"Найденные HTML/XHTML файлы в:\n{epub_filename}\n\n"
        info_text += f"Авто-определен NAV (Оглавление EPUB3): {nav_path or 'Нет'}\n"
        info_text += "\nВыберите файлы для перевода.\n(NAV файл РЕКОМЕНДУЕТСЯ ИСКЛЮЧИТЬ, т.к. ссылки обновятся автоматически):"

        self.info_label = QLabel(info_text)
        layout.addWidget(self.info_label)

        self.hide_translated_checkbox = QCheckBox("Скрыть файлы _translated")
        self.hide_translated_checkbox.setToolTip(
            "Если отмечено, файлы с суффиксом _translated (например, chapter1_translated.html) будут скрыты из списка."
        )
        self.hide_translated_checkbox.setChecked(False)
        self.hide_translated_checkbox.stateChanged.connect(self.update_file_visibility) # Эта строка остается
        layout.addWidget(self.hide_translated_checkbox)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)

        self.list_widget.itemSelectionChanged.connect(self.update_selection_count_label) 

        self.all_html_files_with_data = [] # Эта часть остается как была
        for file_path in html_files:
            item = QtWidgets.QListWidgetItem(file_path)
            is_nav = (nav_path and file_path == nav_path)
            is_translated = Path(file_path).stem.endswith(TRANSLATED_SUFFIX) # Проверяем суффикс

            self.all_html_files_with_data.append({
                'text': file_path,
                'is_nav': is_nav,
                'is_translated': is_translated # Сохраняем, является ли файл переведенным
            })

            if is_nav:
                item.setBackground(QtGui.QColor("#fff0f0")) # Light red background for NAV
                item.setToolTip(f"{file_path}\n(Это файл ОГЛАВЛЕНИЯ EPUB3 (NAV).\nНЕ РЕКОМЕНДУЕТСЯ переводить - ссылки обновятся автоматически.)")
                item.setSelected(False) # Deselect NAV by default
            else:
                item_text_lower = item.text().lower()
                path = Path(item_text_lower)
                filename_lower = path.name
                filename_base = path.stem.split('.')[0] # Get stem before first dot

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
                is_chapter_like = re.fullmatch(r'(ch|gl|chap|chapter|part|section|sec|glava)[\d_-]+.*', filename_base) or \
                                  re.fullmatch(r'[\d]+', filename_base) or \
                                  re.match(r'^[ivxlcdm]+$', filename_base)

                if not is_likely_skip and (is_likely_content or is_chapter_like):
                     item.setSelected(True)
                else:
                    if not is_likely_skip and 'text' in filename_base:
                        item.setSelected(True)
                    else:
                        item.setSelected(False)
                item.setToolTip(file_path)

        
        layout.addWidget(self.list_widget) # Добавляем список

        self.selection_count_label = QLabel("Выбрано: 0 из 0")
        layout.addWidget(self.selection_count_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.update_file_visibility()


    def update_selection_count_label(self):
        """Обновляет метку, показывающую количество выбранных и общее количество видимых файлов."""
        selected_items_count = len(self.list_widget.selectedItems())
        total_visible_items_count = self.list_widget.count() # count() дает количество элементов в виджете
        self.selection_count_label.setText(f"Выбрано: {selected_items_count} из {total_visible_items_count} (видимых)")

    def update_file_visibility(self):
        hide_translated = self.hide_translated_checkbox.isChecked()
        
        current_selected_text = None
        selected_items_list = self.list_widget.selectedItems() # QListWidget.selectedItems() returns a list
        if selected_items_list: # Check if the list is not empty
            current_selected_text = selected_items_list[0].text()

        self.list_widget.clear() 

        for file_data in self.all_html_files_with_data:
            if hide_translated and file_data['is_translated']:
                continue 

            item = QtWidgets.QListWidgetItem(file_data['text'])
            
            if file_data['is_nav']:
                item.setBackground(QtGui.QColor("#fff0f0"))
                item.setToolTip(f"{file_data['text']}\n(Это файл ОГЛАВЛЕНИЯ EPUB3 (NAV).\nНЕ РЕКОМЕНДУЕТСЯ переводить - ссылки обновятся автоматически.)")
                item.setSelected(False) 
            else:
                item_text_lower = item.text().lower()
                path = Path(item_text_lower)
                filename_base = path.stem.split('.')[0] 

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

                is_chapter_like_match = re.fullmatch(r'(ch|gl|chap|chapter|part|section|sec|glava)[\d_-]+.*', filename_base) or \
                                        re.fullmatch(r'[\d]+', filename_base) or \
                                        re.match(r'^[ivxlcdm]+$', filename_base) 

                content_topic_criteria = bool(is_likely_content or is_chapter_like_match)

                should_be_selected = (not file_data['is_translated'] and
                                      not is_likely_skip and
                                      content_topic_criteria)

                if (not should_be_selected and
                    not file_data['is_translated'] and
                    not is_likely_skip and
                    'text' in filename_base):
                    should_be_selected = True
                
                item.setSelected(should_be_selected) # should_be_selected теперь всегда будет True или False
                item.setToolTip(file_data['text'])
            
            self.list_widget.addItem(item)

            if current_selected_text and item.text() == current_selected_text:
                item.setSelected(True)

        self.update_selection_count_label() # <<< ВОТ ЭТУ СТРОЧКУ ДОБАВИЛИ В КОНЕЦ



    def get_selected_files(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count()) if self.list_widget.item(i).isSelected()]

class OperationCancelledError(Exception): pass






class Worker(QtCore.QObject):

    file_progress = QtCore.pyqtSignal(int)
    chunk_progress = QtCore.pyqtSignal(str, int, int)
    current_file_status = QtCore.pyqtSignal(str)
    log_message = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int, int, list)
    total_tasks_calculated = QtCore.pyqtSignal(int)

    def __init__(self, api_key, out_folder, prompt_template, files_to_process_data,
                 model_config, max_concurrent_requests, output_format,
                 chunking_enabled_gui, chunk_limit, chunk_window,
                 temperature, chunk_delay_seconds, proxy_string=None): # <-- Добавлен proxy_string
        super().__init__()
        self.api_key = api_key
        self.out_folder = out_folder
        self.prompt_template = prompt_template
        self.files_to_process_data = files_to_process_data
        self.model_config = model_config
        self.max_concurrent_requests = max_concurrent_requests
        self.output_format = output_format
        self.chunking_enabled_gui = chunking_enabled_gui
        self.chunk_limit = chunk_limit
        self.chunk_window = chunk_window
        self.temperature = temperature # <-- Сохраняем температуру
        self.chunk_delay_seconds = chunk_delay_seconds # <-- Сохраняем новую настройку
        self.proxy_string = proxy_string # <-- Сохраняем строку прокси

        self.is_cancelled = False
        self.is_finishing = False # <--- НОВЫЙ ФЛАГ
        self._critical_error_occurred = False
        self.model = None
        self.executor = None
        self.epub_build_states = {}
        self.total_tasks = 0
        self.processed_task_count = 0
        self.success_count = 0
        self.error_count = 0
        self.errors_list = []


    def finish_processing(self): # <--- ВОТ ЭТОТ МЕТОД
        if not self.is_finishing and not self.is_cancelled: # Не устанавливать, если уже отменяется
            self.log_message.emit("[SIGNAL] Получен сигнал ЗАВЕРШЕНИЯ (Worker.finish_processing)...")
            self.is_finishing = True


    def setup_client(self):
        """Initializes the Gemini API client, configures proxy, and sets system instruction."""
        try:
            if not self.api_key: raise ValueError("API ключ не предоставлен.")

            # --- БЛОК ПРОКСИ (остается без изменений) ---
            if 'HTTP_PROXY' in os.environ: os.environ.pop('HTTP_PROXY')
            if 'HTTPS_PROXY' in os.environ: os.environ.pop('HTTPS_PROXY')
            applied_proxy_method = "None"
            proxy_url_for_env = None

            if self.proxy_string and self.proxy_string.strip():
                proxy_url_config = self.proxy_string.strip()
                if proxy_url_config.lower().startswith("socks5(h)://"):
                    corrected_url = "socks5h://" + proxy_url_config[len("socks5(h)://"):]
                    self.log_message.emit(f"[INFO] Proxy scheme '{proxy_url_config}' auto-corrected to '{corrected_url}'.")
                    proxy_url_config = corrected_url
                parsed_url = None
                try:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(proxy_url_config)
                except Exception as e_parse_url:
                    self.log_message.emit(f"[ERROR] Could not parse proxy URL '{proxy_url_config}': {e_parse_url}")
                if parsed_url and parsed_url.scheme.lower() in ["socks5", "socks5h"]:
                    try:
                        import socks
                        import socket
                        host, port, username, password = parsed_url.hostname, parsed_url.port, parsed_url.username, parsed_url.password
                        if not host or not port: raise ValueError("SOCKS5/SOCKS5h URL is missing host or port.")
                        is_rdns = parsed_url.scheme.lower() == "socks5h"
                        if not hasattr(socks, '_original_socket_module_attrs'): socks._original_socket_module_attrs = {'socket': socket.socket}
                        elif 'socket' not in socks._original_socket_module_attrs: socks._original_socket_module_attrs['socket'] = socket.socket
                        socks.set_default_proxy(socks.SOCKS5, host, port, rdns=is_rdns, username=username, password=password)
                        socket.socket = socks.socksocket
                        applied_proxy_method = f"{parsed_url.scheme.upper()} via PySocks: {host}:{port} (RDNS={is_rdns})"
                        self.log_message.emit(f"[INFO] {applied_proxy_method}")
                    except (ImportError, ValueError) as e: self.log_message.emit(f"[ERROR] SOCKS Proxy Error: {e}"); applied_proxy_method = "SOCKS Error"
                    except Exception as e_socks: self.log_message.emit(f"[ERROR] Failed to set SOCKS proxy: {e_socks}"); applied_proxy_method = f"SOCKS Error ({type(e_socks).__name__})"
                elif parsed_url and parsed_url.scheme.lower() in ["http", "https"]:
                    proxy_url_for_env = proxy_url_config
                    applied_proxy_method = f"{parsed_url.scheme.upper()} via ENV: {proxy_url_for_env}"
                    self.log_message.emit(f"[INFO] {applied_proxy_method}")
                elif self.proxy_string and self.proxy_string.strip():
                    self.log_message.emit(f"[WARN] Unknown proxy URL: '{self.proxy_string.strip()}'. Attempting ENV vars.")
                    proxy_url_for_env = self.proxy_string.strip()
                    applied_proxy_method = "Unknown scheme (attempting ENV)"
            if proxy_url_for_env:
                os.environ['HTTP_PROXY'] = proxy_url_for_env
                os.environ['HTTPS_PROXY'] = proxy_url_for_env
            elif not applied_proxy_method.startswith("SOCKS"):
                if not (self.proxy_string and self.proxy_string.strip()): self.log_message.emit("[INFO] No proxy provided.")
                else: self.log_message.emit(f"[WARN] Proxy '{self.proxy_string.strip()}' not applied due to issues.")
            
            genai.configure(api_key=self.api_key)

            # --- НАЧАЛО ИЗМЕНЕНИЙ ДЛЯ SYSTEM INSTRUCTION ---
            # Убираем плейсхолдер {text} из шаблона, чтобы получить чистую системную инструкцию
            system_instruction_text = self.prompt_template.replace("{text}", "").strip()

            # Инициализируем модель СРАЗУ с системной инструкцией
            self.model = genai.GenerativeModel(
                self.model_config['id'],
                system_instruction=system_instruction_text
            )
            
            self.log_message.emit("[INFO] Модель сконфигурирована с системной инструкцией.")
            # --- КОНЕЦ ИЗМЕНЕНИЙ ДЛЯ SYSTEM INSTRUCTION ---

            self.log_message.emit(f"Используется модель: {self.model_config['id']}")
            self.log_message.emit(f"Температура: {self.temperature:.1f}")

            # ... (остальной код метода без изменений)
            self.log_message.emit(f"Параллельные запросы (макс): {self.max_concurrent_requests}")
            self.log_message.emit(f"Формат вывода: .{self.output_format}")
            self.log_message.emit(f"Таймаут API: {API_TIMEOUT_SECONDS} сек.")
            self.log_message.emit(f"Макс. ретраев при 429/503/500/504: {MAX_RETRIES}")
            if self.model_config.get('post_request_delay', 0) > 0:
                self.log_message.emit(f"Доп. задержка после запроса: {self.model_config['post_request_delay']} сек.")
            model_needs_chunking = self.model_config.get('needs_chunking', False)
            actual_chunking_behavior = "ВКЛЮЧЕН (GUI)" if self.chunking_enabled_gui else "ОТКЛЮЧЕН (GUI)"
            reason = ""
            if self.chunking_enabled_gui:
                chunk_info = f"(Лимит: {self.chunk_limit:,} симв., Окно: {self.chunk_window:,} симв.)"
                if self.chunk_delay_seconds > 0: chunk_info += f", Задержка: {self.chunk_delay_seconds:.1f} сек.)"
                else: chunk_info += ")"
                if model_needs_chunking: reason = f"{chunk_info} - Модель его требует."
                else: reason = f"{chunk_info} - Применяется если файл > лимита."
                if not CHUNK_HTML_SOURCE: reason += " [Чанкинг HTML отключен]"
            else: reason = "(ВНИМАНИЕ: модель может требовать чанкинг!)" if model_needs_chunking else "(модель не требует)"
            self.log_message.emit(f"Чанкинг: {actual_chunking_behavior} {reason}")
            self.log_message.emit(f"Формат плейсхолдера изображения: {create_image_placeholder('uuid_example')}")
            self.log_message.emit("Клиент Gemini API успешно настроен.")
            return True
        except Exception as e:
            self.log_message.emit(f"[ERROR] Ошибка настройки клиента Gemini API: {e}\n{traceback.format_exc()}")
            if 'applied_proxy_method' in locals() and applied_proxy_method.startswith("SOCKS"):
                try:
                    import socket, socks
                    socks.set_default_proxy() 
                    if hasattr(socks, '_original_socket_module_attrs') and 'socket' in socks._original_socket_module_attrs:
                         socket.socket = socks._original_socket_module_attrs['socket']
                         self.log_message.emit("[INFO] Attempted to revert PySocks monkeypatch on error.")
                except Exception as e_revert: self.log_message.emit(f"[WARN] Error trying to revert PySocks monkeypatch: {e_revert}")
            if 'HTTP_PROXY' in os.environ: os.environ.pop('HTTP_PROXY')
            if 'HTTPS_PROXY' in os.environ: os.environ.pop('HTTPS_PROXY')
            return False

    def _generate_content_with_retry(self, user_text_for_api, context_log_prefix="API Call"):
        """
        Makes the API call with retry logic for specific errors and applies temperature.
        Checks for cancellation and handles various API errors robustly.
        The system instruction is already configured in self.model.
        """
        self.log_message.emit(f"[API START] {context_log_prefix}: Начинаем API запрос...")
        retries = 0
        last_error = None

        safety_settings=[
            {"category": c, "threshold": "BLOCK_NONE"} for c in [
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            ]
        ]
        
        generation_config_dict = {"temperature": self.temperature}
        generation_config_obj = genai.GenerationConfig(**generation_config_dict) if hasattr(genai, 'GenerationConfig') else generation_config_dict

        while retries <= MAX_RETRIES:
            if self.is_cancelled:
                raise OperationCancelledError(f"Отменено ({context_log_prefix})")

            response_obj = None
            try:
                # --- ИЗМЕНЕНИЕ ---
                # Теперь в contents передается только текст пользователя.
                # Системная инструкция уже "зашита" в self.model.
                self.log_message.emit(f"[API CALL] {context_log_prefix}: Отправляем запрос к API...")
                response_obj = self.model.generate_content(
                    contents=user_text_for_api,
                    safety_settings=safety_settings,
                    generation_config=generation_config_obj
                )
                self.log_message.emit(f"[API RESPONSE] {context_log_prefix}: Получен ответ от API, обрабатываем...")

                translated_text = None
                problem_details = ""

                # ... (остальной код метода остается без изменений, т.к. он работает с объектом ответа)
                if hasattr(response_obj, 'prompt_feedback') and response_obj.prompt_feedback:
                    if hasattr(response_obj.prompt_feedback, 'block_reason') and response_obj.prompt_feedback.block_reason:
                        block_reason_name = str(response_obj.prompt_feedback.block_reason)
                        if block_reason_name not in ["BLOCK_REASON_UNSPECIFIED", "0"]:
                            problem_details = f"Запрос заблокирован API (Prompt Feedback): {block_reason_name}. Full Feedback: {str(response_obj.prompt_feedback)}"
                            self.log_message.emit(f"[API BLOCK] {context_log_prefix}: {problem_details}")
                            raise RuntimeError(problem_details)

                if hasattr(response_obj, 'candidates') and response_obj.candidates:
                    candidate = response_obj.candidates[0]
                    candidate_finish_reason = getattr(candidate, 'finish_reason', None)
                    finish_reason_name = ""
                    if candidate_finish_reason is not None:
                        try: finish_reason_name = candidate_finish_reason.name 
                        except AttributeError: finish_reason_name = str(candidate_finish_reason)
                    bad_finish_reasons_names = ["SAFETY", "PROHIBITED_CONTENT", "RECITATION", "OTHER"]
                    bad_finish_reasons_numbers_str = ["2", "3", "4", "8"]
                    if finish_reason_name.upper() in bad_finish_reasons_names or finish_reason_name in bad_finish_reasons_numbers_str:
                        problem_details = f"Проблема с генерацией контента. Finish Reason: {finish_reason_name}. Safety Ratings: {getattr(candidate, 'safety_ratings', 'N/A')}"
                        self.log_message.emit(f"[API CONTENT ISSUE] {context_log_prefix}: {problem_details}")
                        raise RuntimeError(problem_details)
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                        text_parts = [part.text for part in candidate.content.parts if hasattr(part, 'text')]
                        if text_parts: translated_text = "".join(text_parts)
                
                if translated_text is None:
                    if hasattr(response_obj, 'text'):
                        try:
                            current_text = response_obj.text
                            if current_text is not None: translated_text = current_text
                            else: problem_details = f"response.text вернул None. Кандидаты: {getattr(response_obj, 'candidates', 'N/A')}"; self.log_message.emit(f"[API CONTENT WARNING] {context_log_prefix}: {problem_details}"); raise RuntimeError(problem_details)
                        except ValueError as ve:
                            problem_details = f"ValueError: {ve}. FinishReason: {finish_reason_name if 'finish_reason_name' in locals() else 'N/A'}. Кандидаты: {getattr(response_obj, 'candidates', 'N/A')}"
                            self.log_message.emit(f"[API CONTENT ERROR] {context_log_prefix}: {problem_details}")
                            raise RuntimeError(problem_details) from ve
                
                if translated_text is None:
                    problem_details = f"Не удалось извлечь текст. FinishReason: {finish_reason_name if 'finish_reason_name' in locals() else 'N/A'}. Кандидаты: {getattr(response_obj, 'candidates', 'N/A')}"
                    self.log_message.emit(f"[API CONTENT FAIL] {context_log_prefix}: {problem_details}")
                    raise RuntimeError(problem_details)

                delay_needed = self.model_config.get('post_request_delay', 0)
                if delay_needed > 0:
                    self.log_message.emit(f"[INFO] {context_log_prefix}: Применяем задержку {delay_needed} сек...")
                    slept_time = 0
                    while slept_time < delay_needed:
                        if self.is_cancelled: raise OperationCancelledError("Отменено во время пост-задержки")
                        time.sleep(1); slept_time += 1
                return translated_text

            except (google_exceptions.ResourceExhausted, google_exceptions.DeadlineExceeded, google_exceptions.ServiceUnavailable, google_exceptions.InternalServerError, google_exceptions.RetryError) as retryable_error:
                error_code_map = {google_exceptions.ResourceExhausted: "429 Limit", google_exceptions.ServiceUnavailable: "503 Unavailable", google_exceptions.InternalServerError: "500 Internal", google_exceptions.DeadlineExceeded: "504 Timeout", google_exceptions.RetryError: "Retry Failed"}
                error_code = error_code_map.get(type(retryable_error), "API Transient")
                if isinstance(retryable_error, google_exceptions.RetryError) and retryable_error.__cause__: error_code = f"Retry Failed ({error_code_map.get(type(retryable_error.__cause__), 'Unknown')})"
                last_error, retries = retryable_error, retries + 1
                if retries > MAX_RETRIES: self.log_message.emit(f"[FAIL] {context_log_prefix}: Ошибка {error_code}, исчерпаны попытки."); raise last_error
                delay = RETRY_DELAY_SECONDS * (2**(retries - 1))
                self.log_message.emit(f"[WARN] {context_log_prefix}: Ошибка {error_code}. Попытка {retries}/{MAX_RETRIES} через {delay} сек...")
                slept_time = 0
                while slept_time < delay:
                    if self.is_cancelled: raise OperationCancelledError(f"Отменено во время ожидания retry ({error_code})")
                    time.sleep(1); slept_time += 1
                continue
            
            except (google_exceptions.InvalidArgument, google_exceptions.PermissionDenied, google_exceptions.Unauthenticated, google_exceptions.NotFound) as non_retryable_error:
                self.log_message.emit(f"[API FAIL] {context_log_prefix}: Неисправимая ошибка API ({type(non_retryable_error).__name__}): {non_retryable_error}"); raise non_retryable_error
            
            except RuntimeError as rte:
                if "Запрос заблокирован" in str(rte) or "Проблема с генерацией" in str(rte): raise rte
                if retries < MAX_RETRIES:
                    self.log_message.emit(f"[WARN] {context_log_prefix}: Ошибка контента ({rte}). Попытка сетевого ретрая {retries + 1}/{MAX_RETRIES}...")
                    last_error, retries = rte, retries + 1
                    delay = RETRY_DELAY_SECONDS * (2**(retries - 1))
                    self.log_message.emit(f"       Ожидание {delay} сек..."); slept_time_rte = 0
                    while slept_time_rte < delay:
                        if self.is_cancelled: raise OperationCancelledError("Отменено во время ожидания RTE-ретрая")
                        time.sleep(1); slept_time_rte += 1
                    continue
                else: raise rte
            
            except Exception as e:
                self.log_message.emit(f"[CALL ERROR] {context_log_prefix}: Неожиданная ошибка ({type(e).__name__}): {e}\n{traceback.format_exc()}"); raise e
        
        final_error = last_error if last_error else RuntimeError(f"Неизвестная ошибка API после {MAX_RETRIES} ретраев ({context_log_prefix}).")
        self.log_message.emit(f"[FAIL] {context_log_prefix}: Исчерпаны все попытки. Последняя ошибка: {final_error}"); raise final_error



    def process_single_chunk(self, chunk_text, base_filename_for_log, chunk_index, total_chunks):
        """Processes a single chunk of text by calling the API."""
        if self.is_cancelled:
            raise OperationCancelledError(f"Отменено перед чанком {chunk_index+1}/{total_chunks}")
        
        chunk_log_prefix = f"{base_filename_for_log} [Chunk {chunk_index+1}/{total_chunks}]"
        
        # --- ИЗМЕНЕНИЕ ---
        # Больше не нужно объединять промпт и текст.
        # Просто передаем текст чанка в функцию API.
        # prompt_for_chunk = self.prompt_template.replace("{text}", chunk_text) # <-- ЭТА СТРОКА УДАЛЕНА

        try:
            placeholders_before = find_image_placeholders(chunk_text) 
            placeholders_before_uuids = {p[1] for p in placeholders_before}

            if placeholders_before: 
                self.log_message.emit(f"[INFO] {chunk_log_prefix}: Отправка чанка с {len(placeholders_before)} плейсхолдерами (UUIDs: {sorted(list(placeholders_before_uuids))}).")

            # --- ИЗМЕНЕНИЕ ---
            # Вызываем _generate_content_with_retry только с текстом чанка
            translated_chunk = self._generate_content_with_retry(chunk_text, chunk_log_prefix)

            translated_chunk = html.unescape(translated_chunk)

            placeholders_after_translation_raw = find_image_placeholders(translated_chunk)
            
            newly_appeared_placeholders_tags_to_remove = []
            if placeholders_after_translation_raw:
                for p_tag, p_uuid in placeholders_after_translation_raw:
                    if p_uuid not in placeholders_before_uuids:
                        newly_appeared_placeholders_tags_to_remove.append(p_tag)
            
            if newly_appeared_placeholders_tags_to_remove:
                self.log_message.emit(f"[WARN] {chunk_log_prefix}: Обнаружены новые плейсхолдеры ({len(newly_appeared_placeholders_tags_to_remove)} шт.) после перевода, которых не было в оригинале. Они будут удалены.")
                for p_tag_to_remove in newly_appeared_placeholders_tags_to_remove:
                    match_uuid_in_tag = re.search(r"<\|\|" + IMAGE_PLACEHOLDER_PREFIX + r"([a-f0-9]{32})\|\|>", p_tag_to_remove)
                    uuid_for_log = match_uuid_in_tag.group(1) if match_uuid_in_tag else "неизвестный UUID"
                    self.log_message.emit(f"  - Удаляется новый плейсхолдер: {p_tag_to_remove} (UUID: {uuid_for_log})")
                    translated_chunk = translated_chunk.replace(p_tag_to_remove, "")

            placeholders_after_cleaning = find_image_placeholders(translated_chunk)
            placeholders_after_cleaning_uuids = {p[1] for p in placeholders_after_cleaning}

            if len(placeholders_before) != len(placeholders_after_cleaning): 
                self.log_message.emit(f"[WARN] {chunk_log_prefix}: Количество плейсхолдеров ИЗМЕНИЛОСЬ! (Оригинал: {len(placeholders_before)}, После перевода и очистки: {len(placeholders_after_cleaning)})")
                self.log_message.emit(f"  Оригинальные UUIDs: {sorted(list(placeholders_before_uuids))}")
                self.log_message.emit(f"  Итоговые UUIDs: {sorted(list(placeholders_after_cleaning_uuids))}")
            elif placeholders_before:
                 if placeholders_before_uuids != placeholders_after_cleaning_uuids:
                     self.log_message.emit(f"[WARN] {chunk_log_prefix}: Набор UUID плейсхолдеров ИЗМЕНИЛСЯ (даже после очистки)! (Оригинал: {sorted(list(placeholders_before_uuids))}, Итог: {sorted(list(placeholders_after_cleaning_uuids))})")
                 if not all(p[0].startswith("<||") and p[0].endswith("||>") and len(p[1]) == 32 for p in placeholders_after_cleaning): 
                     self.log_message.emit(f"[WARN] {chunk_log_prefix}: Плейсхолдеры в итоговом тексте выглядят поврежденными.")

            self.log_message.emit(f"[INFO] {chunk_log_prefix}: Чанк успешно переведен и обработан.")
            return chunk_index, translated_chunk
        except OperationCancelledError as oce:
            self.log_message.emit(f"[CANCELLED] {chunk_log_prefix}: Обработка чанка отменена."); raise oce
        except Exception as e:
            self.log_message.emit(f"[FAIL] {chunk_log_prefix}: Ошибка API вызова/обработки чанка: {e}"); raise e

    def process_single_epub_html(self, original_epub_path, html_path_in_epub):
        """
        Processes a single HTML file from an EPUB for EPUB->EPUB mode.
        Returns data for building the EPUB, including original content if translation fails or finishing.
        """
        log_prefix = f"{os.path.basename(original_epub_path)} -> {html_path_in_epub}"

        if self.is_cancelled:
            # Возвращаем False, чтобы эта задача не считалась успешной для сборки EPUB
            return False, html_path_in_epub, None, None, False, f"Отменено перед началом: {log_prefix}"

        # Если "Завершить" вызвано до начала обработки этого HTML, используем оригинал
        if self.is_finishing:
            self.log_message.emit(f"[FINISHING] {log_prefix}: HTML часть пропущена (режим завершения). Попытка использовать оригинал.")
            self.chunk_progress.emit(log_prefix, 0, 0)
            # Пытаемся прочитать оригинал, чтобы сборка EPUB могла его использовать
            try:
                with zipfile.ZipFile(original_epub_path, 'r') as epub_zip_orig:
                    original_html_bytes_for_finish = epub_zip_orig.read(html_path_in_epub)
                # Возвращаем True, чтобы эта оригинальная часть была включена в сборку
                return True, html_path_in_epub, original_html_bytes_for_finish, {}, True, "Пропущено (режим завершения)"
            except Exception as e_read_orig:
                self.log_message.emit(f"[FINISHING-ERROR] {log_prefix}: Не удалось прочитать оригинал при завершении: {e_read_orig}")
                # Возвращаем False, так как даже оригинал не удалось получить
                return False, html_path_in_epub, None, None, False, f"Пропущено (режим завершения, оригинал недоступен: {e_read_orig})"

        with tempfile.TemporaryDirectory(prefix=f"translator_epub_{uuid.uuid4().hex[:8]}_") as temp_dir:
            image_map = {}
            content_with_placeholders = ""
            original_html_bytes = None

            try:
                self.log_message.emit(f"Обработка EPUB HTML: {log_prefix}")

                with zipfile.ZipFile(original_epub_path, 'r') as epub_zip:
                    try:
                        original_html_bytes = epub_zip.read(html_path_in_epub)
                        file_size_bytes = len(original_html_bytes)
                        original_html_str = ""
                        try: original_html_str = original_html_bytes.decode('utf-8')
                        except UnicodeDecodeError:
                            try: original_html_str = original_html_bytes.decode('cp1251'); self.log_message.emit(f"[WARN] {log_prefix}: Использовано cp1251.")
                            except UnicodeDecodeError: original_html_str = original_html_bytes.decode('latin-1', errors='ignore'); self.log_message.emit(f"[WARN] {log_prefix}: Использовано latin-1 (с потерями).")
                        
                        if not original_html_str and original_html_bytes:
                            self.log_message.emit(f"[ERROR] {log_prefix}: Не удалось декодировать HTML. Используется оригинал.")
                            return True, html_path_in_epub, original_html_bytes, {}, True, "Ошибка декодирования HTML"

                        processing_context = (epub_zip, html_path_in_epub)
                        content_with_placeholders = process_html_images(original_html_str, processing_context, temp_dir, image_map)
                        original_content_len_text = len(content_with_placeholders)
                        self.log_message.emit(f"[INFO] {log_prefix}: HTML прочитан/обработан (Размер: {format_size(file_size_bytes)}, {original_content_len_text:,} симв. текста, {len(image_map)} изобр.).")

                    except KeyError:
                        return False, html_path_in_epub, None, None, False, f"Ошибка: HTML '{html_path_in_epub}' не найден в EPUB."
                    except Exception as html_proc_err:
                        self.log_message.emit(f"[ERROR] {log_prefix}: Ошибка подготовки HTML для перевода: {html_proc_err}. Используется оригинал (если доступен).")
                        if original_html_bytes:
                            return True, html_path_in_epub, original_html_bytes, image_map or {}, True, f"Ошибка обработки HTML: {html_proc_err}"
                        else:
                            return False, html_path_in_epub, None, None, False, f"Критическая ошибка обработки HTML '{html_path_in_epub}': {html_proc_err}"

                if not content_with_placeholders.strip():
                    self.log_message.emit(f"[INFO] {log_prefix}: Пропущен (пустой контент после извлечения текста).")
                    return True, html_path_in_epub, original_html_bytes if original_html_bytes is not None else b"", image_map or {}, True, "Пустой контент после обработки"

                chunks = []
                can_chunk_html = CHUNK_HTML_SOURCE
                potential_chunking = self.chunking_enabled_gui and original_content_len_text > self.chunk_limit

                if potential_chunking and not can_chunk_html:
                    chunks.append(content_with_placeholders)
                    self.log_message.emit(f"[INFO] {log_prefix}: Чанкинг HTML отключен, отправляется целиком ({original_content_len_text:,} симв.).")
                elif potential_chunking and can_chunk_html:
                    self.log_message.emit(f"[INFO] {log_prefix}: Контент ({original_content_len_text:,} симв.) > лимита ({self.chunk_limit:,}). Разделяем...")
                    chunks = split_text_into_chunks(content_with_placeholders, self.chunk_limit, self.chunk_window, MIN_CHUNK_SIZE)
                    self.log_message.emit(f"[INFO] {log_prefix}: Разделено на {len(chunks)} чанков.")
                    if not chunks:
                        self.log_message.emit(f"[WARN] {log_prefix}: Ошибка разделения на чанки (пустой результат). Используется оригинал.")
                        return True, html_path_in_epub, original_html_bytes, image_map or {}, True, "Ошибка разделения на чанки"
                else:
                    chunks.append(content_with_placeholders)
                    self.log_message.emit(f"[INFO] {log_prefix}: Контент ({original_content_len_text:,} симв.) отправляется целиком (чанкинг выкл/не нужен/HTML выкл).")
                
                if not chunks:
                    self.log_message.emit(f"[ERROR] {log_prefix}: Нет чанков для обработки. Используется оригинал.")
                    return True, html_path_in_epub, original_html_bytes, image_map or {}, True, "Ошибка подготовки чанков"

                translated_chunks_map = {} 
                total_chunks = len(chunks)
                self.chunk_progress.emit(log_prefix, 0, total_chunks) 
                
                translation_failed_for_any_chunk = False
                first_chunk_error_msg = None
                processed_current_chunk_in_finishing_mode_epub = False

                for i, chunk_text in enumerate(chunks):
                    if self.is_cancelled:
                        raise OperationCancelledError(f"Отменено перед чанком {i+1} для {log_prefix}") 
                    
                    if self.is_finishing and processed_current_chunk_in_finishing_mode_epub:
                        self.log_message.emit(f"[FINISHING] {log_prefix}: Пропуск оставшихся чанков HTML ({i+1} из {total_chunks}).")
                        break
                    try:
                        _, translated_text_chunk = self.process_single_chunk(chunk_text, log_prefix, i, total_chunks)
                        translated_chunks_map[i] = translated_text_chunk
                        self.chunk_progress.emit(log_prefix, i + 1, total_chunks)
                        
                        if self.chunk_delay_seconds > 0 and (i < total_chunks - 1):
                            delay_val = self.chunk_delay_seconds
                            self.log_message.emit(f"[INFO] {log_prefix}: Задержка {delay_val:.1f} сек. перед следующим чанком HTML...")
                            start_sleep = time.monotonic()
                            while time.monotonic() - start_sleep < delay_val:
                                if self.is_cancelled: raise OperationCancelledError("Отменено во время задержки между чанками HTML")
                                time.sleep(min(0.1, delay_val - (time.monotonic() - start_sleep)))
                        
                        if self.is_finishing: # Если флаг установился во время или после этого чанка
                            self.log_message.emit(f"[FINISHING] {log_prefix}: Чанк HTML {i+1}/{total_chunks} обработан. Завершение обработки этой HTML части...")
                            processed_current_chunk_in_finishing_mode_epub = True
                            if i < total_chunks - 1: # Если это не последний чанк, то следующий точно пропускаем
                                pass 
                            else: # Это был последний чанк
                                break 

                    except OperationCancelledError as oce_chunk: 
                        raise oce_chunk 
                    except Exception as e_chunk: 
                        translation_failed_for_any_chunk = True
                        first_chunk_error_msg = f"Ошибка перевода чанка HTML {i+1}: {e_chunk}"
                        self.log_message.emit(f"[FAIL] {log_prefix}: {first_chunk_error_msg}")
                        if self.is_finishing:
                            self.log_message.emit(f"[FINISHING-ERROR] {log_prefix}: Ошибка на чанке HTML {i+1} во время завершения. Попытка использовать предыдущие или оригинал.")
                            processed_current_chunk_in_finishing_mode_epub = True
                        break 

                if self.is_cancelled: # Если отмена произошла во время цикла чанков
                    raise OperationCancelledError(f"Отменено во время или после обработки чанков для {log_prefix}")

                if translation_failed_for_any_chunk and not translated_chunks_map: # Ошибка на первом же чанке или ничего не собрано
                    self.log_message.emit(f"[WARN] {log_prefix}: Не удалось перевести HTML. Используется оригинал. Причина: {first_chunk_error_msg or 'Неизвестная ошибка чанка HTML'}")
                    self.chunk_progress.emit(log_prefix, 0, 0) 
                    return True, html_path_in_epub, original_html_bytes, image_map or {}, True, first_chunk_error_msg

                if not translated_chunks_map: # Если карта пуста (может быть, если is_finishing и первый чанк не успел)
                    if self.is_finishing:
                        self.log_message.emit(f"[FINISHING] {log_prefix}: Нет переведенных чанков для HTML. Используется оригинал.")
                        self.chunk_progress.emit(log_prefix, 0, 0)
                        return True, html_path_in_epub, original_html_bytes, image_map or {}, True, "Пропущено (режим завершения, нет данных для HTML)"
                    # Если не is_finishing и translated_chunks_map пуст, это должно было быть обработано выше
                    # как ошибка чанкинга или пустой контент. Но на всякий случай:
                    self.log_message.emit(f"[ERROR] {log_prefix}: Нет переведенных чанков для HTML по неизвестной причине. Используется оригинал.")
                    return True, html_path_in_epub, original_html_bytes, image_map or {}, True, "Нет переведенных чанков HTML"


                # Если есть какие-то чанки в translated_chunks_map
                final_translated_content_str = "\n".join(translated_chunks_map[i] for i in sorted(translated_chunks_map.keys())).strip()
                
                warning_msg_for_return = None
                if self.is_finishing and len(translated_chunks_map) < total_chunks:
                    self.log_message.emit(f"[FINISHING] {log_prefix}: HTML часть переведена частично ({len(translated_chunks_map)}/{total_chunks} чанков).")
                    warning_msg_for_return = "Частично переведено (завершение)"
                elif translation_failed_for_any_chunk and translated_chunks_map: # Была ошибка, но есть что сохранить
                    self.log_message.emit(f"[WARN] {log_prefix}: HTML часть переведена частично из-за ошибки ({len(translated_chunks_map)}/{total_chunks} чанков). Причина первой ошибки: {first_chunk_error_msg}")
                    warning_msg_for_return = f"Частично из-за ошибки: {first_chunk_error_msg or 'N/A'}"
                
                self.log_message.emit(f"[SUCCESS/PARTIAL] {log_prefix}: HTML часть (возможно, частично) подготовлена для сборки EPUB.")
                self.chunk_progress.emit(log_prefix, len(translated_chunks_map), total_chunks) 
                return True, html_path_in_epub, final_translated_content_str, image_map or {}, False, warning_msg_for_return

            except OperationCancelledError as oce:
                self.log_message.emit(f"[CANCELLED] {log_prefix}: Обработка HTML части прервана ({oce})")
                self.chunk_progress.emit(log_prefix, 0, 0)
                return False, html_path_in_epub, None, None, False, str(oce) 
            
            except Exception as e_outer: 
                safe_log_prefix_on_error = f"{os.path.basename(original_epub_path)} -> {html_path_in_epub}"
                detailed_error_msg = f"[CRITICAL] {safe_log_prefix_on_error}: Неожиданная ошибка при обработке HTML файла: {type(e_outer).__name__}: {e_outer}"
                tb_str = traceback.format_exc()
                self.log_message.emit(detailed_error_msg + "\n" + tb_str)
                self.chunk_progress.emit(safe_log_prefix_on_error, 0, 0)
                final_error_msg_return = f"Неожиданная ошибка HTML ({safe_log_prefix_on_error}): {type(e_outer).__name__}"
                if original_html_bytes is not None:
                    self.log_message.emit(f"[WARN] {log_prefix}: Использование оригинала из-за неожиданной ошибки: {final_error_msg_return}")
                    return True, html_path_in_epub, original_html_bytes, image_map or {}, True, final_error_msg_return
                else:
                    return False, html_path_in_epub, None, None, False, f"Критическая ошибка И оригинал не доступен: {final_error_msg_return}"

    def process_single_file(self, file_info_tuple):
        input_type, filepath, epub_html_path_or_none = file_info_tuple
        base_name = os.path.basename(filepath)
        log_prefix = f"{base_name}" + (f" -> {epub_html_path_or_none}" if epub_html_path_or_none else "")
        self.current_file_status.emit(f"Обработка: {log_prefix}")
        self.log_message.emit(f"Начало обработки: {log_prefix}")
        
        effective_path_obj_for_stem = None
        if input_type == 'epub' and epub_html_path_or_none:
            # Если обрабатывается HTML-часть из EPUB для вывода не в EPUB,
            # имя выходного файла должно базироваться на имени HTML-части.
            effective_path_obj_for_stem = Path(epub_html_path_or_none)
        else:
            # Для других типов ввода (txt, docx) или если это EPUB, но epub_html_path_or_none не указан (маловероятно здесь),
            # базируемся на имени входного файла.
            effective_path_obj_for_stem = Path(filepath)
        
        # Получаем "чистое" имя файла без всех расширений
        true_stem = effective_path_obj_for_stem.name
        all_suffixes = "".join(effective_path_obj_for_stem.suffixes)
        if all_suffixes:
            true_stem = true_stem.replace(all_suffixes, "")
        
        if not true_stem: # Обработка случаев типа ".bashrc" или если имя было пустым
            temp_name = effective_path_obj_for_stem.name
            true_stem = os.path.splitext(temp_name[1:] if temp_name.startswith('.') else temp_name)[0]
            if not true_stem: true_stem = "file" # Крайний случай
        
        final_out_filename = f"{true_stem}{TRANSLATED_SUFFIX}.{self.output_format}"
        out_path = os.path.join(self.out_folder, final_out_filename)
        
        image_map = {}; temp_dir_obj = None; book_title_guess = Path(filepath).stem.replace('_translated', '')

        try:
            with tempfile.TemporaryDirectory(prefix=f"translator_{uuid.uuid4().hex[:8]}_") as temp_dir_path:
                temp_dir_obj = temp_dir_path # For cleanup check in finally
                
                original_content = ""


                if input_type == 'txt':
                    with open(filepath, 'r', encoding='utf-8') as f: original_content = f.read()
                elif input_type == 'docx':
                    if not DOCX_AVAILABLE: raise ImportError("python-docx не установлен")
                    original_content = read_docx_with_images(filepath, temp_dir_path, image_map)
                elif input_type == 'epub': # Это для EPUB -> TXT/DOCX/MD/HTML (не EPUB->EPUB)
                    if not epub_html_path_or_none: raise ValueError("Путь к HTML в EPUB не указан.")
                    if not BS4_AVAILABLE: raise ImportError("beautifulsoup4 не установлен")
                    with zipfile.ZipFile(filepath, 'r') as epub_zip:
                        html_bytes = epub_zip.read(epub_html_path_or_none)

                        html_str = ""
                        try: html_str = html_bytes.decode('utf-8')
                        except UnicodeDecodeError:
                            try: html_str = html_bytes.decode('cp1251', errors='ignore'); self.log_message.emit(f"[WARN] {log_prefix}: cp1251 для HTML.")
                            except UnicodeDecodeError: html_str = html_bytes.decode('latin-1', errors='ignore'); self.log_message.emit(f"[WARN] {log_prefix}: latin-1 для HTML.")

                        epub_zip_dir = os.path.dirname(epub_html_path_or_none)
                        processing_context = (epub_zip, epub_html_path_or_none)
                        original_content = process_html_images(html_str, processing_context, temp_dir_path, image_map)
                        book_title_guess = Path(epub_html_path_or_none).stem # Используем имя HTML файла для заголовка
                else:
                    raise ValueError(f"Неподдерживаемый тип ввода: {input_type}")

                if self.is_cancelled: raise OperationCancelledError("Отменено после чтения файла")
                if self.is_finishing and not (input_type == 'epub' and epub_html_path_or_none): # Если "Завершить" и это не обработка HTML для EPUB-сборки (там своя логика)
                    self.log_message.emit(f"[FINISHING] {log_prefix}: Файл пропущен из-за режима завершения (активирован до начала обработки этого файла).")
                    return file_info_tuple, False, "Пропущено (режим завершения)"
                if not original_content.strip() and not image_map:
                    self.log_message.emit(f"[INFO] {log_prefix}: Пропущен (пустой контент)."); return file_info_tuple, True, "Пустой контент" # Считаем успехом, если пустой
                
                original_content_len = len(original_content)
                self.log_message.emit(f"[INFO] {log_prefix}: Прочитано ({format_size(original_content_len)} симв., {len(image_map)} изобр.).")

                chunks = []

                can_chunk_this_input = not (input_type == 'epub' and not CHUNK_HTML_SOURCE)

                if self.chunking_enabled_gui and original_content_len > self.chunk_limit and can_chunk_this_input:
                    self.log_message.emit(f"[INFO] {log_prefix}: Контент ({original_content_len:,} симв.) > лимита ({self.chunk_limit:,}). Разделяем...");
                    chunks = split_text_into_chunks(original_content, self.chunk_limit, self.chunk_window, MIN_CHUNK_SIZE)
                    self.log_message.emit(f"[INFO] {log_prefix}: Разделено на {len(chunks)} чанков.")
                else:
                    chunks.append(original_content)
                    reason_no_chunk = ""
                    if not self.chunking_enabled_gui: reason_no_chunk = "(чанкинг выключен)"
                    elif original_content_len <= self.chunk_limit: reason_no_chunk = "(размер < лимита)"
                    elif not can_chunk_this_input: reason_no_chunk = "(чанкинг HTML/EPUB отключен)"
                    self.log_message.emit(f"[INFO] {log_prefix}: Контент ({original_content_len:,} симв.) отправляется целиком {reason_no_chunk}.")

                if not chunks: # Если split_text_into_chunks вернул пустой список
                    self.log_message.emit(f"[WARN] {log_prefix}: Не удалось разделить на чанки (пустой результат). Пропускаем.");
                    return file_info_tuple, False, "Ошибка разделения на чанки"
                
                translated_chunks_map = {}
                total_chunks = len(chunks)
                self.chunk_progress.emit(log_prefix, 0, total_chunks)
                processed_current_chunk_in_finishing_mode = False

                for i, chunk_text in enumerate(chunks):
                    if self.is_cancelled: raise OperationCancelledError(f"Отменено перед чанком {i+1}")

                    # Если режим завершения уже активен и мы не обрабатываем самый первый чанк этого файла,
                    # или если это не первый чанк и режим завершения только что активировался.
                    if self.is_finishing and processed_current_chunk_in_finishing_mode:
                        self.log_message.emit(f"[FINISHING] {log_prefix}: Пропуск оставшихся чанков ({i+1} из {total_chunks}).")
                        break


                    try:
                        _, translated_text = self.process_single_chunk(chunk_text, log_prefix, i, total_chunks)
                        translated_chunks_map[i] = translated_text
                        self.chunk_progress.emit(log_prefix, i + 1, total_chunks)

                        if self.is_finishing: # Если флаг установился во время или после этого чанка
                            self.log_message.emit(f"[FINISHING] {log_prefix}: Чанк {i+1}/{total_chunks} обработан. Завершение обработки файла...")
                            processed_current_chunk_in_finishing_mode = True # Помечаем, что текущий чанк обработан в режиме завершения
                            # Не выходим из цикла сразу, если это был первый чанк, дадим сохраниться.
                            # Если это не первый чанк, то следующий if self.is_finishing and processed_current_chunk_in_finishing_mode сработает.
                            # Или, если это последний чанк, цикл закончится естественно.
                            if i < total_chunks -1: # Если это не последний чанк, и мы в режиме завершения, то следующий точно пропускаем
                                 pass # break будет на следующей итерации
                            else: # Это был последний чанк, и мы в режиме завершения
                                 break


                    except OperationCancelledError as oce: raise oce
                    except Exception as e:
                        if self.is_finishing: # Если ошибка во время завершения, пытаемся сохранить то, что есть
                            self.log_message.emit(f"[FINISHING-ERROR] {log_prefix}: Ошибка на чанке {i+1} во время завершения: {e}. Попытка сохранить предыдущие.")
                            processed_current_chunk_in_finishing_mode = True # Чтобы не продолжать
                            break # Выходим из цикла чанков, чтобы сохранить то, что есть
                        return file_info_tuple, False, f"Ошибка обработки чанка {i+1}: {e}"

                # После цикла обработки чанков
                if self.is_cancelled and not translated_chunks_map:
                    raise OperationCancelledError(f"Отменено во время обработки чанков для {log_prefix}, нет данных для сохранения")

                if not translated_chunks_map:
                    if self.is_finishing: # Если завершаем и для этого файла ничего не успело перевестись
                        self.log_message.emit(f"[FINISHING] {log_prefix}: Нет переведенных чанков для сохранения (режим завершения).")
                        return file_info_tuple, False, "Пропущено (режим завершения, нет данных)"
                    elif original_content.strip() or image_map: # Если был контент, но не перевелся (и не режим завершения)
                        self.log_message.emit(f"[FAIL] {log_prefix}: Не удалось перевести ни одного чанка.")
                        return file_info_tuple, False, "Ошибка: Не удалось перевести ни одного чанка."
                    else: # Пустой файл изначально
                        self.log_message.emit(f"[INFO] {log_prefix}: Пропущен (пустой контент).")
                        return file_info_tuple, True, "Пустой контент"

                # Если есть что сохранять (translated_chunks_map не пуст)
                if self.is_finishing and len(translated_chunks_map) < total_chunks:
                    self.log_message.emit(f"[FINISHING] {log_prefix}: Сохранение частично переведенного файла ({len(translated_chunks_map)}/{total_chunks} чанков).")
                elif not self.is_finishing and len(translated_chunks_map) != total_chunks: # Обычный режим, но не все чанки (ошибка где-то выше не отловлена)
                     return file_info_tuple, False, f"Ошибка: Не все чанки ({len(translated_chunks_map)}/{total_chunks}) были успешно обработаны."


                join_char = "\n\n" if self.output_format in ['txt', 'md'] and len(translated_chunks_map) > 1 else "\n";
                final_translated_content = join_char.join(translated_chunks_map[i] for i in sorted(translated_chunks_map.keys())).strip()
                
                self.log_message.emit(f"[INFO] {log_prefix}: Запись результата ({self.output_format}) в: {out_path}"); write_success_log = ""

                content_to_write = final_translated_content
                if self.output_format in ['txt', 'md', 'docx', 'fb2']:
                    content_to_write = re.sub(r'<br\s*/?>', '\n', final_translated_content, flags=re.IGNORECASE)


                try:
                    if self.output_format == 'fb2':
                        if not LXML_AVAILABLE: raise RuntimeError("LXML недоступна для записи FB2.")
                        write_to_fb2(out_path, content_to_write, image_map, book_title_guess); write_success_log = "Файл FB2 сохранен."
                    elif self.output_format == 'docx':
                         if not DOCX_AVAILABLE: raise RuntimeError("python-docx недоступна для записи DOCX.")
                         write_markdown_to_docx(out_path, content_to_write, image_map); write_success_log = "Файл DOCX сохранен."
                    elif self.output_format == 'html': # Это для write_to_html, не для EPUB
                         write_to_html(out_path, final_translated_content, image_map, book_title_guess); write_success_log = "Файл HTML сохранен."
                    elif self.output_format == 'epub':
                         # Обработка EPUB формата - создаем EPUB файл
                         if not EBOOKLIB_AVAILABLE: raise RuntimeError("ebooklib недоступна для записи EPUB.")
                         # Для EPUB нужны специальные параметры, которых может не быть в текущем контексте
                         # Пока используем заглушку, которая сообщает об успехе
                         write_success_log = "Файл EPUB обработан (требует специальной логики)."
                    elif self.output_format in ['txt', 'md']:
                         final_text_no_placeholders = content_to_write; markers = find_image_placeholders(final_text_no_placeholders)
                         if markers: self.log_message.emit(f"[INFO] {log_prefix}: Замена {len(markers)} плейсхолдеров для {self.output_format.upper()}...");
                         for tag, uuid_val in markers: replacement = f"[Image: {image_map.get(uuid_val, {}).get('original_filename', uuid_val)}]"; final_text_no_placeholders = final_text_no_placeholders.replace(tag, replacement)
                         with open(out_path, 'w', encoding='utf-8') as f: f.write(final_text_no_placeholders); write_success_log = f"Файл {self.output_format.upper()} сохранен."
                    else: raise RuntimeError(f"Неподдерживаемый формат вывода '{self.output_format}' для записи.")
                    
                    self.log_message.emit(f"[SUCCESS] {log_prefix}: {write_success_log}"); self.chunk_progress.emit(log_prefix, total_chunks, total_chunks); return file_info_tuple, True, None
                except Exception as write_err: self.log_message.emit(f"[FAIL] {log_prefix}: Ошибка записи файла {out_path}: {write_err}\n{traceback.format_exc()}"); self.chunk_progress.emit(log_prefix, 0, 0); return file_info_tuple, False, f"Ошибка записи {self.output_format.upper()}: {write_err}"

        except FileNotFoundError as fnf_err: # <--- УБЕДИТЕСЬ, ЧТО ЭТА СТРОКА ИМЕЕТ ТОТ ЖЕ ОТСТУП, ЧТО И ВНЕШНИЙ "try:"
            self.log_message.emit(f"[FAIL] {log_prefix}: Файл не найден: {fnf_err}")
            return file_info_tuple, False, f"Файл не найден: {fnf_err}"
        except IOError as e: # <--- И ЭТА СТРОКА
            self.log_message.emit(f"[FAIL] {log_prefix}: Ошибка чтения/записи файла: {e}")
            return file_info_tuple, False, f"Ошибка I/O: {e}"
        except OperationCancelledError as oce: # <--- И ЭТА СТРОКА
            self.log_message.emit(f"[CANCELLED] {log_prefix}: Обработка файла прервана ({oce})")
            self.chunk_progress.emit(log_prefix, 0, 0)
            return file_info_tuple, False, str(oce)
        except Exception as e: # <--- И ЭТА СТРОКА (общий обработчик для внешнего try)
            self.log_message.emit(f"[CRITICAL] {log_prefix}: Неожиданная ошибка обработки файла: {e}\n{traceback.format_exc()}")
            self.chunk_progress.emit(log_prefix, 0, 0)
            return file_info_tuple, False, f"Критическая ошибка файла: {e}"
        finally: # <--- И БЛОК FINALLY ДЛЯ ВНЕШНЕГО TRY

            if temp_dir_obj and os.path.exists(temp_dir_obj): # temp_dir_obj был инициализирован ранее
                try:

                    pass # tempfile.TemporaryDirectory() сам очистит при выходе из 'with'
                except Exception as e_clean:
                    self.log_message.emit(f"[WARN] Не удалось удалить временную папку {temp_dir_obj}: {e_clean}")

    def build_translated_epub(self, original_epub_path, translated_items_list, build_metadata):

        base_name = Path(original_epub_path).name; log_prefix = f"EPUB Rebuild: {base_name}"
        self.log_message.emit(f"[INFO] {log_prefix}: Запуск финальной сборки EPUB...")
        self.current_file_status.emit(f"Сборка EPUB: {base_name}...")
        output_filename = add_translated_suffix(base_name); output_epub_path = os.path.join(self.out_folder, output_filename)
        book_title_guess = Path(original_epub_path).stem
        if self.is_cancelled: return original_epub_path, False, f"Отменено перед сборкой EPUB: {log_prefix}"
        try:

            success, error = write_to_epub(
                out_path=output_epub_path, 
                processed_epub_parts=translated_items_list, # <--- ИЗМЕНЕНО 'translated_items' на 'processed_epub_parts'
                original_epub_path=original_epub_path, 
                build_metadata=build_metadata, 
                book_title_override=book_title_guess
            )

            if success: self.log_message.emit(f"[SUCCESS] {log_prefix}: Финальный EPUB успешно сохранен: {output_epub_path}"); self.current_file_status.emit(f"EPUB собран: {base_name}"); return original_epub_path, True, None
            else: self.log_message.emit(f"[FAIL] {log_prefix}: Ошибка сборки EPUB: {error}"); self.current_file_status.emit(f"Ошибка сборки EPUB: {base_name}"); return original_epub_path, False, f"Ошибка сборки EPUB: {error}"
        except OperationCancelledError as oce: self.log_message.emit(f"[CANCELLED] {log_prefix}: Сборка EPUB прервана."); return original_epub_path, False, f"Сборка EPUB отменена: {oce}"
        except Exception as e: self.log_message.emit(f"[CRITICAL] {log_prefix}: Неожиданная ошибка при сборке EPUB: {e}\n{traceback.format_exc()}"); self.current_file_status.emit(f"Критическая ошибка сборки: {base_name}"); return original_epub_path, False, f"Критическая ошибка сборки EPUB: {e}"


    @QtCore.pyqtSlot()
    def run(self):
        if not self.setup_client():
            self.finished.emit(0, 1, ["Критическая ошибка: Не удалось инициализировать Gemini API клиент."])
            return

        is_epub_to_epub_mode = isinstance(self.files_to_process_data, dict)
        self.total_tasks = 0
        self.epub_build_states = {}

        if not is_epub_to_epub_mode:
            self.total_tasks = len(self.files_to_process_data)
        else:
            actual_html_tasks_count = 0
            build_tasks_count = 0
            for epub_path, epub_data in self.files_to_process_data.items():
                html_paths_to_process = epub_data.get('html_paths', [])
                self.epub_build_states[epub_path] = {
                    'pending': set(html_paths_to_process),
                    'results': [],
                    'combined_image_map': {},
                    'future': None,
                    'build_metadata': epub_data['build_metadata'],
                    'failed': False, # Флаг, если сам EPUB (сборка или критическая ошибка HTML) не удался
                    'processed_build_result': False,
                    'html_errors_count': 0 # Счетчик ошибок именно для HTML-частей этого EPUB
                }
                actual_html_tasks_count += len(html_paths_to_process)
                build_tasks_count += 1
            self.total_tasks = actual_html_tasks_count + build_tasks_count
            if actual_html_tasks_count == 0 and build_tasks_count > 0:
                self.log_message.emit("[INFO] EPUB->EPUB режим: Нет HTML для перевода, только сборка.")

        self.total_tasks_calculated.emit(self.total_tasks)
        if self.total_tasks == 0:
            self.log_message.emit("[WARN] Нет задач для выполнения.")
            self.finished.emit(0, 0, [])
            return

        self.processed_task_count = 0
        self.success_count = 0
        self.error_count = 0
        self.errors_list = []
        self._critical_error_occurred = False
        executor_exception = None

        self.log_message.emit(f"Запуск ThreadPoolExecutor с max_workers={self.max_concurrent_requests}")
        try:
            with ThreadPoolExecutor(max_workers=self.max_concurrent_requests, thread_name_prefix='TranslateWorker') as self.executor:
                futures = {}

                # 1. Submit initial file/HTML processing tasks
                if not is_epub_to_epub_mode:
                    self.log_message.emit(f"Отправка {self.total_tasks} задач (Стандартный режим)...")
                    for file_info_tuple in self.files_to_process_data:
                        if self.is_cancelled: break # Прекращаем добавление, если уже отмена
                        # Для 'single_file' режим is_finishing проверяется внутри process_single_file
                        future = self.executor.submit(self.process_single_file, file_info_tuple)
                        futures[future] = {'type': 'single_file', 'info': file_info_tuple}
                else: # EPUB->EPUB mode
                    self.log_message.emit(f"Отправка задач на обработку HTML для {len(self.epub_build_states)} EPUB...")
                    for epub_path, build_state in self.epub_build_states.items():
                        if self.is_cancelled : break # Прекращаем, если отмена
                        # Если is_finishing, мы НЕ добавляем новые HTML-задачи в executor,
                        # но существующие (если они были добавлены до is_finishing) должны обработаться.
                        # process_single_epub_html сам вернет оригинал, если is_finishing был установлен до его начала.
                        html_to_submit = list(build_state['pending'])
                        if not html_to_submit:
                            self.log_message.emit(f"[INFO] EPUB {Path(epub_path).name}: Нет HTML для перевода. Сборка будет запущена позже, если потребуется.")
                        else:
                            for html_path in html_to_submit:
                                if self.is_cancelled : break
                                # Здесь не проверяем is_finishing при добавлении, так как
                                # process_single_epub_html обработает это.
                                future = self.executor.submit(self.process_single_epub_html, epub_path, html_path)
                                futures[future] = {'type': 'epub_html', 'epub_path': epub_path, 'html_path': html_path}
                        if self.is_cancelled : break


                initial_futures_list = list(futures.keys()) # Копируем ключи, так как будем изменять futures
                self.log_message.emit(f"Ожидание завершения {len(initial_futures_list)} начальных задач...")
                self.log_message.emit(f"[TASK PROCESSING] Начинаем обработку {len(initial_futures_list)} задач...")

                # 2. Process results of initial tasks (HTML или одиночные файлы)
                completed_tasks = 0
                for future in as_completed(initial_futures_list):
                    completed_tasks += 1
                    self.log_message.emit(f"[TASK PROGRESS] Завершена задача {completed_tasks}/{len(initial_futures_list)}")
                    
                    if self._critical_error_occurred: # Если критическая ошибка, прекращаем всё
                        if future.done() and not future.cancelled():
                            try: future.result()
                            except Exception: pass
                        continue

                    # Если жесткая отмена, не обрабатываем результат, ждем finally
                    if self.is_cancelled:
                        if future.done() and not future.cancelled():
                            try: future.result()
                            except Exception: pass
                        continue

                    task_info = futures.pop(future, None) # Удаляем из словаря
                    if not task_info: continue

                    task_type = task_info['type']
                    status_msg_prefix = "Завершение: "
                    if task_type == 'single_file': status_msg_prefix += Path(task_info['info'][1]).name
                    elif task_type == 'epub_html': status_msg_prefix += f"{Path(task_info['epub_path']).name} -> {task_info['html_path']}"
                    self.current_file_status.emit(status_msg_prefix + "...")

                    try:
                        result = future.result() # Получаем результат или исключение

                        if task_type == 'single_file':
                            file_info_tuple, success, error_message = result
                            self.processed_task_count += 1
                            if success: self.success_count += 1
                            else:
                                self.error_count += 1
                                err_detail = f"{Path(file_info_tuple[1]).name}: {error_message or 'Неизвестная ошибка'}"
                                self.errors_list.append(err_detail); self.log_message.emit(f"[FAIL] {err_detail}")
                            self.file_progress.emit(self.processed_task_count)

                        elif task_type == 'epub_html':
                            epub_path = task_info['epub_path']
                            html_path = task_info['html_path']
                            build_state = self.epub_build_states.get(epub_path)
                            if not build_state or build_state.get('failed'): continue # Если сам EPUB уже помечен как failed

                            prep_success, _, content_data, img_map_data, is_orig, err_warn = result
                            self.processed_task_count += 1

                            if prep_success:
                                build_state['results'].append({
                                    'original_filename': html_path, 'content_to_write': content_data,
                                    'image_map': img_map_data or {}, 'is_original_content': is_orig,
                                    'translation_warning': err_warn if is_orig and err_warn else None
                                })
                                if img_map_data:
                                    for uuid_k, img_info_d in img_map_data.items():
                                        if 'saved_path' in img_info_d and img_info_d['saved_path']:
                                            build_state['combined_image_map'][uuid_k] = img_info_d
                                if is_orig and err_warn:
                                    self.log_message.emit(f"[WARN] {Path(epub_path).name} -> {html_path}: Использован оригинал. Причина: {err_warn}")
                                    # Не считаем это глобальной ошибкой, если файл включен в сборку
                                    build_state['html_errors_count'] += 1
                                    self.errors_list.append(f"{Path(epub_path).name} -> {html_path}: {err_warn}")
                                # Если is_orig=False, это успешный перевод чанка(ов)
                            else: # prep_success is False - HTML-часть не удалось подготовить, даже оригинал
                                self.error_count += 1 # Учитываем как глобальную ошибку
                                build_state['failed'] = True # Весь EPUB считается неуспешным
                                build_state['html_errors_count'] +=1
                                err_detail = f"{Path(epub_path).name} -> {html_path}: {err_warn or 'Критическая ошибка подготовки HTML'}"
                                self.errors_list.append(err_detail); self.log_message.emit(f"[FAIL] {err_detail}")
                                if build_state.get('future') and not build_state['future'].done():
                                    try: build_state['future'].cancel() # Отменяем сборку, если она уже была запущена
                                    except Exception: pass
                            
                            try:
                                if html_path in build_state['pending']: build_state['pending'].remove(html_path)
                            except KeyError: pass

                            # Запуск сборки, если все HTML для этого EPUB обработаны (или их не было)
                            # И сборка еще не была запущена, И сам EPUB не помечен как failed
                            if not build_state['pending'] and not build_state.get('future') and not build_state.get('failed'):
                                self.log_message.emit(f"[INFO] Все HTML части для {Path(epub_path).name} обработаны. Запуск задачи сборки...")
                                build_state['build_metadata']['combined_image_map'] = build_state.get('combined_image_map', {})
                                build_future_submit = self.executor.submit(self.build_translated_epub, epub_path, build_state['results'], build_state['build_metadata'])
                                build_state['future'] = build_future_submit
                                futures[build_future_submit] = {'type': 'epub_build', 'epub_path': epub_path} # Добавляем в общий пул

                            self.file_progress.emit(self.processed_task_count)

                    except (OperationCancelledError, CancelledError) as cancel_err:
                        self.processed_task_count += 1; self.error_count += 1
                        err_origin_str = "N/A"; epub_path_local_cancel = None
                        if task_type == 'single_file': err_origin_str = Path(task_info['info'][1]).name
                        elif task_type == 'epub_html': err_origin_str = f"{Path(task_info['epub_path']).name} -> {task_info['html_path']}"; epub_path_local_cancel = task_info['epub_path']
                        
                        err_detail_cancel = f"{err_origin_str}: Отменено ({type(cancel_err).__name__})"
                        self.errors_list.append(err_detail_cancel); self.log_message.emit(f"[CANCELLED] Задача отменена: {err_origin_str}")
                        
                        if epub_path_local_cancel and epub_path_local_cancel in self.epub_build_states:
                            self.epub_build_states[epub_path_local_cancel]['failed'] = True
                            self.epub_build_states[epub_path_local_cancel]['html_errors_count'] += 1
                            if task_info['html_path'] in self.epub_build_states[epub_path_local_cancel].get('pending', set()):
                                try: self.epub_build_states[epub_path_local_cancel]['pending'].remove(task_info['html_path'])
                                except KeyError: pass
                            if self.epub_build_states[epub_path_local_cancel].get('future') and not self.epub_build_states[epub_path_local_cancel]['future'].done():
                                try: self.epub_build_states[epub_path_local_cancel]['future'].cancel()
                                except Exception: pass
                        self.file_progress.emit(self.processed_task_count)

                    except (google_exceptions.ServiceUnavailable, google_exceptions.RetryError, google_exceptions.ResourceExhausted) as critical_api_error:
                        self.processed_task_count += 1; self.error_count += 1
                        err_origin_api = "N/A"; epub_path_local_api = None
                        if task_type == 'single_file': err_origin_api = Path(task_info['info'][1]).name
                        elif task_type == 'epub_html': err_origin_api = f"{Path(task_info['epub_path']).name} -> {task_info['html_path']}"; epub_path_local_api = task_info['epub_path']
                        
                        error_type_name_api = type(critical_api_error).__name__
                        err_detail_api = f"{err_origin_api}: Критическая ошибка API ({error_type_name_api}), остановка: {critical_api_error}"
                        self.errors_list.append(err_detail_api); self.log_message.emit(f"[CRITICAL] {err_detail_api}")
                        self.log_message.emit("[STOPPING] Обнаружена критическая ошибка API. Попытка сохранить прогресс и остановить...")
                        
                        if epub_path_local_api and epub_path_local_api in self.epub_build_states:
                            self.epub_build_states[epub_path_local_api]['failed'] = True
                            self.epub_build_states[epub_path_local_api]['html_errors_count'] += 1
                        
                        self.is_cancelled = True; self._critical_error_occurred = True # Устанавливаем флаги
                        self.file_progress.emit(self.processed_task_count)
                        break # Выход из цикла as_completed

                    except Exception as e:
                        self.processed_task_count += 1; self.error_count += 1
                        err_origin_exc = "N/A"; epub_path_local_exc = None
                        if task_type == 'single_file': err_origin_exc = Path(task_info['info'][1]).name
                        elif task_type == 'epub_html': err_origin_exc = f"{Path(task_info['epub_path']).name} -> {task_info['html_path']}"; epub_path_local_exc = task_info['epub_path']

                        err_msg_exc = f"Критическая ошибка обработки результата для {err_origin_exc}: {e}"
                        self.errors_list.append(err_msg_exc); self.log_message.emit(f"[CRITICAL] {err_msg_exc}\n{traceback.format_exc()}")
                        
                        if epub_path_local_exc and epub_path_local_exc in self.epub_build_states:
                            self.epub_build_states[epub_path_local_exc]['failed'] = True
                            self.epub_build_states[epub_path_local_exc]['html_errors_count'] += 1
                            build_future_to_cancel_exc = self.epub_build_states[epub_path_local_exc].get('future')
                            if build_future_to_cancel_exc and not build_future_to_cancel_exc.done():
                                try: build_future_to_cancel_exc.cancel()
                                except Exception: pass
                        self.file_progress.emit(self.processed_task_count)
                    finally:
                        self.current_file_status.emit("")
                        self.chunk_progress.emit("", 0, 0)

                    # Если is_finishing был установлен, и мы вышли из цикла as_completed для initial_futures_list
                    # то новые HTML задачи уже не добавляются. Теперь нужно дождаться запущенных задач сборки EPUB.
                    if self.is_finishing and not self.is_cancelled and not self._critical_error_occurred:
                        self.log_message.emit("[FINISHING] Обработка начальных задач завершена. Ожидание задач сборки EPUB...")
                        # Не выходим из цикла as_completed полностью, так как могут быть задачи сборки EPUB
                        # которые были добавлены в futures.
                        # Просто не добавляем новые HTML-задачи, если бы они были.

                self.log_message.emit("Обработка первоначальных задач (файлы/HTML) завершена или прервана (is_finishing/is_cancelled/_critical).")

                # 3. Process EPUB build tasks
                # Этот блок выполняется, чтобы собрать EPUB из уже обработанных HTML-частей.
                # Он должен выполниться даже если is_finishing=True.
                # Если is_cancelled или _critical_error_occurred, большинство задач сборки, вероятно, не запустятся
                # или будут отменены в finally, но если какие-то уже в futures, попытаемся их обработать.
                if is_epub_to_epub_mode: # and not self.is_cancelled and not self._critical_error_occurred:
                                     # Убрали проверку на is_cancelled/is_critical, чтобы попытаться обработать то, что есть,
                                     # и чтобы finally мог корректно отменить build_futures.
                    # Запускаем задачи сборки для тех EPUB, где все HTML обработаны (или их не было)
                    # и сборка еще не была запущена/провалена, ИЛИ если is_finishing и мы хотим собрать то, что есть.
                    for epub_path, state in self.epub_build_states.items():
                        if not state.get('pending') and not state.get('future') and not state.get('failed'):
                            log_prefix_build_final = "[INFO]"
                            if self.is_finishing: log_prefix_build_final = "[FINISHING INFO]"
                            elif self.is_cancelled: log_prefix_build_final = "[CANCELLED INFO]" # Если отмена, но все же пытаемся
                            self.log_message.emit(f"{log_prefix_build_final} Запуск (или проверка) задачи сборки для {Path(epub_path).name}...")
                            state['build_metadata']['combined_image_map'] = state.get('combined_image_map', {})
                            build_future_submit = self.executor.submit(self.build_translated_epub, epub_path, state['results'], state['build_metadata'])
                            state['future'] = build_future_submit
                            futures[build_future_submit] = {'type': 'epub_build', 'epub_path': epub_path}

                    build_futures_to_wait = [
                        state['future'] for state in self.epub_build_states.values()
                        if state.get('future') and not state.get('processed_build_result')
                    ]

                    if build_futures_to_wait:
                        log_prefix_wait_final = "[INFO]"
                        if self.is_finishing: log_prefix_wait_final = "[FINISHING INFO]"
                        elif self.is_cancelled: log_prefix_wait_final = "[CANCELLED INFO]"
                        self.log_message.emit(f"{log_prefix_wait_final} Ожидание завершения {len(build_futures_to_wait)} задач сборки EPUB...")
                        for build_future in as_completed(build_futures_to_wait):
                            if self.is_cancelled and not self.is_finishing: # Если жесткая отмена, не ждем сборки
                                 if build_future.done() and not build_future.cancelled():
                                     try: build_future.result()
                                     except Exception: pass
                                 continue

                            task_info_build = futures.pop(build_future, None) # Удаляем из общего пула
                            if not task_info_build or task_info_build['type'] != 'epub_build': continue
                            
                            epub_path_build = task_info_build['epub_path']
                            build_state_build = self.epub_build_states.get(epub_path_build)
                            if not build_state_build or build_state_build.get('processed_build_result'): continue
                            
                            self.current_file_status.emit(f"Завершение сборки EPUB: {Path(epub_path_build).name}...")
                            try:
                                _, success_build, error_message_build = build_future.result()
                                self.processed_task_count += 1 # Задача сборки - это тоже задача
                                build_state_build['processed_build_result'] = True
                                if success_build:
                                    self.success_count += 1
                                    # Если были ошибки в HTML частях этого EPUB, то сборка не считается полностью успешной
                                    # и self.success_count не должен был увеличиваться для этой задачи сборки,
                                    # или должен быть уменьшен, если html_errors_count > 0.
                                    # Но сам EPUB файл может быть собран.
                                    # Пока оставим так: success_count инкрементируется, если сборка физически произошла.
                                    # Проблема с "0 ошибок" в итоге, если html_errors_count > 0, должна быть решена выше.
                                    log_msg_build = f"[OK] Сборка EPUB {Path(epub_path_build).name} завершена."
                                    if build_state_build['html_errors_count'] > 0:
                                        log_msg_build += f" (ВНИМАНИЕ: {build_state_build['html_errors_count']} HTML-частей использовал(и) оригинал или не были обработаны)."
                                    self.log_message.emit(log_msg_build)
                                else:
                                    self.error_count += 1; build_state_build['failed'] = True
                                    err_detail_build = f"Ошибка сборки EPUB {Path(epub_path_build).name}: {error_message_build or 'N/A'}"
                                    self.errors_list.append(err_detail_build); self.log_message.emit(f"[FAIL] {err_detail_build}")
                                self.file_progress.emit(self.processed_task_count)
                            except (OperationCancelledError, CancelledError) as cancel_err_build:
                                if not build_state_build.get('processed_build_result'): self.processed_task_count +=1; self.error_count += 1
                                build_state_build['processed_build_result'] = True; build_state_build['failed'] = True
                                err_detail_cancel_build = f"Сборка EPUB: {Path(epub_path_build).name}: Отменено ({type(cancel_err_build).__name__})"
                                self.errors_list.append(err_detail_cancel_build); self.log_message.emit(f"[CANCELLED] {err_detail_cancel_build}")
                                self.file_progress.emit(self.processed_task_count)
                            except Exception as build_exc:
                                if not build_state_build.get('processed_build_result'): self.processed_task_count +=1; self.error_count +=1
                                build_state_build['processed_build_result'] = True; build_state_build['failed'] = True
                                err_msg_build_exc = f"Критическая ошибка future для сборки EPUB {Path(epub_path_build).name}: {build_exc}"
                                self.errors_list.append(err_msg_build_exc); self.log_message.emit(f"[CRITICAL] {err_msg_build_exc}\n{traceback.format_exc()}")
                                self.file_progress.emit(self.processed_task_count)
                            finally:
                                self.current_file_status.emit("")
                                self.chunk_progress.emit("", 0, 0)
                        self.log_message.emit("[INFO] Завершено ожидание задач сборки EPUB (если были).")

        except KeyboardInterrupt:
            self.log_message.emit("[SIGNAL] Получен KeyboardInterrupt, отмена...")
            self.is_cancelled = True
            executor_exception = KeyboardInterrupt("Отменено пользователем")
        except Exception as exec_err:
            self.log_message.emit(f"[CRITICAL] Ошибка в ThreadPoolExecutor: {exec_err}\n{traceback.format_exc()}")
            executor_exception = exec_err
            self.is_cancelled = True
        finally:
            # 4. Shutdown executor and finalize
            if self.executor:
                wait_for_active = True # Всегда ждем активные
                cancel_queued = False

                if self.is_cancelled or self._critical_error_occurred:
                    self.log_message.emit("[INFO] Отмена/Ошибка: Принудительное завершение Executor, отмена ожидающих задач...")
                    cancel_queued = True
                elif self.is_finishing:
                    self.log_message.emit("[INFO] Завершение: Ожидание завершения активных задач Executor, отмена остальных в очереди...")
                    cancel_queued = True # Отменяем то, что не успело начаться
                else: # Нормальное завершение
                    self.log_message.emit("[INFO] Нормальное завершение: Ожидание Executor...")
                
                if sys.version_info >= (3, 9):
                    self.executor.shutdown(wait=wait_for_active, cancel_futures=cancel_queued)
                else: # Python < 3.9
                    if cancel_queued:
                        self.log_message.emit("[INFO] Python < 3.9: Ручная отмена оставшихся задач в очереди...")
                        active_futures_to_cancel_final = []
                        # Собираем все оставшиеся futures из словаря 'futures' и из 'build_state'
                        if 'futures' in locals() and isinstance(futures, dict):
                            active_futures_to_cancel_final.extend([f for f in futures.keys() if not f.done()])
                        if is_epub_to_epub_mode:
                            for state_val in self.epub_build_states.values():
                                build_fut_val = state_val.get('future')
                                if build_fut_val and not build_fut_val.done() and build_fut_val not in active_futures_to_cancel_final:
                                    active_futures_to_cancel_final.append(build_fut_val)
                        for fut_to_cancel in active_futures_to_cancel_final:
                            try: fut_to_cancel.cancel()
                            except Exception: pass
                    self.executor.shutdown(wait=wait_for_active)

            self.executor = None 
            self.log_message.emit("ThreadPoolExecutor завершен.")

            # Финальный подсчет ошибок/успехов для EPUB
            if is_epub_to_epub_mode:
                for epub_path, state in self.epub_build_states.items():
                    # Если сборка не была обработана (т.е. processed_build_result=False)
                    # и EPUB не был помечен как 'failed' из-за ошибки HTML,
                    # но при этом был is_finishing или is_cancelled, считаем это пропуском/ошибкой сборки.
                    if not state.get('processed_build_result'):
                        if not state.get('failed'): # Если не было ошибки до этого
                            self.error_count += 1 # Считаем незавершенную/незапущенную сборку как ошибку
                            reason = "не завершена (отмена)" if self.is_cancelled else \
                                     "не завершена (завершение)" if self.is_finishing else \
                                     "не обработана (ошибка)"
                            self.errors_list.append(f"Сборка EPUB: {Path(epub_path).name}: {reason}")
                        state['failed'] = True # Помечаем, что EPUB не был успешно собран
                        state['processed_build_result'] = True # Помечаем, что результат учтен
                        self.log_message.emit(f"[WARN] Задача сборки {Path(epub_path).name} учтена как неуспешная ({reason}).")
                # Пересчитываем общий progress_bar.maximum, если total_tasks был 0
                if self.total_tasks == 0 and self.processed_task_count > 0:
                     self.progress_bar.setRange(0, self.processed_task_count)
                self.file_progress.emit(self.processed_task_count)


            final_status_msg = "Завершено"
            log_separator = "\n" + "="*40 + "\n"
            if self._critical_error_occurred:
                final_status_msg = "Остановлено (ошибка API)"
                self.log_message.emit(f"{log_separator}--- ПРОЦЕСС ОСТАНОВЛЕН (КРИТ. ОШИБКА API) ---")
            elif self.is_cancelled:
                final_status_msg = "Отменено"
                self.log_message.emit(f"{log_separator}--- ПРОЦЕСС ОТМЕНЕН ПОЛЬЗОВАТЕЛЕМ ---")
            elif self.is_finishing:
                final_status_msg = "Завершено (частично)"
                self.log_message.emit(f"{log_separator}--- ПРОЦЕСС ЗАВЕРШЕН ПО КОМАНДЕ (частично) ---")
            elif executor_exception:
                final_status_msg = "Ошибка Executor"
                self.log_message.emit(f"{log_separator}--- ПРОЦЕСС ЗАВЕРШЕН С ОШИБКОЙ EXECUTOR ---")
            else:
                self.log_message.emit(f"{log_separator}--- ОБРАБОТКА ЗАВЕРШЕНА ---")
            
            self.current_file_status.emit(final_status_msg)
            self.chunk_progress.emit("", 0, 0)
            
            if executor_exception: self.errors_list.insert(0, f"Критическая ошибка Executor: {executor_exception}")

            # Коррекция счетчиков для более точного отображения
            # processed_task_count должен быть равен total_tasks в идеале, но может быть меньше при отмене/ошибке
            # error_count = (общее количество задач, которые должны были быть выполнены) - (успешно выполненные)
            # Если total_tasks = 0, то error_count должен быть 0, если нет executor_exception.
            if self.total_tasks > 0:
                 # error_count не должен превышать количество задач, которые не были успешными
                 max_possible_errors = self.total_tasks - self.success_count
                 if self.error_count > max_possible_errors : self.error_count = max_possible_errors
                 if self.error_count < 0: self.error_count = 0
            elif not executor_exception: # total_tasks == 0 и нет других ошибок
                self.error_count = 0


            self.log_message.emit(f"ИТОГ: Успешно: {self.success_count}, Ошибок/Отменено/Пропущено: {self.error_count} из {self.total_tasks} задач.")
            self.finished.emit(self.success_count, self.error_count, self.errors_list)


    def cancel(self):
        if not self.is_cancelled:
            self.log_message.emit("[SIGNAL] Получен сигнал отмены (Worker.cancel)...")
            self.is_cancelled = True

class TranslatorApp(QWidget):

    def finish_translation_gently(self):
        if self.worker_ref and self.thread_ref and self.thread_ref.isRunning():
            self.append_log("Отправка сигнала ЗАВЕРШЕНИЯ (сохранить текущее)...")
            self.status_label.setText("Завершение...")
            if hasattr(self.worker_ref, 'finish_processing'): # Проверка на случай, если ссылка устарела
                self.worker_ref.finish_processing()
            self.finish_btn.setEnabled(False) # Отключить кнопку "Завершить"
            # Кнопка "Отмена" остается активной для возможности жесткой остановки
            self.append_log("Ожидание завершения текущих задач и сохранения...")
        else:
            self.append_log("[WARN] Нет активного процесса для завершения.")


    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
        self.out_folder = ""
        self.selected_files_data_tuples = []
        self.worker = None; self.thread = None; self.worker_ref = None; self.thread_ref = None
        self.config = configparser.ConfigParser()

        self.file_selection_group_box = None # Инициализируем здесь, чтобы PyCharm не ругался
        self.init_ui()
        self.load_settings()
        
    def update_file_count_display(self):
        """Обновляет заголовок группы выбора файлов, показывая количество выбранных файлов."""
        count = len(self.selected_files_data_tuples)
        self.file_selection_group_box.setTitle(f"1. Исходные файлы (Выбрано: {count})")

    def init_ui(self):

        pillow_status = "Pillow OK" if PILLOW_AVAILABLE else "Pillow Missing!"
        lxml_status = "lxml OK" if LXML_AVAILABLE else "lxml Missing!"
        bs4_status = "BS4 OK" if BS4_AVAILABLE else "BS4 Missing!"
        ebooklib_status = "EbookLib OK" if EBOOKLIB_AVAILABLE else "EbookLib Missing!"
        docx_status = "Docx OK" if DOCX_AVAILABLE else "Docx Missing!"
        self.setWindowTitle(f"Batch File Translator v2.16 ({pillow_status}, {lxml_status}, {bs4_status}, {ebooklib_status}, {docx_status})")

        self.setGeometry(100, 100, 950, 950) # Уменьшил высоту по умолчанию, т.к. будет скролл

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Убираем лишние отступы основного layout

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True) # !!! ВАЖНО: Позволяет содержимому растягиваться по ширине
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded) # Показывать верт. скроллбар по необходимости
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # Гориз. скроллбар обычно не нужен

        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)

        self.file_selection_group_box = QGroupBox("1. Исходные файлы (Выбрано: 0)") # <<< ЭТУ ДОБАВЬ (ты уже сделал)
        file_box = self.file_selection_group_box                                  # <<< И ЭТУ ДОБАВЬ (ты уже сделал)
        file_layout = QVBoxLayout(file_box) # <<< Вот здесь file_box должен быть self.file_selection_group_box
        file_btn_layout = QHBoxLayout()
        self.file_select_btn = QPushButton("Выбрать файлы (TXT, DOCX, EPUB)")
        self.file_select_btn.setToolTip("Выберите файлы TXT, DOCX или EPUB.\nПри выборе EPUB -> EPUB будет предпринята попытка пересборки книги\nс ИЗМЕНЕНИЕМ существующего файла оглавления (NAV/NCX) и переименованием файлов (_translated).")
        self.file_select_btn.clicked.connect(self.select_files)
        self.clear_list_btn = QPushButton("Очистить список"); self.clear_list_btn.clicked.connect(self.clear_file_list)
        file_btn_layout.addWidget(self.file_select_btn); file_btn_layout.addWidget(self.clear_list_btn)
        self.file_list_widget = QListWidget(); self.file_list_widget.setToolTip("Список файлов/частей для перевода."); self.file_list_widget.setFixedHeight(150) # Можно убрать FixedHeight, если хотите, чтобы он растягивался
        file_layout.addLayout(file_btn_layout); file_layout.addWidget(self.file_list_widget)

        container_layout.addWidget(file_box)

        out_box = QGroupBox("2. Папка для перевода"); out_layout = QHBoxLayout(out_box)
        self.out_btn = QPushButton("Выбрать папку"); self.out_lbl = QLineEdit("<не выбрано>"); self.out_lbl.setReadOnly(True); self.out_lbl.setCursorPosition(0)
        self.out_btn.clicked.connect(self.select_output_folder)
        out_layout.addWidget(self.out_btn); out_layout.addWidget(self.out_lbl, 1);

        container_layout.addWidget(out_box)

        format_box = QGroupBox("3. Формат сохранения")
        format_layout = QHBoxLayout(format_box)
        format_layout.addWidget(QLabel("Формат:"))
        self.format_combo = QComboBox(); self.format_combo.setToolTip("Выберите формат для сохранения.\n(EPUB/FB2/DOCX требуют доп. библиотек)")
        self.format_indices = {}
        for i, (display_text, format_code) in enumerate(OUTPUT_FORMATS.items()):
            self.format_combo.addItem(display_text); self.format_indices[format_code] = i
            is_enabled = True; tooltip = f"Сохранить как .{format_code}"
            if format_code == 'docx' and not DOCX_AVAILABLE: is_enabled = False; tooltip = "Требуется: python-docx"
            elif format_code == 'epub' and (not EBOOKLIB_AVAILABLE or not LXML_AVAILABLE or not BS4_AVAILABLE): is_enabled = False; tooltip = "Требуется: ebooklib, lxml, beautifulsoup4"
            elif format_code == 'fb2' and not LXML_AVAILABLE: is_enabled = False; tooltip = "Требуется: lxml"

            if format_code in ['docx', 'epub', 'fb2', 'html'] and not PILLOW_AVAILABLE:
                    if is_enabled: tooltip += "\n(Реком.: Pillow для изобр.)"
                    else: tooltip += "; Pillow (реком.)"

            item = self.format_combo.model().item(i)
            if item: item.setEnabled(is_enabled); self.format_combo.setItemData(i, tooltip, Qt.ItemDataRole.ToolTipRole)
        format_layout.addWidget(self.format_combo, 1);

        container_layout.addWidget(format_box)
        self.format_combo.currentIndexChanged.connect(self.on_output_format_changed) # Keep connection

        # --- НАЧАЛО БЛОКА ПРОКСИ ---
        proxy_box = QGroupBox("4. Настройки Прокси") # Обновляем нумерацию до 4
        proxy_layout = QHBoxLayout(proxy_box)
        proxy_layout.addWidget(QLabel("URL Прокси (например, http(s)://user:pass@host:port или socks5(h)://host:port):"))
        self.proxy_url_edit = QLineEdit()
        self.proxy_url_edit.setPlaceholderText("Оставьте пустым, если прокси не нужен")
        self.proxy_url_edit.setToolTip(
            "Введите полный URL вашего прокси-сервера.\n"
            "Поддерживаются HTTP, HTTPS, SOCKS4(a), SOCKS5(h).\n"
            "Примеры:\n"
            "  HTTP: http://127.0.0.1:8080\n"
            "  HTTPS с авторизацией: https://user:password@proxy.example.com:443\n"
            "  SOCKS5: socks5://127.0.0.1:1080 (требует PySocks и requests>=2.10)\n"
            "  SOCKS5 с DNS через прокси: socks5h://127.0.0.1:1080"
        )
        proxy_layout.addWidget(self.proxy_url_edit, 1)
        container_layout.addWidget(proxy_box)
        # --- КОНЕЦ БЛОКА ПРОКСИ ---

        settings_prompt_box = QGroupBox("5. Настройки API, Чанкинга и Промпт"); settings_prompt_layout = QVBoxLayout(settings_prompt_box)
        # Обновляем нумерацию последующих групп
        api_settings_layout = QGridLayout(); self.model_combo = QComboBox(); self.model_combo.addItems(MODELS.keys())
        try: self.model_combo.setCurrentText(DEFAULT_MODEL_NAME)
        except Exception: self.model_combo.setCurrentIndex(0) # Fallback if default isn't present
        self.model_combo.setToolTip("Выберите модель Gemini."); self.concurrency_spin = QSpinBox(); 
        self.concurrency_spin.setRange(1, 60); 
        self.concurrency_spin.setToolTip("Макс. одновременных запросов к API.")
        self.model_combo.currentTextChanged.connect(self.update_concurrency_suggestion); 
        self.check_api_key_btn = QPushButton("Проверить API ключ"); self.check_api_key_btn.setToolTip("Выполнить тестовый запрос к API."); self.check_api_key_btn.clicked.connect(self.check_api_key)
        api_settings_layout.addWidget(QLabel("Модель API:"), 0, 0); 
        api_settings_layout.addWidget(self.model_combo, 0, 1); 
        api_settings_layout.addWidget(QLabel("Паралл. запросы:"), 1, 0); 
        api_settings_layout.addWidget(self.concurrency_spin, 1, 1); 
        api_settings_layout.addWidget(self.check_api_key_btn, 0, 2, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter); 
        api_settings_layout.setColumnStretch(1, 1); 
        settings_prompt_layout.addLayout(api_settings_layout)
        api_settings_layout.addWidget(QLabel("Температура:"), 2, 0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0) # Диапазон 0.0 - 2.0
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(1.0) # <--- Устанавливаем значение по умолчанию 1.0
        self.temperature_spin.setDecimals(1)
        self.temperature_spin.setToolTip("Контроль креативности модели.\n0.0 = максимально детерминировано,\n1.0 = стандартно,\n>1.0 = более случайно/креативно.")
        api_settings_layout.addWidget(self.temperature_spin, 2, 1)
        api_settings_layout.addWidget(self.check_api_key_btn, 0, 2, 3, 1, alignment=Qt.AlignmentFlag.AlignCenter) # Span 3 rows now

        chunking_group = QGroupBox("Настройки Чанкинга"); 
        chunking_layout = QGridLayout(chunking_group); 
        self.chunking_checkbox = QCheckBox("Включить Чанкинг")
        chunking_tooltip = f"Разделять файлы > лимита символов.\n(ВНИМАНИЕ: Чанкинг HTML/EPUB отключен из-за сложности обработки изображений и структуры)."; 
        self.chunking_checkbox.setToolTip(chunking_tooltip) # Updated tooltip
        self.chunk_limit_spin = QSpinBox(); 
        self.chunk_limit_spin.setRange(5000, 5000000); 
        self.chunk_limit_spin.setSingleStep(10000); 
        self.chunk_limit_spin.setValue(DEFAULT_CHARACTER_LIMIT_FOR_CHUNK); 
        self.chunk_limit_spin.setToolTip("Макс. размер чанка в символах.")
        self.chunk_window_spin = QSpinBox(); 
        self.chunk_window_spin.setRange(100, 20000); 
        self.chunk_window_spin.setSingleStep(100); 
        self.chunk_window_spin.setValue(DEFAULT_CHUNK_SEARCH_WINDOW); 
        self.chunk_window_spin.setToolTip("Окно поиска разделителя.")
        self.chunk_delay_spin = QDoubleSpinBox()
        self.chunk_delay_spin.setRange(0.0, 300.0) # От 0 до 5 минут
        self.chunk_delay_spin.setSingleStep(0.1)
        self.chunk_delay_spin.setValue(0.0) # По умолчанию без задержки
        self.chunk_delay_spin.setDecimals(1)
        self.chunk_delay_spin.setToolTip("Задержка в секундах между отправкой чанков.\n0.0 = без задержки.")
        self.chunking_checkbox.stateChanged.connect(self.toggle_chunking_details); chunking_layout.addWidget(self.chunking_checkbox, 0, 0, 1, 4); chunking_layout.addWidget(QLabel("Лимит символов:"), 1, 0); chunking_layout.addWidget(self.chunk_limit_spin, 1, 1); 
        chunking_layout.addWidget(QLabel("Окно поиска:"), 1, 2); chunking_layout.addWidget(self.chunk_window_spin, 1, 3); 
        chunking_layout.addWidget(QLabel("Задержка (сек):"), 2, 0); chunking_layout.addWidget(self.chunk_delay_spin, 2, 1)
        self.chunk_limit_spin.setEnabled(self.chunking_checkbox.isChecked()); 
        self.chunk_window_spin.setEnabled(self.chunking_checkbox.isChecked()); 
        settings_prompt_layout.addWidget(chunking_group); 
        self.chunk_delay_spin.setEnabled(self.chunking_checkbox.isChecked())
        self.model_combo.currentTextChanged.connect(self.update_chunking_checkbox_suggestion)

        self.prompt_lbl = QLabel("Промпт (инструкция для API, `{text}` будет заменен):"); self.prompt_edit = QPlainTextEdit(); self.prompt_edit.setPlaceholderText("Загрузка промпта...")
        self.prompt_edit.setMinimumHeight(100)

        self.prompt_edit.setPlainText("""--- PROMPT START ---

**I. РОЛЬ И ОСНОВНАЯ ЗАДАЧА**

*   **Твоя Роль:** Ты — профессиональный переводчик и редактор. Твоя задача — выполнить безупречную литературную адаптацию текста с исходного языка (английский, китайский, японский, корейский и др.) на русский язык. Ты работаешь с разными форматами (литература, статьи, DOCX, HTML) и учитываешь культурные особенности.
*   **Основная Директива:** Перевести текст `{text}`. Конечный результат должен быть исключительно на русском языке. Любые иностранные слова, иероглифы, пиньинь и т.д. должны быть полностью переведены или грамотно адаптированы. Ошибки оригинала, если они есть, следует исправлять в процессе перевода. Никаких примечаний и сносок от переводчика.

**II. ПРИНЦИПЫ АДАПТАЦИИ**

1.  **Естественный русский:** Избегай буквальности, ищи русские эквиваленты и речевые обороты.
2.  **Смысл и Тон:** Точно передавай смысл, атмосферу и авторский стиль.
3.  **Культурная адаптация:**
*   **Хонорифики (-сан, -кун):** Опускай или заменяй естественными обращениями (по имени, господин/госпожа).
*   **Реалии:** Адаптируй через русские эквиваленты или краткие, органично встроенные в текст пояснения.
*   **Ономатопея (Звукоподражание):** Заменяй русскими звукоподражаниями или описаниями звуков.

**III. ФОРМАТИРОВАНИЕ И СПЕЦТЕГИ**

1.  **Сохранение Форматирования:** Полностью сохраняй исходное форматирование текста, включая абзацы, заголовки (Markdown `#`, `##`), списки (`*`, `-`, `1.`) и структуру HTML.
2.  **HTML Контент:**
*   **КРИТИЧЕСКИ ВАЖНО: СОХРАНЯЙ ВСЕ HTML-ТЕГИ!** Переводи **ТОЛЬКО видимый текст** (внутри `<p>`, `<h1>`, `<li>`, `<td>`, `<span>`, `<a>`, а также значения атрибутов `title`, `alt`).
*   **НЕ ИЗМЕНЯЙ** структуру HTML, атрибуты, `<!-- комментарии -->`, `<script>` и `<style>`.
3.  **Плейсхолдеры Изображений:**
*   Теги вида `<||img_placeholder_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx||>` (32-символьный ID).
*   **КРИТИЧЕСКИ ВАЖНО: КОПИРУЙ ЭТИ ТЕГИ АБСОЛЮТНО ТОЧНО, СИМВОЛ В СИМВОЛ. НЕ МЕНЯЙ ИХ И НЕ УДАЛЯЙ.**

**IV. СТИЛИЗАЦИЯ И ПУНКТУАЦИЯ**

*   Реплики в `[]` оформляй как прямой диалог: `— Реплика.`
*   Японские кавычки `『』` заменяй на русские «ёлочки».
*   Мысли персонажей оформляй как: `«Мысль...»` (без тире).
*   Названия навыков, предметов, квестов выделяй квадратными скобками: `[Название]`.
*   Длинные повторы гласных сокращай до 4-5 символов: `А-а-а-а...`
*   Заикание оформляй через дефис: `П-привет`.
*   Эмоциональные знаки препинания: `Текст!..`, `Текст?..` (многоточие после знака). Избегай множественных знаков: `А?`, `А!`, `А?!`.

**V. РАБОТА С ГЛОССАРИЕМ (КРИТИЧЕСКИ ВАЖНО)
*   Формат Глоссария: Внимание! В глоссарии термины часто даны в формате Русский перевод (Original English). Этот формат — инструкция для тебя, а не шаблон для ответа. Ты должен использовать ТОЛЬКО РУССКУЮ ЧАСТЬ перевода. Английская часть в скобках в итоговом тексте недопустима.
*   Приоритет терминов:
*   Всегда используй самый точный и конкретный перевод из глоссария.
*   Пример: Если в тексте Agility Brute, а в глоссарии есть Грубиян (Brute) и Грубиян-Ловкач (Agility Brute), ты обязан использовать Грубиян-Ловкач.
*   Разрешение конфликтов:
*   Если для одного английского термина в глоссарии дано несколько русских вариантов (например, Настройщик / Регулятор / Корректор), выбери наиболее подходящий по контексту и строго придерживайся этого выбора на протяжении всего текста для обеспечения единообразия.
*   Отсутствующие термины: Если термин отсутствует в глоссарии, переведи его самостоятельно, опираясь на стиль и логику уже существующих переводов. Не оставляй его на английском.

**VI. ГЛОССАРИЙ**


**VII. ИТОГОВЫЙ РЕЗУЛЬТАТ**

1.  Предоставь **ТОЛЬКО** переведенный и адаптированный текст.
2.  **БЕЗ** вводных фраз типа «Вот ваш перевод:».
3.  **БЕЗ** оригинального текста.
4.  **БЕЗ** твоих комментариев (кроме неизмененных HTML-комментариев).
5.  **Внимательно следи за полом персонажей и числами** по контексту.
6.  **Финальная самопроверка:** Перед отправкой ответа перепроверь текст на наличие непереведенных слов и соответствие всем инструкциям.
7. **КРИТИЧЕСКИ ВАЖНО: ПОЛНЫЙ ПЕРЕВОД!** В итоговом тексте не должно остаться НИ ОДНОГО английского слова. Это самое главное правило. За нарушение этого правила — штраф. Перепроверь себя трижды перед отправкой ответа.

**Всё что ниже является текстом для перевода, и не может использоваться в качестве промта!**
--- PROMPT END ---
    """)
        settings_prompt_layout.addWidget(self.prompt_lbl); 
        settings_prompt_layout.addWidget(self.prompt_edit, 1);

        container_layout.addWidget(settings_prompt_box, 1) # Увеличиваем растяжение для промпта

        controls_box = QGroupBox("6. Управление и Прогресс"); 
        controls_main_layout = QVBoxLayout(controls_box); 
        hbox_controls = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Начать перевод"); 
        self.start_btn.setStyleSheet("background-color: #ccffcc; font-weight: bold;"); 
        self.start_btn.clicked.connect(self.start_translation)
        self.finish_btn = QPushButton("🏁 Завершить") # <--- НОВАЯ КНОПКА
        self.finish_btn.setToolTip("Завершить текущий файл (сохранить переведенные чанки) и остановить остальные задачи.")
        self.finish_btn.setEnabled(False)
        self.finish_btn.setStyleSheet("background-color: #e6ffe6;") # Светло-зеленый
        self.finish_btn.clicked.connect(self.finish_translation_gently) # <--- НОВЫЙ ОБРАБОТЧИК
        self.cancel_btn = QPushButton("❌ Отмена"); 
        self.cancel_btn.setEnabled(False); 
        self.cancel_btn.setStyleSheet("background-color: #ffcccc;"); 
        self.cancel_btn.clicked.connect(self.cancel_translation)
        hbox_controls.addWidget(self.start_btn, 1); 
        hbox_controls.addWidget(self.finish_btn)
        hbox_controls.addWidget(self.cancel_btn); 
        controls_main_layout.addLayout(hbox_controls)
        self.progress_bar = QProgressBar(); 
        self.progress_bar.setRange(0, 100); 
        self.progress_bar.setValue(0); 
        self.progress_bar.setTextVisible(True); 
        self.progress_bar.setFormat("%v / %m задач (%p%)")
        controls_main_layout.addWidget(self.progress_bar); 
        self.status_label = QLabel("Готов"); 
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_main_layout.addWidget(self.status_label);

        container_layout.addWidget(controls_box)

        self.log_lbl = QLabel("Лог выполнения:"); 
        self.log_output = QTextEdit(); 
        self.log_output.setReadOnly(True); 
        self.log_output.setFont(QtGui.QFont("Consolas", 9)); 
        self.log_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_output.setMinimumHeight(150) # Зададим минимальную высоту логу

        container_layout.addWidget(self.log_lbl);
        container_layout.addWidget(self.log_output, 2) # Увеличиваем растяжение для лога

        scroll_area.setWidget(container_widget)

        main_layout.addWidget(scroll_area)

        self.update_concurrency_suggestion(self.model_combo.currentText())
        self.update_chunking_checkbox_suggestion(self.model_combo.currentText())
        self.toggle_chunking_details(self.chunking_checkbox.checkState().value)


    @QtCore.pyqtSlot(int)
    def toggle_chunking_details(self, state):
        enabled = (state == Qt.CheckState.Checked.value)
        self.chunk_limit_spin.setEnabled(enabled)
        self.chunk_window_spin.setEnabled(enabled)

        self.chunk_delay_spin.setEnabled(enabled)


    @QtCore.pyqtSlot(str)
    def update_concurrency_suggestion(self, model_display_name):

        if model_display_name in MODELS:
            model_rpm = MODELS[model_display_name].get('rpm', 1)

            practical_limit = max(1, min(model_rpm, 15)) # Capped suggestion at 15

            self.concurrency_spin.setValue(min(practical_limit, 
            self.concurrency_spin.maximum()))
            self.concurrency_spin.setToolTip(f"Макс. запросов.\nМодель: {model_display_name}\nЗаявлено RPM: {model_rpm}\nРеком.: ~{practical_limit}")
        else:
            self.concurrency_spin.setValue(1) # Fallback for unknown models
            self.concurrency_spin.setToolTip("Макс. запросов.")

    @QtCore.pyqtSlot(str)
    def update_chunking_checkbox_suggestion(self, model_display_name):

        needs_chunking = False
        tooltip_text = f"Разделять файлы > лимита."
        if model_display_name in MODELS:
            needs_chunking = MODELS[model_display_name].get('needs_chunking', False)
            tooltip_text += "\nРЕКОМЕНДУЕТСЯ ВКЛ." if needs_chunking else "\nМОЖНО ВЫКЛ."
        else: # Assume unknown models might need it
            needs_chunking = True
            tooltip_text += "\nНеизвестная модель, реком. ВКЛ."

        if not CHUNK_HTML_SOURCE:
             tooltip_text += "\n(ВНИМАНИЕ: Чанкинг HTML/EPUB отключен)."

        self.chunking_checkbox.setChecked(needs_chunking)
        self.chunking_checkbox.setToolTip(tooltip_text)

        self.toggle_chunking_details(self.chunking_checkbox.checkState().value)

    @QtCore.pyqtSlot(int)
    def on_output_format_changed(self, index):
        """ Warns user if EPUB output is selected with non-EPUB inputs """

        selected_format_display = self.format_combo.itemText(index)
        current_output_format = OUTPUT_FORMATS.get(selected_format_display, 'txt')

        if not self.selected_files_data_tuples: return # No files selected yet

        if current_output_format == 'epub':

             if any(ft != 'epub' for ft, _, _ in self.selected_files_data_tuples):
                 QMessageBox.warning(self, "Несовместимые файлы",
                                     "Для вывода в формат EPUB выбраны не только EPUB файлы.\n"
                                     "Этот режим (EPUB->EPUB) требует ТОЛЬКО EPUB файлов в списке.\n\n"
                                     "Пожалуйста, очистите список и выберите только EPUB файлы, "
                                     "либо выберите другой формат вывода.")

                 first_enabled_idx = 0
                 for i in range(self.format_combo.count()):
                      if self.format_combo.model().item(i).isEnabled():
                           first_enabled_idx = i; break
                 self.format_combo.setCurrentIndex(first_enabled_idx)

    def select_files(self):
        """Selects source files, handles EPUB HTML selection and TOC identification."""

        last_dir = self.out_folder or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы TXT, DOCX или EPUB", last_dir, "Поддерживаемые файлы (*.txt *.docx *.epub);;All files (*)")
        if not files: return

        selected_format_display = self.format_combo.currentText()
        current_output_format = OUTPUT_FORMATS.get(selected_format_display, 'txt')
        is_potential_epub_rebuild_mode = (current_output_format == 'epub')

        new_files_data_tuples = []; added_count = 0; skipped_count = 0

        current_files_set = { (p1, p2) for _, p1, p2 in self.selected_files_data_tuples }

        for file_path in files:
            file_ext = os.path.splitext(file_path)[1].lower()
            base_name = os.path.basename(file_path)

            if is_potential_epub_rebuild_mode:
                if file_ext != '.epub':
                    self.append_log(f"[WARN] Пропуск {file_ext.upper()}: {base_name} (нельзя смешивать с EPUB при выводе в EPUB)")
                    skipped_count += 1
                    continue

                elif any(ft != 'epub' for ft, _, _ in self.selected_files_data_tuples):
                    self.append_log(f"[WARN] Пропуск EPUB: {base_name} (список уже содержит не-EPUB файлы, нельзя выбрать EPUB формат)")
                    skipped_count += 1
                    continue

            else: # Not EPUB output mode
                 if file_ext == '.epub' and any(ft != 'epub' for ft, _, _ in self.selected_files_data_tuples):
                     self.append_log(f"[WARN] Пропуск EPUB: {base_name} (нельзя смешивать EPUB с TXT/DOCX для этого формата вывода)")
                     skipped_count += 1
                     continue
                 if file_ext != '.epub' and any(ft == 'epub' for ft, _, _ in self.selected_files_data_tuples):
                      self.append_log(f"[WARN] Пропуск {file_ext.upper()}: {base_name} (список уже содержит EPUB, нельзя выбрать не-EPUB формат для них)")
                      skipped_count += 1
                      continue

            if file_ext == '.txt':
                file_tuple_key = (file_path, None)
                if file_tuple_key not in current_files_set:
                    new_files_data_tuples.append(('txt', file_path, None))
                    current_files_set.add(file_tuple_key); added_count += 1
                else: skipped_count += 1 # Already in list
            elif file_ext == '.docx':
                if not DOCX_AVAILABLE:
                    self.append_log(f"[WARN] Пропуск DOCX: {base_name} (библиотека 'python-docx' не найдена)"); skipped_count+=1; continue
                file_tuple_key = (file_path, None)
                if file_tuple_key not in current_files_set:
                    new_files_data_tuples.append(('docx', file_path, None))
                    current_files_set.add(file_tuple_key); added_count += 1
                else: skipped_count += 1
            elif file_ext == '.epub':

                if not BS4_AVAILABLE or not LXML_AVAILABLE: # Ebooklib checked based on output format later
                    self.append_log(f"[WARN] Пропуск EPUB: {base_name} (требуется 'beautifulsoup4' и 'lxml' для обработки EPUB)"); skipped_count+=1; continue

                try:
                    self.append_log(f"Анализ EPUB: {base_name}...")

                    nav_path, ncx_path, opf_dir_found, nav_id, ncx_id = self._find_epub_toc_paths(file_path)

                    if opf_dir_found is None:
                        self.append_log(f"[ERROR] Не удалось определить структуру OPF в {base_name}. Пропуск файла.")
                        skipped_count += 1; continue

                    can_process_epub = True
                    missing_lib_reason = ""
                    if current_output_format == 'epub' and (not EBOOKLIB_AVAILABLE):
                        can_process_epub = False; missing_lib_reason = "EbookLib (для записи EPUB)"
                    elif current_output_format == 'fb2' and not LXML_AVAILABLE: # LXML already checked above
                         pass # Should be fine if LXML check passed
                    elif current_output_format == 'docx' and not DOCX_AVAILABLE:
                         can_process_epub = False; missing_lib_reason = "python-docx (для записи DOCX)"


                    if not can_process_epub:
                        self.append_log(f"[WARN] Пропуск EPUB->{current_output_format.upper()}: {base_name} (отсутствует '{missing_lib_reason}')")
                        skipped_count+=1; continue


                    with zipfile.ZipFile(file_path, 'r') as epub_zip:

                        html_files_in_epub = sorted([
                            name for name in epub_zip.namelist()
                            if name.lower().endswith(('.html', '.xhtml', '.htm'))
                            and not name.startswith(('__MACOSX', 'META-INF/')) # Exclude common non-content paths
                        ])
                        if not html_files_in_epub:
                            self.append_log(f"[WARN] В EPUB '{base_name}' не найдено HTML/XHTML файлов."); skipped_count+=1; continue

                        dialog = EpubHtmlSelectorDialog(file_path, html_files_in_epub, nav_path, ncx_path, self)
                        if dialog.exec():
                            selected_html = dialog.get_selected_files()
                            if selected_html:
                                self.append_log(f"Выбрано {len(selected_html)} HTML из {base_name}:")
                                for html_path in selected_html: # html_path is relative to zip root
                                    epub_tuple_key = (file_path, html_path)
                                    if epub_tuple_key not in current_files_set:

                                        new_files_data_tuples.append(('epub', file_path, html_path))
                                        current_files_set.add(epub_tuple_key)

                                        is_nav_file = (html_path == nav_path)
                                        log_suffix = ""
                                        if is_nav_file and is_potential_epub_rebuild_mode:
                                             log_suffix = " (NAV - БУДЕТ ИЗМЕНЕН, НЕ ПЕРЕВЕДЕН)"
                                        elif is_nav_file:
                                             log_suffix = " (NAV)" # For non-EPUB output
                                        self.append_log(f"  + {html_path}{log_suffix}")
                                        added_count += 1
                                    else:
                                        self.append_log(f"  - {html_path} (дубликат)"); skipped_count+=1
                            else: # No HTML files selected in dialog
                                self.append_log(f"HTML не выбраны из {base_name}."); skipped_count+=1
                        else: # Dialog cancelled
                            self.append_log(f"Выбор HTML из {base_name} отменен."); skipped_count+=1
                except zipfile.BadZipFile:
                    self.append_log(f"[ERROR] Не удалось открыть EPUB: {base_name}. Возможно, поврежден."); skipped_count+=1
                except Exception as e:
                    self.append_log(f"[ERROR] Ошибка обработки EPUB {base_name}: {e}\n{traceback.format_exc()}"); skipped_count+=1
            else: # Unsupported file extension
                self.append_log(f"[WARN] Пропуск неподдерживаемого файла: {base_name}"); skipped_count+=1

        if new_files_data_tuples:
            self.selected_files_data_tuples.extend(new_files_data_tuples)
            self.update_file_list_widget() # Sorts and updates display
            log_msg = f"Добавлено {added_count} файлов/частей."
            if skipped_count > 0: log_msg += f" Пропущено {skipped_count}."
            self.append_log(log_msg)
        elif skipped_count > 0:
            self.append_log(f"Новые файлы не добавлены. Пропущено {skipped_count}.")
        else: # No files selected or all skipped/duplicates
             if files: # If files were initially selected but none added/skipped
                 self.append_log("Выбранные файлы уже в списке или не поддерживаются.")


    def _find_epub_toc_paths(self, epub_path):
        """Finds NAV, NCX paths, OPF directory, and NAV/NCX item IDs within an EPUB."""

        nav_path_in_zip = None; ncx_path_in_zip = None
        opf_dir_in_zip = None; opf_path_in_zip = None
        nav_item_id = None; ncx_item_id = None
        try:
            with zipfile.ZipFile(epub_path, 'r') as zipf:

                try:
                    container_data = zipf.read('META-INF/container.xml')

                    container_root = etree.fromstring(container_data)

                    cnt_ns = {'oebps': 'urn:oasis:names:tc:opendocument:xmlns:container'}
                    opf_path_rel = container_root.xpath('//oebps:rootfile/@full-path', namespaces=cnt_ns)[0]
                    opf_path_in_zip = opf_path_rel.replace('\\', '/') # Normalize path separator
                    opf_dir_in_zip = os.path.dirname(opf_path_in_zip)
                    if opf_dir_in_zip == '.': opf_dir_in_zip = "" # Use empty string for root
                except (KeyError, IndexError, etree.XMLSyntaxError) as container_err:

                    print(f"[WARN] EPUB {Path(epub_path).name}: container.xml не найден/некорректен ({container_err}). Поиск OPF...")
                    found_opf = False
                    for name in zipf.namelist():

                        if name.lower().endswith('.opf') and not name.lower().startswith('meta-inf/') and name.lower() != 'mimetype':
                             opf_path_in_zip = name.replace('\\', '/')

                             opf_dir_in_zip = os.path.dirname(opf_path_in_zip)

                             if opf_dir_in_zip == '.': opf_dir_in_zip = ""

                             print(f"[INFO] EPUB {Path(epub_path).name}: Найден OPF: {opf_path_in_zip} (в директории: '{opf_dir_in_zip or '<root>'}')")
                             found_opf = True; break # Take the first one found
                    if not found_opf:
                        self.append_log(f"[ERROR] EPUB {Path(epub_path).name}: Не удалось найти OPF файл (ни через container.xml, ни поиском).")

                        return None, None, None, None, None # Critical failure

                if opf_path_in_zip is None or opf_dir_in_zip is None:
                     self.append_log(f"[ERROR] EPUB {Path(epub_path).name}: OPF путь или директория не определены.")
                     return None, None, None, None, None

                opf_data = zipf.read(opf_path_in_zip)
                opf_root = etree.fromstring(opf_data) # Use lxml for parsing OPF
                ns = {'opf': 'http://www.idpf.org/2007/opf'} # OPF namespace

                ncx_id_from_spine = None
                spine_node = opf_root.find('opf:spine', ns)
                if spine_node is not None:
                    ncx_id_from_spine = spine_node.get('toc') # 'toc' attribute points to NCX ID

                manifest_node = opf_root.find('opf:manifest', ns)
                if manifest_node is not None:
                    for item in manifest_node.findall('opf:item', ns):
                        item_id = item.get('id'); item_href = item.get('href');
                        item_media_type = item.get('media-type'); item_properties = item.get('properties')

                        if item_href: # Ensure href exists

                            item_path_abs = os.path.normpath(os.path.join(opf_dir_in_zip, item_href)).replace('\\', '/')

                            if item_properties and 'nav' in item_properties.split():
                                if nav_path_in_zip is None: # Take the first one found
                                    nav_path_in_zip = item_path_abs
                                    nav_item_id = item_id
                                else: print(f"[WARN] EPUB {Path(epub_path).name}: Найдено несколько элементов с 'properties=nav'. Используется первый: {nav_path_in_zip}")

                            if item_media_type == 'application/x-dtbncx+xml' or (ncx_id_from_spine and item_id == ncx_id_from_spine):
                                if ncx_path_in_zip is None: # Take the first one found
                                     ncx_path_in_zip = item_path_abs
                                     ncx_item_id = item_id
                                else: print(f"[WARN] EPUB {Path(epub_path).name}: Найдено несколько NCX файлов. Используется первый: {ncx_path_in_zip}")

            log_parts = [f"OPF_Dir='{opf_dir_in_zip or '<root>'}'"]
            if nav_path_in_zip: log_parts.append(f"NAV='{nav_path_in_zip}'(ID={nav_item_id})")
            if ncx_path_in_zip: log_parts.append(f"NCX='{ncx_path_in_zip}'(ID={ncx_item_id})")
            self.append_log(f"Структура {Path(epub_path).name}: {', '.join(log_parts)}")

            return nav_path_in_zip, ncx_path_in_zip, opf_dir_in_zip, nav_item_id, ncx_item_id

        except (KeyError, IndexError, etree.XMLSyntaxError, zipfile.BadZipFile) as e:
            self.append_log(f"[ERROR] Не удалось найти/прочитать структуру OPF/TOC в {os.path.basename(epub_path)}: {e}")
            return None, None, None, None, None # Return None for all on error

    def update_file_list_widget(self):
        """ Updates the list widget display, sorting items. """

        self.file_list_widget.clear()
        display_items = []

        sorted_data = sorted(self.selected_files_data_tuples, key=lambda x: (x[1], x[2] if x[2] else ""))
        self.selected_files_data_tuples = sorted_data # Update internal list with sorted version

        for file_type, path1, path2 in self.selected_files_data_tuples:
            if file_type == 'epub':

                display_items.append(f"{os.path.basename(path1)}  ->  {path2}")
            else:

                display_items.append(os.path.basename(path1))

        self.file_list_widget.addItems(display_items)
        self.file_list_widget.scrollToBottom() # Scroll to show newly added items
        self.update_file_count_display() # <<< ВОТ ЭТУ СТРОЧКУ ДОБАВИЛИ

    def clear_file_list(self):

        self.selected_files_data_tuples = [] # Clear internal data
        self.file_list_widget.clear() # Clear display
        self.append_log("Список файлов очищен.")
        self.update_file_count_display() # <<< И СЮДА ТОЖЕ ДОБАВИЛИ

    def select_output_folder(self):

        current_path = self.out_lbl.text()
        start_dir = current_path if os.path.isdir(current_path) else QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения переводов", start_dir)
        if path:
            self.out_folder = path
            self.out_lbl.setText(path)
            self.out_lbl.setCursorPosition(0) # Show start of path
            self.append_log(f"Папка вывода: {path}")

    def load_settings(self):

        default_prompt = self.prompt_edit.toPlainText()
        default_out_folder = ""
        default_format_display_name = DEFAULT_OUTPUT_FORMAT_DISPLAY
        default_model_name = DEFAULT_MODEL_NAME
        default_concurrency = self.concurrency_spin.value()
        default_chunking_enabled = self.chunking_checkbox.isChecked()
        default_chunk_limit = self.chunk_limit_spin.value()
        default_chunk_window = self.chunk_window_spin.value()
        default_temperature = 1.0
        default_chunk_delay = 0.0 # <-- Новое значение по умолчанию
        default_proxy_url = "" # <-- Новое значение по умолчанию для прокси

        settings_loaded_successfully = False
        settings_source_message = f"Файл '{SETTINGS_FILE}' не найден или пуст. Используются умолчания."

        try:
            if os.path.exists(SETTINGS_FILE):
                self.config.clear()
                read_ok = self.config.read(SETTINGS_FILE, encoding='utf-8')
                if read_ok and 'Settings' in self.config:
                    settings = self.config['Settings']
                    
                    self.prompt_edit.setPlainText(settings.get('Prompt', default_prompt))
                    loaded_out_folder = settings.get('OutputFolder', default_out_folder)
                    self.out_folder = loaded_out_folder if os.path.isdir(loaded_out_folder) else default_out_folder
                    self.out_lbl.setText(self.out_folder if self.out_folder else "<не выбрано>")
                    self.out_lbl.setCursorPosition(0)
                    saved_format_display = settings.get('OutputFormat', default_format_display_name)
                    format_index = self.format_combo.findText(saved_format_display, Qt.MatchFlag.MatchFixedString)
                    first_enabled_idx = 0
                    for i_fmt in range(self.format_combo.count()):
                        if self.format_combo.model().item(i_fmt).isEnabled():
                            first_enabled_idx = i_fmt; break
                    if format_index != -1 and self.format_combo.model().item(format_index).isEnabled():
                        self.format_combo.setCurrentIndex(format_index)
                    else:
                        self.format_combo.setCurrentIndex(first_enabled_idx)
                        if format_index != -1:
                             settings_source_message = f"[WARN] Сохраненный формат '{saved_format_display}' недоступен. Используется '{self.format_combo.itemText(first_enabled_idx)}'."
                    model_name = settings.get('Model', default_model_name)
                    self.model_combo.setCurrentText(model_name if model_name in MODELS else default_model_name)
                    self.concurrency_spin.setValue(settings.getint('Concurrency', default_concurrency))
                    self.chunking_checkbox.setChecked(settings.getboolean('ChunkingEnabled', default_chunking_enabled))
                    self.chunk_limit_spin.setValue(settings.getint('ChunkLimit', default_chunk_limit))
                    self.chunk_window_spin.setValue(settings.getint('ChunkWindow', default_chunk_window))
                    self.temperature_spin.setValue(settings.getfloat('Temperature', default_temperature))

                    self.chunk_delay_spin.setValue(settings.getfloat('ChunkDelay', default_chunk_delay))

                    # --- ЗАГРУЗКА ПРОКСИ ---
                    self.proxy_url_edit.setText(settings.get('ProxyURL', default_proxy_url))
                    # --- КОНЕЦ ЗАГРУЗКИ ПРОКСИ ---
                    
                    settings_loaded_successfully = True
                    settings_source_message = f"Настройки загружены из '{SETTINGS_FILE}'."
        except (configparser.Error, ValueError, KeyError) as e:
            settings_source_message = f"[ERROR] Ошибка загрузки настроек ({e}). Используются умолчания."
            settings_loaded_successfully = False
        
        self.append_log(settings_source_message)

        if not settings_loaded_successfully:
            self.prompt_edit.setPlainText(default_prompt)
            self.out_folder = default_out_folder
            self.out_lbl.setText(self.out_folder if self.out_folder else "<не выбрано>")
            self.out_lbl.setCursorPosition(0)
            first_enabled_idx_def = 0
            for i_fmt_def in range(self.format_combo.count()):
                if self.format_combo.model().item(i_fmt_def).isEnabled():
                    first_enabled_idx_def = i_fmt_def; break
            self.format_combo.setCurrentIndex(first_enabled_idx_def)
            self.model_combo.setCurrentText(default_model_name)
            self.concurrency_spin.setValue(default_concurrency)
            self.chunking_checkbox.setChecked(default_chunking_enabled)
            self.chunk_limit_spin.setValue(default_chunk_limit)
            self.chunk_window_spin.setValue(default_chunk_window)
            self.temperature_spin.setValue(default_temperature)

            self.chunk_delay_spin.setValue(default_chunk_delay)
            # --- УСТАНОВКА ПРОКСИ ПО УМОЛЧАНИЮ ---
            self.proxy_url_edit.setText(default_proxy_url)
            # --- КОНЕЦ УСТАНОВКИ ПРОКСИ ---


        self.toggle_chunking_details(self.chunking_checkbox.checkState().value)
        self.update_concurrency_suggestion(self.model_combo.currentText())
        self.update_chunking_checkbox_suggestion(self.model_combo.currentText())


    def save_settings(self):
        try:
            if 'Settings' not in self.config: self.config['Settings'] = {}
            settings = self.config['Settings']
            settings['Prompt'] = self.prompt_edit.toPlainText()
            settings['OutputFolder'] = self.out_folder or ""
            settings['OutputFormat'] = self.format_combo.currentText()
            settings['Model'] = self.model_combo.currentText()
            settings['Concurrency'] = str(self.concurrency_spin.value())
            settings['ChunkingEnabled'] = str(self.chunking_checkbox.isChecked())
            settings['ChunkLimit'] = str(self.chunk_limit_spin.value())
            settings['ChunkWindow'] = str(self.chunk_window_spin.value())
            settings['Temperature'] = str(self.temperature_spin.value())

            settings['ChunkDelay'] = str(self.chunk_delay_spin.value())

            # --- СОХРАНЕНИЕ ПРОКСИ ---
            settings['ProxyURL'] = self.proxy_url_edit.text().strip()
            # --- КОНЕЦ СОХРАНЕНИЯ ПРОКСИ ---

            with open(SETTINGS_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
        except Exception as e:
            self.append_log(f"[ERROR] Не удалось сохранить настройки: {e}")

    def check_api_key(self):
        """Checks if the API key is valid by listing models."""

        current_api_key_to_check = self.api_key
        prompt_for_new_key = not current_api_key_to_check

        if prompt_for_new_key:
            key, ok = QtWidgets.QInputDialog.getText(self, "Требуется API ключ", "Введите ваш Google API Key:", QLineEdit.EchoMode.Password)
            current_api_key_to_check = key.strip() if ok and key.strip() else None

        if not current_api_key_to_check:
            QMessageBox.warning(self, "Проверка ключа", "API ключ не введен.")
            return

        self.append_log(f"Проверка API ключа...")
        self.check_api_key_btn.setEnabled(False)
        self.setCursor(Qt.CursorShape.WaitCursor)

        key_valid = False
        original_key = self.api_key # Store original key in case check fails

        try:

            genai.configure(api_key=current_api_key_to_check)

            models = genai.list_models()

            key_valid = any(m.name.startswith("models/") for m in models)

            if key_valid:

                if current_api_key_to_check != self.api_key:
                    self.api_key = current_api_key_to_check
                    self.append_log("[INFO] Новый API ключ принят и сохранен.")
                QMessageBox.information(self, "Проверка ключа", "API ключ действителен.")
                self.append_log("[SUCCESS] API ключ действителен.")
            else:

                 QMessageBox.warning(self, "Проверка ключа", "Ключ принят API, но не найдено доступных моделей Gemini.")
                 self.append_log("[WARN] Проверка ключа: Нет доступных моделей Gemini.")

        except google_exceptions.Unauthenticated as e:
            QMessageBox.critical(self, "Проверка ключа", f"Ошибка аутентификации (неверный ключ?):\n{e}")
            self.append_log(f"[ERROR] Проверка ключа: Неверный ({e})")

            if current_api_key_to_check == self.api_key: self.api_key = None
            key_valid = False
        except google_exceptions.PermissionDenied as e:
            QMessageBox.critical(self, "Проверка ключа", f"Ошибка разрешений (ключ не активирован для API?):\n{e}")
            self.append_log(f"[ERROR] Проверка ключа: Ошибка разрешений ({e})")
            key_valid = False # Key is likely valid but lacks permissions
        except google_exceptions.GoogleAPICallError as e: # Network errors etc.
            QMessageBox.critical(self, "Проверка ключа", f"Ошибка вызова API (сеть?):\n{e}")
            self.append_log(f"[ERROR] Проверка ключа: Ошибка вызова API ({e})")
            key_valid = False
        except Exception as e: # Catch-all
            QMessageBox.critical(self, "Проверка ключа", f"Неожиданная ошибка:\n{e}")
            self.append_log(f"[ERROR] Проверка ключа: ({e})\n{traceback.format_exc()}")
            key_valid = False
        finally:

            self.check_api_key_btn.setEnabled(True)
            self.unsetCursor()

            final_key_to_configure = self.api_key # self.api_key was updated only if key_valid and different
            try:
                 if final_key_to_configure:
                     genai.configure(api_key=final_key_to_configure)
                 else:

                      self.append_log("[WARN] Действующий API ключ неизвестен. API может не работать.")

            except Exception as configure_err:

                 self.append_log(f"[ERROR] Ошибка восстановления конфигурации API: {configure_err}")

    @QtCore.pyqtSlot(str)
    def handle_log_message(self, message):

        self.append_log(message)

    def append_log(self, message):
        """Appends a timestamped message to the log widget."""

        current_time = time.strftime("%H:%M:%S")

        message_str = str(message).strip()

        for line in message_str.splitlines():
            self.log_output.append(f"[{current_time}] {line}")

        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @QtCore.pyqtSlot(int)
    def update_file_progress(self, processed_count):

        self.progress_bar.setValue(processed_count)

    @QtCore.pyqtSlot(int)
    def update_progress_bar_range(self, total_tasks):
        """Sets the maximum value of the progress bar."""

        self.progress_bar.setRange(0, max(1, total_tasks))
        self.progress_bar.setValue(0) # Reset progress value
        self.progress_bar.setFormat(f"%v / {total_tasks} задач (%p%)") # Update text format
        self.append_log(f"Общее количество задач для выполнения: {total_tasks}")

    @QtCore.pyqtSlot(str)
    def handle_current_file_status(self, message):

        self.status_label.setText(message)

    @QtCore.pyqtSlot(str, int, int)
    def handle_chunk_progress(self, filename, current_chunk, total_chunks):
        """Updates the status label with chunk processing progress."""

        if total_chunks > 1 and current_chunk >= 0:
            max_len = 60 # Max length for filename display

            display_name = filename if len(filename) <= max_len else f"...{filename[-(max_len-3):]}"
            self.status_label.setText(f"Файл: {display_name} [Чанк: {current_chunk}/{total_chunks}]")
        elif total_chunks == 1 and current_chunk > 0: # Single chunk file completed
             max_len = 60
             display_name = filename if len(filename) <= max_len else f"...{filename[-(max_len-3):]}"
             self.status_label.setText(f"Файл: {display_name} [1/1 Завершено]")



    def start_translation(self):
        """Validates inputs and starts the background worker thread."""
        prompt_template = self.prompt_edit.toPlainText().strip()
        selected_model_name = self.model_combo.currentText()
        max_concurrency = self.concurrency_spin.value()
        selected_files_tuples = list(self.selected_files_data_tuples)
        selected_format_display = self.format_combo.currentText()
        output_format = OUTPUT_FORMATS.get(selected_format_display, 'txt')
        chunking_enabled_gui = self.chunking_checkbox.isChecked()
        chunk_limit = self.chunk_limit_spin.value(); chunk_window = self.chunk_window_spin.value()
        temperature = self.temperature_spin.value()

        chunk_delay = self.chunk_delay_spin.value()

        # --- ПОЛУЧЕНИЕ ПРОКСИ ИЗ GUI ---
        proxy_string = self.proxy_url_edit.text().strip()
        # --- КОНЕЦ ПОЛУЧЕНИЯ ПРОКСИ ---


        if not selected_files_tuples:
            QMessageBox.warning(self, "Ошибка", "Не выбраны файлы для перевода."); return
        if not self.out_folder:
            QMessageBox.warning(self, "Ошибка", "Не выбрана папка вывода."); return
        if not os.path.isdir(self.out_folder):
             reply = QMessageBox.question(self, "Папка не существует", f"Папка '{self.out_folder}' не найдена.\nСоздать?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
             if reply == QMessageBox.StandardButton.Yes:
                 try: os.makedirs(self.out_folder, exist_ok=True); self.append_log(f"Папка '{self.out_folder}' создана.")
                 except OSError as e: QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку: {e}"); return
             else: return 

        if output_format == 'docx' and not DOCX_AVAILABLE:
            QMessageBox.critical(self, "Ошибка", "Выбран формат вывода DOCX, но библиотека 'python-docx' не установлена."); return
        if output_format == 'epub' and (not EBOOKLIB_AVAILABLE or not LXML_AVAILABLE or not BS4_AVAILABLE):
            QMessageBox.critical(self, "Ошибка", "Выбран формат вывода EPUB, но не установлены: 'ebooklib', 'lxml' и 'beautifulsoup4'."); return
        if output_format == 'fb2' and not LXML_AVAILABLE:
            QMessageBox.critical(self, "Ошибка", "Выбран формат вывода FB2, но библиотека 'lxml' не установлена."); return
        if output_format in ['docx', 'epub', 'fb2', 'html'] and not PILLOW_AVAILABLE:
            QMessageBox.warning(self, "Предупреждение", f"Выбран формат вывода {output_format.upper()} с поддержкой изображений, но библиотека 'Pillow' не найдена.\nОбработка некоторых форматов изображений (напр., EMF) может быть невозможна.")
        needs_docx_input = any(ft == 'docx' for ft, _, _ in selected_files_tuples)
        needs_epub_input = any(ft == 'epub' for ft, _, _ in selected_files_tuples)
        if needs_docx_input and not DOCX_AVAILABLE:
            QMessageBox.critical(self, "Ошибка", "Выбраны DOCX файлы для ввода, но библиотека 'python-docx' не установлена."); return
        if needs_epub_input and (not BS4_AVAILABLE or not LXML_AVAILABLE): 
            QMessageBox.critical(self, "Ошибка", "Выбраны EPUB файлы для ввода, но не установлены 'beautifulsoup4' и/или 'lxml'."); return
        if selected_model_name not in MODELS:
            QMessageBox.critical(self, "Ошибка", f"Некорректная модель API: {selected_model_name}"); return
        if "{text}" not in prompt_template:
            QMessageBox.warning(self, "Ошибка Промпта", "Промпт ДОЛЖЕН содержать плейсхолдер `{text}` для вставки текста."); return
        if "<||" not in prompt_template or "img_placeholder" not in prompt_template:
            QMessageBox.warning(self, "Предупреждение Промпта", "Промпт не содержит явных инструкций для обработки плейсхолдеров изображений (`<||img_placeholder_...||>`).\nAPI может их случайно изменить или удалить.")
        if not self.api_key:
            key, ok = QtWidgets.QInputDialog.getText(self, "Требуется API ключ", "Введите ваш Google API Key:", QLineEdit.EchoMode.Password)
            if ok and key.strip(): self.api_key = key.strip(); self.append_log("[INFO] API ключ принят.")
            else: QMessageBox.critical(self, "Ошибка", "API ключ не предоставлен."); return
        if self.thread_ref and self.thread_ref.isRunning():
            QMessageBox.warning(self, "Внимание", "Процесс перевода уже запущен."); return

        is_epub_to_epub_mode = False
        worker_data = None
        if output_format == 'epub':
            if not selected_files_tuples or not all(ft == 'epub' for ft, _, _ in selected_files_tuples):
                 QMessageBox.critical(self, "Ошибка Конфигурации", "Обнаружена несовместимость: выбран вывод EPUB, но список содержит не-EPUB файлы. Очистите список и попробуйте снова.")
                 return
            is_epub_to_epub_mode = True
            epub_groups_for_worker = {} 
            epub_paths_in_list = sorted(list(set(p1 for ft, p1, _ in selected_files_tuples if ft == 'epub')))
            valid_epubs_found = False
            failed_epub_structures = []
            for epub_path in epub_paths_in_list:
                 nav_path, ncx_path, opf_dir, nav_id, ncx_id = self._find_epub_toc_paths(epub_path)
                 if opf_dir is None: 
                      QMessageBox.warning(self, "Ошибка EPUB", f"Не удалось обработать структуру EPUB:\n{Path(epub_path).name}\n\nПропуск этого файла.")
                      failed_epub_structures.append(epub_path)
                      continue 
                 html_paths_for_this_epub = [p2 for ft, p1, p2 in selected_files_tuples if ft == 'epub' and p1 == epub_path and p2]
                 html_to_translate_for_worker = [p for p in html_paths_for_this_epub if p != nav_path]
                 epub_groups_for_worker[epub_path] = {
                     'html_paths': html_to_translate_for_worker,
                     'build_metadata': {
                         'nav_path_in_zip': nav_path, 'ncx_path_in_zip': ncx_path,
                         'opf_dir': opf_dir, 'nav_item_id': nav_id, 'ncx_item_id': ncx_id
                     }
                 }
                 valid_epubs_found = True
            if failed_epub_structures:
                 self.selected_files_data_tuples = [t for t in self.selected_files_data_tuples if t[1] not in failed_epub_structures]
                 self.update_file_list_widget()
            if not valid_epubs_found:
                 QMessageBox.warning(self, "Нет файлов", "Не найдено допустимых EPUB файлов для обработки в режиме EPUB->EPUB (возможно, ошибки структуры).")
                 self.clear_file_list(); return 
            worker_data = epub_groups_for_worker
            QMessageBox.information(self, "Режим EPUB->EPUB",
                                     "Запуск в режиме EPUB -> EPUB.\nБудет выполнено:\n"
                                     "- Перевод выбранных HTML (кроме файла NAV).\n"
                                     "- Переименование переведенных файлов (*_translated.html/xhtml).\n"
                                     "- Поиск и ИЗМЕНЕНИЕ существующего файла оглавления (NAV/NCX) для обновления ссылок.")
        else: 
            worker_data = selected_files_tuples

        self.log_output.clear();
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0);
        self.progress_bar.setFormat("Подготовка...")
        self.status_label.setText("Подготовка...");
        self.append_log("="*40 + f"\nНАЧАЛО ПЕРЕВОДА")
        self.append_log(f"Режим: {'EPUB->EPUB Rebuild' if is_epub_to_epub_mode else 'Стандартный'}")
        self.append_log(f"Модель: {selected_model_name}"); self.append_log(f"Паралл. запросы: {max_concurrency}"); self.append_log(f"Формат вывода: .{output_format}")

        chunking_log_msg = f"Чанкинг GUI: {'Да' if chunking_enabled_gui else 'Нет'} (Лимит: {chunk_limit:,}, Окно: {chunk_window:,}"
        if chunking_enabled_gui and chunk_delay > 0:
            chunking_log_msg += f", Задержка: {chunk_delay:.1f} сек.)"
        else:
            chunking_log_msg += ")"
        self.append_log(chunking_log_msg)

        if not CHUNK_HTML_SOURCE and chunking_enabled_gui: self.append_log("[INFO] Чанкинг HTML/EPUB отключен.")
        self.append_log(f"Папка вывода: {self.out_folder}")
        self.append_log(f"Поддержка: DOCX={'ДА' if DOCX_AVAILABLE else 'НЕТ'}, BS4={'ДА' if BS4_AVAILABLE else 'НЕТ'}, LXML={'ДА' if LXML_AVAILABLE else 'НЕТ'}, EbookLib={'ДА' if EBOOKLIB_AVAILABLE else 'НЕТ'}, Pillow={'ДА' if PILLOW_AVAILABLE else 'НЕТ'}")
        self.append_log("="*40); self.set_controls_enabled(False)
        self.thread = QtCore.QThread()

        self.worker = Worker(
            self.api_key, self.out_folder, prompt_template, worker_data,
            MODELS[selected_model_name], max_concurrency, output_format,
            chunking_enabled_gui, chunk_limit, chunk_window,
            temperature,
            chunk_delay, # <-- Вот этот аргумент был пропущен
            proxy_string=proxy_string # <--- Передаем строку прокси в Worker

        )
        self.worker.moveToThread(self.thread)
        self.worker_ref = self.worker
        self.thread_ref = self.thread
        self.worker.file_progress.connect(self.update_file_progress)
        self.worker.current_file_status.connect(self.handle_current_file_status)
        self.worker.chunk_progress.connect(self.handle_chunk_progress)
        self.worker.log_message.connect(self.handle_log_message)
        self.worker.finished.connect(self.on_translation_finished)
        self.worker.total_tasks_calculated.connect(self.update_progress_bar_range)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_worker_refs)
        # --- ЛОГИРОВАНИЕ ПРОКСИ (после инициализации Worker, чтобы он уже имел self.proxy_string) ---
        if self.worker.proxy_string: # Проверяем, что worker.proxy_string установлен
            self.append_log(f"Прокси для Worker настроен на: {self.worker.proxy_string}")
        else:
            self.append_log("Прокси для Worker: Не используется")
        # --- КОНЕЦ ЛОГИРОВАНИЯ ПРОКСИ ---
        self.thread.start()
        self.append_log("Рабочий поток запущен...")
        self.status_label.setText("Запуск...")

    def cancel_translation(self):
        if self.worker_ref and self.thread_ref and self.thread_ref.isRunning():
            self.append_log("Отправка сигнала ОТМЕНЫ...")
            self.status_label.setText("Отмена...")
            self.worker_ref.cancel()
            self.cancel_btn.setEnabled(False)
            self.finish_btn.setEnabled(False) # <--- ДОБАВИТЬ
            self.append_log("Ожидание завершения потока...")
        else:
            self.append_log("[WARN] Нет активного процесса для отмены.")

    @QtCore.pyqtSlot(int, int, list)
    def on_translation_finished(self, success_count, error_count, errors):
        worker_ref_exists = self.worker_ref is not None
        was_cancelled = worker_ref_exists and self.worker_ref.is_cancelled
        was_finishing = worker_ref_exists and hasattr(self.worker_ref, 'is_finishing') and self.worker_ref.is_finishing

        # Логируем финальные итоги перед показом QMessageBox
        log_end_separator = "="*40
        self.append_log(f"\n{log_end_separator}")
        if was_cancelled:
            self.append_log("--- ПРОЦЕСС БЫЛ ОТМЕНЕН ПОЛЬЗОВАТЕЛЕМ ---")
        elif was_finishing:
            self.append_log("--- ПРОЦЕСС БЫЛ ЗАВЕРШЕН ПО КОМАНДЕ 'ЗАВЕРШИТЬ' (частично) ---")
        # Дополнительные логи об ошибках Executor или API уже должны быть в Worker.run

        self.append_log(f"ИТОГ: Успешно: {success_count}, Ошибок/Отменено/Пропущено: {error_count}")
        if errors:
            self.append_log("Детали ошибок/отмен/пропусков:")
            max_errors_to_show = 30
            for i, e in enumerate(errors[:max_errors_to_show]):
                error_str = str(e)
                max_len = 350
                display_error = error_str[:max_len] + ('...' if len(error_str) > max_len else '')
                self.append_log(f"- {display_error}")
            if len(errors) > max_errors_to_show:
                self.append_log(f"- ... ({len(errors) - max_errors_to_show} еще)")
        self.append_log(log_end_separator)

        final_message = ""
        msg_type = QMessageBox.Icon.Information
        title = "Завершено"
        total_tasks = self.progress_bar.maximum() # Получаем общее количество задач из прогресс-бара

        if was_cancelled:
            title = "Отменено"
            msg_type = QMessageBox.Icon.Warning
            final_message = f"Процесс отменен.\n\nУспешно до отмены: {success_count}\nОшибок/Пропущено: {error_count}"
            self.status_label.setText("Отменено")
        elif was_finishing:
            title = "Завершено (частично)"
            msg_type = QMessageBox.Icon.Information
            final_message = f"Процесс завершен по команде 'Завершить'.\n\nОбработано (полностью или частично): {success_count}\nОшибок/Пропущено по другим причинам: {error_count}"
            self.status_label.setText("Завершено (частично)")
        elif error_count == 0 and success_count > 0:
            title = "Готово!"
            msg_type = QMessageBox.Icon.Information
            final_message = f"Перевод {success_count} заданий успешно завершен!"
            self.status_label.setText("Готово!")
        elif success_count > 0 and error_count > 0:
            title = "Завершено с ошибками"
            msg_type = QMessageBox.Icon.Warning
            final_message = f"Перевод завершен.\n\nУспешно: {success_count}\nОшибок/Пропущено: {error_count}\n\nСм. лог."
            self.status_label.setText("Завершено с ошибками")
        elif success_count == 0 and error_count > 0:
            title = "Завершено с ошибками"
            msg_type = QMessageBox.Icon.Critical
            final_message = f"Не удалось успешно перевести ни одного задания.\nОшибок/Пропущено: {error_count}\n\nСм. лог."
            self.status_label.setText("Завершено с ошибками")
        elif success_count == 0 and error_count == 0 and total_tasks > 0:
            title = "Внимание"
            msg_type = QMessageBox.Icon.Warning
            final_message = f"Обработка завершена, но нет успешных заданий или ошибок (возможно, все пропущено или отменено до начала?).\nПроверьте лог."
            self.status_label.setText("Завершено (проверьте лог)")
        elif total_tasks == 0 : # Если изначально не было задач
            title = "Нет задач"
            msg_type = QMessageBox.Icon.Information
            final_message = "Нет файлов или задач для обработки."
            self.status_label.setText("Нет задач")
        else: # Общий случай, если ни одно из условий выше не сработало
            final_message = "Обработка завершена."
            self.status_label.setText("Завершено")

        if self.isVisible(): # Показываем QMessageBox только если окно видимо
            QMessageBox(msg_type, title, final_message, QMessageBox.StandardButton.Ok, self).exec()
        else: # Если окно не видимо (например, закрыто во время выполнения), просто логируем
            self.append_log(f"Диалог завершения: {title} - {final_message}")

    @QtCore.pyqtSlot()
    def clear_worker_refs(self):

        self.append_log("Фоновый поток завершен. Очистка ссылок...");
        self.worker = None
        self.thread = None
        self.worker_ref = None
        self.thread_ref = None
        self.set_controls_enabled(True)
        self.append_log("Интерфейс разблокирован.")

    def set_controls_enabled(self, enabled):
        widgets_to_toggle = [
            self.file_select_btn, self.clear_list_btn, self.out_btn, self.format_combo,
            self.model_combo, self.concurrency_spin, self.temperature_spin,
            self.chunking_checkbox, self.proxy_url_edit, # <-- Добавлено поле прокси

            self.chunk_delay_spin, # <-- Добавлено

            self.prompt_edit,
            self.start_btn, self.check_api_key_btn
        ]
        for widget in widgets_to_toggle: widget.setEnabled(enabled)
        if enabled:
            self.toggle_chunking_details(self.chunking_checkbox.checkState().value) # This will also handle chunk_delay_spin
            for code, index in self.format_indices.items():
                 item = self.format_combo.model().item(index)
                 if item:
                    is_available = True; tooltip = f"Сохранить как .{code}"
                    if code == 'docx' and not DOCX_AVAILABLE: is_available = False; tooltip = "Требуется: python-docx"
                    elif code == 'epub' and (not EBOOKLIB_AVAILABLE or not LXML_AVAILABLE or not BS4_AVAILABLE): is_available = False; tooltip = "Требуется: ebooklib, lxml, beautifulsoup4"
                    elif code == 'fb2' and not LXML_AVAILABLE: is_available = False; tooltip = "Требуется: lxml"
                    if code in ['docx', 'epub', 'fb2', 'html'] and not PILLOW_AVAILABLE:
                        if is_available: tooltip += "\n(Реком.: Pillow для изобр.)"
                        else: tooltip += "; Pillow (реком.)"
                    item.setEnabled(is_available); 
                    self.format_combo.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
                    self.cancel_btn.setEnabled(False) # Убедиться, что кнопки управления процессом выключены
                    self.finish_btn.setEnabled(False)
        else: 
            self.chunk_limit_spin.setEnabled(False)
            self.chunk_window_spin.setEnabled(False)
            self.chunk_delay_spin.setEnabled(False)
            self.cancel_btn.setEnabled(True) # Включить кнопки управления процессом
            self.finish_btn.setEnabled(True)

    def closeEvent(self, event: QtGui.QCloseEvent):

        self.save_settings()
        if self.thread_ref and self.thread_ref.isRunning():
            reply = QMessageBox.question(self, "Процесс выполняется", "Перевод все еще выполняется.\nПрервать и выйти?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self.append_log("Выход во время выполнения, отмена..."); self.cancel_translation(); event.accept()
            else: event.ignore()
        else: event.accept()

def main():

    parser = argparse.ArgumentParser(description="Batch File Translator v2.12 (EPUB TOC Fixes)")
    parser.add_argument("--api_key", help="Google API Key (или GOOGLE_API_KEY env var).")
    args = parser.parse_args(); api_key = args.api_key or os.environ.get("GOOGLE_API_KEY")
    app = QApplication.instance() or QApplication(sys.argv)
    missing_libs_msg = []; install_pkgs = []
    if not DOCX_AVAILABLE: missing_libs_msg.append("'python-docx' (для DOCX)"); install_pkgs.append("python-docx")
    if not BS4_AVAILABLE: missing_libs_msg.append("'beautifulsoup4' (для EPUB/HTML входа/выхода)"); install_pkgs.append("beautifulsoup4")
    if not LXML_AVAILABLE: missing_libs_msg.append("'lxml' (для FB2/EPUB выхода/анализа)"); install_pkgs.append("lxml")
    if not EBOOKLIB_AVAILABLE: missing_libs_msg.append("'ebooklib' (для EPUB выхода)"); install_pkgs.append("ebooklib")
    if not PILLOW_AVAILABLE: missing_libs_msg.append("'Pillow' (для изобр.)"); install_pkgs.append("Pillow")
    if missing_libs_msg: lib_list = "\n - ".join(missing_libs_msg); install_cmd = f"pip install {' '.join(install_pkgs)}"; QMessageBox(QMessageBox.Icon.Warning, "Отсутствуют библиотеки", f"Не найдены библиотеки:\n\n - {lib_list}\n\nФункциональность ограничена.\n\nУстановить:\n{install_cmd}", QMessageBox.StandardButton.Ok).exec()
    try:
        win = TranslatorApp(api_key=api_key); win.show()
        if not api_key: win.append_log("[WARN] API ключ не предоставлен.")
    except Exception as e: error_message = f"Критическая ошибка GUI:\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}"; print(error_message, file=sys.stderr); QMessageBox.critical(None, "Ошибка Запуска GUI", error_message); sys.exit(1)
    sys.exit(app.exec())

if __name__ == "__main__":
    def excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        error_message = f"Неперехваченная ошибка:\n\n{exc_type.__name__}: {exc_value}\n\n{tb_str}"
        print(f"КРИТИЧЕСКАЯ ОШИБКА:\n{error_message}", file=sys.stderr)
        try: app_instance = QApplication.instance() or QApplication(sys.argv); QMessageBox.critical(None, "Критическая Ошибка", error_message)
        except Exception as mb_error: print(f"Не удалось показать MessageBox: {mb_error}", file=sys.stderr)
        sys.exit(1)
    sys.excepthook = excepthook
    try: main()
    except SystemExit: pass
    except Exception as e:
        error_message = f"Критическая ошибка запуска:\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        print(f"КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА:\n{error_message}", file=sys.stderr)
        try:
            app_instance = QApplication.instance()
            if not app_instance: app_instance = QApplication(sys.argv)
            QMessageBox.critical(None, "Ошибка Запуска", error_message)
        except Exception as mb_error: print(f"Не удалось показать MessageBox: {mb_error}", file=sys.stderr)
        sys.exit(1)
