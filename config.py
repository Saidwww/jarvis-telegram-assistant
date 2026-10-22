import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS_RAW = os.getenv("ALLOWED_USER_IDS", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:latest")
DATABASE_PATH = os.getenv("DATABASE_PATH", "assistant.db")
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")

# Parse allowed user IDs to a set of integers
ALLOWED_USER_IDS = set()
if ALLOWED_USER_IDS_RAW:
    for uid in ALLOWED_USER_IDS_RAW.split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.add(int(uid))

def validate_config():
    """Validates configuration and prints helpful errors if config is missing."""
    errors = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        errors.append("- TELEGRAM_BOT_TOKEN is missing or is set to the default placeholder.")
    if not ALLOWED_USER_IDS:
        errors.append("- ALLOWED_USER_IDS is empty. You must specify your Telegram User ID to secure the bot.")
    
    if OBSIDIAN_VAULT_PATH and not os.path.isdir(OBSIDIAN_VAULT_PATH):
        print(f"⚠️ Warning: OBSIDIAN_VAULT_PATH directory does not exist: {OBSIDIAN_VAULT_PATH}")
        print("Please check your .env file or create the folder to avoid errors when saving notes.")
        
    if errors:
        print("Configuration Error:")
        for error in errors:
            print(error)
        print("\nPlease update your .env file with your correct credentials and run again.")
        return False
    return True
