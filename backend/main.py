from fastapi import FastAPI, HTTPException, Query, Request, Body
from fastapi.responses import RedirectResponse
from typing import Optional
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from supabase import create_client, Client

import psycopg2
import requests
import json
import uuid
import os
from datetime import datetime
import re
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# OAuth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

HUBSPOT_CLIENT_ID = os.environ.get("HUBSPOT_CLIENT_ID")
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")
HUBSPOT_REDIRECT_URI = os.environ.get("HUBSPOT_REDIRECT_URI")
# ---------- Gemini ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent"
GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro:generateContent"


# ---------- PostgreSQL Connection (Vector DB) ----------
# PostgreSQL
PG_HOST = os.environ.get("PG_HOST")
PG_NAME = os.environ.get("PG_NAME")
PG_USER = os.environ.get("PG_USER")
PG_PASSWORD = os.environ.get("PG_PASSWORD")
PG_PORT = os.environ.get("PG_PORT")

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    database=os.getenv("PG_NAME"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    port="5432"
)

cursor = conn.cursor()

scheduler = BackgroundScheduler()
# ---------- Embedding via Gemini ----------
def generate_embedding(text):
    payload = {
        "model": "models/embedding-001",
        "content": {"parts": [{"text": text}]}
    }
    res = requests.post(
        f"{GEMINI_EMBED_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload
    )
    data = res.json()
    if "embedding" in data:
        return data["embedding"]["values"]
    else:
        print("❌ Embedding error:", data)
        return None

# ---------- Example Chat Endpoint ----------
class ChatRequest(BaseModel):
    query: str

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    prompt = {
        "contents": [
            {"parts": [{"text": req.query}], "role": "user"}
        ]
    }
    response = requests.post(
        f"{GEMINI_CHAT_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=prompt
    )
    reply = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    return {"response": reply}

# ---------- Startup ----------
@app.on_event("startup")
def start_scheduler():
    scheduler.start()
    print("✅ Scheduler started")

# ---------- Routes ----------
@app.get("/")
def home():
    return {"message": "✅ Supabase + FastAPI backend running"}

@app.get("/gmail/thread/{thread_id}")
def get_gmail_thread(thread_id: str, token: str = Query(...)):
    response = supabase.table("gmail_threads").select("*").eq("thread_id", thread_id).execute()
    data = response.data
    if not data:
        raise HTTPException(status_code=404, detail="Thread not found")
    return data[0]

@app.get("/gmail/ingest")
def ingest_gmail(token: Optional[str] = Query(None)):
    if not token:
        return {"error": "Missing access_token (provide via ?token=ACCESS_TOKEN)"}

    threads = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/threads",
        headers={"Authorization": f"Bearer {token}"},
        params={"maxResults": 10}
    ).json().get("threads", [])

    inserted = 0
    for t in threads:
        thread_id = t["id"]
        detail = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"}
        ).json()

        headers = detail.get("messages", [])[0].get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
        snippet = detail.get("snippet", "")
        notes = f"Subject: {subject}\nSnippet: {snippet}"
        embedding = serialize_embedding(model.encode(notes))

        try:
            cursor.execute("""
                INSERT INTO gmail_threads (thread_id, subject, snippet, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (thread_id) DO NOTHING
            """, (thread_id, subject, snippet, embedding))
            inserted += 1
        except Exception as e:
            print(f"❌ Gmail insert failed: {e}")
            conn.rollback()

    conn.commit()
    return {"message": f"✅ Ingested {inserted} Gmail threads into Supabase."}

@app.get("/gmail/search")
def search_gmail(query: str = Query(...)):
    q_embedding = model.encode(query).tolist()
    cursor.execute("""
        SELECT thread_id, subject, snippet
        FROM gmail_threads
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding,))
    results = cursor.fetchall()
    return {"results": [
        {"thread_id": r[0], "subject": r[1], "snippet": r[2]} for r in results
    ]}

@app.post("/chat")
def chat_with_gemini(prompt: str = Query(..., min_length=1), email: str = Query("test@example.com")):
    # --- Embed query ---
    q_embedding = model.encode(prompt).tolist()

    # --- Gmail context ---
    cursor.execute("""
        SELECT subject, snippet
        FROM gmail_threads
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding,))
    gmail_matches = cursor.fetchall()
    gmail_context = [f"Subject: {g[0]}\nSnippet: {g[1]}" for g in gmail_matches]

    # --- HubSpot context ---
    cursor.execute("""
        SELECT name, email, notes
        FROM hubspot_contacts
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding,))
    hubspot_matches = cursor.fetchall()
    hubspot_context = [f"Name: {c[0]} ({c[1]})\nNotes: {c[2]}" for c in hubspot_matches]

    # --- Combine all context ---
    full_context = "\n\n".join(gmail_context + hubspot_context)
    full_prompt = f"""You are a helpful financial AI assistant. Use the context below to answer the user query.\n\nContext:\n{full_context}\n\nUser Query: {prompt}"""

    # --- Call Gemini ---
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ]
    }
    response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))

    if response.status_code != 200:
        return {"error": "Gemini API failed", "details": response.json()}

    try:
        message = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        message = "[⚠️ Gemini response parse error]"

    # --- Save chat history ---
    try:
        cursor.execute("""
            INSERT INTO chat_history (user_email, message, reply)
            VALUES (%s, %s, %s)
        """, (email, prompt, message))
        conn.commit()
    except:
        conn.rollback()

    return {"response": message}


# ---------- GOOGLE OAUTH ----------
@app.get("/auth/url")
def get_auth_url():
    return RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        "response_type=code&"
        "scope=https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events&"
        "access_type=offline&prompt=consent"
    )

@app.get("/auth/callback")
def google_auth_callback(code: str):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    token_response = requests.post(token_url, data=data, headers=headers)

    if token_response.status_code != 200:
        return {"error": "Failed to retrieve token", "detail": token_response.text}

    tokens = token_response.json()

    id_token = tokens.get("id_token")
    if not id_token:
        return {"error": "Missing ID token"}

    # Get user profile
    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    if userinfo.status_code != 200:
        return {"error": "Failed to get user info", "detail": userinfo.text}

    profile = userinfo.json()

    return {
        "tokens": tokens,
        "profile": profile
    }

# ---------- HUBSPOT OAUTH ----------
@app.get("/hubspot/auth-url")
def hubspot_auth_url():
    return RedirectResponse(
        "https://app.hubspot.com/oauth/authorize?"
        f"client_id={HUBSPOT_CLIENT_ID}&"
        f"redirect_uri={HUBSPOT_REDIRECT_URI}&"
        "scope=crm.objects.contacts.read crm.objects.contacts.write crm.objects.custom.read crm.objects.custom.write crm.objects.appointments.read crm.objects.appointments.write&"
        "response_type=code"
    )

@app.get("/hubspot/callback")
def hubspot_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return {"error": "Missing code"}

    tokens = requests.post(
        "https://api.hubapi.com/oauth/v1/token",
        data={
            "grant_type": "authorization_code",
            "client_id": HUBSPOT_CLIENT_ID,
            "client_secret": HUBSPOT_CLIENT_SECRET,
            "redirect_uri": HUBSPOT_REDIRECT_URI,
            "code": code
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    ).json()

    contacts = requests.get(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        headers={"Authorization": f"Bearer {tokens['access_token']}"}
    ).json()

    return {"hubspot_tokens": tokens, "hubspot_contacts": contacts}

# ---------- HUBSPOT INGEST ----------
from fastapi import Query

@app.get("/hubspot/ingest")
def ingest_contacts(token: str = Query(...)):
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.get(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        headers=headers
    )

    try:
        res.raise_for_status()
    except Exception as e:
        print(f"❌ HubSpot API call failed: {e}")
        return {"error": f"HubSpot API error: {e}"}

    contacts = res.json().get("results", [])
    print(f"🔍 Fetched {len(contacts)} contacts from HubSpot")
    inserted = 0

    for contact in contacts:
        props = contact.get("properties", {})
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "")
        notes = f"Name: {name}, Email: {email}"

        if not email:
            print(f"⚠️ Skipping contact without email: {props}")
            continue

        embedding = serialize_embedding(model.encode(notes))

        try:
            cursor.execute("""
                INSERT INTO hubspot_contacts (hubspot_id, name, email, notes, embedding)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (hubspot_id) DO NOTHING
            """, (contact["id"], name, email, notes, embedding))
            inserted += 1
        except Exception as e:
            print(f"❌ HubSpot insert failed: {e}")
            conn.rollback()

    conn.commit()
    return {"message": f"✅ Ingested {inserted} contacts into Supabase."}


# ---------- SEARCH ----------
@app.get("/search")
def semantic_search(query: str = Query(...)):
    q_embedding = model.encode(query).tolist()
    cursor.execute("""
        SELECT hubspot_id, name, email, notes
        FROM hubspot_contacts
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding,))
    results = cursor.fetchall()
    return {"results": [
        {"id": r[0], "name": r[1], "email": r[2], "notes": r[3]} for r in results
    ]}

# ---------- GMAIL INGEST ----------
@app.get("/gmail/ingest")
def ingest_gmail(token: Optional[str] = Query(None)):
    if not token:
        return {"error": "Missing access_token (provide via ?token=ACCESS_TOKEN)"}

    threads = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/threads",
        headers={"Authorization": f"Bearer {token}"},
        params={"maxResults": 10}
    ).json().get("threads", [])

    inserted = 0
    for t in threads:
        thread_id = t["id"]
        detail = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"}
        ).json()
        headers = detail.get("messages", [])[0].get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
        snippet = detail.get("snippet", "")
        notes = f"Subject: {subject}\nSnippet: {snippet}"
        embedding = serialize_embedding(model.encode(notes))

        try:
            cursor.execute("""
                INSERT INTO gmail_threads (thread_id, subject, snippet, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (thread_id) DO NOTHING
            """, (thread_id, subject, snippet, embedding))
            inserted += 1
        except Exception as e:
            print(f"❌ Gmail insert failed: {e}")
            conn.rollback()

    conn.commit()
    return {"message": f"✅ Ingested {inserted} Gmail threads into Supabase."}

@app.get("/gmail/search")
def search_gmail(query: str = Query(...)):
    q_embedding = model.encode(query).tolist()
    cursor.execute("""
        SELECT thread_id, subject, snippet
        FROM gmail_threads
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding,))
    results = cursor.fetchall()
    return {"results": [
        {"thread_id": r[0], "subject": r[1], "snippet": r[2]} for r in results
    ]}

# ---------- CALENDAR INGEST ----------

import traceback

@app.get("/calendar/ingest")
def ingest_calendar(token: Optional[str] = Query(None)):
    if not token:
        return {"error": "Missing access_token (provide via ?token=ACCESS_TOKEN)"}
    
    try:
        response = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "maxResults": 10,
                "singleEvents": True,
                "orderBy": "startTime",
                "timeMin": datetime.utcnow().isoformat() + "Z"
            }
        )

        if response.status_code != 200:
            return {"error": f"Failed to fetch events: {response.text}"}

        events = response.json().get("items", [])
        print("📅 Events Fetched:", json.dumps(events, indent=2))  # Debug output

        inserted = 0
        for event in events:
            event_id = event.get("id")
            summary = event.get("summary", "No Title")
            description = event.get("description", "")
            notes = f"Summary: {summary}\nDescription: {description}"
            embedding = serialize_embedding(model.encode(notes))  # ❗ check this line

            cursor.execute("""
                INSERT INTO calendar_events (event_id, summary, description, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
            """, (event_id, summary, description, embedding))
            inserted += 1

        conn.commit()
        return {"message": f"✅ Ingested {inserted} calendar events into Supabase."}

    except Exception as e:
        print("❌ Calendar ingest error:", e)
        traceback.print_exc()
        return {"error": f"Calendar ingest failed: {e}"}



# ---------- CHAT ----------
@app.post("/chat")
def chat_with_gemini(prompt: str = Query(..., min_length=1)):
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        return {"error": "Gemini API call failed", "details": response.json()}

    try:
        message = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        message = "[⚠️ Failed to parse Gemini response]"
    return {"response": message}

# ---------- TASK MEMORY ----------
class TaskInput(BaseModel):
    instruction: str

@app.post("/tasks/store")
def store_task(email: str = Query(...), task: TaskInput = Body(...)):
    try:
        cursor.execute("""
            INSERT INTO user_tasks (id, user_email, instruction)
            VALUES (%s, %s, %s)
        """, (str(uuid.uuid4()), email, task.instruction))
        conn.commit()
        return {"message": "✅ Task stored successfully"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

@app.get("/tasks/list")
def list_tasks(email: str = Query(...)):
    try:
        cursor.execute("""
            SELECT id, instruction, status, created_at
            FROM user_tasks
            WHERE user_email = %s
            ORDER BY created_at DESC
        """, (email,))
        rows = cursor.fetchall()
        return {
            "tasks": [
                {"id": r[0], "instruction": r[1], "status": r[2], "created_at": r[3].isoformat()}
                for r in rows
            ]
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/tasks/mark-done")
def mark_task_done(task_id: str = Query(...)):
    try:
        cursor.execute("""
            UPDATE user_tasks
            SET status = 'done'
            WHERE id = %s
        """, (task_id,))
        conn.commit()
        return {"message": "✅ Task marked as done"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

# ---------- INSTRUCTION MEMORY ----------
@app.post("/instructions/store")
def store_instruction(email: str = Query(...), instruction: str = Body(...)):
    try:
        cursor.execute("""
            INSERT INTO user_instructions (id, user_email, instruction)
            VALUES (%s, %s, %s)
        """, (str(uuid.uuid4()), email, instruction))
        conn.commit()
        return {"message": "✅ Instruction saved"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

# ---------- TOOL-CALLING ----------
def send_email(recipient: str, subject: str, body: str):
    print(f"📧 Email sent to {recipient}: {subject}\n{body}")
    return True

def create_event(title: str, time: str, attendees: list):
    print(f"📅 Event created: {title} at {time} with {attendees}")
    return True

def create_contact(name: str, email: str):
    print(f"👤 Contact created: {name} ({email})")
    return True

TOOL_MAP = {
    "send_email": send_email,
    "create_event": create_event,
    "create_contact": create_contact
}

@app.post("/tools/call")
def call_tool(tool: str = Query(...), args: dict = Body(...)):
    if tool not in TOOL_MAP:
        return {"error": "❌ Unknown tool"}
    try:
        result = TOOL_MAP[tool](**args)
        return {"message": f"✅ Tool '{tool}' executed", "result": result}
    except Exception as e:
        return {"error": str(e)}
    
    #CHECK_ONGOING_INSTRUCTION
def check_ongoing_instructions():
    results = []
    try:
        cursor.execute("SELECT user_email, instruction FROM user_instructions")
        instructions = cursor.fetchall()

        for email, instruction in instructions:
            cursor.execute("""
                SELECT thread_id, subject, snippet
                FROM gmail_threads
                WHERE created_at >= NOW() - INTERVAL '1 hour'
            """)
            threads = cursor.fetchall()

            for thread_id, subject, snippet in threads:
                token = "your_token_here"
                detail = requests.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
                    headers={"Authorization": f"Bearer {token}"}
                ).json()

                messages = detail.get("messages", [])
                if not messages:
                    results.append(f"⚠️ No messages found in thread {thread_id}")
                    continue

                headers = messages[0].get("payload", {}).get("headers", [])
                from_header = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
                import re
                match = re.search(r'(?:"?([^"]*)"?\s)?<?([\w\.-]+@[\w\.-]+)>?', from_header)
                name = match.group(1) or "Unknown"
                sender_email = match.group(2) if match else None

                if not sender_email:
                    continue

                cursor.execute("SELECT 1 FROM hubspot_contacts WHERE email = %s", (sender_email,))
                exists = cursor.fetchone()

                if not exists and "not in hubspot" in instruction.lower():
                    results.append(f"⚡ Instruction matched: {instruction}")
                    create_contact(name, sender_email)
                    results.append(f"👤 Contact created: {name} ({sender_email})")
                else:
                    results.append(f"✅ {sender_email} already in HubSpot or instruction didn't match")
    except Exception as e:
        results.append(f"❌ Error: {str(e)}")
    return results



# ✅ SCHEDULER SETUP — 
scheduler = BackgroundScheduler()
scheduler.add_job(check_ongoing_instructions, "interval", minutes=2)
scheduler.start()

@app.get("/simulate/instruction-check")
def simulate_instruction_check():
    logs = check_ongoing_instructions()
    return {"message": "✅ Instruction check completed", "logs": logs}


if __name__ == "__main__":
    check_ongoing_instructions()

