# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           Urdu Terminal & VS Code Display Utility                          ║
║           اردو ٹرمینل اور VS Code ڈسپلے یوٹیلیٹی                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  یہ فائل Windows Terminal اور VS Code میں اردو متن صحیح دکھاتی ہے         ║
║  This file safely displays Urdu text in Windows Terminal and VS Code       ║
╚══════════════════════════════════════════════════════════════════════════════╝

چلانے کا طریقہ / How to run:
    python urdu_utils.py

VS Code font سیٹ کرنے کے لیے:
    Ctrl+Shift+P → "Open User Settings JSON" → font lines شامل کریں
"""

# ──────────────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────────────
import io          # فائل encoding کنٹرول کرنے کے لیے
import os          # OS سے encoding معلومات لینے کے لیے
import sys         # stdout encoding سیٹ کرنے کے لیے
import logging     # log فائل میں لکھنے کے لیے
from datetime import datetime   # وقت کے لیے
from pathlib import Path        # فائل پاتھ کے لیے


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Windows Terminal کو UTF-8 موڈ میں ڈالیں
#          Set Windows Terminal to UTF-8 mode
# ══════════════════════════════════════════════════════════════════════════════

def setup_terminal_encoding() -> str:
    """
    Windows terminal کو UTF-8 encoding پر سیٹ کریں۔
    Set Windows terminal to UTF-8 so Urdu prints correctly.

    یہ فنکشن:
      - Windows پر chcp 65001 چلاتا ہے (UTF-8 code page)
      - stdout اور stderr کو UTF-8 میں سیٹ کرتا ہے
      - موجودہ encoding واپس کرتا ہے

    Returns:
        str — active encoding after setup (e.g. "utf-8")
    """
    current_encoding = sys.stdout.encoding or "unknown"

    if sys.platform == "win32":
        # Windows پر UTF-8 code page فعال کریں
        # chcp 65001 = UTF-8
        os.system("chcp 65001 > nul 2>&1")

        # Python کے stdout/stderr کو بھی UTF-8 پر سیٹ کریں
        # یہ ضروری ہے کیونکہ chcp کے باوجود Python پرانی encoding رکھ سکتا ہے
        if hasattr(sys.stdout, "reconfigure"):
            # Python 3.7+ — صاف طریقہ
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        else:
            # پرانے Python کے لیے fallback
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )

        new_encoding = sys.stdout.encoding or "utf-8"
        return new_encoding

    # Linux / Mac — عموماً پہلے سے UTF-8 ہوتا ہے
    return current_encoding


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — اردو safely پرنٹ کریں
#          Print Urdu text safely in any terminal
# ══════════════════════════════════════════════════════════════════════════════

# وہ Nastaleeq حروف جو بعض terminals میں ٹوٹتے ہیں
# Nastaleeq characters that may break in some terminals
_PROBLEMATIC_CHARS: dict[str, str] = {
    "\u0624": "\u0648",   # ؤ → و  (hamza on waw)
    "\u0625": "\u0627",   # إ → ا  (hamza below alef)
    "\u0622": "\u0627",   # آ → ا  (madda on alef) — صرف اگر ضروری ہو
}

def _sanitize(text: str, safe_mode: bool = False) -> str:
    """
    اردو متن کو terminal کے لیے محفوظ بنائیں۔
    Sanitize Urdu text for terminal display.

    Args:
        text:      اردو متن
        safe_mode: True = problematic chars کو replace کریں (بہت پرانے terminals کے لیے)

    Returns:
        sanitized string
    """
    if not safe_mode:
        return text  # جدید terminals کے لیے کچھ نہیں بدلنا

    for bad, good in _PROBLEMATIC_CHARS.items():
        text = text.replace(bad, good)
    return text


def print_urdu(
    text: str,
    label: str = "",
    safe_mode: bool = False,
    also_log: bool = False,
) -> None:
    """
    کسی بھی Windows terminal یا VS Code میں اردو متن صحیح پرنٹ کریں۔
    Print Urdu text safely in any Windows terminal or VS Code.

    یہ فنکشن:
      1. encoding errors کو خاموشی سے handle کرتا ہے
      2. اختیاری label لگاتا ہے (جیسے "[معلومات]")
      3. اختیاری log فائل میں بھی لکھتا ہے

    Args:
        text:      اردو (یا انگریزی) متن
        label:     اختیاری prefix label، مثلاً "✅" یا "[خرابی]"
        safe_mode: True = unsupported chars کو replace کریں
        also_log:  True = urdu_output.log فائل میں بھی لکھیں

    مثال / Example:
        print_urdu("آپ کا پاس ورڈ تبدیل ہو گیا")
        print_urdu("خرابی ہوئی!", label="❌")
    """
    sanitized = _sanitize(text, safe_mode=safe_mode)
    output    = f"{label}  {sanitized}".strip() if label else sanitized

    # terminal میں پرنٹ کریں — encoding error پر ? دکھائیں (crash نہیں)
    try:
        print(output)
    except UnicodeEncodeError:
        # آخری حل: ASCII میں تبدیل کریں اور نامعلوم حروف کو ? سے بدلیں
        print(output.encode("ascii", errors="replace").decode("ascii"))

    # اختیاری: log فائل میں لکھیں
    if also_log:
        _log_to_file(output)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — فائل میں UTF-8 لاگ کریں
#          Log output to file with UTF-8 encoding
# ══════════════════════════════════════════════════════════════════════════════

_LOG_FILE = Path(__file__).parent / "urdu_output.log"

def _log_to_file(text: str) -> None:
    """
    متن کو UTF-8 encoding کے ساتھ log فائل میں لکھیں۔
    Write text to log file with proper UTF-8 encoding.

    فائل: backend/urdu_output.log
    ہر entry میں timestamp شامل ہوتا ہے۔
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry     = f"[{timestamp}]  {text}\n"
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        # log fail ہو تو app crash نہ کرے
        print(f"[log error] {e}")


def setup_urdu_logger(log_file: str = "urdu_output.log") -> logging.Logger:
    """
    UTF-8 فائل handler کے ساتھ Python logger بنائیں۔
    Create a Python logger with UTF-8 file handler.

    یہ Python کے logging module کو صحیح encoding کے ساتھ سیٹ کرتا ہے
    تاکہ اردو log entries corrupt نہ ہوں۔

    Args:
        log_file: log فائل کا نام (default: urdu_output.log)

    Returns:
        logging.Logger — use like: logger.info("پیغام")

    مثال:
        logger = setup_urdu_logger()
        logger.info("سسٹم شروع ہو گیا")
        logger.error("ڈیٹا بیس سے رابطہ نہیں ہو سکا")
    """
    logger = logging.getLogger("urdu_logger")
    logger.setLevel(logging.DEBUG)

    # پہلے سے موجود handlers ہٹائیں (duplicate logs سے بچیں)
    logger.handlers.clear()

    # فائل handler — UTF-8 encoding لازمی
    file_handler = logging.FileHandler(
        log_file,
        encoding="utf-8",   # ← یہ لازمی ہے اردو کے لیے
        mode="a",
    )
    file_handler.setLevel(logging.DEBUG)

    # Console handler — terminal میں بھی دکھائے
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Format: وقت | سطح | پیغام
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — VS Code Settings — اردو font سیٹ اپ
#          VS Code font setup instructions
# ══════════════════════════════════════════════════════════════════════════════

VSCODE_SETTINGS = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VS Code میں اردو font سیٹ کرنے کا طریقہ
  How to set Urdu font in VS Code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 مرحلہ 1 | Step 1:
   Ctrl + Shift + P دبائیں
   "Open User Settings (JSON)" ٹائپ کریں
   Enter دبائیں

 مرحلہ 2 | Step 2 — یہ JSON لائنیں شامل کریں:

  {
    // اردو Naskh style (terminals میں بھی کام کرتا ہے)
    // Urdu Naskh style — works in terminals too
    "editor.fontFamily": "'Urdu Typesetting', 'Noto Nastaliq Urdu', Consolas, monospace",
    "editor.fontSize": 15,
    "editor.lineHeight": 28,

    // Terminal کے لیے الگ font (Nastaleeq ٹوٹتا ہے — Naskh بہتر ہے)
    // Separate terminal font (Nastaleeq breaks — Naskh is better)
    "terminal.integrated.fontFamily": "'Urdu Typesetting', Consolas, monospace",
    "terminal.integrated.fontSize": 14,

    // RTL support (اردو دائیں سے بائیں)
    "editor.unicodeHighlight.allowedLocales": { "ur": true }
  }

 مرحلہ 3 | Step 3:
   فائل محفوظ کریں (Ctrl + S)
   VS Code دوبارہ شروع کریں

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  کون سے fonts کام کرتے ہیں؟ | Which fonts work?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Urdu Typesetting    — Windows میں پہلے سے موجود، terminals میں اچھا
  ✅ Noto Nastaliq Urdu  — Google Fonts سے مفت، بہترین Nastaleeq
  ✅ Jameel Noori Nastaleeq — VS Code comments میں خوبصورت
                             ⚠️  Terminals میں ٹوٹتا ہے — صرف editor میں
  ✅ Arial Unicode MS    — عام استعمال، terminals میں ٹھیک

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

TERMINAL_SETTINGS = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Windows Terminal میں اردو font سیٹ کرنے کا طریقہ
  How to set Urdu font in Windows Terminal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 مرحلہ 1 | Step 1:
   Windows Terminal کھولیں
   Ctrl + , (Settings)

 مرحلہ 2 | Step 2:
   Profiles → Default → Appearance

 مرحلہ 3 | Step 3 — Font face میں لکھیں:
   Urdu Typesetting      ← سب سے محفوظ
   (Jameel Noori Nastaleeq ٹوٹ سکتا ہے)

 مرحلہ 4 | Step 4:
   Font size: 14 یا 15
   Save کریں

 متبادل — settings.json سے:
   %LOCALAPPDATA%\\Packages\\Microsoft.WindowsTerminal_8wekyb3d8bbwe\\LocalState\\settings.json

   "profiles": {
     "defaults": {
       "font": {
         "face": "Urdu Typesetting",
         "size": 14
       }
     }
   }
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def show_vscode_instructions() -> None:
    """VS Code اردو font سیٹ اپ ہدایات دکھائیں۔"""
    print(VSCODE_SETTINGS)


def show_terminal_instructions() -> None:
    """Windows Terminal اردو font سیٹ اپ ہدایات دکھائیں۔"""
    print(TERMINAL_SETTINGS)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Font availability چیک کریں
#          Check if Urdu fonts are installed on this system
# ══════════════════════════════════════════════════════════════════════════════

def check_urdu_fonts() -> dict[str, bool]:
    """
    Windows پر اردو fonts موجود ہیں یا نہیں چیک کریں۔
    Check which Urdu fonts are installed on Windows.

    Returns:
        dict — {font_name: is_installed}
    """
    fonts_to_check = [
        "Urdu Typesetting",
        "Noto Nastaliq Urdu",
        "Jameel Noori Nastaleeq",
        "Arial Unicode MS",
        "Segoe UI",
    ]

    results: dict[str, bool] = {}

    if sys.platform != "win32":
        # Windows کے علاوہ — fonts folder مختلف ہوتا ہے
        for font in fonts_to_check:
            results[font] = False
        return results

    try:
        # Windows fonts folder چیک کریں
        import ctypes
        from ctypes import wintypes

        fonts_dir  = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        user_fonts = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"

        # تمام font فائلیں جمع کریں
        installed: set[str] = set()
        for folder in [fonts_dir, user_fonts]:
            if folder.exists():
                for f in folder.iterdir():
                    installed.add(f.stem.lower())

        for font in fonts_to_check:
            # font name کو file name سے compare کریں (approximate)
            key        = font.lower().replace(" ", "").replace("-", "")
            is_present = any(key in f.replace(" ", "").replace("-", "") for f in installed)
            results[font] = is_present

    except Exception:
        # font check ناکام ہو تو سب False
        for font in fonts_to_check:
            results[font] = False

    return results


def print_font_status() -> None:
    """
    Urdu fonts کی موجودگی terminal میں دکھائیں۔
    Show Urdu font installation status in terminal.
    """
    print("\n" + "─" * 55)
    print("  Urdu Fonts Status | اردو Fonts کی حالت")
    print("─" * 55)

    fonts = check_urdu_fonts()
    for font, installed in fonts.items():
        status = "✅ موجود ہے   (installed)" if installed else "❌ موجود نہیں (not installed)"
        print(f"  {font:<28} {status}")

    print("─" * 55)
    recommended = [f for f, ok in fonts.items() if ok]
    if recommended:
        print(f"\n  ✅ تجویز کردہ font: {recommended[0]}")
        print(f"     VS Code میں لگائیں: \"{recommended[0]}\"")
    else:
        print("\n  ℹ️  Urdu Typesetting install کریں:")
        print("     Windows Settings → Fonts → اردو تلاش کریں")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Demo — تمام functions کا مظاہرہ
#          Demo of all functions
# ══════════════════════════════════════════════════════════════════════════════

def run_demo() -> None:
    """
    تمام اردو display functions کا مکمل مظاہرہ چلائیں۔
    Run a full demo of all Urdu display functions.
    """

    # ── Terminal Encoding سیٹ کریں ───────────────────────────────────────────
    enc = setup_terminal_encoding()
    print(f"\n  Terminal encoding: {enc}")
    print("=" * 55)
    print("  Urdu Terminal Display Demo")
    print("  اردو ٹرمینل ڈسپلے مظاہرہ")
    print("=" * 55)

    # ── بنیادی اردو پرنٹ ─────────────────────────────────────────────────────
    print("\n[1] بنیادی اردو پرنٹ | Basic Urdu print:")
    print_urdu("آپ کا خیر مقدم ہے — CRM AI Agent میں")
    print_urdu("Welcome to CRM AI Agent")

    # ── Labels کے ساتھ ───────────────────────────────────────────────────────
    print("\n[2] Labels کے ساتھ | With labels:")
    print_urdu("ڈیٹا بیس سے رابطہ قائم ہو گیا",  label="✅")
    print_urdu("Kafka producer شروع ہو گیا",       label="✅")
    print_urdu("Gmail ٹوکن محفوظ ہو گیا",          label="💾")
    print_urdu("نیٹ ورک سے رابطہ نہیں ہو سکا",     label="❌")
    print_urdu("API key نہیں ملی — .env چیک کریں", label="⚠️ ")

    # ── CRM پیغامات ──────────────────────────────────────────────────────────
    print("\n[3] CRM پیغامات | CRM Messages:")
    print_urdu("گاہک کا پیغام موصول ہوا",           label="📨")
    print_urdu("AI جواب تیار ہو گیا",               label="🤖")
    print_urdu("ای میل بھیج دی گئی",                label="📧")
    print_urdu("WhatsApp پیغام بھیجا گیا",           label="💬")
    print_urdu("ٹکٹ escalate ہو گیا",               label="🎫")

    # ── Log فائل میں لکھنا ───────────────────────────────────────────────────
    print("\n[4] Log فائل میں لکھنا | Logging to file:")
    print_urdu("یہ پیغام log فائل میں بھی جائے گا", label="📝", also_log=True)
    print_urdu("This message is also saved to log",  label="📝", also_log=True)
    print(f"     Log فائل: {_LOG_FILE}")

    # ── Python Logger ─────────────────────────────────────────────────────────
    print("\n[5] Python Logger (UTF-8):")
    logger = setup_urdu_logger("urdu_output.log")
    logger.info("سسٹم شروع ہو گیا — System started")
    logger.warning("ٹوکن میعاد ختم ہونے والی ہے — Token expiring soon")
    logger.error("ڈیٹا بیس خرابی — Database error")

    # ── Font Status ───────────────────────────────────────────────────────────
    print("\n[6] Installed Urdu Fonts:")
    print_font_status()

    # ── اردو اعداد اور تاریخ ─────────────────────────────────────────────────
    print("[7] اردو اعداد اور تاریخ | Urdu numbers and date:")
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    print_urdu(f"موجودہ وقت: {now}")
    print_urdu(f"کل پیغامات: 1,234")
    print_urdu(f"حل شدہ ٹکٹ: 89  |  زیر التواء: 12")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print_urdu("تمام functions کامیابی سے کام کر رہے ہیں ✅")
    print("=" * 55)
    print("\nاگلے مراحل | Next steps:")
    print("  1. python gmail_setup.py     ← Gmail test کریں")
    print("  2. uvicorn main:app --reload ← API شروع کریں")
    print("  3. pytest tests/ -v          ← tests چلائیں")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # پوچھیں کیا دیکھنا ہے
    print("\nکیا کرنا ہے؟ | What would you like to do?")
    print("  1. Demo چلائیں (سب functions)")
    print("  2. VS Code font ہدایات")
    print("  3. Terminal font ہدایات")
    print("  4. Installed fonts چیک کریں")

    choice = input("\nنمبر داخل کریں | Enter number (1-4): ").strip()

    if choice == "1":
        run_demo()
    elif choice == "2":
        setup_terminal_encoding()
        show_vscode_instructions()
    elif choice == "3":
        setup_terminal_encoding()
        show_terminal_instructions()
    elif choice == "4":
        setup_terminal_encoding()
        print_font_status()
    else:
        # default — demo چلائیں
        run_demo()
