import os
import sys
import datetime
import telebot
import db
import llm
import charts
import config

# Validate configuration before starting
if not config.validate_config():
    sys.exit(1)

# Initialize database
db.init_db()

# Initialize bot
bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)

# Ensure whitelisted user verification
def is_allowed(message):
    user_id = message.from_user.id
    if user_id not in config.ALLOWED_USER_IDS:
        print(f"Refused message from unauthorized user ID: {user_id}")
        bot.reply_to(
            message, 
            "⚠️ *Access Denied.*\nThis is a private personal assistant. "
            "Your User ID is not in the whitelist.", 
            parse_mode="Markdown"
        )
        return False
    return True

def write_obsidian_note(relative_path, content):
    """
    Writes or appends content to a local Obsidian note.
    - relative_path: path relative to OBSIDIAN_VAULT_PATH, e.g. "Personal/Diary/18-June"
    - content: text content of the note
    
    Returns:
        tuple (success, message)
    """
    import os
    
    vault_path = config.OBSIDIAN_VAULT_PATH
    if not vault_path:
        return False, "Obsidian vault path is not configured."
        
    # Unquote URL characters (e.g. %20 -> space) and standardize path
    import urllib.parse
    relative_path = urllib.parse.unquote(relative_path).lstrip('/')
    
    # Path traversal protection: resolve target path and check it stays inside vault
    target_path = os.path.abspath(os.path.join(vault_path, relative_path))
    vault_abs_path = os.path.abspath(vault_path)
    
    # Check if target_path starts with vault_abs_path to prevent writing to other locations
    if not target_path.startswith(vault_abs_path):
        return False, "Access denied: Target path must remain inside your Obsidian vault."
        
    # Append .md extension if missing
    if not target_path.lower().endswith(".md"):
        target_path += ".md"
        
    # Ensure directory exists
    dir_name = os.path.dirname(target_path)
    os.makedirs(dir_name, exist_ok=True)
    
    try:
        now_str = datetime.datetime.now().strftime("%H:%M")
        if os.path.exists(target_path):
            # Append to file
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n### Logged at {now_str}\n{content}\n")
            return True, f"Appended to existing note '{relative_path}'"
        else:
            # Create new file
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(f"# {os.path.basename(target_path)[:-3]}\n\n### Logged at {now_str}\n{content}\n")
            return True, f"Created new note '{relative_path}'"
    except Exception as e:
        return False, f"Error writing to note file: {e}"

def execute_db_action(user_id, action):
    """Executes the action dictionary on the DB or filesystem and returns confirmation text."""
    act_type = action.get("action")
    act_val = action.get("value")
    
    if act_type == "log_sleep":
        try:
            hours = float(act_val)
            if db.log_sleep(user_id, hours):
                return f"\n\n📊 *[Logged {hours} hours of sleep for today]*"
        except (ValueError, TypeError):
            pass
    elif act_type == "log_habit":
        habit_name = str(act_val).strip()
        # Case insensitive matching of habit name to whitelisted ones
        habits = db.get_habits(user_id)
        matched_habit = None
        for h in habits:
            if h.lower() == habit_name.lower():
                matched_habit = h
                break
                
        if matched_habit:
            if db.log_habit(user_id, matched_habit):
                return f"\n\n✅ *[Logged completion of habit '{matched_habit}']* "
            else:
                return f"\n\nℹ️ *[Habit '{matched_habit}' was already logged for today]*"
        else:
            return f"\n\n⚠️ *[Failed to log habit '{habit_name}': Habit not found in your list. Add it first with /addhabit]*"
            
    elif act_type == "create_note":
        path = action.get("path")
        content = action.get("content")
        if path and content:
            success, msg = write_obsidian_note(path, content)
            if success:
                return f"\n\n📝 *[{msg}]*"
            else:
                return f"\n\n⚠️ *[Failed to save note: {msg}]*"
            
    return ""

def make_habits_keyboard(user_id):
    """Generates an inline keyboard listing habits with checkmarks for logged items."""
    habits = db.get_habits(user_id)
    completed_today = set(db.get_habit_logs_for_date(user_id))
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    if not habits:
        return None
        
    for habit in habits:
        is_done = habit in completed_today
        prefix = "✅ " if is_done else "⬜️ "
        callback_data = f"toggle_habit:{habit}"
        markup.add(telebot.types.InlineKeyboardButton(f"{prefix}{habit}", callback_data=callback_data))
    return markup

# --- Command Handlers ---

@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    if not is_allowed(message):
        return
    
    welcome_text = (
        "👋 *Welcome to your Personal AI Assistant!*\n\n"
        "I am connected to your local Ollama instance and SQLite database. "
        "I will help you automate replies, track habits, log sleep, save Obsidian notes, and remember our past conversations.\n\n"
        "🚀 *Core Commands:*\n"
        "• `/habits` - View and check off habits for today.\n"
        "• `/addhabit <name>` - Add a new habit to track.\n"
        "• `/deletehabit <name>` - Remove a habit.\n"
        "• `/sleep <hours>` - Log your sleep hours (e.g. `/sleep 7.5`).\n"
        "• `/note <path> <content>` - Write/append a note to Obsidian (e.g. `/note Personal/Diary/18-June Wrote ML entry`).\n"
        "• `/stats` - Generate and receive charts comparing this month to last month.\n"
        "• `/clearhistory` - Clear conversation history locally.\n"
        "• `/help` - Show this help menu.\n\n"
        "🧠 *Natural Language Features:*\n"
        "You can chat with me naturally! I will remember our conversations. "
        "If you mention sleep, habits, or wanting to write an Obsidian note, I'll log them automatically. Examples:\n"
        "• _\"I slept 8 hours last night\"_\n"
        "• _\"Gym done!\"_\n"
        "• _\"file university/ML/ create note studied regression today\"_\n\n"
        "📸 *Photos:*\n"
        "Send me a photo! If a vision model (like `llama3.2-vision`) is active, I'll analyze it."
    )
    
    try:
        bot.reply_to(message, welcome_text, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['addhabit'])
def handle_addhabit(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: `/addhabit <habit_name>`", parse_mode="Markdown")
        return
        
    habit_name = parts[1].strip()
    if db.add_habit(user_id, habit_name):
        bot.reply_to(message, f"✅ Added habit *{habit_name}* to your whitelist.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Habit *{habit_name}* already exists or is invalid.", parse_mode="Markdown")

@bot.message_handler(commands=['deletehabit'])
def handle_deletehabit(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: `/deletehabit <habit_name>`", parse_mode="Markdown")
        return
        
    habit_name = parts[1].strip()
    if db.delete_habit(user_id, habit_name):
        bot.reply_to(message, f"✅ Deleted habit *{habit_name}* and all its history.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Habit *{habit_name}* not found.", parse_mode="Markdown")

@bot.message_handler(commands=['habits'])
def handle_habits(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    
    markup = make_habits_keyboard(user_id)
    if markup:
        bot.reply_to(message, "🎯 *Your Habits for Today:*\nClick to toggle completion:", reply_markup=markup, parse_mode="Markdown")
    else:
        bot.reply_to(message, "ℹ️ You have no habits configured yet. Add one using `/addhabit <name>`.", parse_mode="Markdown")

@bot.message_handler(commands=['sleep'])
def handle_sleep(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: `/sleep <hours>` (e.g. `/sleep 7.5`)", parse_mode="Markdown")
        return
        
    try:
        hours = float(parts[1].strip())
        if db.log_sleep(user_id, hours):
            bot.reply_to(message, f"📊 Logged *{hours}* hours of sleep for today.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Invalid sleep hours. Please enter a number between 0 and 24.")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number format. Use e.g. `/sleep 8` or `/sleep 7.5`.")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    bot.send_chat_action(chat_id, 'upload_photo')
    
    output_path = "stats.png"
    try:
        charts.generate_stats_chart(user_id, output_path)
        
        habits = db.get_habits(user_id)
        
        # Calculate summary statistics
        (this_start, this_end, today, last_start, last_end, *_ ) = charts.get_month_ranges()
        
        sleep_this = db.get_sleep_stats(user_id, this_start.isoformat(), this_end.isoformat())
        sleep_last = db.get_sleep_stats(user_id, last_start.isoformat(), last_end.isoformat())
        
        valid_sleep_this = [v for v in sleep_this.values() if v is not None]
        valid_sleep_last = [v for v in sleep_last.values() if v is not None]
        
        avg_this = sum(valid_sleep_this) / len(valid_sleep_this) if valid_sleep_this else 0
        avg_last = sum(valid_sleep_last) / len(valid_sleep_last) if valid_sleep_last else 0
        
        caption = (
            "📈 *Monthly Progress Dashboard*\n\n"
            f"💤 *Average Sleep:*\n"
            f"• This Month: *{avg_this:.1f}h/night* ({len(valid_sleep_this)} entries)\n"
            f"• Last Month: *{avg_last:.1f}h/night* ({len(valid_sleep_last)} entries)\n\n"
            f"✅ *Active Habits:* {len(habits)}"
        )
        
        with open(output_path, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=caption, parse_mode="Markdown")
            
        # Cleanup
        if os.path.exists(output_path):
            os.remove(output_path)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to generate stats: {e}")

@bot.message_handler(commands=['clearhistory'])
def handle_clearhistory(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    db.clear_chat_history(user_id)
    bot.reply_to(message, "🧹 Local conversation memory has been cleared.")

@bot.message_handler(commands=['note'])
def handle_note(message):
    if not is_allowed(message):
        return
    user_id = message.from_user.id
    
    # Split: /note, path, content
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ Usage: `/note <relative_path> <content>`\nExample: `/note Personal/Diary/18-June studied reinforcement learning`", parse_mode="Markdown")
        return
        
    path = parts[1].strip()
    content = parts[2].strip()
    
    success, msg = write_obsidian_note(path, content)
    if success:
        bot.reply_to(message, f"📝 *[{msg}]*", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ *[Failed to save note: {msg}]*", parse_mode="Markdown")

# --- Callback Query Handler for Habit Buttons ---

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_habit:"))
def handle_habit_toggle(call):
    user_id = call.from_user.id
    if user_id not in config.ALLOWED_USER_IDS:
        bot.answer_callback_query(call.id, "Access Denied.")
        return
        
    habit_name = call.data.split(":", 1)[1]
    completed_today = db.get_habit_logs_for_date(user_id)
    
    if habit_name in completed_today:
        db.unlog_habit(user_id, habit_name)
        bot.answer_callback_query(call.id, f"Removed completion for {habit_name}")
    else:
        db.log_habit(user_id, habit_name)
        bot.answer_callback_query(call.id, f"Logged {habit_name} as completed!")
        
    # Refresh keyboard
    try:
        markup = make_habits_keyboard(user_id)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        print(f"Error editing keyboard: {e}")

# --- Message Handling ---

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_allowed(message):
        return
        
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        # Create photos dir
        os.makedirs("photos", exist_ok=True)
        
        # Download the highest resolution photo
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"photos/{timestamp}_{file_info.file_path.split('/')[-1]}"
        with open(filename, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        caption = message.caption if message.caption else "Describe this image."
        
        # Check if they have a vision model configured
        if config.OLLAMA_MODEL == "llama3.1:latest" and config.OLLAMA_VISION_MODEL == "llama3.2-vision:latest":
            # Show fallback message because llama3.1 cannot see images
            warning_msg = (
                f"📸 *Photo saved locally* to `{filename}`.\n\n"
                f"⚠️ *Vision Model Required*: Since you are currently using `{config.OLLAMA_MODEL}` (text-only), "
                f"I cannot analyze this image directly.\n\n"
                f"To enable photo analysis:\n"
                f"1. Run `ollama pull llama3.2-vision:latest` in your terminal.\n"
                f"2. Ensure your `.env` lists `OLLAMA_MODEL=llama3.2-vision:latest` (or sets OLLAMA_VISION_MODEL appropriately).\n"
                f"3. Restart the bot."
            )
            bot.reply_to(message, warning_msg, parse_mode="Markdown")
            
            # Save a placeholder text to DB so conversation history tracks the upload
            db.save_chat_message(user_id, "user", f"[Uploaded Photo: {filename}]")
            db.save_chat_message(user_id, "assistant", "Photo received and saved locally, but image analysis is disabled (requires vision model).")
            return
            
        # If a vision model is available, query LLM
        reply, action = llm.query_llm(user_id, caption, image_path=filename)
        
        db.save_chat_message(user_id, "user", f"[Sent Photo with caption: {caption}]")
        db.save_chat_message(user_id, "assistant", reply)
        
        action_suffix = ""
        if action:
            action_suffix = execute_db_action(user_id, action)
            import json
            action_json = json.dumps(action, indent=2, ensure_ascii=False)
            action_suffix += f"\n\n⚙️ *[Action Block]*:\n```json\n{action_json}\n```"
            
        try:
            bot.reply_to(message, reply + action_suffix, parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, reply + action_suffix)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process photo: {e}")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if not is_allowed(message):
        return
        
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    # Send typing indicator
    bot.send_chat_action(chat_id, 'typing')
    
    # Query the Ollama client (resolves history context without duplicates)
    reply_text, action = llm.query_llm(user_id, text)
    
    # Save user and assistant messages to database
    db.save_chat_message(user_id, "user", text)
    db.save_chat_message(user_id, "assistant", reply_text)
    
    # Execute database logging triggers
    action_suffix = ""
    if action:
        action_suffix = execute_db_action(user_id, action)
        import json
        action_json = json.dumps(action, indent=2, ensure_ascii=False)
        action_suffix += f"\n\n⚙️ *[Action Block]*:\n```json\n{action_json}\n```"
        
    # Send response back
    try:
        bot.reply_to(message, reply_text + action_suffix, parse_mode="Markdown")
    except Exception:
        # Fallback to plain text if markdown format causes syntax error
        bot.reply_to(message, reply_text + action_suffix)

# --- Start Bot ---
if __name__ == "__main__":
    print("--------------------------------------------------")
    print("🤖 Personal AI Telegram Assistant is starting...")
    print(f"Ollama Active Model: {config.OLLAMA_MODEL}")
    print(f"Ollama Vision Model: {config.OLLAMA_VISION_MODEL}")
    print(f"Database Path: {config.DATABASE_PATH}")
    print(f"Allowed User IDs: {list(config.ALLOWED_USER_IDS)}")
    print("Listening for messages... Press Ctrl+C to stop.")
    print("--------------------------------------------------")
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\nStopping bot...")
        sys.exit(0)
