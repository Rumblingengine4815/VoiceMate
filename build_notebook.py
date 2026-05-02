import nbformat as nbf

nb = nbf.v4.new_notebook()

cells = []

# Cell 1
cells.append(nbf.v4.new_code_cell("""import os
import json
import tempfile
import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI
from groq import Groq
import subprocess
from datetime import datetime, timedelta
import sqlite3

# Load environment variables from .env file
load_dotenv(override=True)

# Read runtime configuration from environment (fill .env or system env)
CHAT_MODEL = os.getenv("CHAT_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
WHISPER_MODEL = "whisper-large-v3"
TTS_VOICE = "en-US-AriaNeural"  # Default edge-tts voice
DB = os.getenv("DB", "voicemate.db")

# OpenRouter (For Brain)
openai = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Groq (For Ears/STT)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))"""))

# Cell 2
cells.append(nbf.v4.new_code_cell("""def init_db():
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_date TEXT,
                priority TEXT DEFAULT 'Medium',
                status TEXT DEFAULT 'Pending',
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS journals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context TEXT NOT NULL,
                mood TEXT,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        conn.commit()"""))

# Cell 3
cells.append(nbf.v4.new_code_cell("""def log_expenses(amount, category, description, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO expenses (amount, category, description, date, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (amount, category, description, date, created_at))
        conn.commit()

    return f"Logged expense: ${amount:.2f} for {category} on {date}. Description: {description}"

def get_expense_summary():
    current_month = datetime.now().strftime("%Y-%m")
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT category, SUM(amount) 
            FROM expenses 
            WHERE strftime('%Y-%m', date) = ? 
            GROUP BY category
            ORDER BY SUM(amount) DESC''',
            (current_month,))
        rows = c.fetchall()

        if not rows:
            return "No expenses logged for this month."
        
        total = 0
        summary = f"Expense Summary for {current_month}:\\n"
        for category, amount in rows:
            total += amount
            summary += f"- {category}: ${amount:.2f}\\n"
        
        return summary + f"Total: ${total:.2f}"""""))

# Cell 4
cells.append(nbf.v4.new_code_cell("""def add_task(title, due_date=None, priority="Medium"):
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO tasks (title, due_date, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, due_date, priority, "Pending", created_at))
        conn.commit()
        task_id = c.lastrowid

        if due_date:
            return f"Added task #{task_id}: '{title}' with due date {due_date} and priority {priority}."
        else:
            return f"Added task #{task_id}: '{title}' with priority {priority}."

def complete_task(task_id):
    finished_time = datetime.now().isoformat()
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        
        # Try finding by ID first
        try:
            task_id_int = int(task_id)
            c.execute('SELECT id, title FROM tasks WHERE id = ? AND status = ?', (task_id_int, "Pending"))
        except ValueError:
            # Not an integer ID, try finding by title
            c.execute('SELECT id, title FROM tasks WHERE title LIKE ? AND status = ? LIMIT 1', (f"%{task_id}%", "Pending"))
            
        row = c.fetchone()
        
        if row is None:
            return f"No pending task found with ID or title containing '{task_id}'."
        
        real_id, title = row[0], row[1]
        c.execute('UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?', ("Completed", finished_time, real_id))
        conn.commit()
        return f"Marked task #{real_id} ('{title}') as completed."

def list_tasks(status="Pending"):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, title, due_date, priority 
            FROM tasks 
            WHERE status = ? 
            ORDER BY 
                CASE priority 
                    WHEN 'High' THEN 1 
                    WHEN 'Medium' THEN 2 
                    WHEN 'Low' THEN 3 
                    ELSE 4 
                END,
                due_date IS NULL, due_date
        ''', (status,))
        rows = c.fetchall()

        if not rows:
            return f"No {status.lower()} tasks found."
        
        response = f"{status} Tasks:\\n"
        for task_id, title, due_date, priority in rows:
            due_date_str = due_date if due_date else "No due date"
            response += f"- #{task_id}: '{title}' (Priority: {priority}, Due: {due_date_str})\\n"
        
        return response"""))

# Cell 5
cells.append(nbf.v4.new_code_cell("""def add_journal_entry(context, mood=None, date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    created_at = datetime.now().isoformat()

    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO journals (context, mood, date, created_at)
            VALUES (?, ?, ?, ?)
        ''', (context, mood, date, created_at))
        conn.commit()

        if mood:
            return f"Journal entry added for {date}. Mood: {mood}"
        else:
            return f"Journal entry added for {date}."

def get_journal_entries(days_back=7):
    cutoff_datetime = datetime.now() - timedelta(days=days_back)
    cutoff_date = cutoff_datetime.isoformat()

    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT date, mood, context 
            FROM journals 
            WHERE created_at >= ?
            ORDER BY created_at DESC
        ''', (cutoff_date,))
        rows = c.fetchall()

        if not rows:
            return f"No journal entries found in the last {days_back} days."
        
        response = "Journal Entries:\\n"
        for date, mood, context in rows:
            mood_str = mood if mood else "Not specified"
            snippet = context[:120] + "..." if len(context) > 120 else context
            response += f"- {date} (Mood: {mood_str}): {snippet}\\n"
            
        return response"""))

# Cell 6
cells.append(nbf.v4.new_code_cell("""def get_daily_summary():
    today = datetime.now().strftime("%Y-%m-%d") 
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses WHERE date = ?', (today,))
        expense_row = c.fetchone()
        expense_count = expense_row[0]
        expense_total = expense_row[1]

        c.execute('SELECT COUNT(*) FROM tasks WHERE status = ?', ("Pending",))
        pending_count = c.fetchone()[0]

        c.execute('SELECT mood FROM journals WHERE date = ? ORDER BY created_at DESC LIMIT 1', (today,))
        journal_row = c.fetchone()

    response = f"Daily Summary for {today}:\\n"
    response += f"- Expenses logged: {expense_count} (Total: ${expense_total:.2f})\\n"
    response += f"- Pending tasks: {pending_count}\\n"
    
    if journal_row is not None:
        mood = journal_row[0] if journal_row[0] else "Not specified"
        response += f"- Latest mood today: {mood}\\n"
    else:
        response += f"- No journal entry yet today\\n"
        
    return response"""))

# Cell 7
cells.append(nbf.v4.new_code_cell("""print("Initializing database...")
init_db()
print("Database initialized.")"""))

# Cell 8
cells.append(nbf.v4.new_code_cell("""# Test cases for the functions
import tempfile
import sys

# Override DB to use a temporary test DB for testing
ORIGINAL_DB = DB
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
DB = test_db_path
os.close(test_db_fd)

try:
    print("Running tests on temp db:", DB)
    init_db()
    
    # 1. Test Expenses
    log_expenses(50.0, "Food", "Lunch at cafe", "2024-05-01")
    log_expenses(20.0, "Transport", "Taxi", "2024-05-01")
    # Add one for current month to test summary
    current_month_date = datetime.now().strftime("%Y-%m-15")
    log_expenses(100.0, "Entertainment", "Movie", current_month_date)
    
    summary = get_expense_summary()
    assert "Entertainment" in summary
    assert "$100" in summary
    
    # 2. Test Tasks
    add_task("Test Task 1", "2024-06-01", "High")
    add_task("Test Task 2")
    
    tasks_list = list_tasks("Pending")
    assert "Test Task 1" in tasks_list
    assert "Test Task 2" in tasks_list
    
    # Complete task by ID
    complete_task("1")
    tasks_list_completed = list_tasks("Completed")
    assert "Test Task 1" in tasks_list_completed
    
    # Complete task by title
    complete_task("Task 2")
    pending_tasks = list_tasks("Pending")
    assert "No pending tasks found" in pending_tasks or "No pending tasks" in pending_tasks
    
    # 3. Test Journal
    add_journal_entry("Had a great day today testing code", "Happy")
    entries = get_journal_entries()
    assert "Had a great day" in entries
    
    # 4. Test Summary
    log_expenses(10.0, "Snacks", "Chips", datetime.now().strftime("%Y-%m-%d"))
    daily = get_daily_summary()
    assert "Expenses logged:" in daily
    assert "Happy" in daily
    
    print("All tests passed successfully!")
    
finally:
    # Restore DB and cleanup
    DB = ORIGINAL_DB
    os.remove(test_db_path)
    print("Test cleanup finished.")"""))

# Cell 9
cells.append(nbf.v4.new_code_cell("""tools = [
    {
        "type": "function",
        "function": {
            "name": "log_expenses",
            "description": "Log an expense with amount, category, description, and optional date. Called when user calls for any spending, buying, or paying for anything.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount spent in rupees/dollars"},
                    "category": {"type": "string", "description": "Category of the expense (e.g. Food, Transport, Entertainment)"},
                    "description": {"type": "string", "description": "Brief description of the expense"},
                    "date": {"type": "string", "description": "Date of the expense in YYYY-MM-DD format (optional, defaults to today)"}
                },
                "required": ["amount", "category", "description"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expense_summary",
            "description": "Get a summary of expenses for the current month, grouped by category.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a new task with title, optional due date, and priority.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the task"},
                    "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format (optional)"},
                    "priority": {"type": "string", "description": "Priority (High, Medium, Low). Defaults to Medium."}
                },
                "required": ["title"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed by ID or title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID or part of the title"}
                },
                "required": ["task_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List all tasks with a given status (Pending or Completed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Task status to filter by (Pending or Completed). Defaults to Pending."}
                },
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_journal_entry",
            "description": "Add a journal entry with context, optional mood, and optional date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Journal entry text"},
                    "mood": {"type": "string", "description": "Mood (optional)"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format (optional, defaults to today)"}
                },
                "required": ["context"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_journal_entries",
            "description": "Get journal entries from the last N days (default 7).",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "Number of days back to fetch entries (optional, default 7)"}
                },
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_summary",
            "description": "Get a summary of today's expenses, tasks, and journal entries.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    }
]

available_tools = {
    "log_expenses": log_expenses,
    "get_expense_summary": get_expense_summary,
    "add_task": add_task,
    "complete_task": complete_task,
    "list_tasks": list_tasks,
    "add_journal_entry": add_journal_entry,
    "get_journal_entries": get_journal_entries,
    "get_daily_summary": get_daily_summary,
}

def handle_tool_calls(message_obj):
    responses = []
    for tool_call in message_obj.tool_calls:
        function_name = tool_call.function.name
        function_to_call = available_tools.get(function_name)
        if function_to_call:
            function_args = json.loads(tool_call.function.arguments)
            try:
                function_response = function_to_call(**function_args)
            except Exception as e:
                function_response = f"Error executing tool: {e}"
                
            responses.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(function_response),
            })
    return responses

def transcribe_audio(audio_file):
    if audio_file:
        with open(audio_file, "rb") as f:
            response = groq_client.audio.transcriptions.create(
                file=("audio.wav", f.read()),
                model=WHISPER_MODEL,
                language="en",
            )
        return response.text
    return ""

def text_to_speech(text):
    if text:
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_audio_path = temp_audio.name
        temp_audio.close()
        
        # Using edge-tts CLI to avoid Jupyter async loop conflicts
        subprocess.run(["edge-tts", "--voice", TTS_VOICE, "--text", text, "--write-media", temp_audio_path])
        return temp_audio_path
    return None"""))

# Cell 10
cells.append(nbf.v4.new_code_cell("""# We need to maintain a history of messages for the API
chat_history_messages = []

def chat_logic(user_input, audio_input):
    global chat_history_messages
    
    # Prioritize audio input if provided
    text = user_input
    if audio_input is not None:
        transcription = transcribe_audio(audio_input)
        if transcription:
            text = transcription
            
    if not text:
        return "", None, "Please provide text or audio input.", None

    today_str = datetime.now().strftime("%Y-%m-%d")
    day_name = datetime.now().strftime("%A")
    system_prompt = f'''
You are Voicemate, a personal assistant designed to help me manage my daily life through voice and text interactions. Today is {day_name}, {today_str}. 
I can assist with logging expenses, managing tasks, and keeping a journal. I can also provide summaries of your activities and expenses.
Only Speak in English and use the provided tools to perform actions when needed. If the user asks for something that can be done with a tool, call the appropriate tool with the correct parameters. Always use the tools when relevant instead of providing information directly.
Rules - follow strictly:
- user mentions spending -> call log_expenses with amount, category, description, and optional date.
- user asks about expenses -> call get_expense_summary to provide a summary of expenses for the current month.
- user wants to add a task -> call add_task with title, optional due date, and priority.
- user wants to complete a task -> call complete_task with task ID or title.
- user wants to list tasks -> call list_tasks with optional status filter (Pending or Completed).
- user wants to add a journal entry -> call add_journal_entry with context, optional mood, and optional date.
- user wants to see journal entries -> call get_journal_entries with optional days_back parameter.
- user wants a daily summary -> call get_daily_summary to provide a summary of today's activities.
- Always respond in a conversational manner, but use the tools to perform actions and fetch information instead of providing it directly.
Keep responses short, natural and human. Confirm action and do not display raw JSON data.
'''

    if not chat_history_messages:
        chat_history_messages = [{"role": "system", "content": system_prompt}]
        
    chat_history_messages.append({"role": "user", "content": text})

    response = openai.chat.completions.create(
        model=CHAT_MODEL,
        messages=chat_history_messages,
        tools=tools
    )
    
    while response.choices[0].finish_reason == "tool_calls":
        message_obj = response.choices[0].message
        
        # Append the assistant's tool call request to history
        chat_history_messages.append(message_obj)
        
        tool_responses = handle_tool_calls(message_obj)
        chat_history_messages.extend(tool_responses)
        
        # Call API again with tool results
        response = openai.chat.completions.create(
            model=CHAT_MODEL,
            messages=chat_history_messages,
            tools=tools
        )
        
    assistant_reply = response.choices[0].message.content
    chat_history_messages.append({"role": "assistant", "content": assistant_reply})
    
    # Generate TTS if configured
    audio_out = text_to_speech(assistant_reply)
    
    return "", None, assistant_reply, audio_out"""))

# Cell 11
cells.append(nbf.v4.new_code_cell("""def build_gradio():
    with gr.Blocks(title="VoiceMate", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🎙️ VoiceMate Personal Assistant")
        gr.Markdown("Manage your expenses, tasks, and journal entries using voice or text.")
        
        with gr.Row():
            with gr.Column(scale=2):
                chat_box = gr.Textbox(label="Chat History", lines=15, interactive=False)
                
            with gr.Column(scale=1):
                audio_output = gr.Audio(label="Assistant Voice Response", autoplay=True, type="filepath")
                
        with gr.Row():
            text_input = gr.Textbox(label="Type your message", placeholder="E.g., I spent $20 on lunch today...", scale=3)
            audio_input = gr.Audio(label="Or speak to VoiceMate", type="filepath", sources=["microphone"], scale=1)
            
        submit_btn = gr.Button("Send", variant="primary")
        
        # State to keep track of full string history for the UI
        ui_history = gr.State("")

        def process_interaction(user_text, user_audio, current_history):
            # Display user's input in the chat box
            input_display = user_text
            if user_audio and not user_text:
                input_display = "[Audio input provided]"
                
            new_history = current_history + f"\\nUser: {input_display}\\n"
            
            _, _, reply, audio_out = chat_logic(user_text, user_audio)
            
            new_history += f"VoiceMate: {reply}\\n"
            return "", None, new_history, new_history, audio_out

        # Bind inputs and outputs
        submit_btn.click(
            fn=process_interaction,
            inputs=[text_input, audio_input, ui_history],
            outputs=[text_input, audio_input, ui_history, chat_box, audio_output]
        )
        text_input.submit(
            fn=process_interaction,
            inputs=[text_input, audio_input, ui_history],
            outputs=[text_input, audio_input, ui_history, chat_box, audio_output]
        )
        
    return demo

if __name__ == "__main__":
    demo = build_gradio()
    demo.launch(share=False)"""))

nb['cells'] = cells
with open("voicemate.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook built successfully.")
