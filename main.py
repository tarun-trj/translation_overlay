# This script creates a full GUI application for real-time screen translation.
# It allows a user to select a window, and it will overlay translations
# from a source language to an English in real-time.

import sys
import time
import traceback
import ctypes
from ctypes import wintypes
import os
import multiprocessing
import queue
import shutil
from functools import partial

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QDialog,
    QComboBox, QDialogButtonBox, QCheckBox, QHBoxLayout
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QRect, pyqtSlot
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QFontMetrics, QGuiApplication
import win32gui
from PIL import ImageGrab, ImageChops, Image
import pytesseract
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException

# --- App Configuration ---
import language_config

# -----------------------------------------------------------------------------
# ## --- USER SETTINGS --- ##
# -----------------------------------------------------------------------------

# -- Language Settings --
# Supported language codes: https://py-google-translator.readthedocs.io/en/latest/languages.html
TARGET_LANGUAGE = 'en'      # Language to translate TO (e.g., 'en', 'es', 'fr')

# -- Performance Settings --
# Limit the number of parallel translation processes to prevent memory errors.
# Start with 4. If you get errors, try 2.
TRANSLATION_WORKER_COUNT = 4

# -- Detection Settings --
# How much the screen must change (in percent) to trigger a new translation.
# Lower is more sensitive but uses more resources.
CHANGE_THRESHOLD_PERCENT = 0.1

# -- Tesseract Path (Automatic path finding is now default) --
# The script will try to find Tesseract automatically. If it fails, set the path
# manually here. Example: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_MANUAL_PATH = r"D:\APPS\code_libs\tesseract\tesseract.exe"

# -- Debugging --
DEBUG_MODE = False  # Set to True to save debug images and show detailed output

# -----------------------------------------------------------------------------

# --- DYNAMIC TESSERACT CONFIGURATION ---
def configure_tesseract():
    """Finds Tesseract path automatically or uses the manual path."""
    tesseract_path = TESSERACT_MANUAL_PATH or shutil.which('tesseract')
    if not tesseract_path:
        print("--- TESSERACT NOT FOUND ---")
        print("Error: Tesseract executable not found.")
        print("Please do one of the following:")
        print("1. Install Tesseract and add it to your system's PATH.")
        print("2. Set the TESSERACT_MANUAL_PATH variable in this script.")
        print("Download Tesseract from: https://github.com/tesseract-ocr/tesseract")
        sys.exit(1)
    
    print(f"✓ Tesseract found at: {tesseract_path}")
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

configure_tesseract()


# --- SET DPI AWARENESS (MUST BE BEFORE ANY GUI OPERATIONS) ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    print("✓ DPI awareness set successfully")
except Exception as e:
    print(f"Could not set DPI awareness: {e}")
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
        print("✓ DPI awareness set successfully (fallback)")
    except Exception as e2:
        print(f"Could not set DPI awareness using fallback: {e2}")


# --- Graceful Error Handling ---
def handle_exception(exc_type, exc_value, exc_traceback):
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"UNHANDLED EXCEPTION:\n{error_msg}")
    try:
        with open("error.log", "a") as f:
            f.write(f"--- {time.ctime()} ---\n{error_msg}\n")
    except Exception as log_e:
        print(f"Could not write to error.log: {log_e}")
    QApplication.quit()

# --- DPI HELPER FUNCTIONS ---
def get_dpi_scale():
    """Get the DPI scaling factor for the primary monitor"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        scale = dpi / 96.0
        print(f"✓ DPI detected: {int(scale * 100)}% scaling")
        return scale
    except Exception as e:
        print(f"⚠ Could not detect DPI: {e}")
        return 1.0

# --- MODULAR FUNCTIONS FOR CORE LOGIC ---
# These are defined globally so the separate process can access them.

def capture_window_area(hwnd: int) -> tuple[Image.Image | None, QRect | None]:
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return None, None
    try:
        dwmapi = ctypes.windll.dwmapi
        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd),
                                      wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                                      ctypes.byref(rect),
                                      ctypes.sizeof(rect))
        if rect.left == 0 and rect.right == 0:
            rect_tuple = win32gui.GetWindowRect(hwnd)
            rect = wintypes.RECT(*rect_tuple)
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]: return None, None
        screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
        window_qrect = QRect(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
        return screenshot, window_qrect
    except Exception:
        return None, None

def screen_has_changed(new_image: Image.Image, last_image: Image.Image, threshold: float) -> bool:
    if not last_image: return True
    diff = ImageChops.difference(last_image, new_image)
    sum_of_diffs = sum(diff.convert("L").getdata())
    width, height = new_image.size
    max_diff = width * height * 255
    diff_percentage = (sum_of_diffs / max_diff) * 100 if max_diff > 0 else 0
    print(f"   📊 Screen change: {diff_percentage:.2f}% (threshold: {threshold}%)")
    return diff_percentage >= threshold

def extract_text_blocks(image: Image.Image, ocr_lang: str) -> list[dict]:
    lines = {}
    ocr_data = pytesseract.image_to_data(image.convert('L'), lang=ocr_lang, output_type=pytesseract.Output.DICT)

    lines = {}
    ocr_data = pytesseract.image_to_data(image.convert('L'), lang=ocr_lang, output_type=pytesseract.Output.DICT)
    for i in range(len(ocr_data['level'])):
        conf, text = int(ocr_data['conf'][i]), ocr_data['text'][i].strip()
        if conf > 50 and text:
            line_key = (ocr_data['block_num'][i], ocr_data['par_num'][i], ocr_data['line_num'][i])
            if line_key not in lines: lines[line_key] = {'words': []}
            lines[line_key]['words'].append({'text': text, 'left': ocr_data['left'][i], 'top': ocr_data['top'][i], 'width': ocr_data['width'][i], 'height': ocr_data['height'][i]})

    text_blocks = []
    for line_info in lines.values():
        if not line_info['words']: continue
        full_text = "".join([word['text'] for word in line_info['words']])
        left, top = min(w['left'] for w in line_info['words']), min(w['top'] for w in line_info['words'])
        right, bottom = max(w['left'] + w['width'] for w in line_info['words']), max(w['top'] + w['height'] for w in line_info['words'])
        text_blocks.append({'text': full_text, 'rect': QRect(left, top, right - left, bottom - top)})
    return text_blocks

def translate_single_block_worker(block: dict, source_lang: str) -> dict | None:
    """Annotates, checks, and translates a single text block."""
    original_text = block['text']
    
    # 1. Annotate by detecting the language
    try:
        detected_lang = detect(original_text)
        block['detected_lang'] = detected_lang
    except LangDetectException:
        block['detected_lang'] = 'unknown'
        if DEBUG_MODE: print(f"   - Skipping ambiguous block: '{original_text[:20]}...'")
        return None

    # 2. Translate only if detected language matches the selected source language
    if block['detected_lang'] == source_lang:
        try:
            translated_text = GoogleTranslator(source=source_lang, target=TARGET_LANGUAGE).translate(original_text)
            if translated_text:
                if DEBUG_MODE: print(f"   + Translating '{original_text[:20]}...' (detected: {detected_lang})")
                return {'text': translated_text, 'rect': block['rect']}
        except Exception:
            return None
    else:
        if DEBUG_MODE: print(f"   - Skipping block: '{original_text[:20]}...' (detected: {block['detected_lang']}, needed: {source_lang})")
        return None
    return None

def run_ocr_and_translation_subprocess(image, window_qrect, result_queue, ocr_lang, source_lang):
    """
    This function runs in a separate process. It performs OCR, then uses a
    pool of worker processes to perform translation in parallel for maximum speed.
    """
    print("       [Subprocess] Running OCR...")
    text_blocks = extract_text_blocks(image, ocr_lang)
    translated_blocks = []
    if text_blocks:
        print(f"       [Subprocess] Found {len(text_blocks)} blocks, translating with {TRANSLATION_WORKER_COUNT} workers...")
        # Use functools.partial to pass the extra source_lang argument to the worker
        worker_func = partial(translate_single_block_worker, source_lang=source_lang)
        with multiprocessing.Pool(processes=TRANSLATION_WORKER_COUNT) as pool:
            results = pool.map(worker_func, text_blocks)
        translated_blocks = [block for block in results if block is not None]

    for block in translated_blocks:
        block['rect'].translate(window_qrect.left(), window_qrect.top())
    print(f"       [Subprocess] Done. {len(translated_blocks)} blocks translated.")
    result_queue.put(translated_blocks)

# --- WORKER THREAD FOR OCR AND TRANSLATION ---
class TranslationWorker(QThread):
    new_translation = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    paused_state_changed = pyqtSignal(bool)

    def __init__(self, hwnd, ocr_lang, source_lang):
        super().__init__()
        self.hwnd = hwnd
        self.ocr_lang = ocr_lang
        self.source_lang = source_lang
        self._is_running = True
        self._is_paused = False
        self.last_screenshot_image = None
        self.force_retranslate_flag = False
        self.current_process = None

    @pyqtSlot()
    def toggle_pause(self):
        self._is_paused = not self._is_paused
        print(f"[Worker] Paused state set to: {self._is_paused}")
        self.paused_state_changed.emit(self._is_paused)

    @pyqtSlot()
    def force_retranslate(self):
        print("[Worker] Force re-translation requested.")
        if self._is_paused:
            self._is_paused = False
            self.paused_state_changed.emit(False)
            print("[Worker] Un-paused due to force re-translate.")

        self.force_retranslate_flag = True
        if self.current_process and self.current_process.is_alive():
            print("[Worker] Terminating active OCR/Translate process.")
            self.current_process.terminate()

    def run(self):
        print("[Worker] Translation thread started.")
        while self._is_running:
            try:
                while self._is_paused:
                    if not self._is_running: return
                    time.sleep(0.1)

                screenshot, window_qrect = capture_window_area(self.hwnd)
                if not screenshot:
                    self.error_occurred.emit("Target window invalid. Pausing.")
                    time.sleep(1); continue

                should_run_translation = self.force_retranslate_flag or \
                                         screen_has_changed(screenshot, self.last_screenshot_image, CHANGE_THRESHOLD_PERCENT)

                if should_run_translation:
                    print("[Worker] Change detected or forced, starting OCR/Translate process.")
                    self.force_retranslate_flag = False
                    self.last_screenshot_image = screenshot

                    if self.current_process and self.current_process.is_alive():
                        self.current_process.terminate()
                        self.current_process.join()

                    result_queue = multiprocessing.Queue()
                    self.current_process = multiprocessing.Process(
                        target=run_ocr_and_translation_subprocess,
                        args=(screenshot, window_qrect, result_queue, self.ocr_lang, self.source_lang)
                    )
                    self.current_process.start()
                    self.current_process.join()

                    if self.current_process.exitcode == 0:
                        try:
                            self.new_translation.emit(result_queue.get_nowait())
                        except queue.Empty:
                            print("[Worker] Subprocess finished but queue was empty.")
                    else:
                        print(f"[Worker] Subprocess ended with exit code {self.current_process.exitcode}. Likely terminated.")

                    wait_duration = 3.0
                else:
                    wait_duration = 1.0

                start_wait = time.time()
                while time.time() - start_wait < wait_duration:
                    if not self._is_running or self.force_retranslate_flag: break
                    time.sleep(0.1)

            except Exception as e:
                print(f"[Worker] ERROR in translation thread: {e}"); traceback.print_exc()
                self.error_occurred.emit(f"Error in translation thread: {e}")
                time.sleep(2)

    def stop(self):
        print("[Worker] Translation thread stopping.")
        self._is_running = False
        if self.current_process and self.current_process.is_alive():
            self.current_process.terminate()
        self.wait()

# --- OVERLAY WINDOW ---
class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.translated_blocks = []
        self.draw_recognition_boxes = False
        self._affinity_set = False

    def update_translations(self, blocks):
        self.translated_blocks = blocks
        screen_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(0, 0, screen_geo.width(), screen_geo.height())
        self.show()
        if not self._affinity_set: self.set_capture_exclusion()
        self.update()

    @pyqtSlot()
    def clear(self):
        """Clears all translated blocks and hides the overlay window."""
        self.translated_blocks = []
        self.hide()

    def set_capture_exclusion(self):
        try:
            hwnd = int(self.winId())
            if hwnd:
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                ctypes.windll.user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), wintypes.DWORD(WDA_EXCLUDEFROMCAPTURE))
                self._affinity_set = True
                print("✓ Overlay set to be excluded from screen captures.")
        except Exception as e:
            print(f"⚠ Could not set window display affinity: {e}")

    def set_draw_boxes_enabled(self, enabled: bool):
        self.draw_recognition_boxes = enabled
        self.update()

    def paintEvent(self, event):
        if not self.translated_blocks: return
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for block in self.translated_blocks:
            rect = block['rect']
            painter.fillRect(rect.adjusted(-2, -2, 2, 2), QColor(0, 0, 0, 190))
            self.draw_fitted_text(painter, rect, block['text'])
        if self.draw_recognition_boxes:
            painter.save(); painter.setPen(QPen(QColor(255, 0, 0, 200), 2)); painter.setBrush(Qt.BrushStyle.NoBrush)
            for block in self.translated_blocks: painter.drawRect(block['rect'])
            painter.restore()

    def draw_fitted_text(self, painter: QPainter, rect: QRect, text: str):
        painter.save(); painter.setPen(QColor(255, 255, 255))
        for size in range(rect.height(), 5, -1):
            font = QFont('Arial', size, QFont.Weight.Bold); metrics = QFontMetrics(font)
            if metrics.boundingRect(rect, int(Qt.TextFlag.TextWordWrap), text).height() <= rect.height():
                painter.setFont(font)
                painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text)
                break
        painter.restore()

# --- OVERLAY BUTTON WINDOW ---
class OverlayButtonWindow(QWidget):
    force_retranslate_requested = pyqtSignal()
    pause_toggled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        button_style = """
            QPushButton {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                border: 1px solid white;
                font-size: 16px;
                border-radius: 17px;
                padding-bottom: 2px;
            }
            QPushButton:hover { background-color: rgba(30, 30, 30, 220); }
            QPushButton:pressed { background-color: rgba(60, 60, 60, 255); }
        """

        self.pause_button = QPushButton("⏸")
        self.pause_button.setFixedSize(35, 35)
        self.pause_button.setStyleSheet(button_style)
        self.pause_button.clicked.connect(self.pause_toggled.emit)

        self.redo_button = QPushButton("↻")
        self.redo_button.setFixedSize(35, 35)
        self.redo_button.setStyleSheet(button_style)
        self.redo_button.clicked.connect(self.force_retranslate_requested.emit)

        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.redo_button)
        self.setLayout(layout)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.sizeHint().width() - 20, screen.top() + 20)

    @pyqtSlot(bool)
    def set_paused_state(self, is_paused: bool):
        self.pause_button.setText("▶" if is_paused else "⏸")


# --- DIALOG FOR WINDOW SELECTION ---
class WindowSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Select a Window")
        layout = QVBoxLayout(self); label = QLabel("Please choose a window to translate:")
        self.combo_box = QComboBox(); layout.addWidget(label); layout.addWidget(self.combo_box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.windows = self._get_open_windows()
        for title in sorted(self.windows.keys()): self.combo_box.addItem(title, userData=self.windows[title])

    def _get_open_windows(self):
        windows = {}
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                windows[win32gui.GetWindowText(hwnd)] = hwnd
        win32gui.EnumWindows(callback, None)
        return windows

    def selected_window(self):
        if self.result() == QDialog.DialogCode.Accepted:
            return self.combo_box.currentData(), self.combo_box.currentText()
        return None, None

# --- MAIN CONTROL WINDOW ---
class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.target_hwnd = None
        self.worker_thread = None
        self.overlay = OverlayWindow()
        self.overlay_button = OverlayButtonWindow()
        self.setWindowTitle('Real-Time Translator Control')
        layout = QVBoxLayout()
        
        self.status_label = QLabel('Status: Select language and window.')
        
        # Language selection dropdown
        lang_layout = QHBoxLayout()
        lang_label = QLabel("Translate From:")
        self.lang_combo_box = QComboBox()
        self.lang_combo_box.addItem("--- Select a Language ---", None)
        for name, data in language_config.LANGUAGES.items():
            self.lang_combo_box.addItem(name, data)
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_combo_box)
        layout.addLayout(lang_layout)
        
        self.select_button = QPushButton('Select a Window to Translate')
        self.start_button = QPushButton('Start Translation')
        self.force_retranslate_button = QPushButton('Force Retranslate')
        self.stop_button = QPushButton('Stop Translation')
        self.draw_boxes_checkbox = QCheckBox("Show original text boxes (red outline)")

        for w in [self.select_button, self.start_button, self.force_retranslate_button, self.stop_button, self.draw_boxes_checkbox]:
            layout.addWidget(w)
        self.setLayout(layout)

        self.select_button.clicked.connect(self.open_window_selection_dialog)
        self.start_button.clicked.connect(self.start_translation)
        self.stop_button.clicked.connect(self.stop_translation)
        self.draw_boxes_checkbox.stateChanged.connect(lambda state: self.overlay.set_draw_boxes_enabled(state == Qt.CheckState.Checked.value))

        self.lang_combo_box.currentIndexChanged.connect(self.update_start_button_state)
        self.stop_button.setEnabled(False)
        self.force_retranslate_button.setEnabled(False)
        self.update_start_button_state() # Initial check

    def update_start_button_state(self):
        """Enable start button only if a language and window are selected."""
        lang_selected = self.lang_combo_box.currentData() is not None
        window_selected = self.target_hwnd is not None
        self.start_button.setEnabled(lang_selected and window_selected)

    def open_window_selection_dialog(self):
        dialog = WindowSelectionDialog(self)
        if dialog.exec():
            hwnd, title = dialog.selected_window()
            if hwnd:
                self.target_hwnd = hwnd
                self.status_label.setText(f"Selected: '{title[:50]}...'")
        self.update_start_button_state()

    def start_translation(self):
        lang_data = self.lang_combo_box.currentData()
        if not self.target_hwnd or not lang_data:
            self.status_label.setText('Error: Select a language and window!'); return
        if self.worker_thread and self.worker_thread.isRunning(): return
        
        source_lang = lang_data['source']
        ocr_lang = lang_data['ocr']

        self.status_label.setText('Status: Translation running...')
        self.start_button.setEnabled(False); self.stop_button.setEnabled(True)
        self.select_button.setEnabled(False); self.force_retranslate_button.setEnabled(True)
        self.lang_combo_box.setEnabled(False)

        self.worker_thread = TranslationWorker(self.target_hwnd, ocr_lang, source_lang)
        self.worker_thread.new_translation.connect(self.overlay.update_translations)
        self.worker_thread.error_occurred.connect(lambda msg: self.status_label.setText(f"Status: {msg}"))

        self.force_retranslate_button.clicked.connect(self.worker_thread.force_retranslate)
        self.overlay_button.force_retranslate_requested.connect(self.worker_thread.force_retranslate)
        self.overlay_button.pause_toggled.connect(self.worker_thread.toggle_pause)
        self.worker_thread.paused_state_changed.connect(self.overlay_button.set_paused_state)
        self.overlay_button.pause_toggled.connect(self.overlay.clear)
        self.overlay_button.force_retranslate_requested.connect(self.overlay.clear)

        self.worker_thread.start()
        self.overlay_button.show()

    def stop_translation(self):
        if self.worker_thread and self.worker_thread.isRunning(): self.worker_thread.stop()
        self.status_label.setText('Status: Stopped. Select language and window.')
        self.stop_button.setEnabled(False); self.select_button.setEnabled(True)
        self.force_retranslate_button.setEnabled(False); self.lang_combo_box.setEnabled(True)
        self.update_start_button_state()
        self.overlay.clear(); self.overlay_button.hide()
        self.overlay_button.set_paused_state(False)

    def closeEvent(self, event):
        self.stop_translation(); self.overlay.close(); self.overlay_button.close()
        event.accept()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    sys.excepthook = handle_exception
    app = QApplication(sys.argv)
    control_win = ControlWindow()
    control_win.show()
    sys.exit(app.exec())
