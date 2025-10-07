# 🌐 Real-Time Screen Translator

![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

A high-performance, on-screen translator for Windows that captures a selected application window, recognizes text using OCR, and overlays the translation in real-time.

This tool is designed for performance, using a **multi-process architecture** to ensure your GUI never freezes, even during intensive OCR and translation tasks. It's perfect for translating games, applications, or any on-screen text that you can't copy.

---

## ✨ Features

-   🕒 **Real-Time Translation**: Automatically detects visual changes in the target window and updates translations.
-   ⚡ **High Performance**: Utilizes multithreading for screen capture and multiprocessing for OCR/translation to ensure a smooth, non-blocking experience.
-   🧠 **Parallel Processing**: Translates multiple text blocks simultaneously using a process pool for significantly faster results.
-   🎯 **Windowed Capture**: Select any open application window to translate.
-   -   **Interactive Controls**: A simple floating overlay provides one-click controls to pause/resume (⏸/▶) translation or force a manual refresh (↻).
-   🧰 **Dynamic & Configurable**: Automatically finds your Tesseract installation and includes clear settings for language, performance, and sensitivity.
-   🪟 **Intelligent Overlay**: A transparent, click-through overlay that automatically resizes text to fit within the original text block boundaries. The overlay itself is excluded from screen captures, so it won't be re-translated.

---

## ⚙️ How It Works

The application's architecture separates the user interface from heavy processing tasks, ensuring the GUI remains responsive at all times.

1.  **Control Panel (Main UI Thread)**: Built with PyQt6, the main window handles selecting the target window and starting/stopping the translation process.
2.  **Capture & Detection Thread (`TranslationWorker`)**: Runs in the background, continuously capturing screenshots of the selected window, comparing frames to detect visual changes, and avoiding redundant processing when the screen is static.
3.  **OCR & Translation Subprocess**: To prevent GUI lag, OCR and translation are executed in a separate process.
    -   **OCR Stage**: Tesseract OCR analyzes the captured image to extract text blocks.
    -   **Parallel Translation Stage**: A `multiprocessing.Pool` translates all found text blocks simultaneously.
4.  **Overlay Window (`OverlayWindow`)**: The translated text is rendered via a transparent, frameless, click-through PyQt6 window, positioned accurately over the original text locations.

---

## 🛠️ Technology Stack

| Component         | Description                               |
| ----------------- | ----------------------------------------- |
| **Python 3**      | Core programming language                 |
| **PyQt6**         | Graphical user interface framework        |
| **Tesseract OCR** | Text recognition engine                   |
| **Pillow (PIL)**  | Screen capture & image manipulation       |
| **pytesseract**   | Python wrapper for Tesseract              |
| **deep-translator** | Handles translation via Google Translate  |
| **pywin32**       | Windows API access for window management  |

---

## 🚀 Getting Started

### ✅ Prerequisites

1.  **Python 3.10+** installed and added to your system's PATH.
2.  **Tesseract OCR Engine** installed from the [official repository](https://github.com/tesseract-ocr/tesseract).

> **CRITICAL:**
>
> -   During the Tesseract installation, make sure to select the required language packs for the languages you want to translate from (e.g., Japanese, Korean, Chinese).
> -   Ensure the option **"Add Tesseract to the system PATH"** is checked during installation. The script relies on this to find the Tesseract executable.

### 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/tarun-trj/translation_overlay.git
    cd translation_overlay
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    # For Windows
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install the required dependencies:**
    The `requirements.txt` file contains all necessary packages.
    ```bash
    pip install -r requirements.txt
    ```

### ▶️ Usage

1.  **Run the application:**
    ```bash
    python main.py
    ```

2.  **Select a Window:** Click the "Select a Window to Translate" button and choose your target application from the dropdown list.

3.  **Start Translation:** Click "Start Translation."

The translation overlay will appear on top of the target window, and a small control panel with pause (⏸) and refresh (↻) buttons will appear in the top-right corner of your screen.

---

## ⚙️ Configuration

You can customize the translator's behavior by editing the `USER SETTINGS` section at the top of `main.py`.

| Variable                     | Description                                                                                                                            | Default |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `SOURCE_LANGUAGE`            | Language to translate FROM (e.g., 'ja', 'ko', 'zh-CN'). [See codes](https://py-google-translator.readthedocs.io/en/latest/languages.html). | `'ja'`  |
| `TARGET_LANGUAGE`            | Language to translate TO (e.g., 'en', 'es', 'fr').                                                                                     | `'en'`  |
| `OCR_LANGUAGE`               | Tesseract language pack name. Must match the source language (e.g., 'ja' -> 'jpn'). [See names](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-version-4.00.html). | `'jpn'` |
| `TRANSLATION_WORKER_COUNT`   | Number of parallel processes for translation. Reduce if you face memory errors.                                                        | `4`     |
| `CHANGE_THRESHOLD_PERCENT`   | How much the screen must change (%) to trigger a new translation. Lower is more sensitive but uses more resources.                     | `3`     |
| `TESSERACT_MANUAL_PATH`      | Set the full path to `tesseract.exe` if the script can't find it automatically.                                                          | `""`    |

---

## 🤔 Troubleshooting

-   **"Tesseract Not Found" Error**
    -   Verify that Tesseract is installed and that its installation directory was added to your system's PATH. You can check this by opening a new terminal and running `tesseract --version`.
    -   Restart your terminal or IDE after installation to ensure the new PATH is loaded.
    -   As a last resort, set the `TESSERACT_MANUAL_PATH` variable in the script to the full path of your `tesseract.exe`.

-   **Memory Errors or High CPU Usage**
    -   Lower the `TRANSLATION_WORKER_COUNT` in `main.py` to `2` or `1`. This reduces the number of parallel processes.

-   **Incorrect or No Translations**
    -   Ensure the text in the target window is clear and legible. OCR works best on clean, high-contrast text.
    -   Verify that the `SOURCE_LANGUAGE` and `OCR_LANGUAGE` settings in `main.py` correctly match the on-screen language.
