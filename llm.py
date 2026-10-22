import re
import json
import ollama
import db
from config import OLLAMA_MODEL, OLLAMA_VISION_MODEL

def parse_action(response_text):
    """
    Parses the response text to find any action blocks.
    Supports standard markdown blocks, raw json lines, or action prefix json blocks.
    Returns a dict with action details if found, else None.
    """
    # 1. Standard markdown code blocks: ```action {"action": ...} ```
    pattern_md = r"```action\s*(.*?)\s*```"
    match_md = re.search(pattern_md, response_text, re.DOTALL)
    if match_md:
        try:
            return json.loads(match_md.group(1).strip())
        except json.JSONDecodeError:
            pass
            
    # 2. Look for action prefix followed by json: action {"action": ...}
    pattern_pref = r"action\s*(\{.*?\})"
    match_pref = re.search(pattern_pref, response_text, re.DOTALL)
    if match_pref:
        try:
            return json.loads(match_pref.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Look for any standalone json containing '"action"'
    pattern_json = r"(\{.*?\})"
    matches = re.finditer(pattern_json, response_text, re.DOTALL)
    for m in matches:
        chunk = m.group(1).strip()
        if '"action"' in chunk:
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                pass
                
    return None

def clean_response(response_text):
    """Removes the matched action block from the response text to keep chat clean."""
    cleaned = response_text
    
    # Remove standard markdown blocks
    pattern_md = r"```action\s*.*?\s*```"
    cleaned = re.sub(pattern_md, "", cleaned, flags=re.DOTALL)
    
    # Remove action prefix blocks
    pattern_pref = r"action\s*\{.*?\}"
    cleaned = re.sub(pattern_pref, "", cleaned, flags=re.DOTALL)
    
    # Remove stand-alone action json blocks
    pattern_json = r"\{.*?\}"
    matches = list(re.finditer(pattern_json, cleaned, re.DOTALL))
    for m in reversed(matches):
        chunk = m.group(0)
        if '"action"' in chunk:
            try:
                json.loads(chunk)
                cleaned = cleaned[:m.start()] + cleaned[m.end():]
            except json.JSONDecodeError:
                pass
                
    return cleaned.strip()

def query_llm(user_id, user_message, image_path=None):
    """
    Queries the local Ollama LLM with history and context.
    If image_path is provided and a vision model is active, it runs it with vision support.
    
    Returns:
        tuple: (reply_text, action_dict)
    """
    # Fetch active habits to inject into the system prompt
    habits = db.get_habits(user_id)
    habits_str = ", ".join([f'"{h}"' for h in habits]) if habits else "None configured yet. Let the user know they can add habits."
    
    system_prompt = f"""You are a helpful, friendly, and supportive personal assistant. 
Your job is to assist the user with whatever they ask, and to automatically detect when they report sleeping, completing daily habits, or wanting to log thoughts/information in their local Obsidian vault.

Whitelisted active habits: {habits_str}

CRITICAL RULES for Automatic Logging:
1. ONLY trigger logging actions based on the user's CURRENT, most recent message.
2. DO NOT repeat or re-trigger actions that are already recorded in the chat history. If the history shows an action was already performed, ignore it and treat it as past context.
3. Sleep tracking: If the user says how many hours they slept in their current message (e.g. "I slept 7 hours"), log it.
4. Habit tracking: If the user says they completed one of their whitelisted habits in their current message (e.g. "gym done"), log it.
5. Obsidian note logging: If the user wants to write a note, create a file, or log information to their Obsidian vault in their current message (e.g., "file university/ML/ create note studied regression today"), log it.
   - The path must be the relative path inside the vault, excluding the '.md' extension (e.g., 'Personal/Diary/18-June' or 'University/ML/neural-networks').
   - Clean the path to remove leading slashes if the LLM output path starts with a slash, e.g. use 'Personal/Diary/18-June' instead of '/Personal/Diary/18-June'.
   - Extract the actual content that the user wants to save in the note.

Action Block Format:
If you need to log sleep, append this block at the end of your response:
```action
{{"action": "log_sleep", "value": 7.5}}
```
(Replace 7.5 with the actual sleep hours. Value must be a number.)

If you need to log a habit, append this block at the end of your response:
```action
{{"action": "log_habit", "value": "Gym"}}
```
(Replace "Gym" with the exact habit name from the whitelisted active habits.)

If you need to create/update an Obsidian note, append this block at the end of your response:
```action
{{"action": "create_note", "path": "Personal/Diary/18-June", "content": "My notes content here"}}
```
(Replace "Personal/Diary/18-June" with the relative note path and "My notes content here" with the extracted note text.)

If the user is NOT logging sleep, a habit, or an Obsidian note in their current message, DO NOT output any action block. Only include one action block per response.
"""

    # Fetch last 10 messages for context (reduced from 20 to keep context focused)
    history = db.get_chat_history(user_id, limit=10)
    
    # Structure messages for Ollama
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
        
    # Append the new user message
    new_message = {"role": "user", "content": user_message}
    
    # Decide which model to use and attach image if available
    model_to_use = OLLAMA_MODEL
    if image_path:
        # If user uploaded a photo and we want to analyze it, use OLLAMA_VISION_MODEL
        model_to_use = OLLAMA_VISION_MODEL
        new_message["images"] = [image_path]
        
    messages.append(new_message)
    
    try:
        # Query Ollama with low temperature for logical consistency
        response = ollama.chat(
            model=model_to_use, 
            messages=messages,
            options={"temperature": 0.2}
        )
        reply = response["message"]["content"]
        
        # Parse and strip actions
        action = parse_action(reply)
        cleaned_reply = clean_response(reply)
        
        return cleaned_reply, action
    except Exception as e:
        print(f"Error querying Ollama: {e}")
        return f"Error: Could not connect to local Ollama. Please make sure Ollama is running and model '{model_to_use}' is installed.", None
