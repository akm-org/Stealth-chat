#!/usr/bin/env python3
"""
Stealth Messaging App - Complete Flask Implementation
Run with: python stealth_app.py
"""

import os
import io
import base64
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, send_file
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import qrcode

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# In-memory storage
chat_sessions = {}
files = {}
session_activity = {}

# Constants
SALT = b"stealth_salt"
SESSION_TIMEOUT = 30  # minutes
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

def generate_key_from_session_key(session_key):
    """Generate AES key from 11-digit session key"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    return kdf.derive(session_key.encode())

def encrypt_data(data, key):
    """Encrypt data using AES-256-GCM"""
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    encryptor = cipher.encryptor()
    
    if isinstance(data, str):
        data = data.encode()
    
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(nonce + encryptor.tag + ciphertext).decode()

def decrypt_data(encrypted_data, key):
    """Decrypt data using AES-256-GCM"""
    try:
        data = base64.b64decode(encrypted_data.encode())
        nonce = data[:12]
        tag = data[12:28]
        ciphertext = data[28:]
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
        
        return decryptor.update(ciphertext) + decryptor.finalize()
    except Exception:
        return None

def check_session_expired():
    """Check if session has expired"""
    user_id = session.get('authenticated')
    if user_id and user_id in session_activity:
        last_activity = session_activity[user_id]
        if datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT):
            session.clear()
            del session_activity[user_id]
            return True
    return False

def update_activity():
    """Update user activity timestamp"""
    user_id = session.get('authenticated')
    if user_id:
        session_activity[user_id] = datetime.now()

@app.route('/')
def login():
    """Login page"""
    if check_session_expired():
        return redirect(url_for('login'))
    
    if session.get('authenticated'):
        return redirect(url_for('setup'))
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stealth Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                background: #000; color: #00ffff; font-family: 'Courier New', monospace; 
                min-height: 100vh; display: flex; align-items: center; justify-content: center;
                background: radial-gradient(circle, #001122 0%, #000000 100%);
            }
            .container { 
                background: rgba(0,20,40,0.8); border: 2px solid #00ffff; 
                padding: 30px; border-radius: 10px; text-align: center;
                box-shadow: 0 0 20px rgba(0,255,255,0.3);
                min-width: 300px;
            }
            h1 { margin-bottom: 20px; text-shadow: 0 0 10px #00ffff; }
            input { 
                background: #001122; border: 1px solid #00ffff; color: #00ffff; 
                padding: 10px; margin: 10px 0; width: 100%; border-radius: 5px;
                font-family: inherit;
            }
            input:focus { outline: none; box-shadow: 0 0 10px rgba(0,255,255,0.5); }
            button { 
                background: #003366; border: 1px solid #00ffff; color: #00ffff; 
                padding: 10px 20px; margin: 10px 0; cursor: pointer; border-radius: 5px;
                width: 100%; font-family: inherit; transition: all 0.3s;
            }
            button:hover { background: #004488; box-shadow: 0 0 10px rgba(0,255,255,0.5); }
            .error { color: #ff4444; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ STEALTH ACCESS ⚡</h1>
            <form method="POST">
                <input type="password" name="password" placeholder="Enter Access Code" required autofocus>
                <button type="submit">AUTHENTICATE</button>
            </form>
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
        </div>
    </body>
    </html>
    """
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'secret123':
            user_id = secrets.token_hex(16)
            session['authenticated'] = user_id
            session_activity[user_id] = datetime.now()
            return redirect(url_for('setup'))
        else:
            return render_template_string(html, error="ACCESS DENIED"), 403
    
    return render_template_string(html)

@app.route('/', methods=['POST'])
def login_post():
    return login()

@app.route('/setup')
def setup():
    """Chat setup page"""
    if check_session_expired():
        return redirect(url_for('login'))
    
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    update_activity()
    
    # Generate chat session
    session_id = secrets.token_urlsafe(16)
    chat_url = f"{request.host_url}chat/{session_id}"
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(chat_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="cyan", back_color="black")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()
    
    session['chat_url'] = session_id
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Chat Setup</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                background: #000; color: #00ffff; font-family: 'Courier New', monospace; 
                min-height: 100vh; padding: 20px;
                background: radial-gradient(circle, #001122 0%, #000000 100%);
            }
            .container { 
                max-width: 600px; margin: 0 auto; text-align: center;
                background: rgba(0,20,40,0.8); border: 2px solid #00ffff; 
                padding: 30px; border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,255,255,0.3);
            }
            h1 { margin-bottom: 20px; text-shadow: 0 0 10px #00ffff; }
            .url-box { 
                background: #001122; border: 1px solid #00ffff; 
                padding: 15px; margin: 20px 0; border-radius: 5px;
                word-break: break-all; font-size: 14px;
            }
            .qr-code { margin: 20px 0; }
            button, a { 
                background: #003366; border: 1px solid #00ffff; color: #00ffff; 
                padding: 10px 20px; margin: 10px; cursor: pointer; border-radius: 5px;
                text-decoration: none; display: inline-block; font-family: inherit;
                transition: all 0.3s;
            }
            button:hover, a:hover { background: #004488; box-shadow: 0 0 10px rgba(0,255,255,0.5); }
            @media (max-width: 600px) {
                .container { margin: 10px; padding: 20px; }
                .url-box { font-size: 12px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ CHAT SESSION READY ⚡</h1>
            <p>Share this URL with participants:</p>
            <div class="url-box">{{ chat_url }}</div>
            
            <div class="qr-code">
                <p>Or scan QR code:</p>
                <img src="data:image/png;base64,{{ qr_code }}" alt="QR Code" style="max-width: 200px; margin: 10px;">
            </div>
            
            <a href="/chat/{{ session_id }}">ENTER CHAT</a>
            <button onclick="copyUrl()">COPY URL</button>
            <a href="/logout">LOGOUT</a>
        </div>
        
        <script>
            function copyUrl() {
                navigator.clipboard.writeText("{{ chat_url }}").then(() => {
                    alert("URL copied to clipboard!");
                });
            }
        </script>
    </body>
    </html>
    """
    
    return render_template_string(html, chat_url=chat_url, qr_code=qr_b64, session_id=session_id)

@app.route('/chat/<session_id>')
def chat(session_id):
    """Chat interface"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stealth Chat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                background: #000; color: #00ffff; font-family: 'Courier New', monospace; 
                height: 100vh; display: flex; flex-direction: column;
                background: radial-gradient(circle, #001122 0%, #000000 100%);
            }
            .header { 
                background: rgba(0,20,40,0.9); border-bottom: 1px solid #00ffff; 
                padding: 10px; text-align: center; text-shadow: 0 0 10px #00ffff;
            }
            .chat-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
            .join-form { 
                padding: 20px; text-align: center; border-bottom: 1px solid #00ffff;
                background: rgba(0,20,40,0.5);
            }
            .join-form input { 
                background: #001122; border: 1px solid #00ffff; color: #00ffff; 
                padding: 8px; margin: 5px; border-radius: 3px; font-family: inherit;
            }
            .join-form button { 
                background: #003366; border: 1px solid #00ffff; color: #00ffff; 
                padding: 8px 15px; margin: 5px; cursor: pointer; border-radius: 3px;
                font-family: inherit; transition: all 0.3s;
            }
            .join-form button:hover { background: #004488; }
            .messages { 
                flex: 1; overflow-y: auto; padding: 10px; 
                scrollbar-width: thin; scrollbar-color: #00ffff #001122;
                padding-bottom: 200px; /* Space for fixed input area */
            }
            .message { 
                margin: 8px 0; padding: 8px; background: rgba(0,20,40,0.6); 
                border-radius: 5px; border-left: 3px solid #00ffff;
                position: relative; group;
            }
            .message:hover .delete-btn { opacity: 1; }
            .delete-btn {
                position: absolute; top: 5px; right: 5px; 
                background: #660000; border: 1px solid #ff4444; color: #ff4444;
                padding: 2px 6px; border-radius: 3px; cursor: pointer;
                opacity: 0; transition: opacity 0.3s; font-size: 12px;
            }
            .delete-btn:hover { background: #880000; }
            .whisper { border-left-color: #ffff00; background: rgba(40,40,0,0.3); }
            .input-area { 
                position: fixed; bottom: 0; left: 0; right: 0;
                border-top: 1px solid #00ffff; padding: 10px; 
                background: rgba(0,20,40,0.95); backdrop-filter: blur(10px);
                z-index: 1000;
            }
            .input-row { display: flex; gap: 10px; margin-bottom: 10px; }
            .input-row input { 
                flex: 1; background: #001122; border: 1px solid #00ffff; color: #00ffff; 
                padding: 8px; border-radius: 3px; font-family: inherit;
            }
            .input-row button { 
                background: #003366; border: 1px solid #00ffff; color: #00ffff; 
                padding: 8px 15px; cursor: pointer; border-radius: 3px;
                font-family: inherit; transition: all 0.3s; white-space: nowrap;
            }
            .input-row button:hover { background: #004488; }
            .file-drop { 
                border: 2px dashed #00ffff; padding: 20px; text-align: center; 
                border-radius: 5px; margin-bottom: 10px; transition: all 0.3s;
                background: rgba(0,30,60,0.3);
            }
            .file-drop.dragover { border-color: #ffff00; background: rgba(40,40,0,0.3); }
            .drag-overlay {
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,255,255,0.1); border: 3px dashed #00ffff;
                display: none; z-index: 9999; align-items: center; justify-content: center;
                font-size: 24px; text-align: center; color: #00ffff;
                text-shadow: 0 0 20px #00ffff;
            }
            .drag-overlay.active { display: flex; }
            .file-list { margin: 10px 0; }
            .file-item { 
                display: flex; justify-content: space-between; align-items: center;
                padding: 5px; background: rgba(0,20,40,0.5); margin: 5px 0; border-radius: 3px;
            }
            .hidden { display: none; }
            @media (max-width: 600px) {
                .input-row { flex-direction: column; }
                .input-row button { width: 100%; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h2>⚡ STEALTH CHAT ⚡</h2>
        </div>
        
        <div class="chat-container">
            <div id="joinForm" class="join-form">
                <input type="text" id="username" placeholder="Username" required>
                <input type="text" id="sessionKey" placeholder="11-digit session key" pattern="[0-9]{11}" required>
                <button onclick="joinChat()">JOIN CHAT</button>
            </div>
            
            <div id="chatInterface" class="hidden">
                <div id="messages" class="messages"></div>
                
                <div class="input-area">
                    <div class="file-drop" id="fileDrop">
                        <p>📁 Drag & drop files here or click to select</p>
                        <input type="file" id="fileInput" multiple style="display: none;">
                    </div>
                    <div id="fileList" class="file-list"></div>
                    
                    <div class="input-row">
                        <input type="text" id="messageInput" placeholder="Type message... (use !whisper for whisper messages)">
                        <button onclick="sendMessage()">SEND</button>
                        <button onclick="sendFiles()">SEND FILES</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="dragOverlay" class="drag-overlay">
            <div>
                <h2>⚡ DROP FILES TO UPLOAD ⚡</h2>
                <p>Release to add files to chat</p>
            </div>
        </div>
        
        <script>
            let username = '';
            let sessionKey = '';
            let sessionId = '{{ session_id }}';
            let selectedFiles = [];
            let messageInterval;
            let dragCounter = 0;
            
            // Global drag and drop
            document.addEventListener('dragenter', (e) => {
                e.preventDefault();
                dragCounter++;
                if (dragCounter === 1) {
                    document.getElementById('dragOverlay').classList.add('active');
                }
            });
            
            document.addEventListener('dragleave', (e) => {
                e.preventDefault();
                dragCounter--;
                if (dragCounter === 0) {
                    document.getElementById('dragOverlay').classList.remove('active');
                }
            });
            
            document.addEventListener('dragover', (e) => {
                e.preventDefault();
            });
            
            document.addEventListener('drop', (e) => {
                e.preventDefault();
                dragCounter = 0;
                document.getElementById('dragOverlay').classList.remove('active');
                
                if (document.getElementById('chatInterface').classList.contains('hidden')) {
                    return; // Don't handle drops if not in chat
                }
                
                handleFiles(e.dataTransfer.files);
            });
            
            // File drag and drop
            const fileDrop = document.getElementById('fileDrop');
            const fileInput = document.getElementById('fileInput');
            const fileList = document.getElementById('fileList');
            
            fileDrop.addEventListener('click', () => fileInput.click());
            fileDrop.addEventListener('dragover', (e) => {
                e.preventDefault();
                fileDrop.classList.add('dragover');
            });
            fileDrop.addEventListener('dragleave', () => {
                fileDrop.classList.remove('dragover');
            });
            fileDrop.addEventListener('drop', (e) => {
                e.preventDefault();
                fileDrop.classList.remove('dragover');
                handleFiles(e.dataTransfer.files);
            });
            fileInput.addEventListener('change', (e) => {
                handleFiles(e.target.files);
            });
            
            function handleFiles(files) {
                for (let file of files) {
                    if (file.size > 16 * 1024 * 1024) {
                        alert(`File ${file.name} is too large (max 16MB)`);
                        continue;
                    }
                    selectedFiles.push(file);
                }
                updateFileList();
            }
            
            function updateFileList() {
                fileList.innerHTML = '';
                selectedFiles.forEach((file, index) => {
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.innerHTML = `
                        <span>${file.name} (${(file.size/1024/1024).toFixed(2)}MB)</span>
                        <button onclick="removeFile(${index})" style="background: #660000; border: 1px solid #ff4444; color: #ff4444; padding: 2px 8px; border-radius: 3px;">×</button>
                    `;
                    fileList.appendChild(div);
                });
            }
            
            function removeFile(index) {
                selectedFiles.splice(index, 1);
                updateFileList();
            }
            
            function joinChat() {
                username = document.getElementById('username').value.trim();
                sessionKey = document.getElementById('sessionKey').value.trim();
                
                if (!username || !sessionKey) {
                    alert('Please enter username and session key');
                    return;
                }
                
                if (!/^[0-9]{11}$/.test(sessionKey)) {
                    alert('Session key must be exactly 11 digits');
                    return;
                }
                
                fetch('/join_chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_id: sessionId,
                        username: username,
                        session_key: sessionKey
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('joinForm').classList.add('hidden');
                        document.getElementById('chatInterface').classList.remove('hidden');
                        startMessagePolling();
                    } else {
                        alert(data.error || 'Failed to join chat');
                    }
                });
            }
            
            function sendMessage() {
                const messageInput = document.getElementById('messageInput');
                const message = messageInput.value.trim();
                
                if (!message) return;
                
                fetch('/send_message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_key: sessionKey,
                        message: message,
                        username: username
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        messageInput.value = '';
                    } else {
                        alert(data.error || 'Failed to send message');
                    }
                });
            }
            
            function sendFiles() {
                if (selectedFiles.length === 0) {
                    alert('No files selected');
                    return;
                }
                
                const formData = new FormData();
                formData.append('session_key', sessionKey);
                formData.append('username', username);
                
                selectedFiles.forEach(file => {
                    formData.append('files', file);
                });
                
                fetch('/upload_files', {
                    method: 'POST',
                    body: formData
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        selectedFiles = [];
                        updateFileList();
                        fileInput.value = '';
                    } else {
                        alert(data.error || 'Failed to upload files');
                    }
                });
            }
            
            function startMessagePolling() {
                messageInterval = setInterval(() => {
                    fetch(`/get_messages?session_key=${sessionKey}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            displayMessages(data.messages);
                        }
                    });
                }, 1000);
            }
            
            function displayMessages(messages) {
                const messagesDiv = document.getElementById('messages');
                messagesDiv.innerHTML = '';
                
                messages.forEach(msg => {
                    const div = document.createElement('div');
                    div.className = 'message' + (msg.whisper ? ' whisper' : '');
                    
                    let content = `<strong>${msg.username}</strong> (${msg.timestamp}): `;
                    
                    if (msg.type === 'file') {
                        content += `📁 <a href="/download_file/${msg.file_id}" style="color: #00ffff;">${msg.filename}</a> (${msg.filesize})`;
                    } else {
                        content += msg.message;
                    }
                    
                    if (msg.whisper) {
                        content += ' <em>(whisper)</em>';
                    }
                    
                    // Add delete button
                    content += `<button class="delete-btn" onclick="deleteMessage('${msg.id}')">×</button>`;
                    
                    div.innerHTML = content;
                    messagesDiv.appendChild(div);
                });
                
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
            
            function deleteMessage(messageId) {
                if (!confirm('Delete this message?')) return;
                
                fetch('/delete_message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_key: sessionKey,
                        message_id: messageId,
                        username: username
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        alert(data.error || 'Failed to delete message');
                    }
                });
            }
            
            // Enter key to send message
            document.getElementById('messageInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
            
            // Enter key to join chat
            document.getElementById('sessionKey').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    joinChat();
                }
            });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(html, session_id=session_id)

@app.route('/join_chat', methods=['POST'])
def join_chat():
    """Join chat session"""
    data = request.get_json()
    session_id = data.get('session_id')
    username = data.get('username')
    session_key = data.get('session_key')
    
    if not all([session_id, username, session_key]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    if not session_key.isdigit() or len(session_key) != 11:
        return jsonify({'success': False, 'error': 'Session key must be 11 digits'})
    
    # Initialize chat session if not exists
    if session_key not in chat_sessions:
        chat_sessions[session_key] = {
            'users': [],
            'messages': []
        }
    
    # Check if maximum users reached
    if len(chat_sessions[session_key]['users']) >= 5:
        return jsonify({'success': False, 'error': 'Chat room is full (max 5 users)'})
    
    # Add user if not already in session
    if username not in chat_sessions[session_key]['users']:
        chat_sessions[session_key]['users'].append(username)
    
    return jsonify({'success': True})

@app.route('/send_message', methods=['POST'])
def send_message():
    """Send message to chat"""
    data = request.get_json()
    session_key = data.get('session_key')
    message = data.get('message')
    username = data.get('username')
    
    if not all([session_key, message, username]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    if session_key not in chat_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'})
    
    # Check if whisper message
    is_whisper = message.startswith('!whisper ')
    if is_whisper:
        message = message[9:]  # Remove !whisper prefix
    
    # Encrypt message
    key = generate_key_from_session_key(session_key)
    encrypted_message = encrypt_data(message, key)
    
    message_data = {
        'id': secrets.token_hex(8),
        'username': username,
        'message': encrypted_message,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'whisper': is_whisper,
        'whisper_time': datetime.now() if is_whisper else None,
        'type': 'text'
    }
    
    chat_sessions[session_key]['messages'].append(message_data)
    
    return jsonify({'success': True})

@app.route('/upload_files', methods=['POST'])
def upload_files():
    """Upload files to chat"""
    session_key = request.form.get('session_key')
    username = request.form.get('username')
    
    if not all([session_key, username]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    if session_key not in chat_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'})
    
    uploaded_files = request.files.getlist('files')
    if not uploaded_files:
        return jsonify({'success': False, 'error': 'No files uploaded'})
    
    key = generate_key_from_session_key(session_key)
    
    for file in uploaded_files:
        if file.filename == '':
            continue
            
        if len(file.read()) > MAX_FILE_SIZE:
            return jsonify({'success': False, 'error': f'File {file.filename} too large'})
        
        file.seek(0)  # Reset file pointer
        file_data = file.read()
        
        # Encrypt file data
        encrypted_data = encrypt_data(file_data, key)
        
        file_id = secrets.token_hex(16)
        files[file_id] = {
            'data': encrypted_data,
            'filename': file.filename,
            'size': len(file_data),
            'mimetype': file.mimetype or 'application/octet-stream'
        }
        
        # Add file message
        message_data = {
            'id': secrets.token_hex(8),
            'username': username,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'whisper': False,
            'type': 'file',
            'file_id': file_id,
            'filename': file.filename,
            'filesize': f"{len(file_data)/1024/1024:.2f}MB"
        }
        
        chat_sessions[session_key]['messages'].append(message_data)
    
    return jsonify({'success': True})

@app.route('/delete_message', methods=['POST'])
def delete_message():
    """Delete message from chat"""
    data = request.get_json()
    session_key = data.get('session_key')
    message_id = data.get('message_id')
    username = data.get('username')
    
    if not all([session_key, message_id, username]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    if session_key not in chat_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'})
    
    # Find and remove the message
    messages = chat_sessions[session_key]['messages']
    for i, msg in enumerate(messages):
        if msg['id'] == message_id:
            # Check if user owns the message or if it's a file, also delete from files storage
            if msg['username'] == username:
                if msg.get('type') == 'file' and msg.get('file_id') in files:
                    del files[msg['file_id']]
                messages.pop(i)
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'You can only delete your own messages'})
    
    return jsonify({'success': False, 'error': 'Message not found'})

@app.route('/get_messages')
def get_messages():
    """Get messages for chat session"""
    session_key = request.args.get('session_key')
    
    if not session_key or session_key not in chat_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'})
    
    messages = chat_sessions[session_key]['messages']
    key = generate_key_from_session_key(session_key)
    
    # Filter out expired whisper messages and decrypt
    current_time = datetime.now()
    filtered_messages = []
    
    for msg in messages:
        # Remove whisper messages older than 5 seconds
        if msg.get('whisper') and msg.get('whisper_time'):
            if current_time - msg['whisper_time'] > timedelta(seconds=5):
                continue
        
        # Decrypt message if it's text
        if msg['type'] == 'text':
            decrypted_message = decrypt_data(msg['message'], key)
            if decrypted_message:
                msg_copy = msg.copy()
                msg_copy['message'] = decrypted_message.decode()
                filtered_messages.append(msg_copy)
        else:
            filtered_messages.append(msg)
    
    return jsonify({'success': True, 'messages': filtered_messages})

@app.route('/download_file/<file_id>')
def download_file(file_id):
    """Download and decrypt file"""
    if file_id not in files:
        return "File not found", 404
    
    # Get session key from referer or request
    session_key = request.args.get('session_key')
    if not session_key:
        # Try to extract from any active session
        for sk in chat_sessions.keys():
            session_key = sk
            break
    
    if not session_key:
        return "Session not found", 400
    
    file_info = files[file_id]
    key = generate_key_from_session_key(session_key)
    
    # Decrypt file data
    decrypted_data = decrypt_data(file_info['data'], key)
    if not decrypted_data:
        return "Failed to decrypt file", 500
    
    return send_file(
        io.BytesIO(decrypted_data),
        as_attachment=True,
        download_name=file_info['filename'],
        mimetype=file_info['mimetype']
    )

@app.route('/logout')
def logout():
    """Logout user"""
    user_id = session.get('authenticated')
    if user_id and user_id in session_activity:
        del session_activity[user_id]
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    print("🚀 Starting Stealth Messaging App...")
    print("📍 Access at: http://localhost:5000")
    print("🔑 Login password: secret123")
    print("⚡ Ready for stealth communications!")
    app.run(debug=True, host='0.0.0.0', port=5000)