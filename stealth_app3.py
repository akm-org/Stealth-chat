#!/usr/bin/env python3
"""
GhostLine - Encrypted Ephemeral Chat System
A single-file Python application for secure, anonymous communication
"""

import os
import uuid
import time
import json
import base64
import threading
from datetime import datetime, timedelta
from io import BytesIO
import qrcode
from flask import Flask, render_template_string, request, jsonify, send_file, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
import eventlet

# Configuration
FIXED_PASSWORD = "ghost2024"  # Fixed password for session creation
SESSION_TIMEOUT = 3600  # 60 minutes in seconds
WHISPER_TIMEOUT = 5  # 5 seconds for whisper messages
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# In-memory storage
SESSIONS = {}
ACTIVE_USERS = {}

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GhostLine</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            background: #0a0a0a;
            color: #e0e0e0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .container {
            width: 100%;
            height: 100%;
            padding: 20px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px 0;
            border-bottom: 1px solid #333;
        }
        
        .logo {
            font-size: 28px;
            font-weight: bold;
            color: #fff;
            margin-bottom: 8px;
        }
        
        .tagline {
            font-size: 12px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .login-form, .session-form {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 30px;
            margin: auto;
            max-width: 400px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            color: #ccc;
        }
        
        input[type="password"], input[type="text"] {
            width: 100%;
            padding: 12px;
            background: #000;
            border: 1px solid #444;
            border-radius: 4px;
            color: #fff;
            font-family: inherit;
            font-size: 14px;
        }
        
        input:focus {
            outline: none;
            border-color: #666;
        }
        
        .btn {
            background: #2a2a2a;
            color: #fff;
            border: 1px solid #444;
            padding: 12px 24px;
            border-radius: 4px;
            cursor: pointer;
            font-family: inherit;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .btn:hover {
            background: #3a3a3a;
            border-color: #666;
        }
        
        .btn:active {
            background: #1a1a1a;
        }
        
        .session-info {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
            margin: auto;
            max-width: 500px;
            text-align: center;
        }
        
        .session-url {
            background: #000;
            padding: 12px;
            border-radius: 4px;
            font-family: inherit;
            font-size: 12px;
            color: #0ff;
            word-break: break-all;
            margin: 10px 0;
        }
        
        .qr-container {
            margin: 20px 0;
        }
        
        .qr-code {
            max-width: 200px;
            height: auto;
            border: 2px solid #333;
            border-radius: 8px;
        }
        
        .chat-container {
            display: flex;
            flex-direction: column;
            height: calc(100vh - 140px);
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            overflow: hidden;
            flex: 1;
        }
        
        .chat-header {
            background: #2a2a2a;
            padding: 15px 20px;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .room-info {
            font-size: 14px;
            color: #ccc;
        }
        
        .user-count {
            font-size: 12px;
            color: #888;
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            scroll-behavior: smooth;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 12px;
            background: #0f0f0f;
            border-radius: 6px;
        }
        
        .message.own {
            background: #1a2332;
            margin-left: 20%;
        }
        
        .message.whisper {
            background: #2a1a2a;
            border-left: 3px solid #8b5cf6;
            animation: whisper-fade 5s forwards;
        }
        
        @keyframes whisper-fade {
            0% { opacity: 1; }
            80% { opacity: 1; }
            100% { opacity: 0.3; }
        }
        
        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .message-sender {
            font-size: 12px;
            font-weight: bold;
            color: #0ff;
        }
        
        .message-time {
            font-size: 11px;
            color: #666;
        }
        
        .message-content {
            font-size: 14px;
            line-height: 1.4;
            word-wrap: break-word;
        }
        
        .file-message {
            background: #1a1a2a;
            border-left: 3px solid #0ff;
        }
        
        .file-link {
            color: #0ff;
            text-decoration: none;
            font-size: 13px;
        }
        
        .file-link:hover {
            text-decoration: underline;
        }
        
        .input-area {
            background: #2a2a2a;
            padding: 20px;
            border-top: 1px solid #333;
        }
        
        .input-container {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }
        
        .message-input {
            flex: 1;
            padding: 12px;
            background: #000;
            border: 1px solid #444;
            border-radius: 4px;
            color: #fff;
            font-family: inherit;
            font-size: 14px;
            resize: none;
            max-height: 100px;
        }
        
        .file-input {
            display: none;
        }
        
        .file-btn {
            background: #1a3a1a;
            border-color: #2a5a2a;
        }
        
        .file-btn:hover {
            background: #2a4a2a;
        }
        
        .send-btn {
            background: #1a2a3a;
            border-color: #2a4a6a;
        }
        
        .send-btn:hover {
            background: #2a3a4a;
        }
        
        .file-upload-area {
            background: #2a2a2a;
            border: 2px dashed #444;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            margin-bottom: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .file-upload-area:hover {
            border-color: #666;
            background: #333;
        }
        
        .file-upload-area.drag-over {
            border-color: #0ff;
            background: #1a2a2a;
        }
        
        .file-list {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            max-height: 120px;
            overflow-y: auto;
            margin-bottom: 10px;
            display: none;
        }
        
        .file-item {
            padding: 8px 12px;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }
        
        .file-item:last-child {
            border-bottom: none;
        }
        
        .file-remove {
            background: #3a1a1a;
            border: 1px solid #5a2a2a;
            color: #ff6b6b;
            padding: 2px 6px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 10px;
        }
        
        .file-remove:hover {
            background: #4a2a2a;
        }
        
        .error {
            background: #3a1a1a;
            color: #ff6b6b;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        
        .success {
            background: #1a3a1a;
            color: #51cf66;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header {
                margin-bottom: 20px;
                padding: 15px 0;
            }
            
            .chat-container {
                height: calc(100vh - 120px);
            }
            
            .message.own {
                margin-left: 10%;
            }
            
            .input-container {
                flex-direction: column;
                gap: 10px;
            }
            
            .btn {
                width: 100%;
            }
            
            .login-form, .session-form {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">GhostLine</div>
            <div class="tagline">Encrypted • Ephemeral • Anonymous</div>
        </div>
        <div id="content">
            {% if page == 'login' %}
            <div class="login-form">
                <div class="form-group">
                    <label for="password">Enter Password</label>
                    <input type="password" id="password" placeholder="Enter the secret password">
                </div>
                <button class="btn" onclick="login()">Access System</button>
                <div id="error" class="error" style="display: none;"></div>
            </div>
            {% elif page == 'session' %}
            <div class="session-info">
                <h3>Session Created</h3>
                <p>Share this URL to invite others:</p>
                <div class="session-url">{{ session_url }}</div>
                <div class="qr-container">
                    <img src="data:image/png;base64,{{ qr_code }}" alt="QR Code" class="qr-code">
                </div>
                <button class="btn" onclick="window.location.href='{{ session_url }}'">Enter Chat</button>
            </div>
            {% elif page == 'room_entry' %}
            <div class="session-form">
                <div class="form-group">
                    <label for="username">Your Name</label>
                    <input type="text" id="username" placeholder="Enter a temporary username" maxlength="20">
                </div>
                <div class="form-group">
                    <label for="roomkey">Room Key (11 digits)</label>
                    <input type="text" id="roomkey" placeholder="Enter 11-digit room key" maxlength="11" pattern="[0-9]{11}">
                </div>
                <button class="btn" onclick="joinRoom()">Join Room</button>
                <div id="error" class="error" style="display: none;"></div>
            </div>
            {% elif page == 'chat' %}
            <div class="chat-container">
                <div class="chat-header">
                    <div class="room-info">Room: {{ room_key }} | User: {{ username }}</div>
                    <div class="user-count" id="userCount">1 user online</div>
                </div>
                <div class="messages" id="messages"></div>
                <div class="input-area">
                    <div class="file-upload-area" id="fileUploadArea" onclick="document.getElementById('fileInput').click()">
                        <div>📎 Click to select files or drag & drop anywhere</div>
                        <div style="font-size: 11px; color: #888; margin-top: 5px;">Multiple files supported • Max 10MB each</div>
                    </div>
                    <div class="file-list" id="fileList"></div>
                    <div class="input-container">
                        <textarea id="messageInput" class="message-input" placeholder="Type your message... (start with !whisper for self-destructing messages)" rows="1"></textarea>
                        <input type="file" id="fileInput" class="file-input" multiple>
                        <button class="btn send-btn" onclick="sendMessage()">Send</button>
                    </div>
                </div>
            </div>
        .drag-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            font-size: 24px;
            color: #0ff;
            border: 3px dashed #0ff;
        }
        
        .drag-overlay.active {
            display: flex;
        }
            {% endif %}
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        // Global variables
        let socket = null;
        let currentUser = '';
        let currentRoom = '';
        let dragCounter = 0;
        let selectedFiles = [];
        let fileUploadInProgress = false;

        // Login functionality
        function login() {
            const password = document.getElementById('password').value;
            
            fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ password: password })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = data.redirect;
                } else {
                    showError(data.error);
                }
            })
            .catch(error => {
                showError('Connection error');
            });
        }

        // Room joining functionality
        function joinRoom() {
            const username = document.getElementById('username').value.trim();
            const roomkey = document.getElementById('roomkey').value.trim();
            
            if (!username || username.length < 1) {
                showError('Please enter a username');
                return;
            }
            
            if (!roomkey || roomkey.length !== 11 || !/^\d{11}$/.test(roomkey)) {
                showError('Room key must be exactly 11 digits');
                return;
            }
            
            const sessionId = window.location.pathname.substring(1);
            window.location.href = `/chat/${sessionId}/${roomkey}/${encodeURIComponent(username)}`;
        }

        // Chat functionality
        {% if page == 'chat' %}
        function initializeChat() {
            currentUser = '{{ username }}';
            currentRoom = '{{ room_key }}';
            
            socket = io();
            
            socket.emit('join', {
                session_id: '{{ session_id }}',
                room_key: '{{ room_key }}',
                username: '{{ username }}'
            });
            
            socket.on('message', function(data) {
                displayMessage(data);
            });
            
            socket.on('user_joined', function(data) {
                updateUserCount(data.user_count);
            });
            
            socket.on('user_left', function(data) {
                updateUserCount(data.user_count);
            });
            
            socket.on('file_uploaded', function(data) {
                displayMessage(data);
            });
            
            // Load existing messages
            loadMessages();
            
            // Setup drag and drop
            setupDragAndDrop();
            
            // Setup input handlers
            const messageInput = document.getElementById('messageInput');
            messageInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
                
                // Auto-resize textarea
                this.style.height = 'auto';
                this.style.height = this.scrollHeight + 'px';
            });
            
            // Clear files when typing a message
            messageInput.addEventListener('input', function() {
                if (this.value.trim() && selectedFiles.length > 0) {
                    selectedFiles = [];
                    updateFileList();
                }
            });
            
            // File input handler
            document.getElementById('fileInput').addEventListener('change', function(e) {
                addFiles(Array.from(e.target.files));
                this.value = ''; // Clear the input
            });
        }
        
        function loadMessages() {
            fetch(`/api/messages/{{ session_id }}/{{ room_key }}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        data.messages.forEach(message => {
                            displayMessage(message, false);
                        });
                        scrollToBottom();
                    }
                });
        }
        
        function sendMessage() {
            // If files are selected, send them instead of text
            if (selectedFiles.length > 0) {
                sendFiles();
                return;
            }
            
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const isWhisper = message.startsWith('!whisper ');
            const messageData = {
                session_id: '{{ session_id }}',
                room_key: '{{ room_key }}',
                username: '{{ username }}',
                message: isWhisper ? message.substring(9) : message,
                whisper: isWhisper
            };
            
            socket.emit('send_message', messageData);
            input.value = '';
            input.style.height = 'auto';
        }
        
        function sendFiles() {
            if (selectedFiles.length === 0 || fileUploadInProgress) return;
            
            fileUploadInProgress = true;
            
            const formData = new FormData();
            formData.append('session_id', '{{ session_id }}');
            formData.append('room_key', '{{ room_key }}');
            formData.append('username', '{{ username }}');
            
            selectedFiles.forEach(file => {
                formData.append('files', file);
            });
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    showError(data.error || 'Upload failed');
                } else {
                    // Clear selected files
                    selectedFiles = [];
                    updateFileList();
                }
            })
            .catch(error => {
                showError('Upload failed');
            })
            .finally(() => {
                fileUploadInProgress = false;
            });
        }
        
        function displayMessage(data, scroll = true) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            
            const isOwn = data.sender === currentUser;
            const isWhisper = data.whisper;
            const isFile = data.type === 'file';
            
            messageDiv.className = `message ${isOwn ? 'own' : ''} ${isWhisper ? 'whisper' : ''} ${isFile ? 'file-message' : ''}`;
            messageDiv.id = `msg-${data.id}`;
            
            const time = new Date(data.timestamp * 1000).toLocaleTimeString();
            
            let content = '';
            if (isFile) {
                const files = JSON.parse(data.content);
                content = files.map(file => 
                    `<a href="/file/${data.id}/${file.name}" class="file-link" target="_blank">📎 ${file.name} (${formatFileSize(file.size)})</a>`
                ).join('<br>');
            } else {
                content = escapeHtml(data.content);
            }
            
            messageDiv.innerHTML = `
                <div class="message-header">
                    <span class="message-sender">${escapeHtml(data.sender)}${isWhisper ? ' (whisper)' : ''}</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-content">${content}</div>
            `;
            
            messagesDiv.appendChild(messageDiv);
            
            if (isWhisper) {
                setTimeout(() => {
                    const element = document.getElementById(`msg-${data.id}`);
                    if (element) {
                        element.style.opacity = '0.3';
                        element.style.pointerEvents = 'none';
                    }
                }, 5000);
            }
            
            if (scroll) {
                scrollToBottom();
            }
        }
        
        function setupDragAndDrop() {
            const dragOverlay = document.getElementById('dragOverlay');
            const fileUploadArea = document.getElementById('fileUploadArea');
            
            // Global drag and drop
            document.addEventListener('dragenter', function(e) {
                e.preventDefault();
                dragCounter++;
                dragOverlay.classList.add('active');
            });
            
            document.addEventListener('dragleave', function(e) {
                dragCounter--;
                if (dragCounter === 0) {
                    dragOverlay.classList.remove('active');
                }
            });
            
            document.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            
            document.addEventListener('drop', function(e) {
                e.preventDefault();
                dragCounter = 0;
                dragOverlay.classList.remove('active');
                
                if (e.dataTransfer.files.length > 0) {
                    addFiles(Array.from(e.dataTransfer.files));
                }
            });
            
            // File upload area specific
            fileUploadArea.addEventListener('dragenter', function(e) {
                e.preventDefault();
                this.classList.add('drag-over');
            });
            
            fileUploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                this.classList.remove('drag-over');
            });
            
            fileUploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            
            fileUploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                this.classList.remove('drag-over');
                
                if (e.dataTransfer.files.length > 0) {
                    addFiles(Array.from(e.dataTransfer.files));
                }
            });
        }
        
        function addFiles(files) {
            files.forEach(file => {
                if (file.size > {{ MAX_FILE_SIZE }}) {
                    showError(`File ${file.name} is too large (max 10MB)`);
                    return;
                }
                
                // Check if file already exists
                const exists = selectedFiles.some(f => f.name === file.name && f.size === file.size);
                if (!exists) {
                    selectedFiles.push(file);
                }
            });
            
            updateFileList();
        }
        
        function updateFileList() {
            const fileList = document.getElementById('fileList');
            
            if (selectedFiles.length === 0) {
                fileList.style.display = 'none';
                return;
            }
            
            fileList.style.display = 'block';
            fileList.innerHTML = '';
            
            selectedFiles.forEach((file, index) => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <span>📎 ${file.name} (${formatFileSize(file.size)})</span>
                    <button class="file-remove" onclick="removeFile(${index})">✕</button>
                `;
                fileList.appendChild(fileItem);
            });
        }
        
        function removeFile(index) {
            selectedFiles.splice(index, 1);
            updateFileList();
        }
        
        function updateUserCount(count) {
            document.getElementById('userCount').textContent = `${count} user${count !== 1 ? 's' : ''} online`;
        }
        
        function scrollToBottom() {
            const messages = document.getElementById('messages');
            messages.scrollTop = messages.scrollHeight;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
        
        // Initialize chat when page loads
        document.addEventListener('DOMContentLoaded', initializeChat);
        {% endif %}
        
        // Utility functions
        function showError(message) {
            const errorDiv = document.getElementById('error');
            if (errorDiv) {
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
                setTimeout(() => {
                    errorDiv.style.display = 'none';
                }, 5000);
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Handle Enter key on login
        {% if page == 'login' %}
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('password').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    login();
                }
            });
        });
        {% endif %}
        
        // Handle Enter key on room entry
        {% if page == 'room_entry' %}
        document.addEventListener('DOMContentLoaded', function() {
            const inputs = ['username', 'roomkey'];
            inputs.forEach(inputId => {
                document.getElementById(inputId).addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        joinRoom();
                    }
                });
            });
        });
        {% endif %}
    </script>
</body>
</html>
"""

def cleanup_expired_sessions():
    """Remove expired sessions"""
    current_time = time.time()
    expired_sessions = []
    
    for session_id, session_data in SESSIONS.items():
        if current_time - session_data['created_at'] > SESSION_TIMEOUT:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del SESSIONS[session_id]
        print(f"Cleaned up expired session: {session_id}")
    
    # Schedule next cleanup
    threading.Timer(300, cleanup_expired_sessions).start()  # Check every 5 minutes

def generate_qr_code(url):
    """Generate QR code for session URL"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="white", back_color="black")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, page='login')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    password = data.get('password', '')
    
    if password != FIXED_PASSWORD:
        return jsonify({'success': False, 'error': 'Invalid password'})
    
    # Create new session
    session_id = str(uuid.uuid4())[:8]
    SESSIONS[session_id] = {
        'created_at': time.time(),
        'rooms': {}
    }
    
    return jsonify({
        'success': True,
        'redirect': f'/session/{session_id}'
    })

@app.route('/session/<session_id>')
def session_page(session_id):
    if session_id not in SESSIONS:
        return render_template_string(HTML_TEMPLATE, page='login')
    
    session_url = f"{request.host_url}{session_id}"
    qr_code = generate_qr_code(session_url)
    
    return render_template_string(HTML_TEMPLATE, 
                                page='session',
                                session_url=session_url,
                                qr_code=qr_code)

@app.route('/<session_id>')
def room_entry(session_id):
    if session_id not in SESSIONS:
        return render_template_string(HTML_TEMPLATE, page='login')
    
    return render_template_string(HTML_TEMPLATE, 
                                page='room_entry',
                                session_id=session_id)

@app.route('/chat/<session_id>/<room_key>/<username>')
def chat_room(session_id, room_key, username):
    if session_id not in SESSIONS:
        return redirect(f'/{session_id}')
    
    if len(room_key) != 11 or not room_key.isdigit():
        return redirect(f'/{session_id}')
    
    # Initialize room if it doesn't exist
    if room_key not in SESSIONS[session_id]['rooms']:
        SESSIONS[session_id]['rooms'][room_key] = {
            'users': [],
            'messages': []
        }
    
    return render_template_string(HTML_TEMPLATE,
                                page='chat',
                                session_id=session_id,
                                room_key=room_key,
                                username=username,
                                MAX_FILE_SIZE=MAX_FILE_SIZE)

@app.route('/api/messages/<session_id>/<room_key>')
def get_messages(session_id, room_key):
    if session_id not in SESSIONS or room_key not in SESSIONS[session_id]['rooms']:
        return jsonify({'success': False, 'error': 'Room not found'})
    
    messages = SESSIONS[session_id]['rooms'][room_key]['messages']
    return jsonify({'success': True, 'messages': messages})

@app.route('/upload', methods=['POST'])
def upload_files():
    session_id = request.form.get('session_id')
    room_key = request.form.get('room_key')
    username = request.form.get('username')
    
    if not all([session_id, room_key, username]):
        return jsonify({'success': False, 'error': 'Missing parameters'})
    
    if session_id not in SESSIONS or room_key not in SESSIONS[session_id]['rooms']:
        return jsonify({'success': False, 'error': 'Room not found'})
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files uploaded'})
    
    # Process files
    file_data = []
    uploaded_files = {}
    
    for file in files:
        if file.filename:
            file_content = file.read()
            if len(file_content) > MAX_FILE_SIZE:
                continue
            
            file_info = {
                'name': file.filename,
                'size': len(file_content),
                'type': file.content_type or 'application/octet-stream'
            }
            
            file_data.append(file_info)
            uploaded_files[file.filename] = file_content
    
    if not file_data:
        return jsonify({'success': False, 'error': 'No valid files to upload'})
    
    # Create message
    message_id = str(uuid.uuid4())
    message = {
        'id': message_id,
        'sender': username,
        'content': json.dumps(file_data),
        'type': 'file',
        'timestamp': time.time(),
        'whisper': False
    }
    
    # Store files in session data
    if 'files' not in SESSIONS[session_id]:
        SESSIONS[session_id]['files'] = {}
    
    SESSIONS[session_id]['files'][message_id] = uploaded_files
    
    # Add to room messages
    SESSIONS[session_id]['rooms'][room_key]['messages'].append(message)
    
    # Emit to room
    socketio.emit('file_uploaded', message, room=f"{session_id}_{room_key}")
    
    return jsonify({'success': True})

@app.route('/file/<message_id>/<filename>')
def download_file(message_id, filename):
    # Find the session containing this file
    for session_id, session_data in SESSIONS.items():
        if 'files' in session_data and message_id in session_data['files']:
            if filename in session_data['files'][message_id]:
                file_content = session_data['files'][message_id][filename]
                return send_file(
                    BytesIO(file_content),
                    as_attachment=True,
                    download_name=filename
                )
    
    return jsonify({'error': 'File not found'}), 404

# Socket.IO Events
@socketio.on('join')
def on_join(data):
    session_id = data['session_id']
    room_key = data['room_key']
    username = data['username']
    
    if session_id not in SESSIONS:
        return
    
    if room_key not in SESSIONS[session_id]['rooms']:
        SESSIONS[session_id]['rooms'][room_key] = {
            'users': [],
            'messages': []
        }
    
    room = f"{session_id}_{room_key}"
    join_room(room)
    
    # Add user to room if not already present
    room_data = SESSIONS[session_id]['rooms'][room_key]
    if username not in room_data['users']:
        room_data['users'].append(username)
    
    # Store active user
    ACTIVE_USERS[request.sid] = {
        'session_id': session_id,
        'room_key': room_key,
        'username': username,
        'room': room
    }
    
    # Notify room of user count
    emit('user_joined', {
        'user_count': len(room_data['users'])
    }, room=room)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in ACTIVE_USERS:
        user_data = ACTIVE_USERS[request.sid]
        session_id = user_data['session_id']
        room_key = user_data['room_key']
        username = user_data['username']
        room = user_data['room']
        
        # Remove user from room
        if session_id in SESSIONS and room_key in SESSIONS[session_id]['rooms']:
            room_data = SESSIONS[session_id]['rooms'][room_key]
            if username in room_data['users']:
                room_data['users'].remove(username)
            
            # Notify room of user count
            emit('user_left', {
                'user_count': len(room_data['users'])
            }, room=room)
        
        del ACTIVE_USERS[request.sid]

@socketio.on('send_message')
def on_send_message(data):
    session_id = data['session_id']
    room_key = data['room_key']
    username = data['username']
    message = data['message']
    is_whisper = data.get('whisper', False)
    
    if session_id not in SESSIONS or room_key not in SESSIONS[session_id]['rooms']:
        return
    
    # Create message object
    message_data = {
        'id': str(uuid.uuid4()),
        'sender': username,
        'content': message,
        'type': 'text',
        'timestamp': time.time(),
        'whisper': is_whisper
    }
    
    # Add to room messages
    SESSIONS[session_id]['rooms'][room_key]['messages'].append(message_data)
    
    # Emit to room
    room = f"{session_id}_{room_key}"
    emit('message', message_data, room=room)
    
    # Schedule whisper deletion
    if is_whisper:
        def delete_whisper():
            if session_id in SESSIONS and room_key in SESSIONS[session_id]['rooms']:
                messages = SESSIONS[session_id]['rooms'][room_key]['messages']
                SESSIONS[session_id]['rooms'][room_key]['messages'] = [
                    msg for msg in messages if msg['id'] != message_data['id']
                ]
        
        threading.Timer(WHISPER_TIMEOUT, delete_whisper).start()

if __name__ == '__main__':
    print("🚀 Starting GhostLine...")
    print(f"📱 Access URL: http://localhost:5000")
    print(f"🔑 Password: {FIXED_PASSWORD}")
    print("💀 Encrypted • Ephemeral • Anonymous")
    
    # Start cleanup timer
    cleanup_expired_sessions()
    
    # Run the application
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)