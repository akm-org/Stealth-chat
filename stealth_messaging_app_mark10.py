# app.py
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

# --- In-memory Storage ---
users = {}
chat_sessions = {}
messages = {}
files = {}
session_urls = {}
user_sessions = {}
global_session_killed = False
cloaked_sessions = set()
user_impersonations = {}
muted_users = set()

# --- Command Handler (Simplified) ---
class CommandHandler:
    def __init__(self):
        self.commands = {
            '/help': self.handle_help,
            '/status': self.handle_status,
            '/mute': self.handle_mute
        }

    def process_command(self, message_text, sender, session_key, current_session_url):
        if not message_text.startswith('/'):
            return None
        parts = message_text.strip().split(' ', 1)
        command = parts[0].lower()
        if command not in self.commands:
            return {'success': False, 'message': f'Unknown command: {command}. Type /help for available commands.'}
        return self.commands[command](parts[1] if len(parts) > 1 else '', sender, session_key, current_session_url)

    def handle_help(self, args, sender, session_key, current_session_url):
        help_text = """Available Commands:
/help - Show this help message
/status - Show current session status
/mute - Toggle sound notifications"""
        return {'success': True, 'message': help_text, 'broadcast': None}

    def handle_status(self, args, sender, session_key, current_session_url):
        status_info = [f"Username: {sender}", f"Session Key: {session_key}"]
        return {'success': True, 'message': '\n'.join(status_info), 'broadcast': None}

    def handle_mute(self, args, sender, session_key, current_session_url):
        if sender in muted_users:
            muted_users.remove(sender)
            status = "unmuted"
        else:
            muted_users.add(sender)
            status = "muted"
        return {'success': True, 'message': f'Sound notifications {status}.', 'broadcast': None}

command_handler = CommandHandler()

# --- User Initialization ---
def init_users():
    global users
    users = {
        "demigod": {
            "password": bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        },
        "human": {
            "password": bcrypt.hashpw("secret123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        }
    }

init_users()

# --- Cryptography Helpers ---
def generate_key_from_session(session_key, salt=None):
    if salt is None:
        salt = b"stealth_messaging_salt_v5"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return kdf.derive(session_key.encode("utf-8"))

def encrypt_message(message, key):
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(message.encode()) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode()

def decrypt_message(encrypted_message, key):
    try:
        data = base64.b64decode(encrypted_message)
        iv, tag, ciphertext = data[:12], data[12:28], data[28:]
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        return cipher.decryptor().update(ciphertext).decode()
    except Exception:
        return "[DECRYPTION FAILED]"

# --- Flask Routes ---
@app.route("/")
def index():
    user = request.args.get("user")
    if user not in users:
        return render_template_string("<html><body style='background:#000;color:#ff0044;text-align:center;padding-top:50px;'>ACCESS DENIED</body></html>")
    session.clear()
    return render_template_string("""
    <html><head><title>STEALTH LOGIN</title><style>
    body{background:#000;color:#ff0044;font-family:'Courier New';display:flex;justify-content:center;align-items:center;height:100vh}
    .login-container{border:2px solid #ff0044;padding:40px;border-radius:10px;background:rgba(255,0,68,.1)}
    input,button{background:#000;color:#ff0044;border:2px solid #ff0044;padding:10px;margin:10px 0;width:100%}
    button:hover{background:#ff0044;color:#000}
    </style></head><body>
    <div class='login-container'>
        <h2>Stealth Access</h2>
        <form method="POST" action="{{ url_for('login') }}">
            <input type="hidden" name="username" value="{{ user }}">
            <label>Access Code:</label>
            <input type="password" name="password" required>
            <button type="submit">Authenticate</button>
        </form>
    </div>
    </body></html>
    """, user=user)

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    lookup_username = 'demigod' if username.lower() == 'demigod' else username
    user_data = users.get(lookup_username)
    if user_data and bcrypt.checkpw(password.encode(), user_data["password"].encode()):
        session.update({
            "user": username,
            "username": lookup_username,
            "authenticated": True,
            "chat_url": "session_" + secrets.token_urlsafe(16)
        })
        session_urls[session["chat_url"]] = lookup_username
        return redirect(url_for("start"))
    return "ACCESS DENIED - Invalid Credentials", 403

@app.route("/start")
def start():
    if not session.get("authenticated"):
        return redirect(url_for("index"))
    return render_template_string("""
    <html><head><title>STEALTH READY</title><style>
    body{background:#000;color:#ff0044;font-family:'Courier New';display:flex;justify-content:center;align-items:center;height:100vh}
    form button{background:#000;color:#ff0044;border:2px solid #ff0044;padding:20px 40px;font-size:1.5em;cursor:pointer}
    form button:hover{background:#ff0044;color:#000}
    </style></head><body>
    <form method="POST" action="{{ url_for('setup') }}">
        <button type="submit">Initiate Session</button>
    </form>
    </body></html>
    """)

@app.route("/setup", methods=["POST"])
def setup():
    if not session.get("authenticated"):
        return redirect(url_for("index"))
    return render_template_string("""
    <html><head><title>CHAT PORTAL</title><style>
    body{background:#000;color:#ff0044;font-family:'Courier New';padding:40px}
    input{background:#000;color:#ff0044;border:1px solid #ff0044;padding:10px;width:100%}
    </style></head><body>
    <h2>Chat Portal Generated</h2>
    <p>Secure Chat URL:</p>
    <input value="{{ url }}" readonly onclick="this.select()">
    <a href="{{ url_for('chat_session', session_url=session_url_component) }}" style="color:#ff0044">Access Chat</a>
    </body></html>
    """, url=url_for("chat_session", session_url=session["chat_url"], _external=True), session_url_component=session["chat_url"])

@app.route("/<path:session_url>")
def chat_session(session_url):
    if session_url not in session_urls:
        return "INVALID OR EXPIRED SESSION", 404
    return render_template_string("""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>STEALTH CHAT</title>
    <style>
    body{margin:0;background:#000;color:#ff0044;font-family:'Courier New';height:100vh;display:flex;flex-direction:column}
    #messages{flex:1;overflow-y:auto;padding:10px;background:#111}
    #input-area{display:flex;padding:10px}
    input{flex:1;padding:10px;background:#000;color:#ff0044;border:1px solid #ff0044}
    button{background:#000;color:#ff0044;border:1px solid #ff0044;padding:10px;margin-left:10px}
    </style>
    </head><body>
    <div id="messages">Loading...</div>
    <div id="input-area">
        <input id="msg" placeholder="Type message..." autocomplete="off">
        <button onclick="sendMsg()">Send</button>
    </div>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
    const socket = io();
    const room = "{{ session_url }}";
    const username = prompt("Enter username:");
    socket.emit('join', {room, username});
    socket.on('new_message', (msg) => {
        const div = document.createElement('div');
        div.textContent = `[${new Date(msg.timestamp).toLocaleTimeString()}] ${msg.sender}: ${msg.content}`;
        document.getElementById('messages').appendChild(div);
    });
    function sendMsg() {
        const msg = document.getElementById('msg').value.trim();
        if (!msg) return;
        fetch('/send_message', {
            method: 'POST',
            body: new URLSearchParams({session_key: room, message: msg})
        });
        document.getElementById('msg').value = '';
    }
    </script>
    </body></html>
    """, session_url=session_url)

# --- API Routes ---
@app.route("/send_message", methods=["POST"])
def send_message():
    session_key = request.form.get("session_key")
    message = request.form.get("message")
    sender = session.get("username")
    if not sender or session_key != session.get("chat_url"):
        return jsonify({"success": False}), 403
    chat_key = generate_key_from_session(session_key)
    encrypted = encrypt_message(message, chat_key)
    msg_id = secrets.token_urlsafe(8)
    socketio.emit('new_message', {
        "id": msg_id,
        "sender": sender,
        "content": decrypt_message(encrypted, chat_key),
        "timestamp": datetime.now().isoformat()
    }, room=session_key)
    return jsonify({"success": True})

# --- SocketIO Events ---
@socketio.on('join')
def on_join(data):
    join_room(data['room'])

if __name__ == "__main__":
    print("🚀 Stealth Chat running at http://localhost:8080/?user=demigod (password: admin123)")
    socketio.run(app, host="0.0.0.0", port=8080, debug=True)
