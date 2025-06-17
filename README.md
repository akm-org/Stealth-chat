# 🕵️ Stealth Messaging App

A secure, ephemeral messaging application built with Flask that prioritizes privacy and security. Features end-to-end encryption, auto-expiring messages, and no persistent data storage.

![Stealth Messaging App](https://img.shields.io/badge/Python-3.7+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![Security](https://img.shields.io/badge/Encryption-AES--256--GCM-red.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🚀 Quick Start

```bash
# Clone or download the repository
git clone <your-repo-url>
cd stealth-messaging-app

# Install dependencies
pip install flask cryptography qrcode[pil]

# Run the application
python stealth_app.py

# Access the app
# Open http://localhost:5000 in your browser
# Login with password: secret123
```

## 🔐 Key Features

### **Authentication & Security**
- 🔑 **Password Protection**: Login required with password `secret123`
- ⏰ **Session Management**: 30-minute auto-logout with activity tracking
- 🛡️ **AES-256-GCM Encryption**: Military-grade encryption for all messages and files
- 🔒 **Secure Sessions**: Flask-based session management with cryptographic tokens
- 🗑️ **No Persistent Storage**: All data stored in memory only - nothing saved to disk

### **Real-Time Chat System**
- 💬 **Live Messaging**: Real-time chat with 1-second polling
- 👥 **Multi-User Support**: Up to 5 users per chat room
- 🔢 **Session Keys**: 11-digit numeric keys for easy sharing
- 📱 **QR Code Generation**: Instant QR codes for mobile sharing
- 👻 **Whisper Messages**: Auto-deleting messages (disappear after 5 seconds)
- 🗑️ **Message Deletion**: Users can delete their own messages with confirmation

### **File Sharing**
- 📁 **Drag & Drop**: Upload files by dragging anywhere on the interface
- 📎 **Multiple Files**: Select and upload multiple files simultaneously
- 💾 **Size Limit**: 16MB per file for optimal performance
- 🔐 **Encrypted Storage**: Files encrypted and securely stored
- 📥 **Smart Downloads**: Proper MIME type detection and headers
- 🗂️ **File Management**: Delete uploaded files along with messages

### **User Experience**
- 🎨 **Cyberpunk Theme**: Electric blue and black aesthetic
- 📱 **Responsive Design**: Works seamlessly on mobile and desktop
- ⚡ **Smooth Animations**: Polished hover effects and transitions  
- 🖥️ **Fixed Input**: Chat input stays at bottom like modern messengers
- 🎯 **Global Drag Zone**: Drop files anywhere on the interface
- 👀 **Hover Controls**: Delete buttons appear on message hover

## 📋 Technical Specifications

### **Encryption**
- **Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 100,000 iterations
- **Random Generation**: Cryptographically secure random tokens
- **Key Size**: 32-byte encryption keys

### **Security Measures**
- Input validation for session keys (11 digits only)
- User ownership verification for message deletion
- Secure file upload with size limits
- Session timeout and activity tracking
- No data persistence (memory-only storage)

### **Performance**
- **Polling Rate**: 1-second message refresh
- **File Limit**: 16MB per upload
- **User Limit**: 5 users per chat room
- **Session Timeout**: 30 minutes of inactivity

## 🛠️ Installation & Setup

### **Prerequisites**
- Python 3.7 or higher
- pip package manager

### **Dependencies**
```bash
pip install flask cryptography qrcode[pil]
```

### **Running the Application**
```bash
python stealth_app.py
```

The app will start on `http://localhost:5000`

## 📖 Usage Guide

### **1. Initial Setup**
1. Run the application
2. Navigate to `http://localhost:5000`
3. Enter password: `secret123`

### **2. Creating a Chat Room**
1. Click "Generate QR Code" 
2. Share the QR code or copy the chat URL
3. Note down the 11-digit session key

### **3. Joining a Chat**
1. Enter your username
2. Input the 11-digit session key
3. Click "Join Chat"

### **4. Messaging**
- **Regular Messages**: Type and press Enter or click Send
- **Whisper Messages**: Start message with `!whisper` for auto-delete
- **File Upload**: Drag files anywhere or use the file selector
- **Delete Messages**: Hover over your messages and click the × button

### **5. File Sharing**
- Drag and drop files anywhere on the chat interface
- Multiple file selection supported
- Files are encrypted and can be downloaded by all users
- Delete files by deleting the associated message

## 🔧 Configuration

### **Security Settings**
```python
# In stealth_app.py, you can modify:
LOGIN_PASSWORD = "secret123"        # Change login password
SESSION_TIMEOUT = 30 * 60           # Session timeout (30 minutes)
MAX_FILE_SIZE = 16 * 1024 * 1024    # Max file size (16MB)
MAX_USERS_PER_CHAT = 5              # Users per chat room
```

### **Server Settings**
```python
# At the bottom of stealth_app.py:
app.run(host='0.0.0.0', port=5000, debug=False)
```

## 🚨 Security Considerations

### **What's Secure**
- ✅ All messages and files are encrypted with AES-256-GCM
- ✅ No data is permanently stored (memory-only)
- ✅ Session management with automatic timeout
- ✅ User authentication required
- ✅ Cryptographically secure random generation

### **Limitations**
- ⚠️ Data is lost when server restarts (by design)
- ⚠️ Single server instance (no clustering)
- ⚠️ Basic password authentication (consider stronger auth for production)
- ⚠️ HTTP only (consider HTTPS for production deployment)

## 🎨 Customization

### **Theming**
The app uses CSS custom properties for easy theming:
```css
:root {
    --primary-color: #00ffff;      /* Electric blue */
    --bg-color: #000000;           /* Black background */
    --text-color: #ffffff;         /* White text */
    --font-family: 'Courier New';  /* Monospace font */
}
```

### **Adding Features**
The modular Flask structure makes it easy to add:
- Additional message types
- User management features  
- File type restrictions
- Custom encryption methods
- Database persistence (if needed)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This application is designed for educational and legitimate privacy purposes. Users are responsible for complying with all applicable laws and regulations in their jurisdiction. The developers assume no responsibility for misuse of this software.

## 🐛 Troubleshooting

### **Common Issues**

**"Module not found" errors:**
```bash
pip install flask cryptography qrcode[pil]
```

**Port already in use:**
```bash
# Change port in stealth_app.py or kill existing process
lsof -ti:5000 | xargs kill -9  # macOS/Linux
```

**Session timeouts:**
- Sessions expire after 30 minutes of inactivity
- Simply log in again to continue

**File upload failures:**
- Check file size (16MB limit)
- Ensure sufficient disk space
- Try refreshing the page

### **Getting Help**
- Check the [Issues](../../issues) page for known problems
- Create a new issue with detailed error information
- Include Python version and operating system details

---

**Built with ❤️ and Python • Prioritizing Privacy and Security**