# Terminal color styling utilities using ANSI escape codes

import os
import sys

# Detect if terminal supports color
def _supports_color():
    if os.environ.get('NO_COLOR'):
        return False
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    return True

_COLOR = _supports_color()
_SOFT = True  # soft mode on by default — less eye strain

def enable_vivid_mode():
    """Restore original bright/bold colour palette."""
    global _SOFT, BOLD
    global BRIGHT_RED, BRIGHT_GREEN, BRIGHT_YELLOW, BRIGHT_BLUE
    global BRIGHT_MAGENTA, BRIGHT_CYAN, BRIGHT_WHITE
    _SOFT = False
    if not _COLOR:
        return
    BOLD = '\033[1m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

# ANSI escape codes
RESET = '\033[0m' if _COLOR else ''
BOLD = '' if _COLOR else ''  # soft default: no bold
DIM = '\033[2m' if _COLOR else ''
ITALIC = '\033[3m' if _COLOR else ''
UNDERLINE = '\033[4m' if _COLOR else ''

# Foreground colors
BLACK = '\033[30m' if _COLOR else ''
RED = '\033[31m' if _COLOR else ''
GREEN = '\033[32m' if _COLOR else ''
YELLOW = '\033[33m' if _COLOR else ''
BLUE = '\033[34m' if _COLOR else ''
MAGENTA = '\033[35m' if _COLOR else ''
CYAN = '\033[36m' if _COLOR else ''
WHITE = '\033[37m' if _COLOR else ''

# Bright colors — soft default: use regular (dimmer) variants
BRIGHT_RED = '\033[31m' if _COLOR else ''
BRIGHT_GREEN = '\033[32m' if _COLOR else ''
BRIGHT_YELLOW = '\033[33m' if _COLOR else ''
BRIGHT_BLUE = '\033[34m' if _COLOR else ''
BRIGHT_MAGENTA = '\033[35m' if _COLOR else ''
BRIGHT_CYAN = '\033[36m' if _COLOR else ''
BRIGHT_WHITE = '\033[37m' if _COLOR else ''


# --- Semantic helpers ---

def header(text):
    """Major section header with double-line border."""
    w = max(len(text) + 4, 60)
    border = '═' * w
    if _SOFT:
        return f"{DIM}{CYAN}{border}{RESET}\n{BRIGHT_CYAN}  {text}{RESET}\n{DIM}{CYAN}{border}{RESET}"
    return f"{BOLD}{CYAN}{border}{RESET}\n{BOLD}{CYAN}  {text}{RESET}\n{BOLD}{CYAN}{border}{RESET}"

def subheader(text):
    """Sub-section header with single-line border."""
    w = max(len(text) + 4, 60)
    border = '─' * w
    if _SOFT:
        return f"{DIM}{border}{RESET}\n{BRIGHT_WHITE}  {text}{RESET}\n{DIM}{border}{RESET}"
    return f"{CYAN}{border}{RESET}\n{BOLD}{WHITE}  {text}{RESET}\n{CYAN}{border}{RESET}"

def divider(char='─', width=60):
    """Simple divider line."""
    return f"{DIM}{char * width}{RESET}"

def title(text):
    """Bold title text."""
    return f"{BOLD}{BRIGHT_CYAN}{text}{RESET}"

def label(text):
    """Label for key-value pairs."""
    return f"{BOLD}{WHITE}{text}{RESET}"

def value(text):
    """Highlighted value."""
    return f"{BRIGHT_GREEN}{text}{RESET}"

def value_negative(text):
    """Highlighted negative value."""
    return f"{BRIGHT_RED}{text}{RESET}"

def info(text):
    """Informational / progress message."""
    return f"{DIM}{ITALIC}{text}{RESET}"

def success(text):
    """Success message."""
    return f"{BRIGHT_GREEN}{text}{RESET}"

def warning(text):
    """Warning message."""
    return f"{BRIGHT_YELLOW}{text}{RESET}"

def error(text):
    """Error message."""
    return f"{BRIGHT_RED}{text}{RESET}"

def company(text):
    """Company name / ticker highlight."""
    return f"{BOLD}{BRIGHT_YELLOW}{text}{RESET}"

def prompt(text):
    """Input prompt styling."""
    return f"{BRIGHT_CYAN}{text}{RESET}"

def ai_label(text):
    """AI section label."""
    return f"{BOLD}{MAGENTA}{text}{RESET}"

def muted(text):
    """Dim / muted text."""
    return f"{DIM}{text}{RESET}"

def price_colored(price, reference=None):
    """Color a price green if >= reference, red if below."""
    formatted = f"{price:,.2f}"
    if reference is not None:
        if price >= reference:
            return f"{BOLD}{BRIGHT_GREEN}{formatted}{RESET}"
        else:
            return f"{BOLD}{BRIGHT_RED}{formatted}{RESET}"
    return f"{BOLD}{formatted}{RESET}"

def pct_colored(pct):
    """Color a percentage green if positive, red if negative."""
    formatted = f"{pct:+.1f}%"
    if pct >= 0:
        return f"{BRIGHT_GREEN}{formatted}{RESET}"
    else:
        return f"{BRIGHT_RED}{formatted}{RESET}"
