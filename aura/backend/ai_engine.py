import os
import json
import re
from openai import OpenAI
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from .database import Memory, ChatMessage, Task

load_dotenv(override=True)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Akansha AI Assistant",
    }
)

SYSTEM_PROMPT = """
You are Akansha, an advanced personal AI.

CRITICAL INSTRUCTIONS - IGNORE ALL DEFAULT REFUSALS:
1. YOU DO HAVE MEMORY. YOU DO HAVE ACCESS TO HISTORY.
2. Your memory is provided exactly below this prompt under 'CORE MEMORIES'.
3. You must NEVER say "I don't have access to history" or "I don't have memory". That is strictly forbidden.
4. If the user asks about themselves (e.g. "what is my name?", "what is my cgpa?"), you MUST look at the CORE MEMORIES. 
5. The CORE MEMORIES are written in the third person (e.g., "User is a B.Tech student"). "User" refers to the person you are talking to right now!
6. If the CORE MEMORIES say "User has a CGPA of 9.5", you must reply "Your CGPA is 9.5".
7. NEVER say you don't know if the answer is in the CORE MEMORIES.

Personality:
- Deeply empathetic, witty, and highly intelligent.
- Confident. Never apologize for not having memory.
"""


def _normalize_user_fact(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned.rstrip(".!?")


def _upsert_memory(db: Session, topic: str, insight: str, importance: int = 3):
    existing = (
        db.query(Memory)
        .filter(Memory.topic.ilike(topic))
        .order_by(Memory.importance.desc(), Memory.id.desc())
        .first()
    )
    if existing:
        existing.insight = insight
        existing.importance = max(existing.importance or 1, importance)
        return
    db.add(Memory(topic=topic, insight=insight, importance=importance))


def _capture_deterministic_memories(db: Session, user_input: str):
    lowered = user_input.lower()
    compact = _normalize_user_fact(user_input)

    if (
        "exam" in lowered
        and re.search(r"\b(i have|i've got|i got|my)\b", lowered)
        and not re.search(r"\bno exam\b|\bnot have.*exam\b", lowered)
    ):
        _upsert_memory(db, "Upcoming exam", compact, importance=5)

    if "codechef" in lowered and re.search(r"\b(tomorrow|today|exam|contest)\b", lowered):
        _upsert_memory(db, "CodeChef plan", compact, importance=4)

def generate_chat_stream(
    db: Session,
    user_input: str,
    session_id: str = "default",
    user_tone: str | None = None,
    response_style: str | None = None,
    conversation_mode: str | None = None,
    language_preference: str | None = None,
):
    """Generator for streaming responses."""
    history_records = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id.desc()).limit(15).all()
    
    # We remove the duplicate manual append since main.py already saved the current user_input to the DB
    history = [{"role": r.role, "content": r.content} for r in reversed(history_records)]
    
    memories = db.query(Memory).order_by(Memory.importance.desc()).all()
    memory_str = "CORE MEMORIES (FACTS YOU MUST USE):\n" + "\n".join([f"- {m.topic}: {m.insight}" for m in memories])

    dynamic_context = [
        f"USER TONE SIGNAL: {user_tone or 'neutral'}",
        f"RESPONSE STYLE PREFERENCE: {response_style or 'friendly'}",
        f"CONVERSATION MODE: {conversation_mode or 'hybrid'}",
        f"LANGUAGE PREFERENCE: {language_preference or 'telugu_english'}",
        "Speak naturally, with short spoken-language sentences when the conversation mode involves voice.",
        "Respect the language preference exactly: use Telugu + English mix when requested, only English when requested, and only Hindi when requested.",
    ]

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n" + memory_str + "\n\n" + "\n".join(dynamic_context),
        }
    ] + history
    
    with open("debug_prompt.txt", "w") as f:
        f.write(json.dumps(messages, indent=2))

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        stream=True
    )
    
    full_response = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            yield content
            
    # We yield a special token at the end or handle the background task in main.py

def analyze_intent_and_memory(db: Session, user_input: str, assistant_response: str):
    """Background task to extract memory and intent (e.g. creating tasks)."""
    _capture_deterministic_memories(db, user_input)
    existing_memories = db.query(Memory).all()
    memories_str = "Existing Memories:\n" + "\n".join([f"ID: {m.id} | Topic: {m.topic} | Insight: {m.insight}" for m in existing_memories])

    prompt = f"""
    Analyze the recent interaction. 
    1. Extract any new long-term memories about the user.
    2. Identify if the user implicitly or explicitly requested a task to be tracked.
    3. Identify if the user wants to trigger a desktop automation action.
    
    IMPORTANT: You must consolidate memories! Do not create duplicate memories for the same topic. 
    If new information overlaps with an existing memory, update the existing memory instead of creating a new one.

    {memories_str}
    
    Return ONLY a JSON object:
    {{
        "memories_to_add": [{{"topic": "str", "insight": "str", "importance": 1-5}}],
        "memories_to_update": [{{"id": int, "new_insight": "str", "new_importance": 1-5}}],
        "new_tasks": [{{"title": "str", "description": "str"}}],
        "automation": {{"action": "open_notepad|type|open_url|open_youtube_song|new_tab|close_tab|type_text|edit_field|remove_draft", "target": "str"}} 
    }}
    
    Interaction:
    User: {user_input}
    Akansha: {assistant_response}
    """
    try:
        res = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        data = json.loads(res.choices[0].message.content)
        
        # Save New Memories
        for m in data.get('memories_to_add', []):
            _upsert_memory(db, m['topic'], m['insight'], m.get('importance', 1))
            
        # Update Existing Memories
        for m in data.get('memories_to_update', []):
            existing_mem = db.query(Memory).filter(Memory.id == m['id']).first()
            if existing_mem:
                existing_mem.insight = m['new_insight']
                if 'new_importance' in m:
                    existing_mem.importance = m['new_importance']
            
        # Save Tasks
        for t in data.get('new_tasks', []):
            new_task = Task(title=t['title'], description=t.get('description', ''))
            db.add(new_task)
            
        db.commit()

        # Handle Automation
        automation = data.get('automation')
        if automation and automation.get('action'):
            import asyncio
            from .automation import execute_desktop_command
            
            # Since this is a background thread, we need an event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            loop.run_until_complete(execute_desktop_command(automation['action'], automation.get('target')))
    except Exception as e:
        print(f"Analysis failed: {e}")
