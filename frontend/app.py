import streamlit as st
import requests
import json
from datetime import datetime
import time
import re

# Configuration
BACKEND_URL = "http://localhost:8000"

# Custom CSS for ChatGPT-like interface
st.set_page_config(
    page_title="AI Financial Advisor",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
        background: #f8f9fa;
        border-radius: 15px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    .user-message {
        background: #007bff;
        color: white;
        padding: 12px 16px;
        border-radius: 18px 18px 4px 18px;
        margin: 10px 0;
        margin-left: 20%;
        word-wrap: break-word;
    }
    
    .assistant-message {
        background: #e9ecef;
        color: #333;
        padding: 12px 16px;
        border-radius: 18px 18px 18px 4px;
        margin: 10px 0;
        margin-right: 20%;
        word-wrap: break-word;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        margin: 2px;
    }
    
    .status-pending {
        background: #ffc107;
        color: #212529;
    }
    
    .status-done {
        background: #28a745;
        color: white;
    }
    
    .integration-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #007bff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.5rem 1.5rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    
    .sidebar .stSelectbox > div > div {
        background: #f8f9fa;
        border-radius: 10px;
    }
    
    .chat-input {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        width: 90%;
        max-width: 800px;
        background: white;
        border-radius: 25px;
        padding: 10px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        z-index: 1000;
    }
    
    .thinking-animation {
        color: #007bff;
        font-style: italic;
    }
    
    .success-toast {
        background: #d4edda;
        color: #155724;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #c3e6cb;
        margin: 10px 0;
    }
    
    .error-toast {
        background: #f8d7da;
        color: #721c24;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #f5c6cb;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_email" not in st.session_state:
    st.session_state.user_email = "saitej13sai@gmail.com"
if "access_token" not in st.session_state:
    st.session_state.access_token = ""
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Helper functions
def make_request(endpoint, method="GET", params=None, data=None):
    """Make API request to backend"""
    try:
        url = f"{BACKEND_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url, params=params)
        elif method == "POST":
            if data:
                response = requests.post(url, params=params, json=data)
            else:
                response = requests.post(url, params=params)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Request failed: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def display_message(message, is_user=False):
    """Display a chat message"""
    css_class = "user-message" if is_user else "assistant-message"
    icon = "🧑‍💼" if is_user else "🤖"
    
    st.markdown(f"""
    <div class="{css_class}">
        <strong>{icon}</strong> {message}
    </div>
    """, unsafe_allow_html=True)

def simulate_typing(text, placeholder):
    """Simulate typing effect"""
    displayed_text = ""
    for char in text:
        displayed_text += char
        placeholder.markdown(f'<div class="assistant-message thinking-animation">{displayed_text}▊</div>', unsafe_allow_html=True)
        time.sleep(0.02)
    placeholder.markdown(f'<div class="assistant-message">{text}</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown('<div class="main-header"><h2>🤖 AI Financial Advisor</h2></div>', unsafe_allow_html=True)

    # 🔐 Authentication
    st.markdown("### 🔐 Authentication")
    if not st.session_state.authenticated:
        with st.expander("Login with Google", expanded=True):
            if st.button("🔗 Login with Google"):
                js = f"""<script>window.open("{BACKEND_URL}/auth/url", "_blank")</script>"""
                st.components.v1.html(js)

            st.session_state.access_token = st.text_input("🔑 Access Token", type="password")
            if st.button("✅ Authenticate"):
                if st.session_state.access_token:
                    st.session_state.authenticated = True
                    st.success("Authentication successful!")
                    st.rerun()
                else:
                    st.error("Please enter your access token")
    else:
        st.success("✅ Authenticated")
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.session_state.access_token = ""
            st.rerun()

    
    # User Settings
    st.markdown("### ⚙️ Settings")
    st.session_state.user_email = st.text_input("📧 Email", value=st.session_state.user_email)
    
    # Integration Status
    st.markdown("### 🔗 Integrations")
    
    # Gmail Integration
    with st.expander("📧 Gmail", expanded=False):
        if st.button("📥 Ingest Gmail"):
            if st.session_state.access_token:
                result = make_request("/gmail/ingest", params={"token": st.session_state.access_token})
                if "error" not in result:
                    st.success(result["message"])
                else:
                    st.error(result["error"])
            else:
                st.error("Please authenticate first")
    
    # Calendar Integration
    with st.expander("📅 Calendar", expanded=False):
        if st.button("📥 Ingest Calendar"):
            if st.session_state.access_token:
                result = make_request("/calendar/ingest", params={"token": st.session_state.access_token})
                if "error" not in result:
                    st.success(result["message"])
                else:
                    st.error(result["error"])
            else:
                st.error("Please authenticate first")
    
st.markdown("### 🏢 HubSpot Integration")


# -------------------- Ongoing Instruction Memory --------------------
st.markdown("### 🧠 Ongoing Instructions")

with st.expander("➕ Add Instruction", expanded=False):
    new_instruction = st.text_area("📝 Instruction", placeholder="e.g. When someone emails me who is not in HubSpot, create a contact in HubSpot.")

    if st.button("💾 Save Instruction"):
        if new_instruction.strip():
            result = make_request("/instructions/store", method="POST", params={
                "email": st.session_state.user_email
            }, data=new_instruction)
            if "error" not in result:
                st.success("✅ Instruction saved successfully!")
            else:
                st.error(result["error"])
        else:
            st.warning("Instruction cannot be empty.")



# Step 1: Connect HubSpot (opens URL in new tab)
if st.button("🔗 Connect HubSpot"):
    js = f"""<script>window.open("{BACKEND_URL}/hubspot/auth-url", "_blank")</script>"""
    st.components.v1.html(js)

# Step 2: Input token + Authenticate
st.session_state.hubspot_access_token = st.text_input("🔑 HubSpot Access Token", type="password")

if "hubspot_authenticated" not in st.session_state:
    st.session_state.hubspot_authenticated = False

if st.button("✅ Authenticate HubSpot"):
    if st.session_state.hubspot_access_token:
        st.session_state.hubspot_authenticated = True
        st.success("HubSpot authenticated!")
        st.rerun()
    else:
        st.error("Please paste your HubSpot access token")

# Step 3: Ingest contacts if authenticated
if st.session_state.hubspot_authenticated:
    if st.button("📥 Ingest HubSpot"):
        result = make_request("/hubspot/ingest", params={"token": st.session_state.hubspot_access_token})
        if "error" not in result:
            st.success(result["message"])
        else:
            st.error(result["error"])
else:
    st.warning("Please authenticate with HubSpot token to ingest data")


   
            
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    
    # Task Management
    with st.expander("📋 Task Management", expanded=False):
        if st.button("📋 View Tasks"):
            result = make_request("/tasks/list", params={"email": st.session_state.user_email})
            if "error" not in result:
                tasks = result.get("tasks", [])
                st.markdown("**Your Tasks:**")
                for task in tasks:
                    status_class = "status-done" if task["status"] == "done" else "status-pending"
                    st.markdown(f"""
                    <div class="integration-card">
                        <strong>{task['instruction']}</strong><br>
                        <span class="status-badge {status_class}">{task['status']}</span>
                        <small>{task['created_at']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.error(result["error"])
    
    # Ongoing Instructions

    
    # Tools
    with st.expander("🛠️ Tools", expanded=False):
        tool_type = st.selectbox("Select Tool", ["send_email", "create_event", "create_contact"])
        
        if tool_type == "send_email":
            recipient = st.text_input("Recipient:")
            subject = st.text_input("Subject:")
            body = st.text_area("Body:")
            if st.button("📧 Send Email"):
                if recipient and subject and body:
                    result = make_request("/tools/call", method="POST", 
                                        params={"tool": "send_email"},
                                        data={"recipient": recipient, "subject": subject, "body": body})
                    if "error" not in result:
                        st.success(result["message"])
                    else:
                        st.error(result["error"])
        
        elif tool_type == "create_event":
            title = st.text_input("Event Title:")
            event_time = st.text_input("Time (ISO format):")
            attendees = st.text_input("Attendees (comma-separated):")
            if st.button("📅 Create Event"):
                if title and event_time:
                    attendee_list = [email.strip() for email in attendees.split(",") if email.strip()]
                    result = make_request("/tools/call", method="POST", 
                                        params={"tool": "create_event"},
                                        data={"title": title, "time": event_time, "attendees": attendee_list})
                    if "error" not in result:
                        st.success(result["message"])
                    else:
                        st.error(result["error"])
        
        elif tool_type == "create_contact":
            name = st.text_input("Contact Name:")
            email = st.text_input("Contact Email:")
            if st.button("👤 Create Contact"):
                if name and email:
                    result = make_request("/tools/call", method="POST", 
                                        params={"tool": "create_contact"},
                                        data={"name": name, "email": email})
                    if "error" not in result:
                        st.success(result["message"])
                    else:
                        st.error(result["error"])

# Main Chat Interface
st.markdown('<div class="main-header"><h1>💼 AI Financial Advisor</h1><p>Your intelligent assistant for managing clients, emails, and tasks</p></div>', unsafe_allow_html=True)

# Chat container
chat_container = st.container()

with chat_container:
    # Display welcome message
    if len(st.session_state.messages) == 0:
        st.markdown("""
        <div class="assistant-message">
            <strong>🤖</strong> Hello! I'm your AI Financial Advisor assistant. I can help you with:
            <ul>
                <li>📧 Searching and analyzing your emails</li>
                <li>👥 Managing client information from HubSpot</li>
                <li>📅 Scheduling appointments and events</li>
                <li>📋 Creating and managing tasks</li>
                <li>🔍 Answering questions about your clients</li>
            </ul>
            Try asking me something like "Who mentioned their kid plays baseball?" or "Schedule a meeting with John"
        </div>
        """, unsafe_allow_html=True)
    
    # Display chat messages
    for message in st.session_state.messages:
        display_message(message["content"], message["role"] == "user")

# Chat input
with st.container():
    st.markdown("---")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_input = st.text_input("💬 Ask me anything...", key="chat_input", placeholder="Type your message here...")
    
    with col2:
        send_button = st.button("🚀 Send", key="send_button")

# Handle user input
if send_button and user_input:
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Show typing indicator
    with st.container():
        thinking_placeholder = st.empty()
        thinking_placeholder.markdown('<div class="assistant-message thinking-animation">🤖 Thinking...</div>', unsafe_allow_html=True)
    
    # Process the message
    if user_input.lower().startswith("create task:") or "schedule" in user_input.lower() or "remind" in user_input.lower():
        # Handle task creation
        task_instruction = user_input.replace("create task:", "").strip() if user_input.lower().startswith("create task:") else user_input
        result = make_request("/tasks/store", method="POST", 
                            params={"email": st.session_state.user_email},
                            data={"instruction": task_instruction})
        
        if "error" not in result:
            response = f"✅ Task created: {task_instruction}"
        else:
            response = f"❌ Error creating task: {result['error']}"
    
    elif user_input.lower().startswith("search"):
        # Handle search queries
        search_query = user_input.replace("search", "").strip()
        
        # Search Gmail
        gmail_result = make_request("/gmail/search", params={"query": search_query})
        
        # Search HubSpot
        hubspot_result = make_request("/search", params={"query": search_query})
        
        response = f"🔍 Search results for '{search_query}':\n\n"
        
        if "error" not in gmail_result and gmail_result.get("results"):
            response += "📧 **Gmail Results:**\n"
            for email in gmail_result["results"][:3]:
                response += f"• {email['subject']}\n"
        
        if "error" not in hubspot_result and hubspot_result.get("results"):
            response += "\n👥 **HubSpot Contacts:**\n"
            for contact in hubspot_result["results"][:3]:
                response += f"• {contact['name']} ({contact['email']})\n"
        
        if not gmail_result.get("results") and not hubspot_result.get("results"):
            response += "No results found."
    
    else:
        # Handle general chat
        result = make_request("/chat", method="POST", 
                            params={"prompt": user_input, "email": st.session_state.user_email})
        
        if "error" not in result:
            response = result["response"]
        else:
            response = f"❌ Error: {result['error']}"
    
    # Add assistant response to chat
    st.session_state.messages.append({"role": "assistant", "content": response})
    
    # Clear the thinking indicator and rerun to show the new messages
    thinking_placeholder.empty()
    st.rerun()

# Auto-scroll to bottom
if st.session_state.messages:
    st.markdown("""
    <script>
        window.parent.document.querySelector('.main').scrollTop = window.parent.document.querySelector('.main').scrollHeight;
    </script>
    """, unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 20px;">
    <p>🤖 AI Financial Advisor | Built with Streamlit & FastAPI</p>
    <p>💡 <strong>Quick Tips:</strong> Try "Who mentioned AAPL?" or "Schedule a call with Maria"</p>
</div>
""", unsafe_allow_html=True)

# Example queries for testing
with st.expander("💡 Example Queries", expanded=False):
    st.markdown("""
    **Search & Analysis:**
    - "Who mentioned their kid plays baseball?"
    - "Why did Greg say he wanted to sell AAPL stock?"
    - "Search for emails about meetings"
    
    **Task Management:**
    - "Create task: Email Maria to confirm AAPL meeting"
    - "Schedule an appointment with Sara Smith"
    - "Remind me to follow up with John"
    
    **Instructions:**
    - "When someone emails me that is not in HubSpot, create a contact"
    - "When I create a contact, send them a welcome email"
    
    **Tools:**
    - "Send email to maria@example.com about our meeting"
    - "Create calendar event for tomorrow at 2 PM"
    - "Add Greg Smith to my contacts"
    """)

# Real-time updates (optional)
if st.button("🔄 Refresh Data"):
    st.rerun()

