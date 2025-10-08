# language_config.py

"""
This file contains the language configurations for the translator.
Each entry maps a user-friendly name to the codes required by the
translator and the OCR engine.

- 'source': The language code used by deep-translator.
  (List: https://py-google-translator.readthedocs.io/en/latest/languages.html)
- 'ocr': The language data file code used by Tesseract OCR.
  (List: https://tesseract-ocr.github.io/tessdoc/Data-Files-in-version-4.00.html)
"""

LANGUAGES = {
    "Japanese": {
        "source": "ja",
        "ocr": "jpn"
    },
    "Korean": {
        "source": "ko",
        "ocr": "kor"
    },
    "Chinese (Simplified)": {
        "source": "zh-CN",
        "ocr": "chi_sim"
    },
    "Russian": {
        "source": "ru",
        "ocr": "rus"
    },
    "German": {
        "source": "de",
        "ocr": "deu"
    },
}