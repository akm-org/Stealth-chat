from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
import bcrypt
import secrets
import hashlib
import base64
import qrcode
import io
import re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os
import json
from datetime import datetime, timedelta
import mimetypes
import time

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- In-memory Storage (Consider persistence for production) ---
users = {}
chat_sessions = {}
messages = {}
files = {}
session_urls = {}
user_sessions = {}  # Track user sessions with timestamps
global_session_killed = False  # Global kill switch state
cloaked_sessions = set()  # Track cloaked sessions
user_impersonations = {}  # Track user impersonations {username: fake_name}
muted_users = set()  # Track users who have muted alert sounds

# --- Command Handler Module ---
class CommandHandler:
    def __init__(self):
        self.commands = {
            '/nuke': self.handle_nuke,
            '/revive': self.handle_revive,
            '/cloak': self.handle_cloak,
            '/uncloak': self.handle_uncloak,
            '/impersonate': self.handle_impersonate,
            '/help': self.handle_help,
            '/status': self.handle_status,
            '/mute': self.handle_mute
        }
    
    def process_command(self, message_text, sender, session_key, current_session_url):
        """Process a command and return the result"""
        if not message_text.startswith('/'):
            return None
        
        # Parse command and arguments
        parts = message_text.strip().split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        
        if command not in self.commands:
            return {
                'success': False,
                'message': f'Unknown command: {command}. Type /help for available commands.',
                'broadcast': None
            }
        
        # Check if user has permission for admin commands
        admin_commands = ['/nuke', '/revive', '/cloak', '/uncloak', '/impersonate']
        if command in admin_commands and str(sender).lower() != 'demigod':
            return {
                'success': False,
                'message': 'Access denied. Admin privileges required.',
                'broadcast': None
            }
        
        # Execute the command
        return self.commands[command](args, sender, session_key, current_session_url)
    
    def handle_nuke(self, args, sender, session_key, current_session_url):
        """Kill all sessions"""
        global global_session_killed, user_sessions, session_urls
        global_session_killed = True
        user_sessions.clear()
        session_urls.clear()
        
        broadcast_data = {
            'type': 'system_alert',
            'message': 'SYSTEM ALERT: All sessions have been terminated by administrator.',
            'sender': 'SYSTEM',
            'timestamp': datetime.now().isoformat()
        }
        
        print("[INFO] All sessions killed by demigod user")
        return {
            'success': True,
            'message': 'Nuclear option activated. All sessions terminated.',
            'broadcast': broadcast_data
        }
    
    def handle_revive(self, args, sender, session_key, current_session_url):
        """Revive all sessions"""
        global global_session_killed
        global_session_killed = False
        
        broadcast_data = {
            'type': 'system_alert',
            'message': 'SYSTEM ALERT: Global session lock has been lifted.',
            'sender': 'SYSTEM',
            'timestamp': datetime.now().isoformat()
        }
        
        print("[INFO] All sessions revived by demigod user")
        return {
            'success': True,
            'message': 'All sessions have been revived.',
            'broadcast': broadcast_data
        }
    
    def handle_mute(self, args, sender, session_key, current_session_url):
        """Toggle sound notifications for the user"""
        global muted_users
        
        if sender in muted_users:
            muted_users.remove(sender)
            status = "unmuted"
        else:
            muted_users.add(sender)
            status = "muted"
            
        return {
            'success': True,
            'message': f'Sound notifications {status}.',
            'broadcast': None
        }
        
        print("[INFO] Global session restored by demigod user")
        return {
            'success': True,
            'message': 'Global session lock lifted. New connections allowed.',
            'broadcast': broadcast_data
        }
    
    def handle_cloak(self, args, sender, session_key, current_session_url):
        """Cloak current session"""
        if current_session_url:
            cloaked_sessions.add(current_session_url)
            
            broadcast_data = {
                'type': 'system_alert',
                'message': 'SYSTEM ALERT: Session has been cloaked. New users cannot join.',
                'sender': 'SYSTEM',
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"[INFO] Session {current_session_url} has been cloaked")
            return {
                'success': True,
                'message': 'Session cloaked successfully. New users cannot join this session.',
                'broadcast': broadcast_data
            }
        else:
            return {
                'success': False,
                'message': 'Could not determine current session to cloak.',
                'broadcast': None
            }
    
    def handle_uncloak(self, args, sender, session_key, current_session_url):
        """Uncloak current session"""
        if current_session_url:
            cloaked_sessions.discard(current_session_url)
            
            broadcast_data = {
                'type': 'system_alert',
                'message': 'SYSTEM ALERT: Session has been uncloaked. New users can join.',
                'sender': 'SYSTEM',
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"[INFO] Session {current_session_url} has been uncloaked")
            return {
                'success': True,
                'message': 'Session uncloaked successfully. New users can now join.',
                'broadcast': broadcast_data
            }
        else:
            return {
                'success': False,
                'message': 'Could not determine current session to uncloak.',
                'broadcast': None
            }
    
    def handle_impersonate(self, args, sender, session_key, current_session_url):
        """Handle user impersonation"""
        fake_name = args.strip()
        
        if fake_name:
            # Validate fake name
            if not re.match(r'^[a-zA-Z0-9_.-]+$', fake_name):
                return {
                    'success': False,
                    'message': 'Invalid impersonation name. Use only letters, numbers, underscore, dot, and hyphen.',
                    'broadcast': None
                }
            
            user_impersonations[sender] = fake_name
            
            # No broadcast for impersonate command
            print(f"[INFO] User {sender} is now impersonating as {fake_name}")
            return {
                'success': True,
                'message': f'Now impersonating as "{fake_name}". Your messages will appear under this name.',
                'broadcast': None  # No broadcast alert
            }
        else:
            # Stop impersonation
            old_name = user_impersonations.pop(sender, None)
            if old_name:
                # No broadcast for impersonate command
                print(f"[INFO] User {sender} stopped impersonating")
                return {
                    'success': True,
                    'message': 'Impersonation stopped. Messages will now appear under your real username.',
                    'broadcast': None  # No broadcast alert
                }
            else:
                return {
                    'success': False,
                    'message': 'You are not currently impersonating anyone.',
                    'broadcast': None
                }
    
    def handle_mute(self, args, sender, session_key, current_session_url):
        """Toggle sound notifications for the current user"""
        global muted_users
        
        if sender in muted_users:
            muted_users.remove(sender)
            status = "unmuted"
        else:
            muted_users.add(sender)
            status = "muted"
            
        print(f"[INFO] User {sender} has {status} alert sounds")
        return {
            'success': True,
            'message': f'Sound notifications {status}.',
            'broadcast': None
        }
    
    def handle_help(self, args, sender, session_key, current_session_url):
        """Show help information"""
        if str(sender).lower() == 'demigod':
            help_text = """Available Commands:
/help - Show this help message
/status - Show current session status
/nuke - Kill all active sessions (ADMIN)
/revive - Restore global session access (ADMIN)
/cloak - Hide current session from new users (ADMIN)
/uncloak - Allow new users to join current session (ADMIN)
/impersonate [name] - Change display name (ADMIN)
/impersonate - Stop impersonating (ADMIN)

Special Message Types:
!whisper [message] - Send temporary message (auto-deletes after 5s)
!alert [message] - Send high-priority alert message"""
        else:
            help_text = """Available Commands:
/help - Show this help message
/status - Show current session status

Special Message Types:
!whisper [message] - Send temporary message (auto-deletes after 5s)
!alert [message] - Send high-priority alert message"""
        
        return {
            'success': True,
            'message': help_text,
            'broadcast': None
        }
    
    def handle_status(self, args, sender, session_key, current_session_url):
        """Show current status"""
        status_info = []
        
        if str(sender).lower() == 'demigod':
            status_info.append(f"Global Kill Switch: {'ACTIVE' if global_session_killed else 'INACTIVE'}")
            status_info.append(f"Active Sessions: {len(user_sessions)}")
            status_info.append(f"Current Session Cloaked: {'YES' if current_session_url in cloaked_sessions else 'NO'}")
            status_info.append(f"Impersonating: {user_impersonations.get(sender, 'NONE')}")
        else:
            status_info.append(f"Session Key: {session_key}")
            status_info.append(f"Username: {sender}")
        
        return {
            'success': True,
            'message': '\n'.join(status_info),
            'broadcast': None
        }

# Initialize command handler
command_handler = CommandHandler()

# --- User Initialization ---
def init_users():
    """Initialize default users with bcrypt hashed passwords."""
    global users
    users["demigod"] = {
        "password": bcrypt.hashpw("Demig0d@".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    }
    users["human"] = {
        "password": bcrypt.hashpw("secret123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    }

init_users()

# --- Session Management ---
def is_session_expired(session_id):
    """Check if a session has expired (30 minutes of inactivity)."""
    if session_id not in user_sessions:
        return True
    
    last_activity = user_sessions[session_id].get('last_activity')
    if not last_activity:
        return True
    
    # Check if 30 minutes have passed since last activity
    expiry_time = last_activity + timedelta(minutes=30)
    return datetime.now() > expiry_time

def update_session_activity(session_id):
    """Update the last activity timestamp for a session."""
    if session_id in user_sessions:
        user_sessions[session_id]['last_activity'] = datetime.now()

def cleanup_expired_sessions():
    """Remove expired sessions from memory."""
    expired_sessions = []
    for session_id, session_data in user_sessions.items():
        if is_session_expired(session_id):
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        if session_id in user_sessions:
            del user_sessions[session_id]
        if session_id in session_urls:
            del session_urls[session_id]
        print(f"[INFO] Expired session removed: {session_id}")

def is_global_session_killed():
    """Check if global session kill switch is active."""
    return global_session_killed

def is_session_cloaked(session_url):
    """Check if a session is cloaked."""
    return session_url in cloaked_sessions

def get_display_name(username):
    """Get the display name for a user (impersonated name if set, otherwise real name)."""
    return user_impersonations.get(username, username)

# --- Cryptography Helpers ---
def generate_chat_session():
    """Generate a cryptographically secure random chat session URL component."""
    return "session_" + secrets.token_urlsafe(16)

def generate_key_from_session(session_key, salt=None):
    """Generate a 32-byte AES key from the session key using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = b"stealth_messaging_salt_v5"
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(session_key.encode("utf-8"))

def encrypt_message(message, key):
    """Encrypt a message using AES-256-GCM."""
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(message.encode("utf-8")) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode("utf-8")

def decrypt_message(encrypted_message, key):
    """Decrypt a message using AES-256-GCM."""
    try:
        data = base64.b64decode(encrypted_message)
        iv = data[:12]
        tag = data[12:28]
        ciphertext = data[28:]
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")
    except Exception as e:
        print(f"[ERROR] Message decryption failed: {e}")
        return "[DECRYPTION FAILED]"

def encrypt_file(file_data, key):
    """Encrypt file data using AES-256-GCM."""
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(file_data) + encryptor.finalize()
    return iv + encryptor.tag + ciphertext

def decrypt_file(encrypted_data, key):
    """Decrypt file data using AES-256-GCM."""
    try:
        iv = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
    except Exception as e:
        print(f"[ERROR] File decryption failed: {e}")
        return None

# --- Utility Functions ---
def generate_qr_code(data):
    """Generate a QR code image as a base64 encoded string."""
    try:
        qr = qrcode.QRCode(
            version=1, 
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10, 
            border=4
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="#ff0044", back_color="#000000")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        
        return base64.b64encode(img_buffer.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[ERROR] QR Code generation failed: {e}")
        return None

# --- Flask Routes ---

@app.route("/")
def index():
    """Handles the initial user access point, showing login if user exists."""
    # Clean up expired sessions on each request
    cleanup_expired_sessions()
    
    user = request.args.get("user")
    if user not in users:
        return render_template_string("""
        <!DOCTYPE html>
        <html><head><title>ACCESS DENIED</title><style>body{background:#000;margin:0;height:100vh;overflow:hidden;}</style></head><body></body></html>
        """)
    
    # Clear any existing session data to force re-authentication
    session.clear()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>STEALTH LOGIN</title>
        <style>
            :root {
                --primary-color: #ff0044;
                --background-color: #000;
                --font-family: 'Courier New', monospace;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: var(--background-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding: 20px;
            }
            .login-container {
                background: rgba(255, 0, 68, 0.1);
                border: 2px solid var(--primary-color);
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(255, 0, 68, 0.3);
                animation: pulse 2s infinite;
                width: 100%;
                max-width: 400px;
            }
            @keyframes pulse {
                0%, 100% { box-shadow: 0 0 20px rgba(255, 0, 68, 0.3); }
                50% { box-shadow: 0 0 30px rgba(255, 0, 68, 0.6); border-color: #ff3366; }
            }
            .title {
                text-align: center;
                font-size: 1.5rem;
                margin-bottom: 30px;
                text-shadow: 0 0 10px var(--primary-color);
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .form-group { margin-bottom: 25px; }
            label {
                display: block;
                margin-bottom: 8px;
                font-size: 0.875rem;
                text-transform: uppercase;
            }
            input[type="password"] {
                width: 100%;
                padding: 12px;
                background: var(--background-color);
                border: 2px solid var(--primary-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                font-size: 1rem;
                border-radius: 5px;
                outline: none;
                transition: border-color 0.3s, box-shadow 0.3s;
            }
            input[type="password"]:focus {
                border-color: #ff3366;
                box-shadow: 0 0 10px rgba(255, 0, 68, 0.5);
            }
            .login-btn {
                width: 100%;
                padding: 15px;
                background: var(--background-color);
                border: 2px solid var(--primary-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                font-size: 1.125rem;
                cursor: pointer;
                border-radius: 5px;
                transition: all 0.3s ease;
                text-transform: uppercase;
                font-weight: bold;
            }
            .login-btn:hover, .login-btn:focus {
                background: var(--primary-color);
                color: var(--background-color);
                box-shadow: 0 0 15px rgba(255, 0, 68, 0.7);
                outline: none;
            }
            .user-info {
                text-align: center;
                margin-bottom: 25px;
                font-size: 1.125rem;
                text-transform: uppercase;
                opacity: 0.9;
            }
            @media (max-width: 480px) {
                .login-container { padding: 30px 20px; }
                .title { font-size: 1.25rem; }
                input[type="password"] { font-size: 0.875rem; padding: 10px; }
                .login-btn { font-size: 1rem; padding: 12px; }
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="title">Stealth Access</div>
            <div class="user-info">User: {{ user|upper }}</div>
            <form method="POST" action="{{ url_for('login') }}">
                <input type="hidden" name="username" value="{{ user }}">
                <div class="form-group">
                    <label for="password">Access Code:</label>
                    <input type="password" name="password" id="password" required>
                </div>
                <button type="submit" class="login-btn">Authenticate</button>
            </form>
        </div>
    </body>
    </html>
    """, user=user)

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    
    # Check if global kill switch is active
    if is_global_session_killed():
        print(f"[WARN] Login attempt blocked due to global session kill: {username}")
        return "ACCESS DENIED - All sessions terminated", 403
    
    # Make username case-insensitive for 'demigod'
    lookup_username = username
    if username.lower() == 'demigod':
        lookup_username = 'demigod'
    
    user_data = users.get(lookup_username)
    if user_data and bcrypt.checkpw(password.encode("utf-8"), user_data["password"].encode("utf-8")):
        # Store original username for display but use normalized version for admin checks
        session["user"] = username
        session["username"] = lookup_username
        session["authenticated"] = True
        chat_url_component = generate_chat_session()
        session["chat_url"] = chat_url_component
        session_urls[chat_url_component] = lookup_username
        
        # Create user session tracking
        user_sessions[chat_url_component] = {
            'username': lookup_username,
            'display_name': username,
            'created_at': datetime.now(),
            'last_activity': datetime.now()
        }
        
        print(f"[INFO] User '{username}' logged in. Session URL component: {chat_url_component}")
        return redirect(url_for("start"))
    else:
        print(f"[WARN] Failed login attempt for user '{username}'")
        return "ACCESS DENIED - Invalid Credentials", 403

@app.route("/start")
def start():
    if not session.get("authenticated"): 
        return redirect(url_for("index"))
    
    # Check session expiry
    chat_url_component = session.get("chat_url")
    if chat_url_component and is_session_expired(chat_url_component):
        session.clear()
        return redirect(url_for("index"))
    
    # Update session activity
    if chat_url_component:
        update_session_activity(chat_url_component)
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>STEALTH READY</title>
        <style>
            :root { --primary-color: #ff0044; --background-color: #000; --font-family: 'Courier New', monospace; }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: var(--background-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding: 20px;
            }
            .start-container {
                text-align: center;
                background: rgba(255, 0, 68, 0.1);
                border: 2px solid var(--primary-color);
                padding: 60px 40px;
                border-radius: 10px;
                box-shadow: 0 0 30px rgba(255, 0, 68, 0.5);
                animation: glow 3s ease-in-out infinite alternate;
                width: 100%;
                max-width: 500px;
            }
            @keyframes glow {
                from { box-shadow: 0 0 30px rgba(255, 0, 68, 0.5); border-color: var(--primary-color); }
                to { box-shadow: 0 0 50px rgba(255, 0, 68, 0.8); border-color: #ff3366; }
            }
            .title {
                font-size: 2rem;
                margin-bottom: 40px;
                text-shadow: 0 0 15px var(--primary-color);
                animation: flicker 1.5s infinite alternate;
                text-transform: uppercase;
                letter-spacing: 2px;
            }
            @keyframes flicker {
                0%, 100% { opacity: 1; text-shadow: 0 0 15px var(--primary-color); }
                50% { opacity: 0.8; text-shadow: 0 0 20px #ff3366; }
            }
            .start-btn {
                background: var(--background-color);
                border: 3px solid var(--primary-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                font-size: 1.5rem;
                padding: 20px 40px;
                cursor: pointer;
                border-radius: 10px;
                transition: all 0.3s ease;
                text-transform: uppercase;
                font-weight: bold;
                letter-spacing: 2px;
                width: 100%;
                max-width: 300px;
                display: inline-block;
            }
            .start-btn:hover, .start-btn:focus {
                background: var(--primary-color);
                color: var(--background-color);
                box-shadow: 0 0 25px rgba(255, 0, 68, 0.9);
                transform: scale(1.05);
                outline: none;
            }
            @media (max-width: 480px) {
                .start-container { padding: 40px 20px; }
                .title { font-size: 1.5rem; margin-bottom: 30px; }
                .start-btn { font-size: 1.125rem; padding: 15px 30px; letter-spacing: 1px; }
            }
        </style>
    </head>
    <body>
        <div class="start-container">
            <div class="title">System Ready</div>
            <form method="POST" action="{{ url_for('setup') }}">
                <button type="submit" class="start-btn">Initiate Session</button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.route("/setup", methods=["POST"])
def setup():
    if not session.get("authenticated"): 
        return redirect(url_for("index"))
    
    chat_url_component = session.get("chat_url")
    if not chat_url_component or chat_url_component not in session_urls:
        print(f"[WARN] Session error during setup for user ", session.get("user"), " - chat_url missing or invalid.")
        session.pop("chat_url", None)
        return "SESSION ERROR - Please log in again.", 500
    
    # Check session expiry
    if is_session_expired(chat_url_component):
        session.clear()
        return redirect(url_for("index"))
    
    # Update session activity
    update_session_activity(chat_url_component)
    
    full_url = url_for("chat_session", session_url=chat_url_component, _external=True)
    qr_code_b64 = generate_qr_code(full_url)

    if qr_code_b64 is None:
        return "ERROR Generating QR Code", 500
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CHAT PORTAL</title>
        <style>
            :root { --primary-color: #ff0044; --background-color: #000; --font-family: 'Courier New', monospace; }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: var(--background-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                padding: 20px;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }
            .setup-container {
                background: rgba(255, 0, 68, 0.1);
                border: 2px solid var(--primary-color);
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 0 25px rgba(255, 0, 68, 0.4);
                text-align: center;
                width: 100%;
                max-width: 600px;
            }
            .title {
                font-size: 1.75rem;
                margin-bottom: 30px;
                text-shadow: 0 0 10px var(--primary-color);
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .url-section {
                margin-bottom: 30px;
                padding: 20px;
                background: rgba(0, 0, 0, 0.5);
                border: 1px solid var(--primary-color);
                border-radius: 5px;
            }
            .url-label {
                font-size: 0.875rem;
                margin-bottom: 10px;
                text-transform: uppercase;
                display: block;
            }
            .chat-url-input {
                background: var(--background-color);
                border: 2px solid var(--primary-color);
                color: var(--primary-color);
                padding: 12px;
                font-family: var(--font-family);
                font-size: 0.875rem;
                width: 100%;
                border-radius: 5px;
                word-break: break-all;
                outline: none;
                text-align: center;
                cursor: pointer;
            }
            .qr-section { margin-bottom: 35px; }
            .qr-code {
                max-width: 200px;
                height: auto;
                border: 3px solid var(--primary-color);
                border-radius: 5px;
                display: block;
                margin: 10px auto 0;
                background: black;
            }
            .access-btn {
                background: var(--background-color);
                border: 2px solid var(--primary-color);
                color: var(--primary-color);
                font-family: var(--font-family);
                font-size: 1.125rem;
                padding: 15px 30px;
                cursor: pointer;
                border-radius: 5px;
                transition: all 0.3s ease;
                text-transform: uppercase;
                text-decoration: none;
                display: inline-block;
                font-weight: bold;
                letter-spacing: 1px;
            }
            .access-btn:hover, .access-btn:focus {
                background: var(--primary-color);
                color: var(--background-color);
                box-shadow: 0 0 15px rgba(255, 0, 68, 0.7);
                outline: none;
            }
            @media (max-width: 600px) {
                .setup-container { padding: 30px 20px; }
                .title { font-size: 1.375rem; margin-bottom: 25px; }
                .chat-url-input { font-size: 0.75rem; padding: 10px; }
                .qr-code { max-width: 160px; }
                .access-btn { font-size: 1rem; padding: 12px 25px; }
            }
        </style>
    </head>
    <body>
        <div class="setup-container">
            <div class="title">Chat Portal Generated</div>
            
            <div class="url-section">
                <label for="chat-url" class="url-label">Secure Chat URL (Click to Select & Copy):</label>
                <input type="text" id="chat-url" class="chat-url-input" value="{{ chat_url }}" readonly onclick="this.select(); try { document.execCommand('copy'); alert('URL copied to clipboard!'); } catch (err) { alert('Failed to copy URL.'); }">
            </div>
            
            <div class="qr-section">
                <div class="url-label">QR Access Code:</div>
                <img src="data:image/png;base64,{{ qr_code_b64 }}" alt="QR Code for Chat Session" class="qr-code">
            </div>
            
            <a href="{{ url_for('chat_session', session_url=session_url_component) }}" class="access-btn">Access Chat</a>
        </div>
    </body>
    </html>
    """, chat_url=full_url, qr_code_b64=qr_code_b64, session_url_component=chat_url_component)

@app.route("/<path:session_url>")
def chat_session(session_url):
    # Check if global kill switch is active
    if is_global_session_killed():
        return "SESSION TERMINATED - All sessions have been terminated", 403
    
    if session_url not in session_urls:
        print(f"[WARN] Access attempt to invalid session URL: {session_url}")
        return "INVALID OR EXPIRED SESSION", 404
    
    # Check if session is cloaked and user is not already in the session
    if is_session_cloaked(session_url):
        # Check if user is already authenticated for this session
        current_session_url = session.get("current_session_url_component")
        if current_session_url != session_url:
            print(f"[WARN] Access attempt to cloaked session: {session_url}")
            return "SESSION RESTRICTED - This session is currently private", 403
    
    # Check session expiry
    if is_session_expired(session_url):
        print(f"[WARN] Access attempt to expired session: {session_url}")
        return "SESSION EXPIRED - Please log in again", 403
    
    # Update session activity
    update_session_activity(session_url)
    
    session["current_session_url_component"] = session_url
    print(f"[INFO] User accessing chat session: {session_url}")

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>STEALTH CHAT</title>
        <style>
            :root {
                --primary-color: #ff0044;
                --background-color: #000;
                --font-family: 'Courier New', monospace;
                --container-bg: rgba(255, 0, 68, 0.05);
                --input-bg: rgba(0, 0, 0, 0.7);
                --message-bg: rgba(255, 0, 68, 0.1);
                --message-own-bg: rgba(255, 0, 68, 0.15);
                --border-color: #ff0044;
                --text-color: #ff0044;
                --link-color: #ff5577;
                --alert-bg: rgba(255, 0, 0, 0.2);
                --alert-border: #ff0000;
                --system-bg: rgba(255, 255, 0, 0.2);
                --system-border: #ffff00;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            html { height: 100%; }
            body {
                background: var(--background-color);
                color: var(--text-color);
                font-family: var(--font-family);
                height: 100%;
                overflow: hidden;
                display: flex;
                justify-content: center;
            }
            .chat-container {
                display: flex;
                flex-direction: column;
                height: 100%;
                width: 100%;
                max-width: 800px;
                background: var(--container-bg);
                border-left: 1px solid var(--border-color);
                border-right: 1px solid var(--border-color);
            }
            .header {
                background: rgba(255, 0, 68, 0.15);
                border-bottom: 2px solid var(--border-color);
                padding: 12px 20px;
                text-align: center;
                font-size: 1.125rem;
                text-transform: uppercase;
                letter-spacing: 2px;
                text-shadow: 0 0 8px var(--primary-color);
                flex-shrink: 0;
            }
            .setup-section {
                padding: 15px 20px;
                border-bottom: 1px solid var(--border-color);
                background: var(--input-bg);
                flex-shrink: 0;
                transition: opacity 0.5s ease, max-height 0.5s ease;
                overflow: hidden;
                max-height: 300px;
                opacity: 1;
            }
            .setup-section.hidden {
                 padding-top: 0;
                 padding-bottom: 0;
                 border-bottom: none;
                 max-height: 0;
                 opacity: 0;
            }
            .input-group {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 10px;
                align-items: center;
            }
            .input-group input[type="text"], .input-group input[type="password"] {
                background: var(--background-color);
                border: 1px solid var(--border-color);
                color: var(--text-color);
                padding: 8px 12px;
                font-family: var(--font-family);
                font-size: 0.875rem;
                border-radius: 3px;
                outline: none;
                flex: 1;
                min-width: 120px;
            }
            .input-group input:focus {
                 border-color: #ff3366;
                 box-shadow: 0 0 5px rgba(255, 0, 68, 0.3);
            }
            .join-btn, .unlock-btn {
                background: var(--background-color);
                border: 1px solid var(--border-color);
                color: var(--text-color);
                padding: 8px 16px;
                font-family: var(--font-family);
                font-size: 0.875rem;
                cursor: pointer;
                border-radius: 3px;
                transition: all 0.3s ease;
                text-transform: uppercase;
                white-space: nowrap;
            }
            .join-btn:hover, .unlock-btn:hover,
            .join-btn:focus, .unlock-btn:focus {
                background: var(--primary-color);
                color: var(--background-color);
                outline: none;
            }
            .join-btn:disabled, .unlock-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .lock-icon {
                font-size: 1.5rem;
                cursor: pointer;
                margin-left: 10px;
                transition: all 0.3s ease;
                user-select: none;
                padding: 0 5px;
                line-height: 1;
            }
            .lock-icon:hover {
                text-shadow: 0 0 10px var(--primary-color);
                transform: scale(1.1);
            }
            .unlock-section {
                display: none;
                margin-top: 10px;
                padding: 10px;
                border: 1px dashed var(--border-color);
                border-radius: 5px;
                background: rgba(255, 0, 68, 0.1);
                text-align: center;
            }
            .messages-container {
                flex: 1;
                overflow-y: auto;
                padding: 15px 20px;
                background: rgba(0, 0, 0, 0.8);
                border-bottom: 1px solid var(--border-color);
            }
            .messages-container::-webkit-scrollbar {
                width: 8px;
            }
            .messages-container::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.5);
            }
            .messages-container::-webkit-scrollbar-thumb {
                background-color: var(--primary-color);
                border-radius: 4px;
                border: 2px solid var(--background-color);
            }
            .message {
                background: var(--message-bg);
                border: 1px solid var(--border-color);
                padding: 10px 12px;
                margin-bottom: 10px;
                border-radius: 5px;
                word-wrap: break-word;
                max-width: 90%;
                clear: both;
                float: left;
                position: relative;
            }
            .message.own-message {
                background: var(--message-own-bg);
                border-color: #ff3366;
                float: right;
            }
            .message.whisper-message {
                background: rgba(255, 255, 0, 0.1);
                border-color: #ffff00;
                animation: fadeOut 5s forwards;
            }
            .message.alert-message {
                background: var(--alert-bg);
                border-color: var(--alert-border);
                animation: alertPulse 2s infinite;
                font-weight: bold;
                text-shadow: 0 0 5px #ff0000;
                max-width: 100%;
                float: none;
                text-align: center;
            }
            .message.system-message {
                background: var(--system-bg);
                border-color: var(--system-border);
                max-width: 100%;
                float: none;
                text-align: center;
                font-weight: bold;
                text-shadow: 0 0 5px #ffff00;
            }
            .message.command-response {
                background: rgba(0, 255, 0, 0.1);
                border-color: #00ff00;
                max-width: 100%;
                float: none;
                text-align: left;
                font-family: monospace;
                white-space: pre-wrap;
            }
            @keyframes fadeOut {
                0% { opacity: 1; }
                80% { opacity: 1; }
                100% { opacity: 0; display: none; }
            }
            @keyframes alertPulse {
                0%, 100% { box-shadow: 0 0 10px rgba(255, 0, 0, 0.5); }
                50% { box-shadow: 0 0 20px rgba(255, 0, 0, 0.8); }
            }
            .message-header {
                font-size: 0.75rem;
                color: var(--text-color);
                margin-bottom: 5px;
                opacity: 0.7;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .message-content {
                font-size: 0.875rem;
                line-height: 1.4;
                white-space: pre-wrap;
            }
            .message-actions {
                display: none;
                position: absolute;
                top: 5px;
                right: 5px;
                background: rgba(0, 0, 0, 0.8);
                border: 1px solid var(--border-color);
                border-radius: 3px;
                padding: 2px;
            }
            .message:hover .message-actions {
                display: flex;
            }
            .action-btn {
                background: transparent;
                border: none;
                color: var(--text-color);
                cursor: pointer;
                padding: 2px 4px;
                font-size: 0.7rem;
                margin: 0 1px;
                border-radius: 2px;
                transition: all 0.2s ease;
            }
            .action-btn:hover {
                background: var(--primary-color);
                color: var(--background-color);
            }
            .file-link {
                color: var(--link-color);
                text-decoration: underline;
                cursor: pointer;
                font-weight: bold;
            }
            .file-link:hover {
                color: #ffffff;
            }
            .input-section {
                background: rgba(255, 0, 68, 0.15);
                border-top: 2px solid var(--border-color);
                padding: 15px 20px;
                flex-shrink: 0;
                display: none;
            }
            .message-input-group {
                display: flex;
                gap: 10px;
                align-items: center;
                flex-wrap: wrap;
            }
            .message-input {
                flex: 1;
                background: var(--background-color);
                border: 1px solid var(--border-color);
                color: var(--text-color);
                padding: 10px;
                font-family: var(--font-family);
                font-size: 0.875rem;
                border-radius: 3px;
                outline: none;
                min-width: 150px;
            }
            .message-input:focus {
                 border-color: #ff3366;
                 box-shadow: 0 0 5px rgba(255, 0, 68, 0.3);
            }
            .file-input-wrapper {
                position: relative;
                overflow: hidden;
                display: inline-block;
                background: var(--background-color);
                border: 1px solid var(--border-color);
                color: var(--text-color);
                padding: 8px 12px;
                font-size: 0.75rem;
                border-radius: 3px;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .file-input-wrapper:hover {
                background: var(--primary-color);
                color: var(--background-color);
            }
            .file-input {
                position: absolute;
                left: 0;
                top: 0;
                opacity: 0;
                cursor: pointer;
                width: 100%;
                height: 100%;
            }
            #file-name-display {
                font-size: 0.75rem;
                opacity: 0.7;
                margin-left: 5px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 150px;
                display: inline-block;
                vertical-align: middle;
            }
            .send-btn {
                background: var(--background-color);
                border: 1px solid var(--border-color);
                color: var(--text-color);
                padding: 10px 20px;
                font-family: var(--font-family);
                font-size: 0.875rem;
                cursor: pointer;
                border-radius: 3px;
                transition: all 0.3s ease;
                text-transform: uppercase;
                white-space: nowrap;
            }
            .send-btn:hover, .send-btn:focus {
                background: var(--primary-color);
                color: var(--background-color);
                outline: none;
            }
            .send-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .status {
                padding: 15px;
                text-align: center;
                font-size: 0.875rem;
                opacity: 0.8;
            }
            .file-list-preview {
                font-size: 0.75rem;
                color: var(--text-color);
                margin-top: 5px;
                max-height: 60px;
                overflow-y: auto;
                border: 1px solid rgba(255, 0, 68, 0.2);
                padding: 5px;
                background: rgba(0, 0, 0, 0.5);
            }
            .file-list-preview div {
                padding: 2px 0;
            }
            @media (max-width: 768px) {
                .header { font-size: 1rem; padding: 10px 15px; letter-spacing: 1px; }
                .setup-section { padding: 15px; }
                .input-group {
                    flex-direction: column;
                    align-items: stretch;
                }
                .input-group input { min-width: auto; margin-bottom: 5px; }
                .join-btn, .unlock-btn { width: 100%; padding: 10px; }
                .lock-icon { margin-left: 0; margin-top: 5px; text-align: center; }
                .messages-container { padding: 10px 15px; }
                .input-section { padding: 10px 15px; }
                .message-input-group {
                    flex-direction: column;
                    align-items: stretch;
                }
                .message-input { min-width: auto; margin-bottom: 10px; }
                .file-input-wrapper { width: 100%; text-align: center; margin-bottom: 10px; }
                #file-name-display { max-width: none; }
                .send-btn { width: 100%; padding: 12px; }
                .message { max-width: 95%; }
            }
            @media (max-width: 480px) {
                .header { font-size: 0.875rem; }
                .message { padding: 8px 10px; }
                .message-content { font-size: 0.8125rem; }
                .message-header { font-size: 0.6875rem; }
            }
        </style>
    </head>
    <body>
        <div class="chat-container" id="chat-interface">
            <div class="header">Stealth Communications</div>
            
            <div class="setup-section" id="setup-section">
                <div class="input-group">
                    <input type="text" id="username" placeholder="USERNAME" maxlength="20" autocomplete="off">
                    <input type="password" id="session-key" placeholder="SESSION KEY" maxlength="25" pattern="[0-9]{11}" inputmode="numeric" autocomplete="off">
                    <button onclick="joinChat()" class="join-btn" id="join-btn">Join</button>
                    <span class="lock-icon" onclick="clickLock()" id="lock-icon" title="">🔒</span>
                </div>
                
                <div class="unlock-section" id="unlock-section">
                    <button onclick="unlockChat()" class="unlock-btn" id="unlock-btn">Unlock Chat</button>
                    <div class="status" id="click-status">Clicks: <span id="click-count">0</span>/7</div>
                </div>
            </div>
            
            <div class="messages-container" id="messages-container">
                <div class="status" id="initial-status">Enter your username and the session key to join the secure chat room.</div>
            </div>
            
            <div class="input-section" id="input-section">
                <div class="file-list-preview" id="file-list-preview"></div>
                <div class="message-input-group">
                    <input type="text" id="message-input" placeholder="Type your encrypted message..." class="message-input" autocomplete="off">
                    <label class="file-input-wrapper" for="file-input">
                        Attach File(s)
                        <input type="file" id="file-input" class="file-input" accept="*/*" multiple>
                    </label>
                    <button onclick="sendMessage()" class="send-btn" id="send-btn">Send</button>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
        <script>
            let clickCount = 0;
            let chatUnlocked = false;
            let currentRoom = null;
            let currentUsername = null;
            const CLICKS_REQUIRED = 7;
            let selectedFiles = [];
            let socket = null;
            
            // Initialize alert sound with a base64 encoded WAV file
            window.alertSound = new Audio();
            window.alertSound.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAB9AH0AfQB9';
            window.alertSound.volume = 0.5;

            const setupSection = document.getElementById('setup-section');
            const usernameInput = document.getElementById('username');
            const sessionKeyInput = document.getElementById('session-key');
            const joinBtn = document.getElementById('join-btn');
            const lockIcon = document.getElementById('lock-icon');
            const clickCountSpan = document.getElementById('click-count');
            const clickStatusDiv = document.getElementById('click-status');
            const unlockSection = document.getElementById('unlock-section');
            const unlockBtn = document.getElementById('unlock-btn');
            const messagesContainer = document.getElementById('messages-container');
            const initialStatus = document.getElementById('initial-status');
            const inputSection = document.getElementById('input-section');
            const messageInput = document.getElementById('message-input');
            const fileInput = document.getElementById('file-input');
            const fileListPreview = document.getElementById('file-list-preview');
            const sendBtn = document.getElementById('send-btn');

            function showStatus(message, isError = false) {
                console.log(isError ? `Error: ${message}` : `Status: ${message}`);
            }

            // Initialize WebSocket connection
            function initializeSocket() {
                socket = io();
                
                socket.on('connect', function() {
                    console.log('Connected to server');
                });
                
                socket.on('disconnect', function() {
                    console.log('Disconnected from server');
                });
                
                socket.on('new_message', function(data) {
                    appendMessage(data);
                    scrollToBottom();
                });
                
                socket.on('message_deleted', function(data) {
                    removeMessageFromUI(data.message_id);
                });
                
                socket.on('system_broadcast', function(data) {
                    appendSystemMessage(data);
                    scrollToBottom();
                });
                
                socket.on('command_response', function(data) {
                    appendCommandResponse(data);
                    scrollToBottom();
                });
                
                // Create audio element for alert sounds
                window.alertSound = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBTGH0fPTgjMGHm7A7+OZSA0PVqzn77BdGAg+ltryxnMpBSl+zPLaizsIGGS57OihUBELTKXh8bllHgU2jdXzzn0vBSF1xe/glEILElyx6OyrWBUIQ5zd8sFuJAUuhM/z1YU2Bhxqvu7mnEoODlOq5O+zYBoGPJPY88p2KwUme8rx3I4+CRZiturqpVITC0mi4PK8aB8GM4nU8tGAMQYfcsLu45ZFDBFYr+ftrVoXCECY3PLEcSYELIHO8diJOQcZaLvt559NEAxPqOPwtmMcBjiP1/PMeS0GI3fH8OCRQQoUXrTp66hVFApGnt/yvmwhBTCG0fPTgjQGHW/A7eSaRw0PVqzl77BeGQc9ltvyxnUoBSh+zPDaizsIGGS56+mjTxELTKXh8bllHgU1jdT0z3wvBSJ0xe/glEILElyx6OyrWRUIRJve8sFuJAUug8/y1oU2Bhxqvu7mnEoPDVKq5PC0YRoGPJLY88p3KgUme8rx3I4+CRVht+rqpVMSC0mh4fK8aiAFM4nU8tGAMQYfccPu45ZFDBFYr+ftrVwWCECY3PLEcSYGK4DN8tiIOQcZZ7zs56BODwxPpuPxtmQcBjiP1/PMeywGI3fH8OCRQQsUXrTp66hWEwlGnt/zvmwhBTCG0fPTgzQHHG/A7eSaSA0PVqvm77BeGQc9ltrzxnUoBSh9y/HajDsIF2W56+mjUREKTKPh8blnHgU1jdT0z3wvBSF0xPDglEILElux6eyrWRUJQ5vd88FwJAQug8/y1oY2Bhxqvu3mnEoPDVKp5PC0YRsGO5LY88p3KgUmecnw3Y4/CBVhtuvqpVMSC0mh4PG9aiAFMojT89GAMgUfccLv45dGCxFYrufur1sXCECY3PLEcicFKoDN8tiIOQcZZ7rs56BODwxPpuPxtmQdBTiP1/PMey0FI3bH8OCRQQsUXbPq66hWEwlGnt/zvmwhBjCG0PPTgzQHHG3A7eSaSA0PVKzm77BeGQc9ltrzyHQpBSh9y/HajDwIF2S46+mjUREKTKPg8btmHwU1jdT0z30vBSF0xPDglEQKElux6eyrWRUJQ5vd88NvJAQug8/y1oY3BRxqvu3mnEwODVGp5PC0YRsGO5HY88p3LAQlecrw3Y4/CBVhtuvqpVMSC0mh4PG9aiAFMojT89GBMQYfccLv45dGDRBYrufur1sYB0CX3fLEcicFKn/M8diKOQcZZ7vs56BOEQxPpuPxt2MdBTeP1/PNei4FI3bH8OCRQQsUXbPq66hWEwlGnt/zvmwhBjCF0fPTgzUGHG3A7eSaSA0PVKzm77BeGQc9ltrzyHQpBSh9y/HajDwIF2S46+mjUhEKS6Lg8btoHgU1jdT0z30vBSF0xPDglEQKElux6eyrWhQJQ5vd88NvJAQug8/y1oY3BRxpve3mnUsODVGp5PC0YhsGOpHY88p3LAQlecrw3Y8+CBVhtuvqpVMSC0mh4PG9aiAFMojT89GBMQYfccLv45dGDRBXr+fur1sYB0CX3fLEcycFKn/M8diKOQcZZ7vs56BOEQxPpuPxt2MdBTeP1/PNei4FI3bH8OCRQQsUXbPq66hWFAlFnt/zvmwhBjCF0fPTgzUGHG3A7eSaSA4OVKzm77BeGQc9ltrzyHUpBCh9y/HajDwIF2S46+mjUhEKS6Lg8btoHgU1jdT0z30wBCF0xPDglEQKElux6eyrWhQJQ5vd88NvJAUtg8/y1oY3BRxpve3mnUsODVGp5PC0YhsGOpHY88p3LAQlecrw3Y8+CBVhtuvqpVMSC0mh4PG9aiAFMojT89GBMQYfccLv45dGDRBXr+fur1sYB0CX3fLEcycFKn/M8diKOQcZZ7vs56BOEQxPpuPxt2MdBTeP1/PNei4FI3bH8OCRQQsUXbPq66hWFAlFnt/zvmwhBjCF0fPTgzUGHG3A7eSaSA4OVKzm77BeGQc9ltrzyHUpBCh9y/HajDwIF2S46+mjUhEKS6Lg8btoHgU1jdT0z30wBCF0xPDglEQKElux6eyrWhQJQ5vd88NvJAUtg8/y1oY3BRxpve3mnUsODVGp5PC0YhsGOpHY88p3LAQlecrw3Y8+CBVhtuvqpVMSC0mh4PG9aiAFMojT89GBMQYfccLv45dGDRBXr+fur1sYB0CX3fLEcycFKn/M8diKOQcZZ7vs56BOEQxPpuPxt2MdBTeP1/PNei4FI3bH8OCRQQsUXbPq66hWFAlFnt/zvmwhBjCF0fPTgzUGHG3A7eSaSA4OVKzm77BeGQc9ltrzyHUpBCh9y/HajDwIF2S46+mjUhEKS6Lg8btoHgU1jdT0z30wBCF0xPDglEQKElux6eyrWhQJQ5vd88NvJAUtg8/y1oY3BRxpve3mnUsODVGp5PC0YhsGAA==');
                window.alertSound.volume = 0.5;
            }

            // Force authentication on page load/reload
            window.addEventListener('load', function() {
                // Clear any stored authentication state
                sessionStorage.removeItem('authenticated');
                // Reset UI to initial state
                resetToInitialState();
                // Initialize WebSocket
                initializeSocket();
            });

            function resetToInitialState() {
                chatUnlocked = false;
                currentRoom = null;
                currentUsername = null;
                clickCount = 0;
                selectedFiles = [];
                
                setupSection.classList.remove('hidden');
                inputSection.style.display = 'none';
                unlockSection.style.display = 'none';
                
                usernameInput.value = '';
                sessionKeyInput.value = '';
                messageInput.value = '';
                usernameInput.disabled = false;
                sessionKeyInput.disabled = false;
                joinBtn.disabled = false;
                joinBtn.textContent = 'Join';
                unlockBtn.disabled = false;
                unlockBtn.textContent = 'Unlock Chat';
                lockIcon.textContent = '🔒';
                lockIcon.style.cursor = 'pointer';
                clickCountSpan.textContent = '0';
                clickStatusDiv.textContent = `Clicks: 0/${CLICKS_REQUIRED}`;
                
                messagesContainer.innerHTML = '<div class="status" id="initial-status">Enter your username and the session key to join the secure chat room.</div>';
                updateFileListPreview();
            }

            function clickLock() {
                if (chatUnlocked || !currentRoom) return;

                clickCount++;
                clickCountSpan.textContent = clickCount;
                clickStatusDiv.textContent = `Clicks: ${clickCount}/${CLICKS_REQUIRED}`;
                
                lockIcon.style.transform = 'scale(1.2)';
                setTimeout(() => { lockIcon.style.transform = 'scale(1)'; }, 100);

                if (clickCount >= CLICKS_REQUIRED) {
                    unlockSection.style.display = 'block';
                    lockIcon.textContent = '🔓';
                    lockIcon.style.cursor = 'default';
                    clickStatusDiv.textContent = `Ready to Unlock`;
                }
            }

            async function joinChat() {
                const username = usernameInput.value.trim();
                const sessionKey = sessionKeyInput.value.trim();
                
                if (!username) {
                    alert('Please enter a username.');
                    usernameInput.focus();
                    return;
                }
                if (!/^[a-zA-Z0-9_.-]+$/.test(username)) {
                     alert('Username can only contain letters, numbers, underscore, dot, and hyphen.');
                     usernameInput.focus();
                     return;
                }
                if (!sessionKey) {
                    alert('Please enter the session key.');
                    sessionKeyInput.focus();
                    return;
                }
                if (sessionKey.length !== 11 || !/^[0-9]+$/.test(sessionKey)) {
                    alert('Enter the Correct Key');
                    sessionKeyInput.focus();
                    return;
                }
                
                joinBtn.disabled = true;
                joinBtn.textContent = 'Joining...';
                showStatus('Attempting to join chat...');

                try {
                    const response = await fetch("{{ url_for('join_chat') }}", {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: username, session_key: sessionKey })
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        currentRoom = sessionKey;
                        currentUsername = username;
                        
                        // Join WebSocket room
                        socket.emit('join', {room: sessionKey, username: username});
                        
                        messagesContainer.innerHTML = '';
                        showStatus('Successfully joined chat. Click the lock 7 times to unlock.');
                        usernameInput.disabled = true;
                        sessionKeyInput.disabled = true;
                        joinBtn.textContent = 'Joined';
                        joinBtn.disabled = true;
                        lockIcon.style.cursor = 'pointer';
                        unlockBtn.disabled = false;
                        unlockBtn.textContent = 'Unlock Chat';
                        chatUnlocked = false;
                        inputSection.style.display = 'none';
                        setupSection.classList.remove('hidden');
                        
                        // Update mute status for the user
                        updateMuteStatus(username);

                    } else {
                        alert(data.message || `Failed to join chat (HTTP ${response.status})`);
                        showStatus(data.message || `Failed to join chat (HTTP ${response.status})`, true);
                        joinBtn.textContent = 'Join';
                        usernameInput.disabled = false;
                        sessionKeyInput.disabled = false;
                    }
                } catch (error) {
                    console.error('Join Chat Error:', error);
                    alert('Connection failed during join attempt. Check console for details.');
                    showStatus('Connection failed during join attempt.', true);
                    joinBtn.textContent = 'Join';
                    usernameInput.disabled = false;
                    sessionKeyInput.disabled = false;
                } finally {
                    joinBtn.disabled = false;
                }
            }

            async function unlockChat() {
                if (clickCount < CLICKS_REQUIRED) {
                    alert(`Click the lock ${CLICKS_REQUIRED} times first!`);
                    return;
                }
                if (!currentRoom) {
                    alert('You must join a chat room first!');
                    return;
                }
                
                unlockBtn.disabled = true;
                unlockBtn.textContent = 'Unlocking...';
                showStatus('Attempting to unlock chat...');

                try {
                    const response = await fetch("{{ url_for('unlock') }}", {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_key: currentRoom })
                    });
                    const data = await response.json();

                    if (response.ok && data.success) {
                        chatUnlocked = true;
                        inputSection.style.display = 'block';
                        unlockBtn.textContent = 'Chat Unlocked';
                        unlockSection.style.display = 'none';
                        setupSection.classList.add('hidden');
                        showStatus('Chat unlocked successfully.');
                        loadMessages();
                        messageInput.focus();
                    } else {
                        alert(data.message || `Failed to unlock chat (HTTP ${response.status})`);
                        showStatus(data.message || `Failed to unlock chat (HTTP ${response.status})`, true);
                        unlockBtn.textContent = 'Unlock Chat';
                        unlockBtn.disabled = false;
                    }
                } catch (error) {
                    console.error('Unlock Chat Error:', error);
                    alert('Connection failed during unlock attempt. Check console for details.');
                    showStatus('Connection failed during unlock attempt.', true);
                    unlockBtn.textContent = 'Unlock Chat';
                    unlockBtn.disabled = false;
                }
            }

            function updateFileListPreview() {
                fileListPreview.innerHTML = '';
                if (selectedFiles.length > 0) {
                    fileListPreview.style.display = 'block';
                    selectedFiles.forEach(file => {
                        const fileDiv = document.createElement('div');
                        fileDiv.textContent = file.name;
                        fileListPreview.appendChild(fileDiv);
                    });
                } else {
                    fileListPreview.style.display = 'none';
                }
            }

            fileInput.addEventListener('change', (event) => {
                selectedFiles = Array.from(event.target.files);
                updateFileListPreview();
            });

            // Drag and Drop functionality - now on the entire chat-container
            const chatContainer = document.getElementById('chat-interface');

            chatContainer.addEventListener('dragover', (event) => {
                event.preventDefault();
                // No visual feedback needed for dragover
            });

            chatContainer.addEventListener('drop', (event) => {
                event.preventDefault();
                if (event.dataTransfer.files.length > 0) {
                    selectedFiles = Array.from(event.dataTransfer.files);
                    updateFileListPreview();
                }
            });

            async function sendMessage() {
                if (!chatUnlocked || !currentRoom) {
                    alert('Chat is not unlocked or you are not in a room!');
                    return;
                }
                
                const message = messageInput.value.trim();
                
                if (!message && selectedFiles.length === 0) {
                    return;
                }
                
                if (message && selectedFiles.length > 0) {
                    alert('You can send either a text message OR file(s), not both at the same time.');
                    return;
                }
                
                sendBtn.disabled = true;
                sendBtn.textContent = 'Sending...';
                showStatus('Sending message/file(s)...');

                const formData = new FormData();
                formData.append('session_key', currentRoom);
                
                if (selectedFiles.length > 0) {
                    for (const file of selectedFiles) {
                        if (file.size > 16 * 1024 * 1024) { // 16 MB limit per file
                            alert(`File '${file.name}' exceeds the 16MB limit.`);
                            sendBtn.disabled = false;
                            sendBtn.textContent = 'Send';
                            showStatus('File size limit exceeded for one or more files.', true);
                            return;
                        }
                        formData.append('files[]', file);
                    }
                } else {
                    formData.append('message', message);
                }
                
                try {
                    const response = await fetch("{{ url_for('send_message') }}", {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        messageInput.value = '';
                        selectedFiles = [];
                        updateFileListPreview();
                        showStatus('Message/file(s) sent successfully.');
                        // Handle command response if present
                        if (data.command_response) {
                            appendCommandResponse(data.command_response);
                            scrollToBottom();
                        }
                    } else {
                        alert(data.message || `Failed to send message/file(s) (HTTP ${response.status})`);
                        showStatus(data.message || `Failed to send message/file(s) (HTTP ${response.status})`, true);
                    }
                } catch (error) {
                    console.error('Send Message/File Error:', error);
                    alert('Connection failed during send attempt. Check console for details.');
                    showStatus('Connection failed during send attempt.', true);
                } finally {
                    sendBtn.disabled = false;
                    sendBtn.textContent = 'Send';
                }
            }

            async function loadMessages() {
                if (!chatUnlocked || !currentRoom) return;

                try {
                    const response = await fetch(`{{ url_for('get_messages') }}?session_key=${currentRoom}`);
                    const data = await response.json();

                    if (response.ok && data.success) {
                        messagesContainer.innerHTML = '';
                        data.messages.forEach(msg => {
                            appendMessage(msg);
                        });
                        scrollToBottom();
                    } else {
                        console.error('Failed to load messages:', data.message);
                    }
                } catch (error) {
                    console.error('Load Messages Error:', error);
                }
            }

            function scrollToBottom() {
                const isAtBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop <= messagesContainer.clientHeight + 10;
                if (isAtBottom) {
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                }
            }

            function appendMessage(msg) {
                const messageDiv = document.createElement('div');
                let messageClass = `message ${msg.sender === currentUsername ? 'own-message' : ''}`;
                
                // Check for whisper message
                if (msg.whisper) {
                    messageClass += ' whisper-message';
                }
                
                // Check for alert message
                if (msg.alert) {
                    messageClass += ' alert-message';
                }
                
                messageDiv.className = messageClass;
                messageDiv.setAttribute('data-message-id', msg.id);

                const headerDiv = document.createElement('div');
                headerDiv.className = 'message-header';
                let senderDisplay = msg.sender;
                if (msg.whisper) {
                    senderDisplay += ' (whisper)';
                }
                if (msg.alert) {
                    senderDisplay += ' (ALERT)';
                }
                
                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'message-actions';
                
                const copyBtn = document.createElement('button');
                copyBtn.className = 'action-btn';
                copyBtn.textContent = '📋';
                copyBtn.title = 'Copy';
                copyBtn.onclick = () => copyMessage(msg);
                
                actionsDiv.appendChild(copyBtn);
                
                // Only show delete button for own messages or if user is demigod
                if (msg.sender === currentUsername || currentUsername.toLowerCase() === 'demigod') {
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'action-btn';
                    deleteBtn.textContent = '🗑️';
                    deleteBtn.title = 'Delete';
                    deleteBtn.onclick = () => deleteMessage(msg.id);
                    actionsDiv.appendChild(deleteBtn);
                }
                
                headerDiv.innerHTML = `<span>${senderDisplay}</span><span>${new Date(msg.timestamp).toLocaleTimeString()}</span>`;
                messageDiv.appendChild(headerDiv);
                messageDiv.appendChild(actionsDiv);

                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';

                if (msg.type === 'text') {
                    contentDiv.textContent = msg.content;
                } else if (msg.type === 'file' && msg.files && msg.files.length > 0) {
                    msg.files.forEach(file => {
                        const fileLink = document.createElement('a');
                        fileLink.href = `{{ url_for('download_file', file_id='') }}${file.file_id}`;
                        fileLink.className = 'file-link';
                        fileLink.textContent = `Download: ${file.filename} (${(file.size / 1024).toFixed(2)} KB)`;
                        fileLink.target = '_blank';
                        fileLink.download = file.filename;
                        contentDiv.appendChild(fileLink);
                        contentDiv.appendChild(document.createElement('br'));
                    });
                }
                messageDiv.appendChild(contentDiv);
                messagesContainer.appendChild(messageDiv);
                
                // Auto-remove whisper messages after 5 seconds
                if (msg.whisper) {
                    setTimeout(() => {
                        if (messageDiv.parentNode) {
                            messageDiv.parentNode.removeChild(messageDiv);
                        }
                    }, 5000);
                }
            }

            // Track if the current user has muted sounds
            let soundsMuted = false;
            
            // Function to update mute status from server
            function updateMuteStatus(username) {
                fetch(`/check_mute_status?username=${encodeURIComponent(username)}`)
                    .then(response => response.json())
                    .then(data => {
                        soundsMuted = data.muted;
                        console.log(`Sound notifications ${soundsMuted ? 'muted' : 'active'} for user ${username}`);
                    })
                    .catch(error => console.error('Error checking mute status:', error));
            }
            
            function appendSystemMessage(data) {
                // Skip displaying alerts for impersonate commands
                if (data.message && data.message.includes('User identity changed') || 
                    data.message && data.message.includes('User identity restored')) {
                    return; // Don't show any alert for impersonate commands
                }
                
                // For cloak and uncloak, don't show popup alerts anymore
                // Just add to the message container and auto-remove after 3 seconds
                
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message system-message';
                
                const headerDiv = document.createElement('div');
                headerDiv.className = 'message-header';
                headerDiv.innerHTML = `<span>SYSTEM</span><span>${new Date(data.timestamp).toLocaleTimeString()}</span>`;
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.textContent = data.message;
                
                messageDiv.appendChild(headerDiv);
                messageDiv.appendChild(contentDiv);
                messagesContainer.appendChild(messageDiv);
                
                // Play sound alert if not muted
                if (!soundsMuted && window.alertSound) {
                    window.alertSound.play().catch(e => console.error('Error playing sound:', e));
                }
                
                // Auto-remove system messages after 3 seconds
                setTimeout(() => {
                    if (messageDiv.parentNode) {
                        messageDiv.parentNode.removeChild(messageDiv);
                    }
                }, 3000);
            }

            function appendCommandResponse(data) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message command-response';
                
                const headerDiv = document.createElement('div');
                headerDiv.className = 'message-header';
                headerDiv.innerHTML = `<span>COMMAND RESPONSE</span><span>${new Date().toLocaleTimeString()}</span>`;
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.textContent = data.message;
                
                messageDiv.appendChild(headerDiv);
                messageDiv.appendChild(contentDiv);
                messagesContainer.appendChild(messageDiv);
                
                // Play sound alert if not muted and it's not a mute command response
                if (!soundsMuted && window.alertSound && !data.message.includes('Sound notifications')) {
                    window.alertSound.play().catch(e => console.error('Error playing sound:', e));
                }
                
                // If this is a mute command response, update the mute status
                if (data.message.includes('Sound notifications')) {
                    soundsMuted = data.message.includes('muted');
                }
                
                // Auto-remove command responses after 3 seconds
                setTimeout(() => {
                    if (messageDiv.parentNode) {
                        messageDiv.parentNode.removeChild(messageDiv);
                    }
                }, 3000);
            }

            function copyMessage(msg) {
                let textToCopy = '';
                if (msg.type === 'text') {
                    textToCopy = msg.content;
                } else if (msg.type === 'file' && msg.files && msg.files.length > 0) {
                    textToCopy = msg.files.map(file => `${file.filename} (${(file.size / 1024).toFixed(2)} KB)`).join(', ');
                }
                
                if (textToCopy) {
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        // Visual feedback - find the copy button that was clicked
                        const messageElement = document.querySelector(`[data-message-id="${msg.id}"]`);
                        if (messageElement) {
                            const copyBtn = messageElement.querySelector('.action-btn[title="Copy"]');
                            if (copyBtn) {
                                const originalText = copyBtn.textContent;
                                copyBtn.textContent = '✓';
                                setTimeout(() => {
                                    copyBtn.textContent = originalText;
                                }, 1000);
                            }
                        }
                    }).catch(err => {
                        console.error('Failed to copy text: ', err);
                        alert('Failed to copy message');
                    });
                }
            }

            async function deleteMessage(messageId) {
                if (!confirm('Are you sure you want to delete this message?')) {
                    return;
                }
                
                try {
                    const response = await fetch("{{ url_for('delete_message') }}", {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            message_id: messageId, 
                            session_key: currentRoom 
                        })
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        // Message will be removed via WebSocket event
                        showStatus('Message deleted successfully.');
                    } else {
                        alert(data.message || 'Failed to delete message');
                        showStatus(data.message || 'Failed to delete message', true);
                    }
                } catch (error) {
                    console.error('Delete Message Error:', error);
                    alert('Connection failed during delete attempt.');
                    showStatus('Connection failed during delete attempt.', true);
                }
            }

            function removeMessageFromUI(messageId) {
                const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                if (messageElement) {
                    messageElement.remove();
                }
            }

            messageInput.addEventListener('keypress', function(event) {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            });

        </script>
    </body>
    </html>
    """, session_url=session_url)

# --- WebSocket Events ---
@socketio.on('join')
def on_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    print(f"[INFO] User '{username}' joined WebSocket room '{room}'")

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    username = data['username']
    leave_room(room)
    print(f"[INFO] User '{username}' left WebSocket room '{room}'")

# --- Chat API Routes ---
@app.route("/join_chat", methods=["POST"])
def join_chat():
    data = request.get_json()
    username = data.get("username")
    session_key = data.get("session_key")

    if not username or not session_key:
        return jsonify({"success": False, "message": "Username and session key are required."}), 400

    # Check if global kill switch is active
    if is_global_session_killed():
        return jsonify({"success": False, "message": "All sessions have been terminated."}), 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 403

    if session_key not in chat_sessions:
        chat_sessions[session_key] = {"messages": []}

    session["chat_session_key"] = session_key
    session["username"] = username

    # Update session activity
    if current_session_url:
        update_session_activity(current_session_url)

    return jsonify({"success": True, "message": "Joined chat successfully."})

@app.route("/unlock", methods=["POST"])
def unlock():
    data = request.get_json()
    session_key = data.get("session_key")

    if not session_key or session_key != session.get("chat_session_key"):
        return jsonify({"success": False, "message": "Invalid session key or not joined."}), 400

    # Check if global kill switch is active
    if is_global_session_killed():
        return jsonify({"success": False, "message": "All sessions have been terminated."}), 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 403

    session["chat_unlocked"] = True
    print("[INFO] Chat session ", session_key, " unlocked for user ", session.get("username"))

    # Update session activity
    if current_session_url:
        update_session_activity(current_session_url)

    return jsonify({"success": True, "message": "Chat unlocked."})

@app.route("/check_mute_status")
def check_mute_status():
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "message": "Username is required."}), 400
    
    # Check if the user has muted alert sounds
    is_muted = username in muted_users
    
    return jsonify({"success": True, "muted": is_muted})

@app.route("/send_message", methods=["POST"])
def send_message():
    session_key = request.form.get("session_key")
    # Use the normalized username stored in session
    sender = session.get("username")
    files_uploaded = request.files.getlist("files[]")
    message_text = request.form.get("message")

    if not sender or not session_key or session_key != session.get("chat_session_key") or not session.get("chat_unlocked"):
        return jsonify({"success": False, "message": "Unauthorized or chat not unlocked."}), 403

    # Check if global kill switch is active and handle revive command
    if is_global_session_killed():
        if message_text and message_text.strip() == "/revive" and str(sender).lower() == "demigod":
            command_result = command_handler.process_command(message_text.strip(), sender, session_key, session.get("current_session_url_component"))
            if command_result and command_result['broadcast']:
                socketio.emit('system_broadcast', command_result['broadcast'], broadcast=True)
            return jsonify({
                "success": True, 
                "message": "Command executed.",
                "command_response": command_result
            })
        return jsonify({"success": False, "message": "All sessions have been terminated."}), 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 403

    # Process commands using the command handler
    if message_text and message_text.strip().startswith('/'):
        command_result = command_handler.process_command(
            message_text.strip(), 
            sender, 
            session_key, 
            current_session_url
        )
        
        if command_result:
            # Broadcast system message if required
            if command_result.get('broadcast'):
                socketio.emit('system_broadcast', command_result['broadcast'], room=session_key)
            
            return jsonify({
                "success": command_result['success'], 
                "message": "Command executed." if command_result['success'] else command_result['message'],
                "command_response": command_result
            })

    # Check for whisper message
    is_whisper = False
    if message_text and message_text.startswith("!whisper "):
        is_whisper = True
        message_text = message_text[9:]  # Remove "!whisper " prefix

    # Check for alert message
    is_alert = False
    if message_text and message_text.startswith("!alert "):
        is_alert = True
        message_text = message_text[7:]  # Remove "!alert " prefix

    chat_key = generate_key_from_session(session_key)
    timestamp = datetime.now().isoformat()

    if message_text:
        if files_uploaded:
            return jsonify({"success": False, "message": "Cannot send both text and files at the same time."}), 400
        
        encrypted_message = encrypt_message(message_text, chat_key)
        msg_id = secrets.token_urlsafe(8)
        
        # Use display name (impersonated name if set)
        display_name = get_display_name(sender)
        
        message_data = {
            "id": msg_id,
            "sender": display_name,
            "type": "text",
            "content": encrypted_message,
            "timestamp": timestamp,
            "whisper": is_whisper,
            "alert": is_alert
        }
        chat_sessions[session_key]["messages"].append(message_data)
        
        # Decrypt for WebSocket broadcast
        decrypted_message_data = {
            "id": msg_id,
            "sender": display_name,
            "type": "text",
            "content": decrypt_message(encrypted_message, chat_key),
            "timestamp": timestamp,
            "whisper": is_whisper,
            "alert": is_alert
        }
        
        # Broadcast to all users in the room via WebSocket
        socketio.emit('new_message', decrypted_message_data, room=session_key)
        
        message_type = "alert" if is_alert else ("whisper" if is_whisper else "text")
        print(f"[INFO] Encrypted {message_type} message sent in session '{session_key}' by '{sender}' (displayed as '{display_name}')")
        
        # Update session activity
        if current_session_url:
            update_session_activity(current_session_url)
        
        return jsonify({"success": True, "message": "Message sent."})

    elif files_uploaded:
        file_metadata_list = []
        for file_obj in files_uploaded:
            file_id = secrets.token_urlsafe(16)
            filename = file_obj.filename
            file_data = file_obj.read()
            encrypted_file_data = encrypt_file(file_data, chat_key)
            
            if encrypted_file_data is None:
                return jsonify({"success": False, "message": f"Failed to encrypt file {filename}."}), 500

            files[file_id] = {
                "data": encrypted_file_data,
                "filename": filename,
                "mimetype": file_obj.mimetype,
                "size": len(file_data)
            }
            file_metadata_list.append({"file_id": file_id, "filename": filename, "size": len(file_data)})
            print(f"[INFO] Encrypted file '{filename}' stored with ID '{file_id}'")

        msg_id = secrets.token_urlsafe(8)
        
        # Use display name (impersonated name if set)
        display_name = get_display_name(sender)
        
        message_data = {
            "id": msg_id,
            "sender": display_name,
            "type": "file",
            "files": file_metadata_list,
            "timestamp": timestamp,
            "whisper": False,  # Files cannot be whisper messages
            "alert": False     # Files cannot be alert messages
        }
        chat_sessions[session_key]["messages"].append(message_data)
        
        # Broadcast to all users in the room via WebSocket
        socketio.emit('new_message', message_data, room=session_key)
        
        print(f"[INFO] Encrypted file(s) message sent in session '{session_key}' by '{sender}' (displayed as '{display_name}')")
        
        # Update session activity
        if current_session_url:
            update_session_activity(current_session_url)
        
        return jsonify({"success": True, "message": "File(s) sent."})

    return jsonify({"success": False, "message": "No message or file provided."}), 400

@app.route("/delete_message", methods=["POST"])
def delete_message():
    data = request.get_json()
    message_id = data.get("message_id")
    session_key = data.get("session_key")
    sender = session.get("username")

    if not sender or not session_key or session_key != session.get("chat_session_key") or not session.get("chat_unlocked"):
        return jsonify({"success": False, "message": "Unauthorized or chat not unlocked."}), 403

    # Check if global kill switch is active
    if is_global_session_killed():
        return jsonify({"success": False, "message": "All sessions have been terminated."}), 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 403

    if session_key not in chat_sessions:
        return jsonify({"success": False, "message": "Chat session not found."}), 404

    # Find and remove the message
    messages = chat_sessions[session_key]["messages"]
    message_found = False
    for i, msg in enumerate(messages):
        if msg["id"] == message_id:
            # Check if user can delete this message (own message or demigod)
            # For impersonated messages, check against the real sender name
            real_sender = sender
            display_name = get_display_name(sender)
            if msg["sender"] == display_name or str(sender).lower() == "demigod":
                del messages[i]
                message_found = True
                
                # Broadcast deletion to all users in the room via WebSocket
                socketio.emit('message_deleted', {"message_id": message_id}, room=session_key)
                
                print(f"[INFO] Message '{message_id}' deleted by '{sender}' in session '{session_key}'")
                break
            else:
                return jsonify({"success": False, "message": "You can only delete your own messages."}), 403

    if not message_found:
        return jsonify({"success": False, "message": "Message not found."}), 404

    # Update session activity
    if current_session_url:
        update_session_activity(current_session_url)

    return jsonify({"success": True, "message": "Message deleted."})

@app.route("/get_messages", methods=["GET"])
def get_messages():
    session_key = request.args.get("session_key")
    sender = session.get("username")

    if not sender or not session_key or session_key != session.get("chat_session_key"):
        return jsonify({"success": False, "message": "Unauthorized or not joined."}), 403

    # Check if global kill switch is active
    if is_global_session_killed():
        return jsonify({"success": False, "message": "All sessions have been terminated."}), 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 403

    if session_key not in chat_sessions:
        return jsonify({"success": False, "message": "Chat session not found."}), 404

    chat_key = generate_key_from_session(session_key)
    decrypted_messages = []
    current_time = datetime.now()

    # Filter out expired whisper messages and decrypt
    valid_messages = []
    for msg in chat_sessions[session_key]["messages"]:
        # Check if whisper message has expired (5 seconds)
        if msg.get("whisper", False):
            msg_time = datetime.fromisoformat(msg["timestamp"])
            if (current_time - msg_time).total_seconds() > 5:
                continue  # Skip expired whisper messages
        valid_messages.append(msg)

    # Update the messages list to remove expired whispers
    chat_sessions[session_key]["messages"] = valid_messages

    for msg in valid_messages:
        if msg["type"] == "text":
            decrypted_content = decrypt_message(msg["content"], chat_key)
            decrypted_messages.append({
                "id": msg["id"],
                "sender": msg["sender"],
                "type": "text",
                "content": decrypted_content,
                "timestamp": msg["timestamp"],
                "whisper": msg.get("whisper", False),
                "alert": msg.get("alert", False)
            })
        elif msg["type"] == "file":
            decrypted_messages.append({
                "id": msg["id"],
                "sender": msg["sender"],
                "type": "file",
                "files": msg["files"],
                "timestamp": msg["timestamp"],
                "whisper": msg.get("whisper", False),
                "alert": msg.get("alert", False)
            })

    # Update session activity
    if current_session_url:
        update_session_activity(current_session_url)

    return jsonify({"success": True, "messages": decrypted_messages})

@app.route("/download_file/<file_id>")
def download_file(file_id):
    sender = session.get("username")
    session_key = session.get("chat_session_key")

    if not sender or not session_key:
        return "Unauthorized", 403

    # Check if global kill switch is active
    if is_global_session_killed():
        return "All sessions have been terminated", 403

    # Check session expiry
    current_session_url = session.get("current_session_url_component")
    if current_session_url and is_session_expired(current_session_url):
        return "Session expired. Please log in again.", 403

    if file_id not in files:
        return "File not found", 404

    file_info = files[file_id]
    chat_key = generate_key_from_session(session_key)
    decrypted_data = decrypt_file(file_info["data"], chat_key)

    if decrypted_data is None:
        return "Failed to decrypt file", 500

    # Update session activity
    if current_session_url:
        update_session_activity(current_session_url)

    return send_file(
        io.BytesIO(decrypted_data),
        as_attachment=True,
        download_name=file_info["filename"],
        mimetype=file_info["mimetype"]
    )

if __name__ == "__main__":
    print("[INFO] Starting Enhanced Stealth Messaging App with Command Module...")
    print("[INFO] Access via: http://localhost:8080/?user=demigod or http://localhost:8080/?user=human")
    print("[INFO] Default passwords: demigod='Demig0d@', human='secret123'")
    print("[INFO] Features: WebSocket real-time messaging, Copy/Delete messages, Session expiry (30 min)")
    print("[INFO] Admin commands: /nuke, /revive, /cloak, /uncloak, /impersonate, /help, /status")
    print("[INFO] Special messages: !whisper [message] (temporary message), !alert [message] (high-priority alert)")
    socketio.run(app, host="localhost", port=65100, debug=True, allow_unsafe_werkzeug=True)
