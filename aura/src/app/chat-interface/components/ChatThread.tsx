'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ModelSelector from './ModelSelector';
import MessageBubble from './MessageBubble';
import ChatComposer from './ChatComposer';
import PromptTemplateModal from './PromptTemplateModal';
import AvatarPanel, { type Emotion } from './AvatarPanel';
import {
  Brain,
  Share2,
  MoreHorizontal,
  Star,
  Trash2,
  Mic,
  MicOff,
  ChevronDown,
  CheckCheck,
  Pin,
  GitBranch,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  addMinutes,
  applyPlannerCommand,
  applyPlannerReminderFollowUp,
  cleanPlannerTitle,
  extractDateValue,
  extractTimeWindow,
  formatTime12h,
  inferPlannerCommand,
  isLikelyTaskDetails,
  isPlannerPreparationPrompt,
  isReminderOnlyPlannerFollowUp,
  isWeakPlannerTitle,
  type PlannerCommand,
} from '@/lib/plannerCommands';
import { isAutomationIntent, normalizeAutomationPrompt } from '@/lib/automationCommands';
import { deleteSessionTitle } from '@/hooks/chatSessionTitles';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sessionId?: string;
  model?: string;
  timestamp: Date;
  attachments?: Array<{ id: string; name: string; type: string; size: string; previewUrl?: string }>;
  memoryRefs?: string[];
  isStreaming?: boolean;
  tokenCount?: number;
  emotion?: Emotion;
  pinned?: boolean;
  displayOrder?: number | null;
  branchFromId?: number | null;
}

const INITIAL_MESSAGES: Message[] = [
  {
    id: 'msg-001',
    role: 'user',
    content:
      'Can you help me refactor this Express.js auth middleware to use async/await properly and add proper error handling?',
    timestamp: new Date(Date.now() - 8 * 60000),
    attachments: [
      { id: 'att-001', name: 'auth.middleware.ts', type: 'typescript', size: '3.2 KB' },
    ],
  },
  {
    id: 'msg-002',
    role: 'assistant',
    content: `Absolutely! Here's a refactored version of your auth middleware with proper async/await and error handling:\n\n\`\`\`typescript\nimport { Request, Response, NextFunction } from 'express'
;\nimport jwt from 'jsonwebtoken'
;\nimport { UserService } from '../services/user.service'
;\n\nexport const authMiddleware = async (\n  req: Request,\n  res: Response,\n  next: NextFunction\n): Promise<void> => {\n  try {\n    const authHeader = req.headers.authorization;\n    \n    if (!authHeader?.startsWith('Bearer ')) {\n      res.status(401).json({ \n        error: 'Missing or invalid authorization header' \n      });\n      return;\n    }\n\n    const token = authHeader.split(' ')[1];\n    const decoded = jwt.verify(token, process.env.JWT_SECRET!) as JWTPayload;\n    \n    const user = await UserService.findById(decoded.userId);\n    if (!user || !user.isActive) {\n      res.status(401).json({ error: 'User not found or inactive' });\n      return;\n    }\n\n    req.user = user;\n    next();\n  } catch (error) {\n    if (error instanceof jwt.TokenExpiredError) {\n      res.status(401).json({ error: 'Token has expired' });\n    } else if (error instanceof jwt.JsonWebTokenError) {\n      res.status(401).json({ error: 'Invalid token' });\n    } else {\n      next(error);\n    }\n  }\n};\n\`\`\`\n\nKey improvements:\n\n1. **Proper async/await** — removed callback-style patterns entirely\n2. **Granular JWT error handling** — distinguishes expired vs. invalid tokens\n3. **Explicit void return type** — prevents accidental response-after-send bugs`,
    model: 'Akansha',
    timestamp: new Date(Date.now() - 7 * 60000),
    tokenCount: 412,
    memoryRefs: ['Node.js expertise', 'TypeScript preference'],
    emotion: 'happy',
  },
  {
    id: 'msg-003',
    role: 'user',
    content: 'This is great! Can you also add rate limiting to this middleware?',
    timestamp: new Date(Date.now() - 4 * 60000),
  },
  {
    id: 'msg-004',
    role: 'assistant',
    content: `Here's how to add rate limiting using \`express-rate-limit\`:\n\n\`\`\`typescript\nimport rateLimit from 'express-rate-limit'\n;\n\nexport const rateLimiter = rateLimit({\n  windowMs: 15 * 60 * 1000,\n  max: 100,\n  standardHeaders: 'draft-7',\n  legacyHeaders: false,\n  handler: (req, res) => {\n    res.status(429).json({\n      error: 'Too many requests',\n      retryAfter: Math.ceil(req.rateLimit.resetTime.getTime() / 1000),\n    });\n  },\n});\n\`\`\`\n\nApply it in your router:\n\n\`\`\`typescript\nrouter.use('/api/auth', rateLimiter, authMiddleware);\n\`\`\`\n\n**Production tip:** Use Redis store for multi-instance deployments.`,
    model: 'Akansha',
    timestamp: new Date(Date.now() - 2 * 60000),
    tokenCount: 389,
    memoryRefs: ['Node.js expertise'],
    emotion: 'neutral',
  },
];

const EMOTION_RESPONSES: Record<string, Emotion> = {
  sad: 'sad',
  happy: 'happy',
  excited: 'happy',
  confused: 'thinking',
  help: 'thinking',
  wow: 'surprised',
  amazing: 'surprised',
  thanks: 'happy',
  error: 'thinking',
  default: 'neutral',
};

const CHAT_INTERRUPT_PATTERN =
  /\b(stop|wait|pause|hold on|enough|silent|mute|aagu|aapu|ruko|ruk jao)\b|ఆపు|ఆగు|रुको|बस/i;

const TRANSIENT_SPEECH_ERRORS = new Set(['no-speech', 'aborted', 'audio-capture', 'network']);

function detectEmotion(text: string): Emotion {
  const lower = text.toLowerCase();
  for (const [keyword, emotion] of Object.entries(EMOTION_RESPONSES)) {
    if (lower.includes(keyword)) return emotion;
  }
  return 'neutral';
}

type ChatAttachmentPayload = {
  name: string;
  type: string;
  size: number;
  data_url?: string;
  text?: string;
};

function chatLanguagePreference() {
  if (typeof window === 'undefined') return 'telugu_english';
  const stored =
    window.localStorage.getItem('akansha_voice_language') ||
    window.localStorage.getItem('akansha_app_language');
  if (stored === 'hindi') return 'hindi';
  if (stored === 'english') return 'english';
  return 'telugu_english';
}

function detectSpeechLang(text: string) {
  const preference = chatLanguagePreference();
  const hasTelugu = /[\u0C00-\u0C7F]/.test(text);
  const hasHindi = /[\u0900-\u097F]/.test(text);
  const words = new Set((text.toLowerCase().match(/[a-z]+/g) ?? []));

  if (hasHindi || preference === 'hindi') return 'hi-IN';
  if (hasTelugu || preference === 'telugu_english') return 'te-IN';
  if (
    ['namaste', 'hindi', 'kaise', 'kya', 'mujhe', 'aap', 'hai', 'nahi', 'batao'].some((word) =>
      words.has(word)
    )
  ) {
    return 'hi-IN';
  }
  if (
    ['telugu', 'anna', 'andi', 'naku', 'naaku', 'meeru', 'ela', 'unnaru', 'cheppu'].some((word) =>
      words.has(word)
    )
  ) {
    return 'te-IN';
  }
  return 'en-IN';
}

function getMessageNumericId(message: Message): number | null {
  if (/^\d+$/.test(message.id)) return Number(message.id);
  return null;
}

function insertMessageAfter(messages: Message[], anchorId: string | null, message: Message): Message[] {
  if (!anchorId) return [...messages, message];
  const anchorIndex = messages.findIndex((item) => item.id === anchorId);
  if (anchorIndex < 0) return [...messages, message];
  return [
    ...messages.slice(0, anchorIndex + 1),
    message,
    ...messages.slice(anchorIndex + 1),
  ];
}

function isAlertReminderIntent(text: string) {
  return /\b(alert|alarm|reminder|remainder|notify|notification|pop\s*up|popup|remind me)\b/i.test(text);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
    reader.readAsText(file);
  });
}

function formatChatError(error: unknown): string {
  const rawMessage = error instanceof Error ? error.message : String(error || '');
  const lower = rawMessage.toLowerCase();

  if (lower.includes('402') || lower.includes('credit')) {
    return 'The AI provider rejected this request because the account token/credit budget is too low. I reduced the output token limit for new requests, so try sending it again.';
  }

  if (lower.includes('413') || lower.includes('too large') || lower.includes('payload')) {
    return 'That screenshot is too large to send as-is. Crop it to the important area or paste a smaller image, then I can analyze it.';
  }

  if (lower.includes('image') || lower.includes('vision') || lower.includes('unsupported')) {
    return 'I could not analyze that image with the current vision model response. Try pasting the screenshot again, or attach a smaller PNG/JPG.';
  }

  if (lower.includes('failed to fetch') || lower.includes('networkerror') || lower.includes('network')) {
    return 'I could not reach the local chat service. Please make sure the FastAPI backend is running on port 8000.';
  }

  return rawMessage
    ? `I could not finish that request: ${rawMessage.slice(0, 260)}`
    : 'I could not finish that request. Please try once more.';
}

async function buildChatAttachments(files?: File[]): Promise<ChatAttachmentPayload[] | undefined> {
  if (!files?.length) return undefined;
  const supported = files.slice(0, 5);
  const payloads = await Promise.all(
    supported.map(async (file) => {
      const base = {
        name: file.name,
        type: file.type || 'application/octet-stream',
        size: file.size,
      };

      if (file.type.startsWith('image/')) {
        return {
          ...base,
          data_url: await readFileAsDataUrl(file),
        };
      }

      if (
        file.type.startsWith('text/') ||
        /\.(md|txt|json|csv|ts|tsx|js|jsx|py)$/i.test(file.name)
      ) {
        const text = await readFileAsText(file);
        return {
          ...base,
          text: text.slice(0, 16000),
        };
      }

      return base;
    })
  );
  return payloads;
}

export default function ChatThread({
  sessionId,
  onStatsChange,
}: {
  sessionId: string;
  onStatsChange?: (messages: number, tokens: number) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedModel, setSelectedModel] = useState('Akansha');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingAfterMessageId, setStreamingAfterMessageId] = useState<string | null>(null);
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [activeBranchFromId, setActiveBranchFromId] = useState<number | null>(null);

  useEffect(() => {
    setMessages([]);
    fetch(`http://localhost:8000/api/chat?session_id=${sessionId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.messages) {
          setMessages(
            data.messages.map((m: any) => ({
              id: m.id.toString(),
              sessionId: m.session_id,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
              pinned: Boolean(m.pinned),
              displayOrder: typeof m.display_order === 'number' ? m.display_order : null,
              branchFromId: typeof m.branch_from_id === 'number' ? m.branch_from_id : null,
            }))
          );
        }
      })
      .catch((err) => console.error('Failed to load chat history:', err));
  }, [sessionId]);
  const [currentEmotion, setCurrentEmotion] = useState<Emotion>('neutral');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [automationPermissionCount, setAutomationPermissionCount] = useState<number | null>(null);
  const [avatarMinimized, setAvatarMinimized] = useState(false);
  const [showAvatarBar, setShowAvatarBar] = useState(true);
  const activeSessionIdRef = useRef(sessionId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const micStoppedManuallyRef = useRef(false);
  const voiceEnabledRef = useRef(false);
  const isListeningRef = useRef(false);
  const isSpeakingRef = useRef(false);
  const isStreamingRef = useRef(false);
  const recognitionStartingRef = useRef(false);
  const voiceRestartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceAutoStartAttemptedRef = useRef(false);
  const voiceListeningToastShownRef = useRef(false);
  const activeChatAbortRef = useRef<AbortController | null>(null);
  const sendFromVoiceRef = useRef<(content: string) => void>(() => undefined);
  const pendingTranscriptRef = useRef('');
  const pendingPlannerRef = useRef<PlannerCommand | null>(null);

  useEffect(() => {
    activeSessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    voiceEnabledRef.current = voiceEnabled;
    if (!voiceEnabled && voiceRestartTimerRef.current) {
      clearTimeout(voiceRestartTimerRef.current);
      voiceRestartTimerRef.current = null;
    }
  }, [voiceEnabled]);

  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => {
    const totalCharacters =
      messages.reduce((acc, msg) => acc + msg.content.length, 0) + streamingContent.length;
    const totalTokens = Math.floor(totalCharacters / 4);
    onStatsChange?.(messages.length + (streamingContent ? 1 : 0), totalTokens);
  }, [messages, onStatsChange, streamingContent]);

  useEffect(() => {
    if (streamingAfterMessageId) {
      document
        .getElementById(`chat-message-${streamingAfterMessageId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    if (activeBranchFromId) {
      document
        .getElementById(`chat-message-${activeBranchFromId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeBranchFromId, messages, streamingAfterMessageId, streamingContent]);

  useEffect(() => {
    fetch('http://localhost:8000/api/automation/browser/status')
      .then((res) => res.json())
      .then((status) => {
        const permissions = status?.permissions ?? {};
        setAutomationPermissionCount(Object.values(permissions).filter(Boolean).length);
      })
      .catch(() => setAutomationPermissionCount(null));
  }, []);

  // Text-to-speech
  const speak = useCallback(
    (text: string) => {
      if (!voiceEnabled || typeof window === 'undefined') return;
      window.speechSynthesis?.cancel();
      const plainText = text
        .replace(/```[\s\S]*?```/g, 'code block')
        .replace(/\*\*/g, '')
        .replace(/`/g, '');
      const utterance = new SpeechSynthesisUtterance(plainText.slice(0, 500));
      const speechLang = detectSpeechLang(plainText);
      utterance.lang = speechLang;
      utterance.rate = 1.0;
      utterance.pitch = 1.1;
      utterance.volume = 0.9;
      const voices = window.speechSynthesis.getVoices();
      const femaleVoice = voices.find(
        (v) =>
          v.lang.toLowerCase().startsWith(speechLang.slice(0, 2).toLowerCase()) &&
          (v.name.toLowerCase().includes('female') ||
            v.name.includes('Samantha') ||
            v.name.includes('Victoria') ||
            v.name.includes('Karen') ||
            v.name.includes('Heera') ||
            v.name.includes('Swara') ||
            v.name.includes('Shruti') ||
            v.name.includes('Neerja'))
      ) ?? voices.find(
        (v) =>
          v.name.toLowerCase().includes('female') ||
          v.name.includes('Samantha') ||
          v.name.includes('Victoria') ||
          v.name.includes('Karen') ||
          v.name.includes('Heera') ||
          v.name.includes('Swara') ||
          v.name.includes('Shruti') ||
          v.name.includes('Neerja')
      );
      if (femaleVoice) utterance.voice = femaleVoice;
      utterance.onstart = () => {
        setIsSpeaking(true);
        setCurrentEmotion('speaking');
      };
      utterance.onend = () => {
        setIsSpeaking(false);
        setCurrentEmotion('neutral');
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        setCurrentEmotion('neutral');
      };
      speechRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [voiceEnabled]
  );

  // Speech-to-text
  const toggleListening = useCallback(() => {
    if (typeof window === 'undefined') return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast.error('Speech recognition not supported in this browser');
      return;
    }

    if (isListeningRef.current || recognitionStartingRef.current) {
      micStoppedManuallyRef.current = true;
      recognitionStartingRef.current = false;
      if (voiceRestartTimerRef.current) {
        clearTimeout(voiceRestartTimerRef.current);
        voiceRestartTimerRef.current = null;
      }
      recognitionRef.current?.stop();
      setIsListening(false);
      voiceEnabledRef.current = false;
      setVoiceEnabled(false);
      voiceListeningToastShownRef.current = false;
      return;
    }

    const startRecognition = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
      } catch (error) {
        console.error('Microphone permission denied:', error);
        micStoppedManuallyRef.current = true;
        recognitionStartingRef.current = false;
        setVoiceEnabled(false);
        toast.error('Microphone permission is blocked. Allow mic access in your browser.');
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;
      const preference = chatLanguagePreference();
      recognition.lang =
        preference === 'hindi' ? 'hi-IN' : preference === 'telugu_english' ? 'te-IN' : 'en-IN';

      pendingTranscriptRef.current = '';
      micStoppedManuallyRef.current = false;
      voiceEnabledRef.current = true;
      setVoiceEnabled(true);

      recognition.onstart = () => {
        recognitionStartingRef.current = false;
        setIsListening(true);
        if (!voiceListeningToastShownRef.current) {
          voiceListeningToastShownRef.current = true;
          toast.info('Listening... speak now');
        }
      };

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const alternatives = Array.from(event.results[i]).map((alternative) =>
            alternative.transcript.trim()
          );
          const chunk = alternatives
            .filter(Boolean)
            .sort((left, right) => right.length - left.length)[0];
          if (event.results[i].isFinal) {
            finalTranscript += `${chunk} `;
          } else {
            interimTranscript += `${chunk} `;
          }
        }

        const heardText = `${finalTranscript} ${interimTranscript}`.trim();
        if (heardText && (isSpeakingRef.current || isStreamingRef.current)) {
          window.speechSynthesis?.cancel();
          activeChatAbortRef.current?.abort();
          activeChatAbortRef.current = null;
          setIsSpeaking(false);
          setIsStreaming(false);
          setStreamingContent('');
          setCurrentEmotion('thinking');
          if (CHAT_INTERRUPT_PATTERN.test(heardText) && !finalTranscript.trim()) {
            pendingTranscriptRef.current = '';
            return;
          }
        }

        if (finalTranscript.trim()) {
          const spokenText = finalTranscript.trim();
          pendingTranscriptRef.current = '';
          sendFromVoiceRef.current(spokenText);
        }
      };

      recognition.onerror = (event: any) => {
        recognitionStartingRef.current = false;
        setIsListening(false);
        const errorCode = event?.error;

        if (errorCode === 'not-allowed' || errorCode === 'service-not-allowed') {
          micStoppedManuallyRef.current = true;
          voiceListeningToastShownRef.current = false;
          toast.error('Browser blocked voice input. Allow microphone and speech access.');
          return;
        }

        if (TRANSIENT_SPEECH_ERRORS.has(errorCode)) {
          if (!micStoppedManuallyRef.current && voiceEnabledRef.current && !voiceRestartTimerRef.current) {
            voiceRestartTimerRef.current = setTimeout(() => {
              voiceRestartTimerRef.current = null;
              if (isListeningRef.current || recognitionStartingRef.current || !voiceEnabledRef.current) return;
              recognitionRef.current = null;
              toggleListening();
            }, 500);
          }
          return;
        }

        toast.error(`Voice input paused (${errorCode || 'unknown error'}). I will keep trying while voice mode is on.`);
      };

      recognition.onend = () => {
        recognitionStartingRef.current = false;
        setIsListening(false);
        const spokenText = pendingTranscriptRef.current.trim();
        if (!micStoppedManuallyRef.current && spokenText) {
          sendFromVoiceRef.current(spokenText);
        }

        if (!micStoppedManuallyRef.current && voiceEnabledRef.current) {
          voiceRestartTimerRef.current = setTimeout(() => {
            voiceRestartTimerRef.current = null;
            if (isListeningRef.current || recognitionStartingRef.current) return;
            recognitionRef.current = null;
            toggleListening();
          }, 350);
        }
        pendingTranscriptRef.current = '';
      };

      recognitionRef.current = recognition;

      try {
        recognitionStartingRef.current = true;
        recognition.start();
      } catch (error) {
        recognitionStartingRef.current = false;
        console.error('Speech recognition start failed:', error);
        if (!micStoppedManuallyRef.current && voiceEnabledRef.current) {
          voiceRestartTimerRef.current = setTimeout(() => {
            voiceRestartTimerRef.current = null;
            if (isListeningRef.current || recognitionStartingRef.current || !voiceEnabledRef.current) return;
            recognitionRef.current = null;
            toggleListening();
          }, 600);
          return;
        }
        toast.error('Could not start voice input. Refresh once and try again.');
      }
    };

    void startRecognition();
  }, [isListening]);

  const simulateStreaming = useCallback(
    (content: string, emotion: Emotion = 'neutral', shouldSpeak = false) => {
      setIsStreaming(true);
      setStreamingContent('');
      setCurrentEmotion('thinking');
      let index = 0;
      const words = content.split(' ');
      const interval = setInterval(() => {
        if (index < words.length) {
          setStreamingContent((prev) => prev + (prev ? ' ' : '') + words[index]);
          index++;
        } else {
          clearInterval(interval);
          const newMsg: Message = {
            id: `msg-${Date.now()}`,
            role: 'assistant',
            content,
            model: selectedModel,
            timestamp: new Date(),
            tokenCount: Math.floor(content.length / 4),
            memoryRefs: Math.random() > 0.5 ? ['Previous context'] : undefined,
            emotion,
          };
          setMessages((prev) => [...prev, newMsg]);
          setIsStreaming(false);
          setStreamingContent('');
          setCurrentEmotion(emotion);
          if (shouldSpeak) {
            speak(content);
          }
        }
      }, 35);
    },
    [selectedModel, speak]
  );

  const addAssistantMessage = useCallback(
    (content: string, emotion: Emotion = 'neutral') => {
      const nextMessage: Message = {
        id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        role: 'assistant',
        content,
        model: selectedModel,
        timestamp: new Date(),
        tokenCount: Math.floor(content.length / 4),
        emotion,
      };
      setMessages((previous) => [...previous, nextMessage]);
      fetch('http://localhost:8000/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: 'assistant',
          content,
          session_id: activeSessionIdRef.current,
        }),
      })
        .then(() => {
          window.dispatchEvent(new CustomEvent('akansha-history-updated'));
        })
        .catch((error) => console.error('Failed to persist planner assistant message:', error));
    },
    [selectedModel]
  );

  const handleSend = useCallback(
    (content: string, attachments?: File[], source: 'text' | 'voice' = 'text') => {
      if (!content.trim() && !attachments?.length) return;
      const hasAttachments = Boolean(attachments?.length);
      const continueFromId = activeBranchFromId;
      const continueFromLocalId = continueFromId ? String(continueFromId) : null;
      const shouldSpeakReply = source === 'voice';
      activeChatAbortRef.current?.abort();
      activeChatAbortRef.current = null;
      window.speechSynthesis?.cancel();
      setIsSpeaking(false);
      setStreamingContent('');
      setIsStreaming(false);
      const detectedEmotion = detectEmotion(content);
      const localUserMessageId = `msg-${Date.now()}`;
      const userMsg: Message = {
        id: localUserMessageId,
        role: 'user',
        content,
        timestamp: new Date(),
        attachments: attachments?.map((f, i) => ({
          id: `att-${i}`,
          name: f.name,
          type: f.type,
          size: `${(f.size / 1024).toFixed(1)} KB`,
          previewUrl: f.type.startsWith('image/') ? URL.createObjectURL(f) : undefined,
        })),
        branchFromId: continueFromId,
      };
      setMessages((prev) => insertMessageAfter(prev, continueFromLocalId, userMsg));
      setStreamingAfterMessageId(localUserMessageId);
      setCurrentEmotion('thinking');

      const persistPlannerSideMessage = (role: 'user' | 'assistant', messageContent: string) => {
        fetch('http://localhost:8000/api/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role,
            content: messageContent,
            session_id: activeSessionIdRef.current,
          }),
        })
          .then(() => {
            window.dispatchEvent(new CustomEvent('akansha-history-updated'));
          })
          .catch((error) => console.error(`Failed to persist ${role} planner message:`, error));
      };

      const resolvePlannerTitle = (draft: PlannerCommand) => {
        if (draft.mode === 'delete') return draft.title;
        if (!isWeakPlannerTitle(draft.title)) return draft.title;

        const previousUserMessage = [...messages]
          .reverse()
          .find(
            (message) =>
              message.role === 'user' &&
              message.content.trim().toLowerCase() !== content.trim().toLowerCase() &&
              !inferPlannerCommand(message.content)
          );

        if (!previousUserMessage) return draft.title;
        const nextTitle = cleanPlannerTitle(previousUserMessage.content);
        return isWeakPlannerTitle(nextTitle) ? draft.title : nextTitle;
      };

      const finalizePlannerAction = (draft: PlannerCommand) => {
        const resolvedTitle = resolvePlannerTitle(draft).trim();
        return applyPlannerCommand(
          {
            ...draft,
            title: resolvedTitle,
          },
          resolvedTitle
        );
      };

      const pendingPlanner = pendingPlannerRef.current;
      if (!hasAttachments && pendingPlanner) {
        if (isPlannerPreparationPrompt(content)) {
          addAssistantMessage(
            pendingPlanner.kind === 'calendar'
              ? 'I am still waiting for the real calendar details. Tell me the event title, date, time, and whether you want a reminder.'
              : 'I am still waiting for the real to-do details. Tell me the actual items you want me to save.',
            'thinking'
          );
          return;
        }

        persistPlannerSideMessage('user', content);
        const replyLower = content.toLowerCase();
        const replyDate = extractDateValue(content);
        const replyTimes = extractTimeWindow(content);
        const treatAsTaskDetails =
          pendingPlanner.kind === 'task' &&
          !replyDate &&
          !replyTimes.startTime &&
          isLikelyTaskDetails(content);
        const reminderEnabled =
          /\b(no|without)\b/.test(replyLower)
            ? false
            : pendingPlanner.reminderEnabled || /\b(yes|remind|notification|notify)\b/.test(replyLower);

        const resolvedDraft: PlannerCommand = {
          ...pendingPlanner,
          title: treatAsTaskDetails ? content.trim() : pendingPlanner.title,
          date: replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10),
          startTime: replyTimes.startTime || pendingPlanner.startTime,
          endTime:
            replyTimes.endTime ||
            pendingPlanner.endTime ||
            (replyTimes.startTime ? addMinutes(replyTimes.startTime, 30) : undefined),
          reminderEnabled,
          reminderAt:
            reminderEnabled && (replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10))
              ? `${replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10)}T${
                  replyTimes.startTime || pendingPlanner.startTime || '09:00'
                }:00`
              : undefined,
        };

        if (resolvedDraft.kind === 'calendar' && !resolvedDraft.startTime) {
          addAssistantMessage(
            'Got it. Tell me the reminder or event time in AM/PM format, like 6:30 PM or 9:15 AM.',
            'thinking'
          );
          pendingPlannerRef.current = resolvedDraft;
          return;
        }

        const plannerResult = finalizePlannerAction(resolvedDraft);
        addAssistantMessage(plannerResult.message, plannerResult.success ? 'happy' : 'thinking');
        pendingPlannerRef.current = null;
        return;
      }

      if (!hasAttachments && isReminderOnlyPlannerFollowUp(content)) {
        persistPlannerSideMessage('user', content);
        const plannerResult = applyPlannerReminderFollowUp(content);
        addAssistantMessage(plannerResult.message, plannerResult.success ? 'happy' : 'thinking');
        pendingPlannerRef.current = null;
        return;
      }

      if (!hasAttachments && !isAlertReminderIntent(content) && isAutomationIntent(content)) {
        fetch('http://localhost:8000/api/automation/browser/prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: normalizeAutomationPrompt(content),
            background: true,
          }),
        })
          .then((res) => res.json())
          .then((payload) => {
            const messageText =
              payload?.message ||
              payload?.detail ||
              'I tried to run that automation command, but I could not confirm the result.';
            const noteText = payload?.note ? ` ${payload.note}` : '';
            addAssistantMessage(`${messageText}${noteText}`.trim(), payload?.success ? 'happy' : 'thinking');
          })
          .catch((error) => {
            console.error('Chat automation failed:', error);
            addAssistantMessage(
              'I tried to run that automation command, but the automation service was unavailable.',
              'thinking'
            );
          })
          .finally(() => {
            setIsStreaming(false);
          });
        return;
      }

      const plannerIntent = hasAttachments ? null : inferPlannerCommand(content);
      if (plannerIntent) {
        persistPlannerSideMessage('user', content);
        if (isPlannerPreparationPrompt(content)) {
          pendingPlannerRef.current = {
            ...plannerIntent,
            title: 'Planner item',
          };
          addAssistantMessage(
            plannerIntent.kind === 'calendar'
              ? 'Sure — tell me the actual calendar details in your next message, like the event title, date, time, and whether you want a reminder. I will wait instead of saving this setup sentence.'
              : 'Sure — send me the actual to-do items in your next message, and I will add them properly instead of saving this setup sentence.',
            'thinking'
          );
          return;
        }

        const needsReminderFollowUp =
          plannerIntent.mode === 'create' &&
          !plannerIntent.reminderEnabled &&
          !plannerIntent.startTime &&
          !plannerIntent.reminderAt;
        const needsCalendarTime =
          plannerIntent.kind === 'calendar' &&
          plannerIntent.mode === 'create' &&
          (!plannerIntent.startTime || !plannerIntent.date);

        if (needsReminderFollowUp || needsCalendarTime) {
          pendingPlannerRef.current = plannerIntent;
          addAssistantMessage(
            plannerIntent.kind === 'calendar'
              ? `I can add "${resolvePlannerTitle(plannerIntent)}" to your calendar. Do you want a reminder too? If yes, tell me the date and time in AM/PM, like tomorrow 6:30 PM.`
              : `I can add "${resolvePlannerTitle(plannerIntent)}" to your to-do list. Do you want a reminder too? If yes, tell me the date and time in AM/PM, like today 8:45 PM.`,
            'thinking'
          );
          return;
        }

        const plannerResult = finalizePlannerAction({
          ...plannerIntent,
          title: resolvePlannerTitle(plannerIntent),
          date: plannerIntent.date || new Date().toISOString().slice(0, 10),
          endTime:
            plannerIntent.kind === 'calendar'
              ? plannerIntent.endTime || addMinutes(plannerIntent.startTime || '09:00', 30)
              : plannerIntent.endTime,
          reminderAt:
            plannerIntent.reminderEnabled && (plannerIntent.date || new Date().toISOString().slice(0, 10))
              ? `${plannerIntent.date || new Date().toISOString().slice(0, 10)}T${
                  plannerIntent.startTime || '09:00'
                }:00`
              : undefined,
        });
        addAssistantMessage(plannerResult.message, plannerResult.success ? 'happy' : 'thinking');
        return;
      }

      const streamResponse = async () => {
        const controller = new AbortController();
        activeChatAbortRef.current = controller;
        setIsStreaming(true);
        setStreamingContent('');
        setCurrentEmotion('thinking');
        let accumulated = '';
        let serverUserMessageId: string | null = null;
        let serverAssistantMessageId: string | null = null;

        try {
          const attachmentPayloads = await buildChatAttachments(attachments);
          const response = await fetch('http://localhost:8000/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({
              message: content,
              session_id: activeSessionIdRef.current,
              conversation_mode: shouldSpeakReply ? 'voice' : 'text',
              language_preference: chatLanguagePreference(),
              attachments: attachmentPayloads,
              continue_from_message_id: continueFromId,
            }),
          });

          if (!response.body) {
            throw new Error('Streaming response was not available');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop() ?? '';

            for (const event of events) {
              const payloadLine = event.split('\n').find((line) => line.startsWith('data: '));
              if (!payloadLine) continue;

              const payload = JSON.parse(payloadLine.slice(6));
              if (payload.type === 'chunk') {
                accumulated += payload.content;
                setStreamingContent(accumulated);
              }
              if (payload.type === 'done') {
                accumulated = payload.content;
                setStreamingContent(accumulated);
                if (payload.user_message_id) {
                  serverUserMessageId = String(payload.user_message_id);
                }
                if (payload.assistant_message_id) {
                  serverAssistantMessageId = String(payload.assistant_message_id);
                }
              }
              if (payload.type === 'error') {
                throw new Error(payload.message);
              }
            }
          }

          if (controller.signal.aborted) return;
          const responseEmotion: Emotion = detectedEmotion === 'sad' ? 'sad' : 'happy';
          const newMsg: Message = {
            id: serverAssistantMessageId || `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'assistant',
            content: accumulated,
            model: selectedModel,
            timestamp: new Date(),
            tokenCount: Math.floor(accumulated.length / 4),
            emotion: responseEmotion,
            branchFromId: continueFromId,
          };
          setMessages((prev) => {
            const savedUserMessageId = serverUserMessageId;
            const next = savedUserMessageId
              ? prev.map((message) =>
                  message.id === localUserMessageId ? { ...message, id: savedUserMessageId } : message
                )
              : prev;
            return insertMessageAfter(next, savedUserMessageId || localUserMessageId, newMsg);
          });
          setStreamingAfterMessageId(null);
          const assistantNumericId = serverAssistantMessageId ? Number(serverAssistantMessageId) : null;
          if (continueFromId && assistantNumericId) {
            setActiveBranchFromId(assistantNumericId);
          }
          setCurrentEmotion(responseEmotion);
          window.dispatchEvent(new CustomEvent('akansha-history-updated'));
          if (shouldSpeakReply) {
            speak(accumulated);
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          console.error(err);
          simulateStreaming(formatChatError(err), 'sad', shouldSpeakReply);
        } finally {
          if (activeChatAbortRef.current === controller) {
            activeChatAbortRef.current = null;
          }
          if (!controller.signal.aborted) {
            setIsStreaming(false);
            setStreamingContent('');
            setStreamingAfterMessageId(null);
          }
        }
      };

      void streamResponse();
    },
    [activeBranchFromId, addAssistantMessage, messages, selectedModel, simulateStreaming, speak]
  );

  const stopActiveResponse = useCallback(() => {
    activeChatAbortRef.current?.abort();
    activeChatAbortRef.current = null;
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    setIsStreaming(false);
    setStreamingContent('');
    setStreamingAfterMessageId(null);
    setCurrentEmotion('neutral');
    toast.info('Stopped. You can type or attach a screenshot now.');
  }, []);

  useEffect(() => {
    sendFromVoiceRef.current = (content: string) => handleSend(content, undefined, 'voice');
  }, [handleSend]);

  useEffect(() => {
    if (!voiceEnabled) return;

    const keepAlive = setInterval(() => {
      if (
        voiceEnabledRef.current &&
        !micStoppedManuallyRef.current &&
        !isListeningRef.current &&
        !recognitionStartingRef.current
      ) {
        toggleListening();
      }
    }, 1600);

    return () => clearInterval(keepAlive);
  }, [toggleListening, voiceEnabled]);

  useEffect(() => {
    return () => {
      activeChatAbortRef.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, []);

  const handleShare = () => {
    navigator.clipboard.writeText('https://akansha.ai/share/conv-abc123');
    toast.success('Shareable link copied to clipboard');
  };

  const handleDeleteConversation = async () => {
    const confirmed = window.confirm('Delete this conversation from chat history?');
    if (!confirmed) return;

    try {
      const response = await fetch(
        `http://localhost:8000/api/chat/session/${encodeURIComponent(sessionId)}`,
        { method: 'DELETE' }
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Could not delete this conversation.');
      }

      deleteSessionTitle(sessionId);
      setMessages([]);
      setStreamingContent('');
      setIsStreaming(false);
      window.dispatchEvent(new CustomEvent('akansha-history-updated'));
      window.dispatchEvent(new CustomEvent('akansha-new-chat'));
      toast.success('Conversation deleted');
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      toast.error(error instanceof Error ? error.message : 'Could not delete this conversation.');
    }
  };

  const toggleMessagePin = useCallback((message: Message) => {
    const numericId = getMessageNumericId(message);
    if (!numericId) {
      toast.info('This message can be pinned after it finishes saving.');
      return;
    }

    const nextPinned = !message.pinned;
    setMessages((previous) =>
      previous.map((item) => (item.id === message.id ? { ...item, pinned: nextPinned } : item))
    );

    fetch(`http://localhost:8000/api/chat/message/${numericId}/pin`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: nextPinned }),
    })
      .then((response) => {
        if (!response.ok) throw new Error('Could not update the pin.');
        toast.success(nextPinned ? 'Message pinned' : 'Message unpinned');
      })
      .catch((error) => {
        console.error('Failed to pin message:', error);
        setMessages((previous) =>
          previous.map((item) => (item.id === message.id ? { ...item, pinned: message.pinned } : item))
        );
        toast.error(error instanceof Error ? error.message : 'Could not update the pin.');
      });
  }, []);

  const continueFromMessage = useCallback((message: Message) => {
    const numericId = getMessageNumericId(message);
    if (!numericId) {
      toast.info('Wait for this message to finish saving, then continue from it.');
      return;
    }

    setActiveBranchFromId(numericId);
    setTimeout(() => {
      document.querySelector<HTMLTextAreaElement>('textarea[placeholder^="Message Akansha"]')?.focus();
    }, 0);
    toast.success('Continue mode is active. Your next message will be inserted here.');
  }, []);

  const clearContinueMode = useCallback(() => {
    setActiveBranchFromId(null);
    toast.info('Continue mode cleared. New replies will go to the bottom.');
  }, []);

  const totalTokens = Math.floor(messages.reduce((acc, msg) => acc + msg.content.length, 0) / 4);
  const pinnedMessages = messages.filter((message) => message.pinned);
  const activeBranchMessage = activeBranchFromId
    ? messages.find((message) => getMessageNumericId(message) === activeBranchFromId)
    : null;

  return (
    <div className="flex flex-col h-full">
      {/* Chat header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/50 shrink-0">
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-foreground truncate">Akansha Chat</h2>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-muted-foreground">{messages.length} messages</span>
            <span className="text-muted-foreground/40">·</span>
            <span className="text-xs text-[#00C9A7] flex items-center gap-1">
              <Brain size={10} />
              Memory active
            </span>
            <span className="text-muted-foreground/40">·</span>
            <span className="text-xs text-[#38bdf8] flex items-center gap-1">
              <CheckCheck size={10} />
              {automationPermissionCount === null
                ? 'Automation permissions checking'
                : `${automationPermissionCount} automation permissions active`}
            </span>
            <span className="text-muted-foreground/40">·</span>
            <span className="text-xs text-muted-foreground font-mono tabular-nums">
              {totalTokens.toLocaleString()} tokens
            </span>
          </div>
        </div>

        <ModelSelector selected={selectedModel} onChange={setSelectedModel} />

        <div className="flex items-center gap-1">
          <button
            onClick={handleShare}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Share conversation"
          >
            <Share2 size={15} />
          </button>

          <div className="relative">
            <button
              onClick={() => setMoreMenuOpen(!moreMenuOpen)}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="More options"
            >
              <MoreHorizontal size={15} />
            </button>
            {moreMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setMoreMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-1 z-50 bg-card border border-border rounded-xl shadow-lg py-1 min-w-[160px] animate-fade-in">
                  {[
                    { key: 'menu-star', icon: Star, label: 'Star conversation' },
                    { key: 'menu-share', icon: Share2, label: 'Share publicly' },
                    {
                      key: 'menu-delete',
                      icon: Trash2,
                      label: 'Delete conversation',
                      danger: true,
                    },
                  ].map(({ key, icon: Icon, label, danger }) => (
                    <button
                      key={key}
                      onClick={() => {
                        setMoreMenuOpen(false);
                        if (key === 'menu-delete') {
                          void handleDeleteConversation();
                          return;
                        }
                        toast.success(`${label} action triggered`);
                      }}
                      className={`flex items-center gap-2 w-full px-3 py-2 text-sm transition-colors ${
                        danger
                          ? 'text-red-500 hover:bg-red-500/5'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      <Icon size={14} />
                      {label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {pinnedMessages.length > 0 && (
        <div className="px-4 py-2 border-b border-border bg-amber-400/[0.03] shrink-0">
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin">
            <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-400 shrink-0">
              <Pin size={12} fill="currentColor" />
              Pinned
            </span>
            {pinnedMessages.slice(0, 6).map((message) => (
              <button
                key={`pinned-${message.id}`}
                type="button"
                onClick={() => document.getElementById(`chat-message-${message.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                className="max-w-72 truncate rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1.5 text-xs text-foreground hover:bg-amber-400/15 transition-colors"
                title={message.content}
              >
                {message.role === 'user' ? 'You: ' : 'Akansha: '}
                {message.content || 'Attachment message'}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Avatar bar (minimized or full) */}
      {showAvatarBar && (
        <div className="px-4 py-2 border-b border-border bg-card/30 flex items-center gap-3 shrink-0">
          {avatarMinimized ? (
            <AvatarPanel
              emotion={currentEmotion}
              isSpeaking={isSpeaking}
              isListening={isListening}
              onToggleMic={toggleListening}
              onToggleVoice={() => {
                const next = !voiceEnabled;
                if (next) {
                  micStoppedManuallyRef.current = false;
                  voiceAutoStartAttemptedRef.current = false;
                }
                setVoiceEnabled(next);
              }}
              voiceEnabled={voiceEnabled}
              minimized={true}
              onToggleMinimize={() => setAvatarMinimized(false)}
            />
          ) : (
            <div className="flex items-center gap-3 w-full">
              <div className="flex items-center gap-2">
                {/* Compact inline avatar */}
                <div className="relative">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold"
                    style={{ background: 'linear-gradient(135deg, #6C47FF, #00C9A7)' }}
                  >
                    A
                  </div>
                  {isSpeaking && (
                    <div className="absolute inset-0 rounded-full border-2 border-[#6C47FF] animate-ping opacity-50" />
                  )}
                  {isListening && (
                    <div className="absolute inset-0 rounded-full border-2 border-red-500 animate-pulse opacity-70" />
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold text-foreground">Akansha</p>
                  <p className="text-xs text-muted-foreground capitalize">
                    {currentEmotion === 'speaking'
                      ? 'Speaking...'
                      : currentEmotion === 'thinking'
                        ? 'Thinking...'
                        : isListening
                          ? 'Listening...'
                          : 'Ready'}
                  </p>
                </div>
              </div>

              {/* Voice waveform */}
              {(isSpeaking || isListening) && (
                <div className="flex items-center gap-0.5 h-5">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div
                      key={`wave-${i}`}
                      className="w-1 rounded-full"
                      style={{
                        background: isListening ? '#EF4444' : '#6C47FF',
                        animation: `waveform ${0.4 + i * 0.06}s ease-in-out infinite alternate`,
                        animationDelay: `${i * 0.08}s`,
                      }}
                    />
                  ))}
                </div>
              )}

              <div className="flex items-center gap-1 ml-auto">
                <button
                  onClick={toggleListening}
                  className={`p-1.5 rounded-lg transition-all text-xs ${
                    isListening
                      ? 'bg-red-500/15 text-red-500 border border-red-500/30'
                      : 'bg-muted text-muted-foreground hover:text-foreground border border-border'
                  }`}
                  title={isListening ? 'Stop listening' : 'Voice input'}
                >
                  {isListening ? <MicOff size={13} /> : <Mic size={13} />}
                </button>
                <button
                  onClick={() => setAvatarMinimized(true)}
                  className="p-1.5 rounded-lg bg-muted text-muted-foreground hover:text-foreground border border-border transition-all"
                  title="Minimize"
                >
                  <ChevronDown size={13} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-1">
        {messages.map((msg) => (
          <React.Fragment key={msg.id}>
            <MessageBubble
              message={msg}
              onTogglePin={toggleMessagePin}
              onContinueFrom={continueFromMessage}
              isBranchAnchor={activeBranchFromId === getMessageNumericId(msg)}
            />
            {isStreaming && streamingAfterMessageId === msg.id && (
              <div className="message-enter">
                <MessageBubble
                  message={{
                    id: 'streaming',
                    role: 'assistant',
                    content: streamingContent,
                    model: selectedModel,
                    timestamp: new Date(),
                    isStreaming: true,
                  }}
                />
              </div>
            )}
          </React.Fragment>
        ))}

        {isStreaming && !streamingAfterMessageId && (
          <div className="message-enter">
            <MessageBubble
              message={{
                id: 'streaming',
                role: 'assistant',
                content: streamingContent,
                model: selectedModel,
                timestamp: new Date(),
                isStreaming: true,
              }}
            />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Prompt suggestions */}
      <div className="px-4 py-2 flex items-center gap-2 overflow-x-auto scrollbar-thin shrink-0">
        {[
          'Add unit tests',
          'Explain the JWT flow',
          'Add TypeScript generics',
          'How to handle refresh tokens?',
        ].map((suggestion) => (
          <button
            key={`suggestion-${suggestion}`}
            onClick={() => handleSend(suggestion)}
            className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {suggestion}
          </button>
        ))}
      </div>

      {activeBranchMessage && (
        <div className="mx-4 mb-2 rounded-2xl border border-[#6C47FF]/25 bg-[#6C47FF]/10 px-3 py-2 text-xs text-foreground flex items-center gap-3 shrink-0">
          <GitBranch size={14} className="text-[#9B7FFF] shrink-0" />
          <span className="min-w-0 flex-1 truncate">
            Continuing from {activeBranchMessage.role === 'user' ? 'your' : 'Akansha'} message:
            {' '}
            <span className="text-muted-foreground">{activeBranchMessage.content || 'attachment message'}</span>
          </span>
          <button
            type="button"
            onClick={clearContinueMode}
            className="p-1 rounded-lg hover:bg-background/50 text-muted-foreground hover:text-foreground transition-colors"
            title="Clear continue mode"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Composer */}
      <ChatComposer
        onSend={handleSend}
        onStop={stopActiveResponse}
        onOpenPromptLibrary={() => setPromptModalOpen(true)}
        isStreaming={isStreaming}
        selectedModel={selectedModel}
        onToggleMic={toggleListening}
        isListening={isListening}
      />

      <PromptTemplateModal
        open={promptModalOpen}
        onClose={() => setPromptModalOpen(false)}
        onSelect={(p) => {
          handleSend(p);
          setPromptModalOpen(false);
        }}
      />
    </div>
  );
}
