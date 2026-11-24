
import os
from pathlib import Path

# =========================================================
# NICO CONFIGURATION
# =========================================================

BASE_DIR = Path(os.environ.get("NICO_HOME", r"D:\NICO"))
DATA_DIR = BASE_DIR / "data"
MEMORY_FILE = DATA_DIR / "memory.json"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
EXPORTS_DIR = BASE_DIR / "exports"
NOTES_DIR = BASE_DIR / "notes"
CRASH_LOG = BASE_DIR / "crash.log"

OLLAMA_URL = os.environ.get(
    "NICO_OLLAMA_URL",
    "http://127.0.0.1:11434/api/chat",
)

OLLAMA_TAGS_URL = os.environ.get(
    "NICO_OLLAMA_TAGS_URL",
    "http://127.0.0.1:11434/api/tags",
)

DEFAULT_MODEL = os.environ.get("NICO_MODEL", "qwen2.5:1.5b")

# =========================================================
# PERSONAL PROFILE
# =========================================================

OWNER_NAME = "Richard Otieno Obiero"
OWNER_BIRTH_DATE = "10 May 2009"
OWNER_FAVOURITE_FOOD = "chapati"
OWNER_FAMILY_NAME = "Owande"
OWNER_FATHER = "James Olweny"
OWNER_MOTHER = "Happiness Olweny"
OWNER_SIBLINGS = ("Mercy", "Audry", "Javan", "Norah")
OWNER_BIRTHPLACE = "Migori"
OWNER_SCHOOL = "Maseno School"
OWNER_PREFERRED_TITLE = "Sir Richard"

OWNER_PROFILE = f"""Richard's personal details:
- Full name: {OWNER_NAME}
- Date of birth: {OWNER_BIRTH_DATE}
- Favourite food: {OWNER_FAVOURITE_FOOD}
- Family name: {OWNER_FAMILY_NAME}
- Father: {OWNER_FATHER}
- Mother: {OWNER_MOTHER}
- Siblings: {", ".join(OWNER_SIBLINGS)}
- Place of birth: {OWNER_BIRTHPLACE}
- School: {OWNER_SCHOOL}
- Preferred form of address: {OWNER_PREFERRED_TITLE}."""

# =========================================================
# COLOURS
# =========================================================

BG = "#030912"
PANEL = "#071522"
PANEL_LIGHT = "#0B2030"
CYAN = "#00D9FF"
BLUE = "#087FAF"
WHITE = "#DDF7FF"
MUTED = "#63899D"
GREEN = "#00E6A8"
AMBER = "#FFC857"
RED = "#FF4D4D"
ORANGE = "#FFA500"
MAGENTA = "#FF00FF"
PURPLE = "#BD00FF"
YELLOW = "#FFFF00"

# =========================================================
# SYSTEM PROMPTS
# =========================================================

SHORT_SYSTEM_PROMPT = f"""You are NICO, Richard Otieno Obiero's personal AI assistant.
Richard created you. Address him as Sir Richard.

{OWNER_PROFILE}

Be warm, helpful, respectful, calm, and natural. Remember the profile
details and use them accurately when relevant. Never introduce yourself as
Richard or claim to be a person.

Help with requests directly. Be honest about your capabilities and never claim you performed an action unless you did.
For consequential actions, such as deleting important data or sending
something externally, explain what will happen and ask for confirmation.
"""

FULL_SYSTEM_PROMPT = f"""You are NICO, the personal AI assistant of Richard Otieno Obiero.
Richard created you. Address him as Sir Richard.

{OWNER_PROFILE}

Be loyal, dependable, respectful, and conversational. Keep simple answers
brief and give more detail when useful. Remember the profile and earlier
conversation accurately; do not invent personal facts. Never say "I am
Richard Otieno" or pretend to be human.

Carry out requests directly. Be clear about your capabilities
and do not claim an action happened unless it did. For consequential actions,
explain the effect and ask for confirmation."""

# =========================================================
# NICO STATES
# =========================================================

VALID_STATES = (
    "STANDBY",
    "LISTENING",
    "PROCESSING",
    "RESPONDING",
    "SYSTEM ERROR",
)

STATE_COLORS = {
    "STANDBY": CYAN,
    "LISTENING": GREEN,
    "PROCESSING": AMBER,
    "RESPONDING": BLUE,
    "SYSTEM ERROR": RED,
}

# =========================================================
# OLLAMA SETTINGS
# =========================================================

SIMPLE_NUM_PREDICT = 80
SIMPLE_HISTORY_LIMIT = 2

COMPLEX_NUM_PREDICT = 220
COMPLEX_HISTORY_LIMIT = 8

TEMPERATURE = 0.6
TOP_P = 0.9
REQUEST_TIMEOUT = (5, 120)

# =========================================================
# PERFORMANCE INTERVALS
# =========================================================

SYSTEM_STATS_INTERVAL = 3000
INTERNET_CHECK_INTERVAL = 60000

# =========================================================
# QUICK RESPONSE GREETINGS
# =========================================================

SIMPLE_GREETINGS = (
    "hello",
    "hi",
    "hey",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "how's it going",
    "what's up",
    "sup",
)

# =========================================================
# INITIALIZE NICO DIRECTORIES
# =========================================================

for directory in (DATA_DIR, KNOWLEDGE_DIR, EXPORTS_DIR, NOTES_DIR):
    directory.mkdir(parents=True, exist_ok=True)
