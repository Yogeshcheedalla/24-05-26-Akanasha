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
  MessageCircleMore,
  MessageSquareReply,
  Mic,
  MicOff,
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
  notes: string | null;
  last_intro_text: string | null;
  timestamp: string | null;
}

type PendingSpeakerIntro = {
  displayName: string | null;
  relationship: string | null;
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

  const relationshipMatch = lowered.match(
    /\b(mother|mom|mummy|amma|father|dad|nanna|brother|sister|wife|husband|friend|owner|self|me|myself|teacher|colleague|cousin|uncle|aunty|aunt|guest)\b/i
  );
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
      displayName = match[1]
        .replace(/\b(and|for|to|with|relationship|relation)\b.*$/i, '')
        .trim();
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
  if (displayName && /yogesh/i.test(displayName)) {
    relationship = 'owner';
  }

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
    speakingVolume,
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
  const conversationRef = useRef<HTMLDivElement>(null);
  const spokenOffsetRef = useRef(0);
  const pendingPlannerRef = useRef<PlannerCommand | null>(null);
  const plannerContextRef = useRef('');
  const speakerProfilesRef = useRef<SpeakerProfileData[]>([]);
  const activeSpeakerRef = useRef<SpeakerProfileData | null>(null);

  useEffect(() => {
    speakerProfilesRef.current = speakerProfiles;
  }, [speakerProfiles]);

  useEffect(() => {
    activeSpeakerRef.current = activeSpeaker;
    if (activeSpeaker?.display_name) {
      window.localStorage.setItem('akansha-active-speaker', activeSpeaker.display_name);
    }
  }, [activeSpeaker]);

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
      setBackgroundListening(profileData.profile.background_listening);
      setGoogleStatus(googleData);
    } catch (error) {
      console.error('Failed to load assistant profile:', error);
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
      console.error('Failed to load speaker profiles:', error);
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
      console.error('Failed to load social inbox:', error);
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
    if (!finalTranscript) return;
    void handleConversationTurn(finalTranscript, 'voice');
    clearTranscript();
  }, [clearTranscript, finalTranscript]);

  const queueReadySpeech = useCallback(
    (fullText: string, force = false) => {
      const remaining = fullText.slice(spokenOffsetRef.current);
      if (!remaining.trim()) return;

      const isFirstSpokenChunk = spokenOffsetRef.current === 0;
      const minChars = isFirstSpokenChunk ? 24 : 72;
      const idealChars = isFirstSpokenChunk ? 34 : 132;
      const softBreakChars = isFirstSpokenChunk ? 48 : 176;
      const minWords = isFirstSpokenChunk ? 4 : 14;
      const wordCount = remaining
        .trim()
        .split(/\s+/)
        .filter(Boolean).length;

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
        const readyPunctuation = punctuationMatches.filter((match) => (match.index ?? 0) >= minChars);
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
        void speak(cleaned, {
          voiceGender,
          voiceLanguage,
          voiceTone,
          queue: true,
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
      console.error('Failed to save profile:', error);
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

  const handleConversationTurn = useCallback(
    async (message: string, inputMode: 'voice' | 'text') => {
      const trimmed = message.trim();
      const interruptionCommand =
        /^(stop|wait|pause|hold on|enough|mute|silent|aagu|aapu|ruko|ruk jao)$/i.test(trimmed) ||
        /^(ఆపు|ఆగు|रुको|बस)$/i.test(trimmed);

      if (!trimmed) return;

      if (inputMode === 'voice' && awaitingSpeakerIntro) {
        const intro = extractSpeakerIntro(trimmed);
        const nextIntro = {
          displayName: intro.displayName || pendingSpeakerIntro?.displayName || null,
          relationship: intro.relationship || pendingSpeakerIntro?.relationship || null,
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
          const followUp = `Thanks ${nextIntro.displayName}. Now tell me your relationship to Yogesh, like mother, father, friend, or owner.`;
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
          const res = await fetch('http://localhost:8000/api/voice/speakers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              display_name: nextIntro.displayName,
              relationship_to_owner: nextIntro.relationship,
              notes: `Voice onboarding from ${inputMode} mode`,
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
          setAwaitingSpeakerIntro(false);
          setPendingSpeakerIntro(null);

          const confirmation = `Nice to meet you, ${nextSpeaker.display_name}. I will remember that you are ${nextSpeaker.relationship_to_owner ?? 'connected to Yogesh'} and I will respond with ${speakerAccessLabel(nextSpeaker.access_level)}.`;
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
          console.error('Failed to save voice speaker:', error);
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
        !/^(stop|wait|pause|hold on|enough|mute|silent|aagu|aapu|ruko|ruk jao)$/i.test(trimmed)
      ) {
        const introPrompt =
          'Who are you? I am hearing you for the first time. Tell me your name and your relationship to Yogesh so I can remember your voice profile.';
        setAwaitingSpeakerIntro(true);
        setPendingSpeakerIntro(null);
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

      if (interruptionCommand && (isSpeaking || streaming)) {
        stopSpeaking();
        setStreaming(false);
        setAssistantEmotion('thinking');
        setResponseText('Okay, I stopped. I am listening again.');
        if (backgroundListening && inputMode === 'voice') {
          startListening();
        }
        clearTranscript();
        return;
      }
      if (streaming) return;

      const currentSpeaker = activeSpeakerRef.current;
      const speakerIsLimited = inputMode === 'voice' && currentSpeaker && currentSpeaker.access_level !== 'owner';
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
            ? `${currentSpeaker.display_name}, I heard you. Because you are using trusted access, I can chat and guide you, but device automation, social sending, or delete actions still need Yogesh's voice or chat approval.`
            : `${currentSpeaker?.display_name}, I can talk with you, but I cannot run protected actions until Yogesh approves or speaks as the owner.`;
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
        const reminderEnabled =
          /\b(no|without)\b/.test(replyLower)
            ? false
            : pendingPlanner.reminderEnabled || /\b(yes|remind|notification|notify)\b/.test(replyLower);
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
            (reminderEnabled && (replyDate || pendingPlanner.date || new Date().toISOString().slice(0, 10))
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

      if (isAutomationIntent(trimmed)) {
        const automationPrompt = normalizeAutomationPrompt(trimmed);
        setAssistantEmotion('thinking');
        setStreaming(true);
        setResponseText('');

        try {
          const automationResponse = await fetch('http://localhost:8000/api/automation/browser/prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt: automationPrompt,
              background: true,
            }),
          });
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
          console.error('Voice automation failed:', error);
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
            (plannerIntent.reminderEnabled && (plannerIntent.date || new Date().toISOString().slice(0, 10))
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
      setUserEmotion(inferredEmotion);
      setAssistantEmotion(inferredEmotion === 'sad' ? 'thinking' : inferredEmotion);
      setStreaming(true);
      setResponseText('');

      try {
        const response = await fetch('http://localhost:8000/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: trimmed,
            session_id: sessionId,
            user_tone: inferredEmotion,
            response_style: voiceTone,
            conversation_mode: assistantMode,
            language_preference: voiceLanguage,
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
        console.error('Voice assistant stream failed:', error);
        const fallback =
          "I'm sorry - the real-time channel dropped. Please check that the Python backend is running and OpenRouter is configured.";
        setResponseText(fallback);
        toast.error('Akansha could not finish that response');
      } finally {
        setStreaming(false);
        setTypedMessage('');
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
      sessionId,
      startListening,
      stopSpeaking,
      streaming,
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
      console.error('Failed to initialize Google auth:', error);
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
      console.error('Failed to load Gmail summary:', error);
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
      console.error('Failed to load Calendar events:', error);
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
        console.error(`Failed to connect ${platform}:`, error);
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
        console.error('Failed to send approved reply:', error);
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
    <div className="space-y-8 pb-10">
      <div
        className={`grid grid-cols-1 items-start gap-6 ${
          showSettings ? 'xl:grid-cols-[1.65fr_0.95fr]' : ''
        }`}
      >
      <section className="flex flex-col rounded-3xl border border-white/10 bg-slate-950 shadow-[0_40px_120px_rgba(15,23,42,0.6)]">
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
              onClick={() => setShowSettings((open) => !open)}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10"
            >
              <Settings2 size={15} />
              {showSettings ? 'Hide controls' : 'Show controls'}
            </button>
          </div>
        </div>

        <div className="grid flex-1 grid-cols-1 gap-6 p-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="flex min-h-[580px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950">
            <div className="relative flex-1">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(108,71,255,0.3),_transparent_48%),radial-gradient(circle_at_bottom,_rgba(34,197,94,0.15),_transparent_35%)]" />
              <AssistantAvatarStage
                isListening={isListening}
                isSpeaking={isSpeaking}
                speakingVolume={speakingVolume}
                viseme={viseme}
                emotion={assistantEmotion}
                listenerEmotion={userEmotion}
                voiceGender={voiceGender}
              />

              <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center pt-5">
                <div className="rounded-full border border-white/10 bg-black/30 px-4 py-2 text-sm text-slate-200 backdrop-blur-md">
                  {profile?.full_name ?? 'Companion mode'} · {emotionLabel(assistantEmotion)}
                </div>
              </div>

              <div className="absolute inset-x-0 bottom-0 flex flex-col gap-4 p-6">
                <div className="grid grid-cols-5 gap-2">
                  {Array.from({ length: 5 }).map((_, index) => {
                    const active = isSpeaking
                      ? Math.max(0.22, speakingVolume - index * 0.08)
                      : isListening
                        ? 0.55 - index * 0.06
                        : 0.16;
                    return (
                      <div
                        key={`wave-bar-${index}`}
                        className="h-20 rounded-full bg-gradient-to-t from-[#6c47ff] via-[#38bdf8] to-[#34d399] transition-all duration-150"
                        style={{
                          transform: `scaleY(${Math.max(active, 0.14)})`,
                          transformOrigin: 'bottom',
                        }}
                      />
                    );
                  })}
                </div>

                <div className="flex flex-wrap items-center justify-center gap-3">
                  <button
                    onClick={isListening ? stopListening : startListening}
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

      {showSettings && (
        <aside className="flex flex-col gap-5 xl:self-start">
          <section className="rounded-3xl border border-white/10 bg-slate-900/85 p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Voice profile</p>
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
                  Replies now follow your selected language preference for Telugu + English, English,
                  or Hindi. The Irina clip stays available only as a preview sample.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Shortcut: <span className="font-medium text-slate-300">Ctrl + Shift + Space</span>{' '}
                  toggles continuous voice listening on or off.
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
