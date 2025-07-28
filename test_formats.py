#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки форматов
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем функции
from TransGemini import OUTPUT_FORMATS

def test_get_possible_output_formats(input_format: str) -> list:
    """Тестовая версия функции"""
    available_formats = []
    for display_name, format_code in OUTPUT_FORMATS.items():
        if format_code in ['txt', 'docx', 'html', 'md', 'epub']:
            available_formats.append((display_name, format_code))
    return available_formats

if __name__ == "__main__":
    print("OUTPUT_FORMATS из TransGemini:")
    for display_name, format_code in OUTPUT_FORMATS.items():
        print(f"  {display_name} -> {format_code}")
    
    print("\nДоступные форматы для TXT:")
    formats = test_get_possible_output_formats('txt')
    for display_name, format_code in formats:
        print(f"  {display_name} ({format_code})")
    
    print(f"\nВсего доступных форматов: {len(formats)}")
    
    # Проверяем, есть ли EPUB
    epub_found = any(format_code == 'epub' for display_name, format_code in formats)
    print(f"EPUB найден: {'ДА' if epub_found else 'НЕТ'}")
