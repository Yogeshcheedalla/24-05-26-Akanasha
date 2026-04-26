# Akansha: Your Personal Autonomous AI Assistant

Akansha is a sophisticated, multimodal AI companion designed for seamless productivity and human-like interaction. Built with a **Next.js 15** frontend and a **FastAPI** backend, it integrates voice capabilities, animated avatars, and Google Workspace automation.

---

## 🚀 Key Features

- **Autonomous Intelligence**: Proactive assistance and memory-aware conversations.
- **Multimodal Interaction**: Switch between text, voice, and hybrid modes seamlessly.
- **Dynamic Avatar**: Real-time animated presence with emotional intelligence and lip-sync.
- **Google Integration**: Manage your Gmail, Calendar, and reminders directly through natural language.
- **Customizable Persona**: Adjust the assistant's voice, tone (friendly, professional, energetic), and mode.

---

## 📂 Project Structure

```text
MY-AI/
├── README.md           # Workspace overview (this file)
└── aura/               # Main Application Repository
    ├── frontend/       # Next.js 15 TypeScript UI
    ├── backend/        # FastAPI Python Logic & AI Engine
    ├── public/         # Static assets & avatar models
    ├── src/            # Frontend components & state management
    ├── akansha.db      # Local SQLite database for memory
    └── .env            # Environment configuration (AI keys, OAuth)
```

---

## 🛠️ Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/Yogeshcheedalla/akansha.git
cd akansha
```

### 2. Setup the Backend
Navigate to the `aura` directory and install Python dependencies:
```bash
cd aura
pip install -r requirements.txt
```

Run the FastAPI server:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Setup the Frontend
In a new terminal (inside the `aura` directory), install Node dependencies:
```bash
npm install
```

Start the development server:
```bash
npm run dev
```
The application will be live at **[http://localhost:4030](http://localhost:4030)**.

---

## ⚙️ Configuration

Create a `.env` file in the `aura/` directory with the following variables:

```env
# AI Engine
OPENROUTER_API_KEY=your_key_here

# Google Integration
GOOGLE_CLIENT_ID=your_id_here
GOOGLE_CLIENT_SECRET=your_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback

# ElevenLabs (Voice)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

---

## 🌐 Browser Compatibility

For the best experience with **Voice Interaction** and **Speech-to-Text (STT)**, we recommend using:
- **Google Chrome** (v110+)
- **Microsoft Edge** (v110+)

*Note: Some features like background listening and high-quality browser TTS are optimized for Chromium-based browsers.*

## 🧪 Verification

To ensure everything is working correctly, you can run:
- **Build Test**: `npm run build`
- **Type Check**: `npm run type-check`
- **Logic Check**: `python -m py_compile backend/main.py`
