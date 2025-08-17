# --- START OF FILE Worker.py ---

import sys
import os
import json
import time
import ebooklib
from ebooklib import epub
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.api_core.exceptions import PermissionDenied, ResourceExhausted, InvalidArgument, DeadlineExceeded
import threading
import logging
import random

class RateLimiter:
    def __init__(self, requests_per_minute):
        self.lock = threading.Lock()
        if requests_per_minute > 0:
            self.delay_between_requests = 60.0 / requests_per_minute
        else:
            self.delay_between_requests = 0
        self.last_request_time = 0

    def wait(self):
        with self.lock:
            current_time = time.monotonic()
            elapsed = current_time - self.last_request_time
            
            if elapsed < self.delay_between_requests:
                sleep_time = self.delay_between_requests - elapsed
                time.sleep(sleep_time)
            
            self.last_request_time = time.monotonic()


def setup_logging(output_dir):
    log_file = os.path.join(output_dir, "worker_log.txt")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_progress(output_dir):
    progress_file = os.path.join(output_dir, "progress.json")
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
             return {"processed_chapters": [], "blocked_chapters": [], "paused": False}
    return {"processed_chapters": [], "blocked_chapters": [], "paused": False}

def save_progress(output_dir, processed_chapters, blocked_chapters, paused=False):
    progress_file = os.path.join(output_dir, "progress.json")
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump({
            "processed_chapters": list(processed_chapters),
            "blocked_chapters": list(blocked_chapters),
            "paused": paused
        }, f, ensure_ascii=False, indent=2)

def load_glossary(output_dir):
    glossary_file = os.path.join(output_dir, "glossary.json")
    if os.path.exists(glossary_file):
        try:
            with open(glossary_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_glossary(output_dir, glossary):
    glossary_file = os.path.join(output_dir, "glossary.json")
    with open(glossary_file, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)

def extract_text_from_chapter(chapter):
    soup = BeautifulSoup(chapter.get_content(), "lxml")
    return soup.get_text(separator=" ", strip=True)

def parse_api_response(response):
    try:
        if not response or not hasattr(response, 'text') or not response.text:
            return {}
            
        cleaned_text = response.text.strip()
        if not cleaned_text:
            logging.warning("Received empty response from API.")
            return {}

        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        
        return json.loads(cleaned_text)

    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON from API response: {response.text[:200]}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred in parse_api_response: {str(e)}")
        return {}

def generate_content_with_retry(model, prompt, chapter_name):
    max_retries = 5
    base_delay = 5
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt, request_options={"timeout": 120})
            return response
        except ResourceExhausted as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logging.warning(f"Rate limit hit for chapter {chapter_name}. Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                logging.error(f"API limit reached for chapter {chapter_name} after {max_retries} attempts.")
                raise e
        except DeadlineExceeded as e:
            logging.error(f"API timeout for chapter {chapter_name}: {str(e)}")
            return None

    return None

def process_chapter(chapter, api_key, model_name, output_dir, lock, rate_limiter, prompt_template):
    chapter_name = chapter.get_name()
    if any(x in chapter_name.lower() for x in ["nav.xhtml", "cover", "description", "title", "copyright"]):
        logging.info(f"Skipping metadata file: {chapter_name}")
        return chapter_name, None

    start_time = time.time()
    try:
        if load_progress(output_dir).get("paused", False):
            return chapter_name, None

        logging.info(f"Processing chapter: {chapter_name}")
        chapter_text = extract_text_from_chapter(chapter)
        if not chapter_text.strip():
            logging.info(f"Chapter {chapter_name} is empty, skipping.")
            return chapter_name, None

        if load_progress(output_dir).get("paused", False):
            logging.info(f"Halting API call for {chapter_name}; pause detected.")
            return chapter_name, None

        rate_limiter.wait()
            
        logging.info(f"Sending API request for {chapter_name}")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        prompt = prompt_template.format(text=chapter_text[:30000])

        response = generate_content_with_retry(model, prompt, chapter_name)

        if response is None:
            return chapter_name, None

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            logging.warning(f"Chapter {chapter_name} blocked by API: {response.prompt_feedback.block_reason}")
            with lock:
                progress = load_progress(output_dir)
                blocked_chapters = set(progress.get("blocked_chapters", []))
                blocked_chapters.add(chapter_name)
                save_progress(output_dir, progress["processed_chapters"], list(blocked_chapters), progress.get("paused", False))
            return chapter_name, None

        terms = parse_api_response(response)
        
        if terms:
            with lock:
                current_glossary = load_glossary(output_dir)
                for term, definition in terms.items():
                    if term not in current_glossary:
                        current_glossary[term] = definition
                save_glossary(output_dir, current_glossary)
                logging.info(f"Updated glossary for {chapter_name}. Time taken: {time.time() - start_time:.2f} seconds")

        return chapter_name, terms
    except (PermissionDenied, ResourceExhausted) as e:
        logging.error(f"Permanent API error for chapter {chapter_name}: {str(e)}. Triggering API key switch.")
        raise
    except Exception as e:
        logging.error(f"Critical error processing chapter {chapter_name}: {str(e)}", exc_info=True)
        return chapter_name, None

# ИЗМЕНЕНО: Добавлен `model_rpm` в аргументы
def main(epub_path, api_key, output_dir, model_name, num_threads, prompt_template, model_rpm):
    setup_logging(output_dir)
    logging.info(f"Starting Worker with EPUB: {epub_path}, Model: {model_name}, Threads: {num_threads}, RPM: {model_rpm}")
    progress = load_progress(output_dir)

    if progress.get("paused", False):
        logging.info("Processing is paused. Please resume from the launcher to continue.")
        sys.exit(0)

    processed_chapters = set(progress.get("processed_chapters", []))
    blocked_chapters = set(progress.get("blocked_chapters", []))
    
    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        logging.error(f"Error reading EPUB file: {str(e)}")
        sys.exit(1)

    chapters = [item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]
    chapters_to_process = [ch for ch in chapters if ch.get_name() not in processed_chapters and ch.get_name() not in blocked_chapters]

    if not chapters_to_process:
        logging.info("All chapters already processed or blocked.")
        sys.exit(0)

    logging.info(f"Found {len(chapters_to_process)} chapters to process.")
    lock = threading.Lock()
    
    # ИЗМЕНЕНО: RateLimiter использует точный RPM, переданный из Launcher
    rate_limiter = RateLimiter(int(model_rpm))
    logging.info(f"Rate limiter initialized for {model_rpm} RPM.")

    try:
        with ThreadPoolExecutor(max_workers=int(num_threads)) as executor:
            from concurrent.futures import as_completed
            future_to_chapter = {
                executor.submit(process_chapter, chapter, api_key, model_name, output_dir, lock, rate_limiter, prompt_template): chapter
                for chapter in chapters_to_process
            }
            
            for future in as_completed(future_to_chapter):
                chapter_name = future_to_chapter[future].get_name()
                try:
                    _, terms = future.result()
                    with lock:
                        current_progress = load_progress(output_dir)
                        current_processed = set(current_progress.get("processed_chapters", []))
                        
                        if terms is not None:
                            current_processed.add(chapter_name)
                            logging.info(f"Completed chapter: {chapter_name}")
                        
                        save_progress(output_dir, list(current_processed), current_progress['blocked_chapters'], current_progress.get("paused", False))
                except Exception as exc:
                     logging.error(f'Chapter {chapter_name} generated a final exception: {exc}')

    except (PermissionDenied, ResourceExhausted):
        logging.info("Exiting due to persistent API limit. Launcher will try next key.")
        sys.exit(10)
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {str(e)}", exc_info=True)
        sys.exit(1)

    logging.info("Processing completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    # ИЗМЕНЕНО: Ожидаем 8 аргументов
    if len(sys.argv) != 8:
        logging.error(f"Usage: Worker.py <epub_path> <api_key> <output_dir> <model> <threads> <prompt> <rpm>")
        logging.error(f"Received {len(sys.argv)} arguments: {sys.argv}")
        sys.exit(1)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    # ИЗМЕНЕНО: Добавлен `rpm`
    epub_path, api_key, output_dir, model, threads, prompt, rpm = sys.argv[1:8]
    main(epub_path, api_key, output_dir, model, threads, prompt, rpm)