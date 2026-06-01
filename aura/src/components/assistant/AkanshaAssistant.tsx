'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  AtSign,
  AudioLines,
  Bell,
  Camera,
  CalendarDays,
  Check,
  CheckCheck,
  Clock3,
  Loader2,
  Mail,
  Maximize2,
  MessageCircleMore,
  MessageSquareReply,
  Mic,
  MicOff,
  Minimize2,
  PauseCircle,
  Play,
  RefreshCw,
  Settings2,
  Send,
  Sparkles,
  Trash2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  useVoice,
  type VoiceGender,
  type VoiceFrequencySignature,
  type VoiceLanguagePreference,
  type VoiceTone,
} from '@/hooks/useVoice';
import {
  addMinutes,
  applyPlannerCommand,
  applyPlannerReminderFollowUp,
  cleanPlannerTitle,
  extractDateValue,
  extractTimeWindow,
  inferPlannerCommand,
  isLikelyTaskDetails,
  isPlannerPreparationPrompt,
  isReminderOnlyPlannerFollowUp,
  isWeakPlannerTitle,
  type PlannerCommand,
} from '@/lib/plannerCommands';
import { isAutomationIntent, normalizeAutomationPrompt } from '@/lib/automationCommands';

type AssistantMode = 'text' | 'voice' | 'hybrid';
type AssistantEmotion = 'happy' | 'neutral' | 'thinking' | 'sad' | 'surprised';

function isAlertReminderIntent(text: string) {
  return /\b(alert|alarm|reminder|remainder|notify|notification|pop\s*up|popup|remind me)\b/i.test(
    text
  );
}

interface ProfileResponse {
  profile: {
    full_name: string;
    email: string;
    preferred_mode: AssistantMode;
    voice_gender: VoiceGender;
    voice_tone: VoiceTone;
    voice_language: VoiceLanguagePreference;
    avatar_style: string;
    background_listening: boolean;
    interrupt_enabled: boolean;
    google_connected: boolean;
    google_email: string | null;
  };
}

interface GoogleStatus {
  configured: boolean;
  connected: boolean;
  email: string | null;
  scopes: string[];
  redirect_uri: string;
  setup_required: boolean;
}

interface GmailSummaryResponse {
  connected: boolean;
  summary: string;
  emails: Array<{
    id: string;
    sender: string;
    subject: string;
    snippet: string;
    important: boolean;
  }>;
}

interface CalendarResponse {
  connected: boolean;
  events: Array<{
    id?: string;
    title: string;
    start: string;
    description?: string;
  }>;
  error?: string;
}

interface SocialInboxMessage {
  id: number;
  platform: 'whatsapp' | 'instagram' | 'twitter' | 'telegram' | 'discord';
  sender: string;
  content: string;
  intent: string;
  sentiment: string;
  is_read: boolean;
  timestamp: string;
  suggested_replies: string[];
}

interface SocialInboxResponse {
  platforms: Array<{
    key: 'whatsapp' | 'instagram' | 'twitter' | 'telegram' | 'discord';
    label: string;
    connected: boolean;
    accent: string;
  }>;
  messages: SocialInboxMessage[];
}

const SOCIAL_INBOX_FALLBACK: SocialInboxResponse = {
  platforms: [
    { key: 'whatsapp', label: 'WhatsApp', connected: false, accent: '#25D366' },
    { key: 'instagram', label: 'Instagram', connected: false, accent: '#F43F5E' },
    { key: 'twitter', label: 'X / Twitter', connected: false, accent: '#60A5FA' },
    { key: 'telegram', label: 'Telegram', connected: false, accent: '#38BDF8' },
    { key: 'discord', label: 'Discord', connected: false, accent: '#818CF8' },
  ],
  messages: [
    {
      id: 1,
      platform: 'whatsapp',
      sender: 'Rahul',
      content: "Hey, can we move tomorrow's practice interview to 7:30 PM?",
      intent: 'schedule',
      sentiment: 'neutral',
      is_read: false,
      timestamp: new Date().toISOString(),
      suggested_replies: [
        'Yes Rahul, 7:30 PM works for me.',
        'I can do tomorrow, but I need a little later. Would 8 PM work?',
        'Let me confirm in a few minutes and I will get back to you.',
      ],
    },
    {
      id: 2,
      platform: 'instagram',
      sender: 'Ananya Design',
      content: 'Loved your AI project post. Are you open to collaborating on a reel next week?',
      intent: 'collaboration',
      sentiment: 'positive',
      is_read: false,
      timestamp: new Date().toISOString(),
      suggested_replies: [
        'That sounds exciting. I would love to hear the idea in a little more detail.',
        'Yes, I am open to it. Can you share the concept and expected timeline?',
        'I am interested. Let us lock a quick call and plan it properly.',
      ],
    },
  ],
};

type SpeakerAccessLevel = 'owner' | 'trusted' | 'guest';

interface SpeakerProfileData {
  id: number;
  display_name: string;
  relationship_to_owner: string | null;
  access_level: SpeakerAccessLevel;
  closeness_level?: 'close' | 'normal' | 'distant' | 'new' | null;
  communication_style?: string | null;
  language_preference?:
    | VoiceLanguagePreference
    | 'hinglish'
    | 'formal_english'
    | 'casual_english'
    | null;
  notes: string | null;
  context_profile?: Record<string, unknown> | null;
  conversation_summary?: string | null;
  mood_state?: string | null;
  interaction_count?: number;
  last_intro_text: string | null;
  last_heard_text: string | null;
  voice_signature?: {
    sample_text?: string;
    language_preference?: VoiceLanguagePreference;
    tone_preference?: VoiceTone;
    word_count?: number;
    average_word_length?: number;
    vowel_ratio?: number;
    audio_frequency?: VoiceFrequencySignature | null;
    created_at?: string;
  } | null;
  timestamp: string | null;
}

type PendingSpeakerIntro = {
  displayName: string | null;
  relationship: string | null;
  sampleText?: string;
};

const AUTOMATION_READINESS_CHECKLIST = [
  'Continuous voice command loop',
  'Open websites and desktop apps',
  'Fill website form details',
  'Ask before submit with popup',
  'Submit after owner confirmation',
  'YouTube search and result play',
  'Scroll page one step at a time',
  'Pause or resume present media',
  'Close current tab or window',
  'Set, increase, or decrease volume',
  'Edit active fields and shortcuts',
  'Warn before risky commands',
  'First-time speaker onboarding',
  'Owner, trusted, and guest limits',
  'True 3D mesh avatar stage',
];

const SPEAKER_RELATIONSHIP_ALIASES: Record<string, string> = {
  amma: 'mother',
  mom: 'mother',
  mummy: 'mother',
  mother: 'mother',
  dad: 'father',
  nanna: 'father',
  father: 'father',
  self: 'owner',
  me: 'owner',
  myself: 'owner',
  teacher: 'professor',
  mentor: 'professor',
  classmate: 'friend',
};

function detectUserTone(text: string): AssistantEmotion {
  const normalized = text.toLowerCase();
  if (/(amazing|awesome|love|excited|great|nice|happy)/.test(normalized)) return 'happy';
  if (/(sad|upset|tired|hurt|depressed|bad)/.test(normalized)) return 'sad';
  if (/(wow|seriously|surprised|what)/.test(normalized)) return 'surprised';
  if (/(how|why|help|think|maybe|confused|wonder)/.test(normalized)) return 'thinking';
  return 'neutral';
}

function emotionLabel(emotion: AssistantEmotion) {
  switch (emotion) {
    case 'happy':
      return 'Warm and upbeat';
    case 'sad':
      return 'Gentle and supportive';
    case 'thinking':
      return 'Reflective and focused';
    case 'surprised':
      return 'Alert and expressive';
    default:
      return 'Balanced and steady';
  }
}

function extractSpeakerIntro(text: string) {
  const normalized = text.trim();
  const lowered = normalized.toLowerCase();
  const relationshipAlternates =
    'mother|mom|mummy|amma|father|dad|nanna|brother|sister|wife|husband|friend|owner|self|me|myself|teacher|colleague|cousin|uncle|aunty|aunt|guest';

  const relationshipMatch = lowered.match(new RegExp(`\\b(${relationshipAlternates})\\b`, 'i'));
  const relationshipWords = new Set([
    'mother',
    'mom',
    'mummy',
    'father',
    'dad',
    'nanna',
    'brother',
    'sister',
    'wife',
    'husband',
    'friend',
    'owner',
    'self',
    'me',
    'myself',
    'teacher',
    'colleague',
    'cousin',
    'uncle',
    'aunty',
    'aunt',
    'guest',
  ]);

  const namePatterns = [
    /\bmy name is\s+([a-z][a-z\s'-]{1,40})/i,
    /\bi am\s+([a-z][a-z\s'-]{1,40})/i,
    /\bthis is\s+([a-z][a-z\s'-]{1,40})/i,
    /\bi'm\s+([a-z][a-z\s'-]{1,40})/i,
  ];

  let displayName: string | null = null;
  for (const pattern of namePatterns) {
    const match = normalized.match(pattern);
    if (match?.[1]) {
      const rawName = match[1]
        .replace(/\b(and|for|to|with|relationship|relation)\b.*$/i, '')
        .trim();
      const rawNameLower = rawName.toLowerCase().replace(/\s+/g, ' ');
      const shouldKeepRelationshipWordAsName = rawNameLower === 'amma' || /yogesh/i.test(rawName);
      displayName = shouldKeepRelationshipWordAsName
        ? rawName
        : rawName.replace(new RegExp(`\\b(?:${relationshipAlternates})\\b.*$`, 'i'), '').trim();
      break;
    }
  }

  if (
    !displayName &&
    /^[a-z][a-z\s'-]{1,40}$/i.test(normalized) &&
    (!relationshipWords.has(lowered) || lowered === 'amma')
  ) {
    displayName = normalized.trim();
  }

  let relationship = relationshipMatch?.[1]?.toLowerCase() ?? null;
  relationship = relationship ? SPEAKER_RELATIONSHIP_ALIASES[relationship] || relationship : null;
  return {
    displayName: displayName ? displayName.replace(/\s+/g, ' ').trim() : null,
    relationship,
  };
}

function speakerAccessLabel(accessLevel: SpeakerAccessLevel) {
  if (accessLevel === 'owner') return 'full access';
  if (accessLevel === 'trusted') return 'trusted access';
  return 'guest access';
}

function buildSpeakerContextProfile(relationship: string | null, inputMode: 'voice' | 'text') {
  const normalized = relationship || 'guest';
  const base = {
    owner: 'the owner',
    onboarding_source: inputMode,
    expected_behavior: 'Relationship-aware, emotionally natural, privacy-safe conversation.',
  };

  if (normalized === 'owner') {
    return {
      ...base,
      role: 'Primary user',
      priorities: [
        'automation accuracy',
        'fast answers',
        'B.Tech studies',
        'Akansha project progress',
      ],
    };
  }
  if (normalized === 'mother') {
    return {
      ...base,
      role: 'Mother',
      priorities: ['health', 'food', 'rest', 'wellbeing', 'family warmth'],
    };
  }
  if (normalized === 'father') {
    return {
      ...base,
      role: 'Father',
      priorities: ['discipline', 'progress', 'studies', 'future planning'],
    };
  }
  if (normalized === 'professor') {
    return {
      ...base,
      role: 'Professor or mentor',
      priorities: ['academics', 'project status', 'performance', 'clear structure'],
    };
  }
  if (normalized === 'friend') {
    return {
      ...base,
      role: 'Friend',
      priorities: ['casual talk', 'college updates', 'fun topics', 'light jokes'],
    };
  }

  return {
    ...base,
    role: normalized,
    priorities: ['polite conversation', 'limited access', 'owner privacy'],
  };
}

function defaultClosenessForRelationship(relationship: string | null) {
  if (relationship === 'owner' || relationship === 'mother' || relationship === 'father') {
    return 'close';
  }
  return 'new';
}

function defaultCommunicationStyleForRelationship(relationship: string | null) {
  if (relationship === 'owner') return 'proactive close companion';
  if (relationship === 'mother') return 'warm Indian family care';
  if (relationship === 'father') return 'practical supportive guidance';
  if (relationship === 'friend') return 'casual Indian college style';
  if (relationship === 'professor') return 'formal academic respect';
  return 'polite cautious guest';
}

function voiceToneForSpeaker(speaker: SpeakerProfileData | null, fallback: VoiceTone): VoiceTone {
  const relationship = speaker?.relationship_to_owner;
  if (relationship === 'mother') return 'calm';
  if (relationship === 'father') return 'professional';
  if (relationship === 'professor') return 'professional';
  if (relationship === 'friend') return 'energetic';
  return fallback;
}

function buildAssistantSpeakerPayload(
  speaker: SpeakerProfileData | null,
  fallbackName: string | undefined,
  userEmotion: AssistantEmotion,
  selectedLanguage: VoiceLanguagePreference
) {
  if (speaker) {
    return {
      id: speaker.id,
      display_name: speaker.display_name,
      relationship_to_owner: speaker.relationship_to_owner,
      access_level: speaker.access_level,
      closeness_level:
        speaker.closeness_level || defaultClosenessForRelationship(speaker.relationship_to_owner),
      communication_style:
        speaker.communication_style ||
        defaultCommunicationStyleForRelationship(speaker.relationship_to_owner),
      language_preference: selectedLanguage,
      stored_language_preference: speaker.language_preference,
      notes: speaker.notes,
      context_profile: speaker.context_profile,
      conversation_summary: speaker.conversation_summary,
      mood_state: userEmotion,
      interaction_count: speaker.interaction_count || 0,
      last_heard_text: speaker.last_heard_text,
      selected_language_preference: selectedLanguage,
    };
  }

  return {
    display_name: fallbackName || 'the owner',
    relationship_to_owner: 'owner',
    access_level: 'owner',
    closeness_level: 'close',
    communication_style: 'proactive close companion',
    language_preference: selectedLanguage,
    notes: 'Primary Akansha owner using chat/session identity.',
    context_profile: {
      education: 'B.Tech student',
      project:
        'Building Akansha as a voice, chat, automation, memory, and relationship-aware assistant.',
    },
    conversation_summary: 'Owner wants fast, accurate, emotionally natural and proactive help.',
    mood_state: userEmotion,
    interaction_count: 0,
    selected_language_preference: selectedLanguage,
  };
}

function buildVoiceSignature(
  sampleText: string | undefined,
  languagePreference: VoiceLanguagePreference,
  tonePreference: VoiceTone,
  audioFrequency: VoiceFrequencySignature | null
) {
  const normalized = (sampleText || '').trim();
  const words = normalized.split(/\s+/).filter(Boolean);
  const lettersOnly = normalized.toLowerCase().replace(/[^a-z]/g, '');
  const vowelCount = (lettersOnly.match(/[aeiou]/g) || []).length;
  const totalCharacters = words.reduce((total, word) => total + word.length, 0);

  return {
    sample_text: normalized,
    language_preference: languagePreference,
    tone_preference: tonePreference,
    word_count: words.length,
    average_word_length: words.length ? Number((totalCharacters / words.length).toFixed(2)) : 0,
    vowel_ratio: lettersOnly.length ? Number((vowelCount / lettersOnly.length).toFixed(3)) : 0,
    audio_frequency: audioFrequency,
    created_at: new Date().toISOString(),
  };
}

function speakerFrequencyDistance(
  saved: VoiceFrequencySignature | null | undefined,
  current: VoiceFrequencySignature | null | undefined
) {
  if (!saved || !current || current.sampleCount < 12) return 0;
  const centroidDistance =
    Math.abs(saved.spectralCentroidHz - current.spectralCentroidHz) /
    Math.max(900, saved.spectralCentroidHz, current.spectralCentroidHz);
  const bandDistance =
    Math.abs(saved.lowBandEnergy - current.lowBandEnergy) +
    Math.abs(saved.midBandEnergy - current.midBandEnergy) +
    Math.abs(saved.highBandEnergy - current.highBandEnergy);
  const levelDistance = Math.abs(saved.rmsLevel - current.rmsLevel) * 2.5;
  return centroidDistance + bandDistance * 0.5 + levelDistance;
}

function shouldChallengeSpeakerIdentity(
  speaker: SpeakerProfileData | null,
  currentFrequency: VoiceFrequencySignature | null
) {
  if (!speaker) return false;
  if (speaker.access_level === 'owner' || speaker.relationship_to_owner === 'owner') {
    return false;
  }

  const savedFrequency = speaker?.voice_signature?.audio_frequency;
  if (!savedFrequency || !currentFrequency) return false;
  if ((savedFrequency.sampleCount ?? 0) < 20 || (currentFrequency.sampleCount ?? 0) < 60) {
    return false;
  }

  return speakerFrequencyDistance(savedFrequency, currentFrequency) > 1.1;
}

const AssistantAvatarStage = dynamic(
  () =>
    import('./AssistantAvatarStage').then((module) => ({
      default: module.AssistantAvatarStage,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-full border border-white/10 bg-black/30 px-4 py-2 text-sm text-slate-200 backdrop-blur-md">
          Loading avatar stage...
        </div>
      </div>
    ),
  }
);

export function AkanshaAssistant({ sessionId = 'voice-default' }: { sessionId?: string }) {
  const {
    isListening,
    isSpeaking,
    transcript,
    finalTranscript,
    voiceNotice,
    voiceNoticeId,
    speakingVolume,
    voiceFrequencySignature,
    viseme,
    voiceChoices,
    voiceGender,
    voiceTone,
    voiceLanguage,
    backgroundListening,
    selectedVoiceId,
    setVoiceGender,
    setVoiceTone,
    setVoiceLanguage,
    setBackgroundListening,
    setSelectedVoiceId,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    previewSelectedVoice,
    clearTranscript,
    clearVoiceNotice,
  } = useVoice();

  const [assistantMode, setAssistantMode] = useState<AssistantMode>('hybrid');
  const [assistantEmotion, setAssistantEmotion] = useState<AssistantEmotion>('neutral');
  const [userEmotion, setUserEmotion] = useState<AssistantEmotion>('neutral');
  const [profile, setProfile] = useState<ProfileResponse['profile'] | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [gmailSummary, setGmailSummary] = useState<GmailSummaryResponse | null>(null);
  const [calendarState, setCalendarState] = useState<CalendarResponse | null>(null);
  const [socialInbox, setSocialInbox] = useState<SocialInboxResponse | null>(null);
  const [speakerProfiles, setSpeakerProfiles] = useState<SpeakerProfileData[]>([]);
  const [activeSpeaker, setActiveSpeaker] = useState<SpeakerProfileData | null>(null);
  const [awaitingSpeakerIntro, setAwaitingSpeakerIntro] = useState(false);
  const [pendingSpeakerIntro, setPendingSpeakerIntro] = useState<PendingSpeakerIntro | null>(null);
  const [responseText, setResponseText] = useState(
    'Hello! I am Akansha. I can chat, speak, listen, and help you plan your day naturally.'
  );
  const [typedMessage, setTypedMessage] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadingGoogleAction, setLoadingGoogleAction] = useState<'gmail' | 'calendar' | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [selectedReply, setSelectedReply] = useState<Record<number, string>>({});
  const [sendingReplyId, setSendingReplyId] = useState<number | null>(null);
  const [showSettings, setShowSettings] = useState(true);
  const [avatarFullscreen, setAvatarFullscreen] = useState(false);
  const conversationRef = useRef<HTMLDivElement>(null);
  const voiceTurnTimerRef = useRef<number | null>(null);
  const lastVoiceNoticeIdRef = useRef(0);
  const spokenOffsetRef = useRef(0);
  const pendingPlannerRef = useRef<PlannerCommand | null>(null);
  const plannerContextRef = useRef('');
  const speakerProfilesRef = useRef<SpeakerProfileData[]>([]);
  const activeSpeakerRef = useRef<SpeakerProfileData | null>(null);
  const activeResponseAbortRef = useRef<AbortController | null>(null);
  const lastIdentityChallengeAtRef = useRef(0);

  useEffect(() => {
    speakerProfilesRef.current = speakerProfiles;
  }, [speakerProfiles]);

  useEffect(() => {
    activeSpeakerRef.current = activeSpeaker;
    if (activeSpeaker?.display_name) {
      window.localStorage.setItem('akansha-active-speaker', activeSpeaker.display_name);
    }
  }, [activeSpeaker]);

  useEffect(() => {
    return () => {
      activeResponseAbortRef.current?.abort();
    };
  }, []);

  const loadProfile = useCallback(async () => {
    setLoadingProfile(true);
    try {
      const [profileRes, googleRes] = await Promise.all([
        fetch('http://localhost:8000/api/profile'),
        fetch('http://localhost:8000/api/google/status'),
      ]);
      const profileData: ProfileResponse = await profileRes.json();
      const googleData: GoogleStatus = await googleRes.json();

      setProfile(profileData.profile);
      setAssistantMode(profileData.profile.preferred_mode);
      setVoiceGender(profileData.profile.voice_gender);
      setVoiceTone(profileData.profile.voice_tone);
      setVoiceLanguage(profileData.profile.voice_language);
      window.localStorage.setItem('akansha_voice_language', profileData.profile.voice_language);
      setBackgroundListening(profileData.profile.background_listening);
      setGoogleStatus(googleData);
    } catch (error) {
      console.warn('Failed to load assistant profile:', error);
      toast.error('Could not load Akansha preferences');
    } finally {
      setLoadingProfile(false);
    }
  }, [setBackgroundListening, setVoiceGender, setVoiceLanguage, setVoiceTone]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const loadSpeakerProfiles = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/voice/speakers');
      if (!res.ok) {
        throw new Error('Could not load voice speaker profiles');
      }
      const data: { speakers: SpeakerProfileData[] } = await res.json();
      setSpeakerProfiles(data.speakers ?? []);

      const cachedSpeakerName = window.localStorage.getItem('akansha-active-speaker');
      if (cachedSpeakerName) {
        const matched = (data.speakers ?? []).find(
          (speaker) => speaker.display_name.toLowerCase() === cachedSpeakerName.toLowerCase()
        );
        if (matched) {
          setActiveSpeaker(matched);
        }
      }
    } catch (error) {
      console.warn('Failed to load speaker profiles:', error);
    }
  }, []);

  useEffect(() => {
    void loadSpeakerProfiles();
  }, [loadSpeakerProfiles]);

  const loadSocialInbox = useCallback(async () => {
    setSocialLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/social/inbox');
      if (!res.ok) {
        setSocialInbox(SOCIAL_INBOX_FALLBACK);
        return;
      }
      const data: SocialInboxResponse = await res.json();
      setSocialInbox(data);
    } catch (error) {
      console.warn('Failed to load social inbox:', error);
      setSocialInbox(SOCIAL_INBOX_FALLBACK);
    } finally {
      setSocialLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSocialInbox();
  }, [loadSocialInbox]);

  useEffect(() => {
    conversationRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [responseText, transcript, streaming]);

  useEffect(() => {
    const settledTranscript = finalTranscript.trim() || transcript.trim();
    if (!settledTranscript) return;
    if (voiceTurnTimerRef.current) {
      window.clearTimeout(voiceTurnTimerRef.current);
    }

    voiceTurnTimerRef.current = window.setTimeout(
      () => {
        void handleConversationTurn(settledTranscript, 'voice');
        clearTranscript();
        voiceTurnTimerRef.current = null;
      },
      finalTranscript.trim() ? 760 : 1300
    );

    return () => {
      if (voiceTurnTimerRef.current) {
        window.clearTimeout(voiceTurnTimerRef.current);
        voiceTurnTimerRef.current = null;
      }
    };
  }, [clearTranscript, finalTranscript, transcript]);

  useEffect(() => {
    if (!voiceNotice || voiceNoticeId === lastVoiceNoticeIdRef.current) return;
    lastVoiceNoticeIdRef.current = voiceNoticeId;
    if (assistantMode === 'text') {
      clearVoiceNotice();
      return;
    }

    setAssistantEmotion('thinking');
    setResponseText(voiceNotice);
    void speak(voiceNotice, {
      voiceGender,
      voiceLanguage,
      voiceTone,
      queue: false,
      preferBrowser: true,
    });

    const timer = window.setTimeout(() => {
      clearVoiceNotice();
      if (backgroundListening) {
        startListening();
      }
    }, 2400);

    return () => window.clearTimeout(timer);
  }, [
    assistantMode,
    backgroundListening,
    clearVoiceNotice,
    speak,
    startListening,
    voiceGender,
    voiceLanguage,
    voiceNotice,
    voiceNoticeId,
    voiceTone,
  ]);

  const queueReadySpeech = useCallback(
    (fullText: string, force = false) => {
      const remaining = fullText.slice(spokenOffsetRef.current);
      if (!remaining.trim()) return;

      const isFirstSpokenChunk = spokenOffsetRef.current === 0;
      const minChars = isFirstSpokenChunk ? 24 : 72;
      const idealChars = isFirstSpokenChunk ? 34 : 132;
      const softBreakChars = isFirstSpokenChunk ? 48 : 176;
      const minWords = isFirstSpokenChunk ? 4 : 14;
      const wordCount = remaining.trim().split(/\s+/).filter(Boolean).length;

      const findWhitespaceBoundary = (targetChars: number) => {
        if (remaining.length < targetChars) return -1;

        const searchSlice = remaining.slice(0, Math.min(remaining.length, targetChars));
        const whitespaceIndex = Math.max(
          searchSlice.lastIndexOf(' '),
          searchSlice.lastIndexOf('\n'),
          searchSlice.lastIndexOf('\t')
        );

        if (whitespaceIndex >= minChars) {
          return whitespaceIndex + 1;
        }

        return -1;
      };

      let boundaryIndex = -1;
      const punctuationMatches = [...remaining.matchAll(/[.!?।\n]/g)];
      if (punctuationMatches.length) {
        const readyPunctuation = punctuationMatches.filter(
          (match) => (match.index ?? 0) >= minChars
        );
        const chosenPunctuation = isFirstSpokenChunk
          ? readyPunctuation[0]
          : readyPunctuation[readyPunctuation.length - 1];

        if (chosenPunctuation) {
          boundaryIndex = (chosenPunctuation.index ?? 0) + chosenPunctuation[0].length;
        }
      }

      if (boundaryIndex <= 0) {
        const softPunctuation = [...remaining.matchAll(/[,;:]/g)].find(
          (match) => (match.index ?? 0) >= minChars
        );
        if (softPunctuation) {
          boundaryIndex = (softPunctuation.index ?? 0) + softPunctuation[0].length;
        }
      }

      if (
        boundaryIndex <= 0 &&
        !force &&
        (remaining.length >= idealChars || wordCount >= minWords)
      ) {
        boundaryIndex = findWhitespaceBoundary(idealChars);
      }

      if (boundaryIndex <= 0 && !force && remaining.length >= softBreakChars) {
        boundaryIndex = findWhitespaceBoundary(softBreakChars);
      }

      if (force && boundaryIndex <= 0) {
        boundaryIndex = remaining.length;
      }

      if (boundaryIndex <= 0) return;

      const speakable = remaining.slice(0, boundaryIndex);
      spokenOffsetRef.current += boundaryIndex;
      const cleaned = speakable.trim();
      if (cleaned) {
        const relationshipVoiceTone = voiceToneForSpeaker(activeSpeakerRef.current, voiceTone);
        void speak(cleaned, {
          voiceGender,
          voiceLanguage,
          voiceTone: relationshipVoiceTone,
          queue: true,
          preferBrowser: isFirstSpokenChunk || cleaned.length <= 180,
        });
      }
    },
    [speak, voiceGender, voiceLanguage, voiceTone]
  );

  const persistProfilePatch = useCallback(async (patch: Record<string, string | boolean>) => {
    try {
      const res = await fetch('http://localhost:8000/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data: ProfileResponse = await res.json();
      setProfile(data.profile);
    } catch (error) {
      console.warn('Failed to save profile:', error);
    }
  }, []);

  useEffect(() => {
    const handleContinuousVoiceShortcut = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || !event.shiftKey || event.code !== 'Space') {
        return;
      }

      event.preventDefault();
      const shouldEnable = !backgroundListening || !isListening;

      if (shouldEnable) {
        setBackgroundListening(true);
        void persistProfilePatch({ background_listening: true });
        startListening();
        toast.success('Continuous voice mode is on');
        return;
      }

      setBackgroundListening(false);
      void persistProfilePatch({ background_listening: false });
      stopListening();
      stopSpeaking();
      toast.success('Continuous voice mode is off');
    };

    window.addEventListener('keydown', handleContinuousVoiceShortcut);
    return () => window.removeEventListener('keydown', handleContinuousVoiceShortcut);
  }, [
    backgroundListening,
    isListening,
    persistProfilePatch,
    setBackgroundListening,
    startListening,
    stopListening,
    stopSpeaking,
  ]);

  useEffect(() => {
    if (loadingProfile || isListening || isSpeaking || streaming) return;
    if (assistantMode === 'text') return;

    if (!backgroundListening) {
      setBackgroundListening(true);
      void persistProfilePatch({ background_listening: true });
    }

    const timer = window.setTimeout(() => {
      startListening();
    }, 400);

    return () => window.clearTimeout(timer);
  }, [
    assistantMode,
    backgroundListening,
    isListening,
    isSpeaking,
    loadingProfile,
    persistProfilePatch,
    setBackgroundListening,
    startListening,
    streaming,
  ]);

  const saveSpeakerProfile = useCallback(
    async (intro: PendingSpeakerIntro, inputMode: 'voice' | 'text') => {
      const displayName = intro.displayName?.trim();
      if (!displayName) {
        throw new Error('Speaker name is required');
      }

      const res = await fetch('http://localhost:8000/api/voice/speakers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: displayName,
          relationship_to_owner: intro.relationship,
          closeness_level: defaultClosenessForRelationship(intro.relationship),
          communication_style: defaultCommunicationStyleForRelationship(intro.relationship),
          language_preference: voiceLanguage,
          notes: `Voice onboarding from ${inputMode} mode`,
          context_profile: buildSpeakerContextProfile(intro.relationship, inputMode),
          conversation_summary: `${displayName} introduced themselves as ${intro.relationship || 'connected to the owner'}. Keep replies consistent with that relationship.`,
          mood_state: 'neutral',
          last_heard_text: intro.sampleText || '',
          voice_signature: buildVoiceSignature(
            intro.sampleText,
            voiceLanguage,
            voiceTone,
            voiceFrequencySignature
          ),
        }),
      });

      if (!res.ok) {
        throw new Error('Could not save speaker profile');
      }

      const data: { speaker: SpeakerProfileData } = await res.json();
      const nextSpeaker = data.speaker;
      setSpeakerProfiles((current) => {
        const filtered = current.filter((item) => item.id !== nextSpeaker.id);
        return [...filtered, nextSpeaker];
      });
      setActiveSpeaker(nextSpeaker);
      return nextSpeaker;
    },
    [voiceFrequencySignature, voiceLanguage, voiceTone]
  );

  const handleConversationTurn = useCallback(
    async (message: string, inputMode: 'voice' | 'text') => {
      const trimmed = message.trim();
      const startContinuousCommand =
        /^(please start|start listening|start voice|continue listening|wake up|listen again)$/i.test(
          trimmed
        );
      const stopContinuousCommand =
        /^(stop|stop listening|pause listening|sleep|voice off|microphone off|mic off)$/i.test(
          trimmed
        );
      const interruptionCommand =
        /^(stop|wait|pause|hold on|enough|mute|silent|aagu|aapu|ruko|ruk jao|bas)$/i.test(trimmed) ||
        /^(ఆపు|ఆగు|రుకో|रुको|बस)$/i.test(trimmed) ||
        /^(ఆపు|ఆగు|రుకో|रुको|बस)$/i.test(trimmed);

      if (!trimmed) return;

      const shouldInterruptActiveReply = isSpeaking || streaming || activeResponseAbortRef.current;
      if (shouldInterruptActiveReply) {
        activeResponseAbortRef.current?.abort();
        activeResponseAbortRef.current = null;
        stopSpeaking();
        setStreaming(false);
        spokenOffsetRef.current = 0;
        if (interruptionCommand) {
          setAssistantEmotion('thinking');
          setResponseText('Okay, I stopped. I am listening again.');
          if (backgroundListening && inputMode === 'voice') {
            startListening();
          }
          clearTranscript();
          return;
        }
      }

      if (inputMode === 'voice' && startContinuousCommand) {
        setBackgroundListening(true);
        void persistProfilePatch({ background_listening: true });
        startListening();
        const confirmation = 'I am listening continuously again. Tell me the next task.';
        setAssistantEmotion('happy');
        setResponseText(confirmation);
        void speak(confirmation, {
          voiceGender,
          voiceLanguage,
          voiceTone,
          queue: false,
          preferBrowser: true,
        });
        clearTranscript();
        return;
      }

      if (inputMode === 'voice' && stopContinuousCommand) {
        setBackgroundListening(false);
        void persistProfilePatch({ background_listening: false });
        stopListening();
        stopSpeaking();
        const confirmation =
          'Okay, continuous voice is paused. Press the mic or say please start after turning the mic on again.';
        setAssistantEmotion('thinking');
        setResponseText(confirmation);
        clearTranscript();
        return;
      }

      if (
        inputMode === 'voice' &&
        activeSpeakerRef.current &&
        !awaitingSpeakerIntro &&
        shouldChallengeSpeakerIdentity(activeSpeakerRef.current, voiceFrequencySignature) &&
        Date.now() - lastIdentityChallengeAtRef.current > 5 * 60 * 1000
      ) {
        lastIdentityChallengeAtRef.current = Date.now();
        window.localStorage.removeItem('akansha-active-speaker');
        activeSpeakerRef.current = null;
        setActiveSpeaker(null);
        const introPrompt =
          'Who are you? I am listening to a different voice for the first time. Tell me your name and your relationship to the owner so I can set the correct limits.';
        setAwaitingSpeakerIntro(true);
        setPendingSpeakerIntro({ displayName: null, relationship: null, sampleText: trimmed });
        setAssistantEmotion('thinking');
        setResponseText(introPrompt);
        void speak(introPrompt, {
          voiceGender,
          voiceLanguage,
          voiceTone,
          queue: false,
        });
        return;
      }

      if (inputMode === 'voice' && awaitingSpeakerIntro) {
        const intro = extractSpeakerIntro(trimmed);
        const nextIntro = {
          displayName: intro.displayName || pendingSpeakerIntro?.displayName || null,
          relationship: intro.relationship || pendingSpeakerIntro?.relationship || null,
          sampleText: pendingSpeakerIntro?.sampleText || trimmed,
        };

        if (!nextIntro.displayName) {
          const followUp =
            'I heard you, but I still need your name. Say something like: my name is Amma.';
          setPendingSpeakerIntro(nextIntro);
          setAssistantEmotion('thinking');
          setResponseText(followUp);
          void speak(followUp, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
          return;
        }

        if (!nextIntro.relationship) {
          const followUp = `Thanks ${nextIntro.displayName}. Now tell me your relationship to the owner, like mother, father, friend, or owner.`;
          setPendingSpeakerIntro(nextIntro);
          setAssistantEmotion('thinking');
          setResponseText(followUp);
          void speak(followUp, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
          return;
        }

        try {
          const nextSpeaker = await saveSpeakerProfile(nextIntro, inputMode);
          setAwaitingSpeakerIntro(false);
          setPendingSpeakerIntro(null);

          const confirmation = `Nice to meet you, ${nextSpeaker.display_name}. I will remember that you are ${nextSpeaker.relationship_to_owner ?? 'connected to the owner'} and I will respond with ${speakerAccessLabel(nextSpeaker.access_level)}.`;
          setAssistantEmotion('happy');
          setResponseText(confirmation);
          void speak(confirmation, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
          return;
        } catch (error) {
          console.warn('Failed to save voice speaker:', error);
          const fallback =
            'I could not save your voice profile just now. Please try your introduction once more.';
          setAssistantEmotion('thinking');
          setResponseText(fallback);
          void speak(fallback, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
          return;
        }
      }

      if (
        inputMode === 'voice' &&
        !activeSpeakerRef.current &&
        !awaitingSpeakerIntro &&
        !/^(stop|wait|pause|hold on|enough|mute|silent|aagu|aapu|ruko|ruk jao|bas)$/i.test(trimmed) &&
        !/^(ఆపు|ఆగు|రుకో|रुको|बस)$/i.test(trimmed) &&
        !/^(ఆపు|ఆగు|రుకో|रुको|बस)$/i.test(trimmed)
      ) {
        const intro = extractSpeakerIntro(trimmed);
        if (intro.displayName || intro.relationship) {
          const nextIntro = {
            displayName: intro.displayName,
            relationship: intro.relationship,
            sampleText: trimmed,
          };

          if (!nextIntro.displayName) {
            const followUp =
              'I heard the relationship, but I still need your name. Say something like: my name is Amma.';
            setAwaitingSpeakerIntro(true);
            setPendingSpeakerIntro(nextIntro);
            setAssistantEmotion('thinking');
            setResponseText(followUp);
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
            return;
          }

          if (!nextIntro.relationship) {
            const followUp = `Thanks ${nextIntro.displayName}. Now tell me your relationship to the owner, like mother, father, friend, or owner.`;
            setAwaitingSpeakerIntro(true);
            setPendingSpeakerIntro(nextIntro);
            setAssistantEmotion('thinking');
            setResponseText(followUp);
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
            return;
          }

          try {
            const nextSpeaker = await saveSpeakerProfile(nextIntro, inputMode);
            setAwaitingSpeakerIntro(false);
            setPendingSpeakerIntro(null);
            const confirmation = `Nice to meet you, ${nextSpeaker.display_name}. I will remember that you are ${nextSpeaker.relationship_to_owner ?? 'connected to the owner'} and I will respond with ${speakerAccessLabel(nextSpeaker.access_level)}.`;
            setAssistantEmotion('happy');
            setResponseText(confirmation);
            void speak(confirmation, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
            return;
          } catch (error) {
            console.warn('Failed to save voice speaker:', error);
            const fallback =
              'I understood your introduction, but I could not save your voice profile just now. Please try once more.';
            setAwaitingSpeakerIntro(true);
            setPendingSpeakerIntro(nextIntro);
            setAssistantEmotion('thinking');
            setResponseText(fallback);
            void speak(fallback, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
            return;
          }
        }

        // Default normal app sessions to the owner profile. Only ask identity when
        // the speaker explicitly starts an introduction, so the owner is not challenged
        // repeatedly during the same conversation.
      }

      if (streaming && !shouldInterruptActiveReply) return;

      const currentSpeaker = activeSpeakerRef.current;
      const speakerIsLimited =
        inputMode === 'voice' && currentSpeaker && currentSpeaker.access_level !== 'owner';
      const speakerNeedsOwnerApproval =
        speakerIsLimited &&
        (isAutomationIntent(trimmed) ||
          inferPlannerCommand(trimmed)?.mode === 'delete' ||
          /\b(delete|remove|clear|send message|whatsapp|telegram|instagram|twitter|discord|volume|brightness|shutdown|restart)\b/i.test(
            trimmed
          ));

      if (speakerNeedsOwnerApproval) {
        const limitationMessage =
          currentSpeaker?.access_level === 'trusted'
            ? `${currentSpeaker.display_name}, I heard you. Because you are using trusted access, I can chat and guide you, but device automation, social sending, or delete actions still need the owner's voice or chat approval.`
            : `${currentSpeaker?.display_name}, I can talk with you, but I cannot run protected actions until the owner approves or speaks as the owner.`;
        setAssistantEmotion('thinking');
        setResponseText(limitationMessage);
        void speak(limitationMessage, {
          voiceGender,
          voiceLanguage,
          voiceTone,
          queue: false,
        });
        return;
      }

      const resolvePlannerTitle = (draft: PlannerCommand) => {
        if (draft.mode === 'delete') return draft.title;
        if (!isWeakPlannerTitle(draft.title)) return draft.title;
        const fallbackTitle = cleanPlannerTitle(plannerContextRef.current);
        return isWeakPlannerTitle(fallbackTitle) ? draft.title : fallbackTitle;
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
      if (pendingPlanner) {
        if (isPlannerPreparationPrompt(trimmed)) {
          const followUp =
            pendingPlanner.kind === 'calendar'
              ? 'I am still waiting for the real calendar details. Tell me the event title, date, time, and whether you want a reminder.'
              : 'I am still waiting for the real to-do details. Tell me the actual items you want me to save.';
          setAssistantEmotion('thinking');
          setResponseText(followUp);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
          return;
        }

        const replyLower = trimmed.toLowerCase();
        const replyDate = extractDateValue(trimmed);
        const replyTimes = extractTimeWindow(trimmed);
        const treatAsTaskDetails =
          pendingPlanner.kind === 'task' &&
          !replyDate &&
          !replyTimes.startTime &&
          isLikelyTaskDetails(trimmed);
        const reminderEnabled = /\b(no|without)\b/.test(replyLower)
          ? false
          : pendingPlanner.reminderEnabled ||
            /\b(yes|remind|notification|notify)\b/.test(replyLower);
        const replyReminderTime = inferPlannerCommand(
          `${pendingPlanner.kind === 'calendar' ? 'add to calendar' : 'add to todo list'} ${trimmed}`
        )?.reminderAt;

        const resolvedDraft: PlannerCommand = {
          ...pendingPlanner,
          title: treatAsTaskDetails ? trimmed : pendingPlanner.title,
          date: replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10),
          startTime: replyTimes.startTime || pendingPlanner.startTime,
          endTime:
            replyTimes.endTime ||
            pendingPlanner.endTime ||
            (replyTimes.startTime ? addMinutes(replyTimes.startTime, 30) : undefined),
          reminderEnabled,
          reminderAt:
            replyReminderTime ||
            pendingPlanner.reminderAt ||
            (reminderEnabled &&
            (replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10))
              ? `${replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10)}T${
                  replyTimes.startTime || pendingPlanner.startTime || '09:00'
                }:00`
              : undefined),
        };

        if (resolvedDraft.kind === 'calendar' && !resolvedDraft.startTime) {
          const followUp =
            'Got it. Tell me the reminder or event time in AM/PM format, like 6:30 PM or 9:15 AM.';
          setResponseText(followUp);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
          pendingPlannerRef.current = resolvedDraft;
          return;
        }

        const plannerResult = finalizePlannerAction(resolvedDraft);
        setAssistantEmotion(plannerResult.success ? 'happy' : 'thinking');
        setResponseText(plannerResult.message);
        if (inputMode !== 'text' || assistantMode !== 'text') {
          void speak(plannerResult.message, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
        }
        pendingPlannerRef.current = null;
        return;
      }

      if (isReminderOnlyPlannerFollowUp(trimmed)) {
        const plannerResult = applyPlannerReminderFollowUp(trimmed);
        setAssistantEmotion(plannerResult.success ? 'happy' : 'thinking');
        setResponseText(plannerResult.message);
        if (inputMode !== 'text' || assistantMode !== 'text') {
          void speak(plannerResult.message, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
        }
        setTypedMessage('');
        return;
      }

      if (!isAlertReminderIntent(trimmed) && isAutomationIntent(trimmed)) {
        const automationPrompt = normalizeAutomationPrompt(trimmed);
        setAssistantEmotion('thinking');
        setStreaming(true);
        setResponseText('');

        try {
          const automationResponse = await fetch(
            'http://localhost:8000/api/automation/browser/prompt',
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                prompt: automationPrompt,
                background: true,
              }),
            }
          );
          const payload = await automationResponse.json();
          const messageText =
            payload?.message ||
            payload?.detail ||
            'I tried to run that automation command, but I could not confirm the result.';
          const noteText = payload?.note ? ` ${payload.note}` : '';
          const automationReply = `${messageText}${noteText}`.trim();
          setAssistantEmotion(payload?.success ? 'happy' : 'thinking');
          setResponseText(automationReply);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(automationReply, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
          setTypedMessage('');
          return;
        } catch (error) {
          console.warn('Voice automation failed:', error);
          const fallback =
            'I tried to run that automation command, but the automation service was unavailable.';
          setAssistantEmotion('thinking');
          setResponseText(fallback);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(fallback, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
          return;
        } finally {
          setStreaming(false);
        }
      }

      const plannerIntent = inferPlannerCommand(trimmed);
      if (plannerIntent) {
        plannerContextRef.current = trimmed;
        if (isPlannerPreparationPrompt(trimmed)) {
          pendingPlannerRef.current = {
            ...plannerIntent,
            title: 'Planner item',
          };
          const followUp =
            plannerIntent.kind === 'calendar'
              ? 'Sure — tell me the actual calendar details in your next message, like the event title, date, time, and whether you want a reminder. I will wait instead of saving this setup sentence.'
              : 'Sure — tell me the actual to-do items in your next message, and I will add them properly instead of saving this setup sentence.';
          setAssistantEmotion('thinking');
          setResponseText(followUp);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
          return;
        }

        const needsReminderFollowUp =
          plannerIntent.mode === 'create' &&
          plannerIntent.reminderEnabled &&
          !plannerIntent.reminderAt &&
          !plannerIntent.startTime;
        const needsCalendarTime =
          plannerIntent.kind === 'calendar' &&
          plannerIntent.mode === 'create' &&
          (!plannerIntent.startTime || !plannerIntent.date);

        if (needsReminderFollowUp || needsCalendarTime) {
          pendingPlannerRef.current = plannerIntent;
          const followUp =
            plannerIntent.kind === 'calendar'
              ? `I can add "${resolvePlannerTitle(plannerIntent)}" to your calendar. Do you want a reminder too? If yes, tell me the date and time in AM/PM, like tomorrow 6:30 PM.`
              : `I can add "${resolvePlannerTitle(plannerIntent)}" to your to-do list. Do you want a reminder too? If yes, tell me the date and time in AM/PM, like today 8:45 PM.`;
          setAssistantEmotion('thinking');
          setResponseText(followUp);
          if (inputMode !== 'text' || assistantMode !== 'text') {
            void speak(followUp, {
              voiceGender,
              voiceLanguage,
              voiceTone,
              queue: false,
            });
          }
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
            plannerIntent.reminderAt ||
            (plannerIntent.reminderEnabled &&
            (plannerIntent.date || new Date().toISOString().slice(0, 10))
              ? `${plannerIntent.date || new Date().toISOString().slice(0, 10)}T${
                  plannerIntent.startTime || '09:00'
                }:00`
              : undefined),
        });
        setAssistantEmotion(plannerResult.success ? 'happy' : 'thinking');
        setResponseText(plannerResult.message);
        if (inputMode !== 'text' || assistantMode !== 'text') {
          void speak(plannerResult.message, {
            voiceGender,
            voiceLanguage,
            voiceTone,
            queue: false,
          });
        }
        return;
      }

      plannerContextRef.current = trimmed;

      if (isSpeaking) {
        stopSpeaking();
      }
      spokenOffsetRef.current = 0;

      const inferredEmotion = detectUserTone(trimmed);
      const relationshipVoiceTone = voiceToneForSpeaker(activeSpeakerRef.current, voiceTone);
      setUserEmotion(inferredEmotion);
      setAssistantEmotion(inferredEmotion === 'sad' ? 'thinking' : inferredEmotion);
      setStreaming(true);
      setResponseText('');
      const controller = new AbortController();
      activeResponseAbortRef.current = controller;

      try {
        const response = await fetch('http://localhost:8000/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
          body: JSON.stringify({
            message: trimmed,
            session_id: sessionId,
            user_tone: inferredEmotion,
            response_style: relationshipVoiceTone,
            conversation_mode: assistantMode,
            language_preference: voiceLanguage,
            speaker_profile: buildAssistantSpeakerPayload(
              activeSpeakerRef.current,
              profile?.full_name,
              inferredEmotion,
              voiceLanguage
            ),
          }),
        });

        if (!response.body) {
          throw new Error('Streaming response was not available');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let accumulated = '';

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
              setResponseText(accumulated);
              if (inputMode !== 'text' || assistantMode !== 'text') {
                queueReadySpeech(accumulated, false);
              }
            }
            if (payload.type === 'done') {
              accumulated = payload.content;
              setResponseText(accumulated);
              if (inputMode !== 'text' || assistantMode !== 'text') {
                queueReadySpeech(accumulated, true);
              }
            }
            if (payload.type === 'error') {
              throw new Error(payload.message);
            }
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        console.warn('Voice assistant stream failed:', error);
        const message = error instanceof Error ? error.message : String(error);
        const fallback = /timeout|timed out/i.test(message)
          ? 'That response took too long, so I stopped it and kept voice ready. Please say it once more.'
          : /401|auth|authentication|openrouter|api key/i.test(message)
            ? 'The AI provider key is not active in the running backend. Check C:\\MY-AI\\aura\\.env and restart the backend.'
            : 'The real-time channel had a temporary issue. I kept listening, so you can try again.';
        setResponseText(fallback);
        toast.error('Akansha could not finish that response');
      } finally {
        if (activeResponseAbortRef.current === controller) {
          activeResponseAbortRef.current = null;
        }
        if (!controller.signal.aborted) {
          setStreaming(false);
          setTypedMessage('');
          if (backgroundListening && inputMode === 'voice') {
            window.setTimeout(() => startListening(), 120);
          }
        }
      }
    },
    [
      assistantMode,
      awaitingSpeakerIntro,
      backgroundListening,
      clearTranscript,
      isSpeaking,
      pendingSpeakerIntro,
      queueReadySpeech,
      saveSpeakerProfile,
      sessionId,
      startListening,
      stopSpeaking,
      streaming,
      voiceFrequencySignature,
      voiceGender,
      voiceLanguage,
      voiceTone,
    ]
  );

  const connectGoogle = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/google/auth-url');
      const data = await res.json();
      if (!data.configured || !data.auth_url) {
        toast.info(data.message ?? 'Google OAuth is not configured yet');
        return;
      }
      window.open(data.auth_url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.warn('Failed to initialize Google auth:', error);
      toast.error('Could not start Google sign-in');
    }
  }, []);

  const loadGmailSummary = useCallback(async () => {
    setLoadingGoogleAction('gmail');
    try {
      const res = await fetch('http://localhost:8000/api/google/gmail/summary');
      const data: GmailSummaryResponse = await res.json();
      setGmailSummary(data);
    } catch (error) {
      console.warn('Failed to load Gmail summary:', error);
      toast.error('Could not fetch Gmail summary');
    } finally {
      setLoadingGoogleAction(null);
    }
  }, []);

  const loadCalendarEvents = useCallback(async () => {
    setLoadingGoogleAction('calendar');
    try {
      const res = await fetch('http://localhost:8000/api/google/calendar/events');
      const data: CalendarResponse = await res.json();
      setCalendarState(data);
    } catch (error) {
      console.warn('Failed to load Calendar events:', error);
      toast.error('Could not fetch calendar events');
    } finally {
      setLoadingGoogleAction(null);
    }
  }, []);

  const disconnectGoogle = useCallback(async () => {
    await fetch('http://localhost:8000/api/google/disconnect', { method: 'POST' });
    toast.success('Google account disconnected');
    loadProfile();
    setGmailSummary(null);
    setCalendarState(null);
  }, [loadProfile]);

  const connectSocialPlatform = useCallback(
    async (platform: 'whatsapp' | 'instagram' | 'twitter' | 'telegram' | 'discord') => {
      setConnectingPlatform(platform);
      try {
        await fetch(`http://localhost:8000/api/social/connect/${platform}`, { method: 'POST' });
        toast.success(`${platform} linked to Akansha`);
        await loadSocialInbox();
      } catch (error) {
        console.warn(`Failed to connect ${platform}:`, error);
        toast.error(`Could not connect ${platform}`);
      } finally {
        setConnectingPlatform(null);
      }
    },
    [loadSocialInbox]
  );

  const approveAndSendReply = useCallback(
    async (message: SocialInboxMessage) => {
      const reply = selectedReply[message.id] ?? message.suggested_replies[0] ?? '';
      if (!reply.trim()) {
        toast.info('Choose or write a reply first');
        return;
      }

      setSendingReplyId(message.id);
      try {
        const response = await fetch('http://localhost:8000/api/social/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message_id: message.id,
            platform: message.platform,
            sender: message.sender,
            reply,
            approved: true,
          }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail ?? 'Reply could not be sent');
        }

        toast.success(`Reply approved for ${message.sender}`);
        await loadSocialInbox();
      } catch (error) {
        console.warn('Failed to send approved reply:', error);
        toast.error('Reply could not be sent');
      } finally {
        setSendingReplyId(null);
      }
    },
    [loadSocialInbox, selectedReply]
  );

  const modeOptions: Array<{ value: AssistantMode; label: string }> = [
    { value: 'text', label: 'Text' },
    { value: 'voice', label: 'Voice' },
    { value: 'hybrid', label: 'Hybrid' },
  ];

  const stageStatus = useMemo(() => {
    if (streaming) return 'Thinking in real time';
    if (isListening) return 'Listening';
    if (isSpeaking) return 'Speaking';
    return 'Ready';
  }, [isListening, isSpeaking, streaming]);

  const socialPlatformMeta = useMemo(
    () => ({
      whatsapp: { label: 'WhatsApp', icon: MessageCircleMore },
      instagram: { label: 'Instagram', icon: Camera },
      twitter: { label: 'X / Twitter', icon: AtSign },
      telegram: { label: 'Telegram', icon: Send },
      discord: { label: 'Discord', icon: MessageCircleMore },
    }),
    []
  );

  return (
    <div
      className={
        avatarFullscreen
          ? 'fixed inset-0 z-[80] overflow-y-auto bg-slate-950 p-4'
          : 'space-y-8 pb-10'
      }
    >
      <div
        className={`grid grid-cols-1 items-start gap-6 ${
          showSettings && !avatarFullscreen ? 'xl:grid-cols-[1.65fr_0.95fr]' : ''
        }`}
      >
        <section
          className={`flex flex-col border border-white/10 bg-slate-950 shadow-[0_40px_120px_rgba(15,23,42,0.6)] ${
            avatarFullscreen ? 'min-h-[calc(100vh-2rem)] rounded-[28px]' : 'rounded-3xl'
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-5">
            <div>
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">
                Akansha Live Presence
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-white">
                Voice, presence, and natural conversation in one flow
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-200">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                {stageStatus}
              </div>

              <button
                onClick={() => setAvatarFullscreen((fullscreen) => !fullscreen)}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10"
              >
                {avatarFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                {avatarFullscreen ? 'Exit full screen' : 'Full screen'}
              </button>

              <button
                onClick={() => setShowSettings((open) => !open)}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10"
              >
                <Settings2 size={15} />
                {showSettings ? 'Hide controls' : 'Show controls'}
              </button>
            </div>
          </div>

          <div
            className={`grid flex-1 grid-cols-1 gap-6 p-6 ${
              avatarFullscreen
                ? 'lg:grid-cols-[minmax(680px,1fr)_minmax(300px,380px)]'
                : 'lg:grid-cols-[minmax(520px,1.45fr)_minmax(300px,0.72fr)]'
            }`}
          >
            <div
              className={`flex flex-col overflow-hidden rounded-[28px] border border-white/10 bg-slate-950 ${
                avatarFullscreen ? 'min-h-[calc(100vh-12rem)]' : 'min-h-[720px]'
              }`}
            >
              <div className="relative flex-1">
                <AssistantAvatarStage
                  isListening={isListening}
                  isSpeaking={isSpeaking}
                  speakingVolume={speakingVolume}
                  viseme={viseme}
                  emotion={assistantEmotion}
                  listenerEmotion={userEmotion}
                  voiceGender={voiceGender}
                  voiceTone={voiceToneForSpeaker(activeSpeaker, voiceTone)}
                />

                <div className="absolute inset-x-0 bottom-0 flex flex-col gap-4 p-6">
                  <div className="flex flex-wrap items-center justify-center gap-3">
                    <button
                      onClick={() => {
                        if (isListening || backgroundListening) {
                          setBackgroundListening(false);
                          void persistProfilePatch({ background_listening: false });
                          stopListening();
                          return;
                        }
                        setBackgroundListening(true);
                        void persistProfilePatch({ background_listening: true });
                        startListening();
                      }}
                      className={`inline-flex h-14 w-14 items-center justify-center rounded-full transition-all ${
                        isListening
                          ? 'bg-red-500 text-white shadow-[0_0_40px_rgba(239,68,68,0.35)]'
                          : 'bg-[#6c47ff] text-white shadow-[0_0_40px_rgba(108,71,255,0.35)]'
                      }`}
                    >
                      {isListening ? <MicOff size={24} /> : <Mic size={24} />}
                    </button>

                    <button
                      onClick={() => {
                        stopSpeaking();
                        if (backgroundListening) startListening();
                      }}
                      className="inline-flex h-12 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm text-slate-100 transition-colors hover:bg-white/10"
                    >
                      <PauseCircle size={18} />
                      Interrupt
                    </button>

                    <button
                      onClick={() => (isSpeaking ? stopSpeaking() : previewSelectedVoice())}
                      className="inline-flex h-12 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 text-sm text-slate-100 transition-colors hover:bg-white/10"
                    >
                      {isSpeaking ? <VolumeX size={18} /> : <Play size={18} />}
                      {isSpeaking ? 'Mute reply' : 'Replay'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="rounded-[28px] border border-white/10 bg-slate-900/85 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
                      Interaction mode
                    </p>
                    <p className="mt-2 text-sm text-slate-200">
                      Switch between text, voice, and hybrid conversations.
                    </p>
                  </div>
                  <div className="inline-flex rounded-full bg-slate-800 p-1">
                    {modeOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => {
                          setAssistantMode(option.value);
                          if (option.value === 'voice') {
                            setAvatarFullscreen(true);
                          }
                          void persistProfilePatch({ preferred_mode: option.value });
                        }}
                        className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                          assistantMode === option.value
                            ? 'bg-[#6c47ff] text-white'
                            : 'text-slate-400 hover:text-slate-100'
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                {(assistantMode === 'text' || assistantMode === 'hybrid') && (
                  <div className="mt-4 flex gap-3">
                    <textarea
                      value={typedMessage}
                      onChange={(event) => setTypedMessage(event.target.value)}
                      rows={3}
                      placeholder="Talk to Akansha with text, or keep the mic open in hybrid mode..."
                      className="flex-1 resize-none rounded-2xl border border-white/10 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 outline-none transition-colors focus:border-[#6c47ff]/60"
                    />
                    <button
                      onClick={() => void handleConversationTurn(typedMessage, 'text')}
                      disabled={streaming || !typedMessage.trim()}
                      className="inline-flex h-fit items-center gap-2 rounded-2xl bg-[#6c47ff] px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-[#5a35ee] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {streaming ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Sparkles size={16} />
                      )}
                      Send
                    </button>
                  </div>
                )}
              </div>

              <div className="flex-1 rounded-[28px] border border-white/10 bg-slate-900/85 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
                      Live conversation
                    </p>
                    <p className="mt-2 text-sm text-slate-200">
                      Akansha adapts voice and facial expression to your tone.
                    </p>
                  </div>
                  {streaming && <Loader2 size={18} className="animate-spin text-[#38bdf8]" />}
                </div>

                <div className="mt-4 space-y-4">
                  <div className="rounded-2xl border border-indigo-500/20 bg-indigo-500/8 p-4">
                    <p className="text-xs uppercase tracking-[0.22em] text-indigo-200/80">
                      You · {emotionLabel(userEmotion)}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-indigo-50">
                      {transcript ||
                        finalTranscript ||
                        'Your live transcript will appear here when you speak.'}
                    </p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                    <p className="text-xs uppercase tracking-[0.22em] text-emerald-200/80">
                      Akansha · {emotionLabel(assistantEmotion)}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-100">
                      {responseText ||
                        'Akansha is ready to reply naturally with voice and avatar cues.'}
                    </p>
                  </div>
                </div>
                <div ref={conversationRef} />
              </div>
            </div>
          </div>
        </section>

        {showSettings && !avatarFullscreen && (
          <aside className="flex flex-col gap-5 xl:self-start">
            <section className="rounded-3xl border border-white/10 bg-slate-900/85 p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
                    Automation checklist
                  </p>
                  <h2 className="mt-2 text-lg font-semibold text-white">Ready checks</h2>
                </div>
                <CheckCheck size={20} className="text-emerald-300" />
              </div>

              <div className="mt-5 grid max-h-[340px] gap-2 overflow-y-auto pr-1">
                {AUTOMATION_READINESS_CHECKLIST.map((item) => (
                  <div
                    key={item}
                    className="flex items-center gap-3 rounded-2xl border border-emerald-400/10 bg-emerald-400/5 px-3 py-2.5 text-sm text-slate-100"
                  >
                    <span className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-200">
                      <Check size={13} />
                    </span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-3xl border border-white/10 bg-slate-900/85 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
                    Voice profile
                  </p>
                  <h2 className="mt-2 text-lg font-semibold text-white">
                    Natural conversation controls
                  </h2>
                </div>
                {loadingProfile && <Loader2 size={18} className="animate-spin text-slate-500" />}
              </div>

              <div className="mt-5 space-y-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Voice gender
                  </label>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {(['female', 'male'] as VoiceGender[]).map((gender) => (
                      <button
                        key={gender}
                        onClick={() => {
                          setVoiceGender(gender);
                          void persistProfilePatch({ voice_gender: gender });
                        }}
                        className={`rounded-2xl px-4 py-3 text-sm transition-colors ${
                          voiceGender === gender
                            ? 'bg-[#6c47ff] text-white'
                            : 'bg-slate-950 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        {gender === 'female' ? 'Female voice' : 'Male voice'}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Language preference
                  </label>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                    {(
                      [
                        { value: 'telugu_english', label: 'Telugu + English' },
                        { value: 'english', label: 'English' },
                        { value: 'hindi', label: 'Hindi' },
                      ] as Array<{ value: VoiceLanguagePreference; label: string }>
                    ).map((option) => (
                      <button
                        key={option.value}
                        onClick={() => {
                          setVoiceLanguage(option.value);
                          window.localStorage.setItem('akansha_voice_language', option.value);
                          void persistProfilePatch({ voice_language: option.value });
                        }}
                        className={`rounded-2xl px-4 py-3 text-sm transition-colors ${
                          voiceLanguage === option.value
                            ? 'bg-[#6c47ff] text-white'
                            : 'bg-slate-950 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Voice tone
                  </label>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {(['friendly', 'professional', 'energetic', 'calm'] as VoiceTone[]).map(
                      (tone) => (
                        <button
                          key={tone}
                          onClick={() => {
                            setVoiceTone(tone);
                            void persistProfilePatch({ voice_tone: tone });
                          }}
                          className={`rounded-2xl px-4 py-3 text-sm capitalize transition-colors ${
                            voiceTone === tone
                              ? 'bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-400/30'
                              : 'bg-slate-950 text-slate-300 hover:bg-slate-800'
                          }`}
                        >
                          {tone}
                        </button>
                      )
                    )}
                  </div>
                </div>

                <div>
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Voice variant
                  </label>
                  <select
                    value={selectedVoiceId ?? ''}
                    onChange={(event) => setSelectedVoiceId(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-200 outline-none focus:border-[#6c47ff]/50"
                  >
                    {voiceChoices.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.name} · {voice.lang}
                      </option>
                    ))}
                  </select>
                  <p className="mt-2 text-xs text-slate-400">
                    Replies now follow your selected language preference for Telugu + English,
                    English, or Hindi. The Irina clip stays available only as a preview sample.
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    Shortcut:{' '}
                    <span className="font-medium text-slate-300">Ctrl + Shift + Space</span> toggles
                    continuous voice listening on or off.
                  </p>
                </div>

                <label className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-200">
                  Background listening
                  <button
                    type="button"
                    onClick={() => {
                      const next = !backgroundListening;
                      setBackgroundListening(next);
                      void persistProfilePatch({ background_listening: next });
                    }}
                    className={`relative h-6 w-11 flex-shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none ${
                      backgroundListening ? 'bg-emerald-500' : 'bg-slate-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none absolute left-1 top-1 h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        backgroundListening ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </label>
              </div>
            </section>
          </aside>
        )}
      </div>
    </div>
  );
}
