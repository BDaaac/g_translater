#!/usr/bin/env python3
"""
Создает тестовый EPUB файл для тестирования переводчика
"""

from ebooklib import epub
import uuid

def create_test_epub(filename="test_book.epub"):
    """Создает простой EPUB файл для тестирования"""
    
    book = epub.EpubBook()
    
    # Метаданные
    book.set_identifier(f'urn:uuid:{uuid.uuid4()}')
    book.set_title('Test Book')
    book.set_language('en')
    book.add_author('Test Author')
    
    # CSS
    default_css = epub.EpubItem(
        uid="default",
        file_name="style/default.css",
        media_type="text/css",
        content='''
            body {
                font-family: "Times New Roman", serif;
                line-height: 1.6;
                margin: 1em;
            }
            h1 {
                text-align: center;
                font-size: 1.8em;
                margin: 2em 0 1em 0;
            }
            p {
                margin: 1em 0;
                text-indent: 1em;
            }
        '''
    )
    book.add_item(default_css)
    
    # Создаем главы
    chapters = []
    
    # Глава 1
    chapter1 = epub.EpubHtml(
        title='Chapter 1',
        file_name='chapter1.xhtml',
        lang='en'
    )
    chapter1.content = '''<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Chapter 1: The Beginning</title>
    <link rel="stylesheet" type="text/css" href="style/default.css"/>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
</head>
<body>
    <h1>Chapter 1: The Beginning</h1>
    <p>This is the first chapter of our test book. It contains some sample text that should be translated from English to Russian.</p>
    <p>The story begins in a small town where everyone knows each other. The main character, John, is a young man with big dreams.</p>
    <p>He has always wanted to travel the world and see new places. Today is the day he decides to start his journey.</p>
</body>
</html>'''.encode('utf-8')
    
    book.add_item(chapter1)
    chapters.append(chapter1)
    
    # Глава 2
    chapter2 = epub.EpubHtml(
        title='Chapter 2',
        file_name='chapter2.xhtml',
        lang='en'
    )
    chapter2.content = '''<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Chapter 2: The Journey</title>
    <link rel="stylesheet" type="text/css" href="style/default.css"/>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
</head>
<body>
    <h1>Chapter 2: The Journey</h1>
    <p>John packed his bags and left his hometown early in the morning. The sun was just rising over the hills.</p>
    <p>He walked to the train station with excitement in his heart. This was the beginning of his adventure.</p>
    <p>The train arrived on time, and John climbed aboard. As the train pulled away from the station, he watched his hometown disappear into the distance.</p>
</body>
</html>'''.encode('utf-8')
    
    book.add_item(chapter2)
    chapters.append(chapter2)
    
    # Глава 3
    chapter3 = epub.EpubHtml(
        title='Chapter 3',
        file_name='chapter3.xhtml',
        lang='en'
    )
    chapter3.content = '''<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Chapter 3: New Horizons</title>
    <link rel="stylesheet" type="text/css" href="style/default.css"/>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
</head>
<body>
    <h1>Chapter 3: New Horizons</h1>
    <p>The train journey took several hours. John watched the countryside roll by through the window.</p>
    <p>He saw fields of wheat, small villages, and distant mountains. Everything looked so peaceful and beautiful.</p>
    <p>When the train finally stopped at the big city, John felt both excited and nervous. This was going to be the adventure of a lifetime.</p>
</body>
</html>'''.encode('utf-8')
    
    book.add_item(chapter3)
    chapters.append(chapter3)
    
    # Устанавливаем spine и toc
    book.spine = ['nav'] + chapters
    book.toc = chapters
    
    # Добавляем минимальную навигацию
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Сохраняем EPUB без дополнительных опций
    try:
        epub.write_epub(filename, book)
        print(f"✅ Test EPUB created: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error creating EPUB: {e}")
        return False

if __name__ == "__main__":
    create_test_epub()
