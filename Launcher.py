# --- START OF FILE Launcher.py ---

import sys
import os
import json
import subprocess
import importlib.util

# --- БЛОК АВТОМАТИЧЕСКОЙ УСТАНОВКИ ЗАВИСИМОСТЕЙ ---

REQUIRED_PACKAGES = {
    "PyQt6": "PyQt6",
    "ebooklib": "ebooklib",
    "bs4": "beautifulsoup4",
    "google.generativeai": "google-generativeai",
    "lxml": "lxml"
}

def check_and_install_dependencies():
    """Проверяет наличие необходимых библиотек и предлагает их установить."""
    missing_packages = []
    for import_name, install_name in REQUIRED_PACKAGES.items():
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            missing_packages.append(install_name)

    if not missing_packages:
        return True

    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)

    package_list = "\n".join(f"- {pkg}" for pkg in missing_packages)
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setText(f"Обнаружены отсутствующие библиотеки, необходимые для работы программы:\n\n{package_list}\n\nРазрешить их автоматическую установку с помощью pip?")
    msg_box.setWindowTitle("Установка зависимостей")
    msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    
    response = msg_box.exec()

    if response == QMessageBox.StandardButton.Yes:
        try:
            for package in missing_packages:
                print(f"Установка {package}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            
            QMessageBox.information(None, "Успех", "Все библиотеки были успешно установлены. Пожалуйста, перезапустите программу, чтобы изменения вступили в силу.")
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(None, "Ошибка установки", f"Не удалось установить библиотеки. Пожалуйста, установите их вручную командой:\npip install {' '.join(missing_packages)}\n\nОшибка: {e}")
            return False
    else:
        QMessageBox.critical(None, "Отмена", "Установка отменена. Программа не может продолжить работу без необходимых библиотек.")
        return False

# --- КОНЕЦ БЛОКА УСТАНОВКИ ---


from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QLineEdit, QComboBox, QFileDialog, QLabel, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIntValidator

# ИЗМЕНЕНО: Структура моделей и их ID взяты из предоставленного вами скрипта
MODELS = {
    "Gemini 2.5 Flash Preview (10 RPM)": {
        "id": "models/gemini-2.5-flash",
        "rpm": 10
    },
    "Gemini 2.5 Pro (5 RPM)": {
        "id": "models/gemini-2.5-pro",
        "rpm": 5
    },
    "Gemini 2.0 Flash (15 RPM)": {
        "id": "models/gemini-2.0-flash",
        "rpm": 15
    },
    "Gemini 2.5 Flash-Lite (10 RPM)": {
        "id": "models/gemini-2.5-flash-lite-preview-06-17",
        "rpm": 10
    }
}
DEFAULT_MODEL_NAME = "Gemini 2.5 Flash Preview (10 RPM)"

DEFAULT_PROMPT = """Ты профессиональный лингвист-терминолог. Твоя задача - создать глоссарий терминов для последовательного перевода книги.

ИНСТРУКЦИИ:
1. Найди в тексте ВСЕ:
   - Имена персонажей (включая прозвища, титулы)
   - Названия мест, организаций, техник, артефактов
   - Специфические термины и понятия мира произведения
   - Устойчивые словосочетания и титулы

2. Для каждого термина предложи ОДИН лучший вариант перевода на русский язык.

3. Учитывай контекст и жанр произведения при переводе.

4. НЕ включай в глоссарий:
   - Обычные слова без специального значения
   - Термины, встречающиеся только 1 раз (если это не ключевое имя/название)

ФОРМАТ ВЫВОДА (строго JSON):
{{
  "термин_на_оригинале": "перевод_на_русский",
  "Son Goku": "Сон Гоку",
  "Kamehameha": "Камехамеха"
}}

ВАЖНО: 
- Выводи ТОЛЬКО JSON без дополнительного текста
- Сохраняй оригинальное написание (регистр букв)
- Для имён используй благозвучную транслитерацию
- Для терминов предпочитай осмысленный перевод транслитерации

Текст для анализа:
{text}
"""

class WorkerThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, str)
    progress_signal = pyqtSignal(int, int, str)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            total = 0
            processed = 0
            while True:
                output = self.process.stdout.readline()
                if output == '' and self.process.poll() is not None:
                    break
                if output:
                    self.log_signal.emit(output.strip())
                    if "Found" in output and "chapters to process" in output:
                        total = int(output.split("Found ")[1].split(" chapters")[0])
                        self.progress_signal.emit(processed, total, "")
                    if "Completed chapter" in output:
                        processed += 1
                        current_chapter = output.split("Completed chapter: ")[1]
                        self.progress_signal.emit(processed, total, current_chapter)
            stderr = self.process.stderr.read()
            returncode = self.process.poll()
            self.finished_signal.emit(returncode, stderr)
        except Exception as e:
            self.log_signal.emit(f"Error running Worker: {str(e)}")
            self.finished_signal.emit(1, str(e))

    def stop(self):
        if hasattr(self, 'process') and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
            self.log_signal.emit("Worker process terminated.")


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPUB Glossary Builder")
        self.setGeometry(100, 100, 800, 750)
        self.init_ui()
        self.api_keys = []
        self.current_key_index = 0
        self.worker_thread = None
        self.paused = False
        self.total_chapters = 0

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        layout.addWidget(QLabel("1. Select EPUB file:"))
        self.epub_path = QLineEdit()
        epub_button = QPushButton("Browse")
        epub_button.clicked.connect(self.browse_epub)
        epub_layout = QHBoxLayout()
        epub_layout.addWidget(self.epub_path)
        epub_layout.addWidget(epub_button)
        layout.addLayout(epub_layout)

        layout.addWidget(QLabel("2. Enter API keys (one per line):"))
        self.api_keys_input = QTextEdit()
        layout.addWidget(self.api_keys_input)

        layout.addWidget(QLabel("3. Select output directory:"))
        self.output_dir = QLineEdit()
        output_button = QPushButton("Browse")
        output_button.clicked.connect(self.browse_output)
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_dir)
        output_layout.addWidget(output_button)
        layout.addLayout(output_layout)
        
        layout.addWidget(QLabel("4. Enter prompt for AI (use {text} as a placeholder for chapter text):"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setText(DEFAULT_PROMPT)
        layout.addWidget(self.prompt_input)

        settings_layout = QHBoxLayout()
        model_layout = QVBoxLayout()
        model_layout.addWidget(QLabel("5. Select Gemini model:"))
        self.model_combo = QComboBox()
        # ИЗМЕНЕНО: Загружаем модели из нового словаря
        self.model_combo.addItems(MODELS.keys())
        self.model_combo.setCurrentText(DEFAULT_MODEL_NAME)
        model_layout.addWidget(self.model_combo)
        settings_layout.addLayout(model_layout)

        threads_layout = QVBoxLayout()
        threads_layout.addWidget(QLabel("6. Number of threads:"))
        self.threads_input = QLineEdit("1")
        self.threads_input.setValidator(QIntValidator(1, 15))
        threads_layout.addWidget(self.threads_input)
        settings_layout.addLayout(threads_layout)
        layout.addLayout(settings_layout)
        
        rate_limit_warning = QLabel("<b>RPM</b> = Запросов В Минуту. Чтобы избежать блокировки, количество потоков не должно превышать RPM модели. \n<b>Рекомендуется 1-2 потока для стабильной работы.</b>")
        rate_limit_warning.setStyleSheet("color: #8B4513; padding: 5px; background-color: #FFF8DC; border-radius: 3px;")
        layout.addWidget(rate_limit_warning)


        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start/Continue")
        self.start_button.clicked.connect(self.start_processing)
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        button_layout.addWidget(self.pause_button)
        layout.addLayout(button_layout)

        layout.addWidget(QLabel("Processing Progress:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.current_chapter_label = QLabel("Current chapter: None")
        layout.addWidget(self.current_chapter_label)

        layout.addWidget(QLabel("Progress Log:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

    def browse_epub(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select EPUB file", "", "EPUB files (*.epub)")
        if file_name:
            self.epub_path.setText(file_name)
            self.log_area.append(f"Selected EPUB: {file_name}")

    def browse_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Select output directory")
        if directory:
            self.output_dir.setText(directory)
            self.log_area.append(f"Selected output directory: {directory}")

    def save_pause_state(self, is_paused):
        output_dir = self.output_dir.text()
        if not output_dir: return
        
        progress_file = os.path.join(output_dir, "progress.json")
        progress = {"processed_chapters": [], "blocked_chapters": [], "paused": False}
        
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress = json.load(f)
            except Exception as e:
                self.log_area.append(f"Error reading progress file: {str(e)}")

        progress["paused"] = is_paused
        
        try:
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_area.append(f"Error saving progress file: {str(e)}")

    def toggle_pause(self):
        self.paused = not self.paused
        self.save_pause_state(self.paused)

        if self.paused:
            self.pause_button.setText("Resume")
            self.log_area.append("Processing paused. Worker will stop after finishing current tasks.")
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop()
        else:
            self.pause_button.setText("Pause")
            self.log_area.append("Processing resumed...")
            self.start_processing(resuming=True)

    def start_processing(self, resuming=False):
        epub_file = self.epub_path.text()
        output_dir = self.output_dir.text()
        threads = self.threads_input.text()
        prompt = self.prompt_input.toPlainText()
        self.api_keys = [key.strip() for key in self.api_keys_input.toPlainText().strip().split("\n") if key.strip()]
        
        # ИЗМЕНЕНО: Получаем ID модели и RPM из словаря
        model_display_name = self.model_combo.currentText()
        model_id = MODELS[model_display_name]['id']
        model_rpm = MODELS[model_display_name]['rpm']

        if not all([epub_file, output_dir, self.api_keys, threads, prompt]):
            self.log_area.append("Error: Please fill in all fields.")
            return
        
        if "{text}" not in prompt:
            self.log_area.append("Error: The prompt must contain the '{text}' placeholder.")
            return

        if not resuming:
            self.log_area.clear()
            self.log_area.append("Starting processing...")
            self.save_pause_state(False)
            self.current_key_index = 0
            self.progress_bar.setValue(0)
            self.current_chapter_label.setText("Current chapter: None")

        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.paused = False
        self.pause_button.setText("Pause")
        
        # ИЗМЕНЕНО: Передаем ID модели и RPM
        self.run_worker(epub_file, output_dir, threads, model_id, model_rpm, prompt)

    def run_worker(self, epub_file, output_dir, threads, model_id, model_rpm, prompt):
        if self.current_key_index >= len(self.api_keys):
            self.log_area.append("Error: All API keys exhausted.")
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            return

        current_key = self.api_keys[self.current_key_index]
        self.log_area.append(f"Using API key {self.current_key_index + 1} with model {model_id}...")

        # ИЗМЕНЕНО: Передаем model_id и model_rpm в Worker
        command = [sys.executable, "Worker.py", epub_file, current_key, output_dir, model_id, threads, prompt, str(model_rpm)]
        self.worker_thread = WorkerThread(command)
        self.worker_thread.log_signal.connect(self.update_log)
        self.worker_thread.finished_signal.connect(
            lambda code, err: self.handle_worker_result(code, err, epub_file, output_dir, threads, model_id, model_rpm, prompt)
        )
        self.worker_thread.progress_signal.connect(self.update_progress)
        self.worker_thread.start()

    def update_log(self, message):
        self.log_area.append(message)

    def update_progress(self, processed, total, current_chapter):
        self.total_chapters = total
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(processed)
            self.progress_bar.setFormat(f"{processed}/{total} chapters processed")
            self.current_chapter_label.setText(f"Current chapter: {current_chapter or 'None'}")

    def handle_worker_result(self, returncode, stderr, epub_file, output_dir, threads, model_id, model_rpm, prompt):
        if self.paused:
            self.log_area.append("Worker stopped due to pause.")
            self.start_button.setEnabled(True)
            return

        if returncode == 0:
            self.log_area.append("Processing completed successfully!")
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            if self.total_chapters > 0:
                self.progress_bar.setValue(self.total_chapters)
        elif returncode == 10:
            self.log_area.append("API key limit reached. Trying next key...")
            self.current_key_index += 1
            self.run_worker(epub_file, output_dir, threads, model_id, model_rpm, prompt)
        else:
            self.log_area.append(f"Worker failed with error: {stderr}")
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            
    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
        event.accept()

if __name__ == "__main__":
    if check_and_install_dependencies():
        app = QApplication(sys.argv)
        window = LauncherWindow()
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(1)