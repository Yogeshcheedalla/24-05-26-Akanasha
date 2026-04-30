# Akansha

Akansha is a Next.js + FastAPI assistant workspace with chat history, memory, voice conversation, avatar presence, and Google integration scaffolding.

## What’s in this build

- Multi-session chat with renameable conversation titles
- Voice assistant page with:
  - text / voice / hybrid modes
  - browser STT + TTS
  - interrupt control
  - background listening toggle
  - male / female voice selection
  - friendly / professional / energetic / calm tone presets
  - animated avatar with blinking, head motion, emotion cues, and mouth movement
- Emotion-aware interaction styling based on detected user tone
- Google integration endpoints for:
  - OAuth connect flow
  - Gmail summary fetch
  - Calendar event fetch
  - Calendar reminder creation
- User preference storage for mode, voice, and assistant settings

## Local run

Frontend:

```bash
npm install
npm run dev
```

Backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

Frontend runs on [http://localhost:4000](http://localhost:4000) and the API runs on [http://localhost:8000](http://localhost:8000).

## Required environment variables

Create a `.env` file in the project root.

### AI response generation

```env
OPENROUTER_API_KEY=your_openrouter_key
```

### Google OAuth

```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback
```

### Dedicated female cloned voice

```env
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=your_irina_cloned_voice_id
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

## Google Cloud setup

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable:
   - Gmail API
   - Google Calendar API
4. Configure the OAuth consent screen.
5. Create an OAuth 2.0 Web Application credential.
6. Add this redirect URI:

```text
http://localhost:8000/api/google/callback
```

## Notes about voice mode

- Speech input still uses browser-native speech recognition.
- Male playback can still use browser speech synthesis.
- Female playback is now wired for a dedicated cloned-voice backend pipeline through ElevenLabs.
- To make every female response sound like the same Irina voice, create or import the Irina voice clone in ElevenLabs and place that cloned `voice_id` in `.env`.
- Background listening works best in Chromium-based browsers.
- Spoken playback happens after the response is assembled.

## Useful routes

- `/chat-interface`
- `/voice-assistant`
- `/conversation-history`
- `/settings`
- `/api-keys`
- `/sign-up-login-screen`

## Verification

These checks pass on the current codebase:

```bash
npm run build
npm run type-check
python -m py_compile backend/main.py backend/database.py backend/ai_engine.py
```
