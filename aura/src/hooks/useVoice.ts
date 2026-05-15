'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type VoiceGender = 'male' | 'female';
export type VoiceTone = 'friendly' | 'professional' | 'energetic' | 'calm';
export type VoiceLanguagePreference = 'telugu_english' | 'english' | 'hindi';

export interface VoiceFrequencySignature {
  averageFrequencyHz: number;
  spectralCentroidHz: number;
  lowBandEnergy: number;
  midBandEnergy: number;
  highBandEnergy: number;
  rmsLevel: number;
  sampleCount: number;
  capturedAt: string;
}

interface VoiceOption {
  id: string;
  name: string;
  lang: string;
  gender: VoiceGender;
  kind?: 'system' | 'sample';
}

interface SpeakOptions {
  voiceGender?: VoiceGender;
  voiceTone?: VoiceTone;
  voiceLanguage?: VoiceLanguagePreference;
}
interface QueueSpeakOptions extends SpeakOptions {
  queue?: boolean;
  preferBrowser?: boolean;
}

interface QueuedSpeechItem {
  text: string;
  options?: SpeakOptions;
  preparedAudio?: Promise<Blob | null>;
}

type VoiceLanguageMode = 'english' | 'telugu' | 'mixed' | 'hindi';
type VisemeCode = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

interface VisemeFrame {
  at: number;
  viseme: VisemeCode;
  intensity: number;
}

interface VoiceState {
  isListening: boolean;
  isSpeaking: boolean;
  transcript: string;
  finalTranscript: string;
  speakingVolume: number;
  viseme: number;
}

const TONE_CONFIG: Record<VoiceTone, { rate: number; pitch: number; volume: number }> = {
  friendly: { rate: 1, pitch: 1.05, volume: 0.95 },
  professional: { rate: 0.98, pitch: 0.96, volume: 0.92 },
  energetic: { rate: 1.08, pitch: 1.12, volume: 1 },
  calm: { rate: 0.9, pitch: 0.94, volume: 0.88 },
};

const FAST_BROWSER_SPEECH_CHAR_LIMIT = 180;

function shouldUseFastBrowserSpeech(text: string, options?: QueueSpeakOptions | SpeakOptions) {
  if (!options || !('queue' in options)) {
    return false;
  }

  const languageMode = detectVoiceLanguageMode(text, options.voiceLanguage ?? 'english');
  if (languageMode !== 'english') {
    return false;
  }

  return Boolean(
    options.queue &&
      (('preferBrowser' in options && options.preferBrowser) ||
        text.trim().length <= FAST_BROWSER_SPEECH_CHAR_LIMIT)
  );
}

function inferGender(name: string): VoiceGender {
  const normalized = name.toLowerCase();
  if (
    [
      'female',
      'samantha',
      'victoria',
      'karen',
      'zira',
      'aria',
      'sara',
      'jenny',
      'ava',
      'nancy',
      'lisa',
      'hazel',
      'heera',
      'priya',
    ].some((token) => normalized.includes(token))
  ) {
    return 'female';
  }

  if (
    [
      'male',
      'david',
      'mark',
      'daniel',
      'alex',
      'george',
      'james',
      'guy',
      'ryan',
      'adam',
      'aaron',
      'leo',
      'rohan',
      'rahul',
    ].some((token) => normalized.includes(token))
  ) {
    return 'male';
  }

  return 'male';
}

const FEMALE_SAMPLE_VOICE_ID = 'sample-irina-energetic';
const FEMALE_SAMPLE_PATH = '/audio/irina-energetic.mp3';
const FEMALE_SAMPLE_OPTION: VoiceOption = {
  id: FEMALE_SAMPLE_VOICE_ID,
  name: 'Irina energetic e-commerce girl (sample)',
  lang: 'en-US',
  gender: 'female',
  kind: 'sample',
};
const SPEECH_INTERRUPT_PATTERN =
  /\b(stop|wait|pause|hold on|enough|silent|mute|aagu|aapu|ruko|ruk jao)\b|ఆపు|ఆగు|रुको|बस/i;

const INTERRUPTION_RESTART_DELAY_MS = 80;
const LISTENING_KEEPALIVE_MS = 650;

function recognitionLanguagesFor(preference: VoiceLanguagePreference) {
  if (preference === 'hindi') return ['hi-IN', 'en-IN'];
  if (preference === 'telugu_english') return ['en-IN', 'te-IN', 'hi-IN'];
  return ['en-IN', 'en-US', 'hi-IN', 'te-IN'];
}

function preferredRecognitionLanguage(preference: VoiceLanguagePreference, index = 0) {
  const languages = recognitionLanguagesFor(preference);
  return languages[index % languages.length] ?? languages[0] ?? 'en-IN';
}

const TELUGU_VISEMES: Record<string, VisemeCode> = {
  '\u0C05': 1, '\u0C06': 1, '\u0C3E': 1,
  '\u0C07': 2, '\u0C08': 2, '\u0C0E': 2, '\u0C0F': 2, '\u0C10': 2,
  '\u0C3F': 2, '\u0C40': 2, '\u0C46': 2, '\u0C47': 2, '\u0C48': 2,
  '\u0C09': 3, '\u0C0A': 3, '\u0C12': 3, '\u0C13': 3, '\u0C14': 3,
  '\u0C41': 3, '\u0C42': 3, '\u0C4A': 3, '\u0C4B': 3, '\u0C4C': 3,
  '\u0C2A': 4, '\u0C2B': 4, '\u0C2C': 4, '\u0C2D': 4, '\u0C2E': 4,
  '\u0C35': 5,
  '\u0C24': 6, '\u0C25': 6, '\u0C26': 6, '\u0C27': 6, '\u0C1F': 6,
  '\u0C20': 6, '\u0C21': 6, '\u0C22': 6, '\u0C28': 6, '\u0C23': 6,
  '\u0C32': 6, '\u0C33': 6, '\u0C30': 6, '\u0C31': 6, '\u0C38': 6,
  '\u0C15': 7, '\u0C16': 7, '\u0C17': 7, '\u0C18': 7, '\u0C1A': 7,
  '\u0C1B': 7, '\u0C1C': 7, '\u0C1D': 7, '\u0C2F': 7, '\u0C36': 7,
  '\u0C37': 7, '\u0C39': 7,
};

const HINDI_VISEMES: Record<string, VisemeCode> = {
  '\u0905': 1, '\u0906': 1, '\u093E': 1,
  '\u0907': 2, '\u0908': 2, '\u090F': 2, '\u0910': 2,
  '\u093F': 2, '\u0940': 2, '\u0947': 2, '\u0948': 2,
  '\u0909': 3, '\u090A': 3, '\u0913': 3, '\u0914': 3,
  '\u0941': 3, '\u0942': 3, '\u094B': 3, '\u094C': 3,
  '\u092A': 4, '\u092B': 4, '\u092C': 4, '\u092D': 4, '\u092E': 4,
  '\u0935': 5,
  '\u0924': 6, '\u0925': 6, '\u0926': 6, '\u0927': 6, '\u091F': 6,
  '\u0920': 6, '\u0921': 6, '\u0922': 6, '\u0928': 6, '\u0923': 6,
  '\u0932': 6, '\u0930': 6, '\u0938': 6,
  '\u0915': 7, '\u0916': 7, '\u0917': 7, '\u0918': 7, '\u091A': 7,
  '\u091B': 7, '\u091C': 7, '\u091D': 7, '\u092F': 7, '\u0936': 7,
  '\u0937': 7, '\u0939': 7,
};

const TELUGU_MATRA_VISEMES: Record<string, VisemeCode> = {
  '\u0C3E': 1,
  '\u0C3F': 2, '\u0C40': 2, '\u0C46': 2, '\u0C47': 2, '\u0C48': 2,
  '\u0C41': 3, '\u0C42': 3, '\u0C4A': 3, '\u0C4B': 3, '\u0C4C': 3,
};

const HINDI_MATRA_VISEMES: Record<string, VisemeCode> = {
  '\u093E': 1,
  '\u093F': 2, '\u0940': 2, '\u0947': 2, '\u0948': 2,
  '\u0941': 3, '\u0942': 3, '\u094B': 3, '\u094C': 3,
};

function isTeluguChar(char: string) {
  return /[\u0C00-\u0C7F]/.test(char);
}

function isHindiChar(char: string) {
  return /[\u0900-\u097F]/.test(char);
}

function isIndicMark(char: string) {
  return /[\u0C01-\u0C04\u0C3E-\u0C56\u0C62-\u0C63\u0901-\u0903\u093C-\u094D\u0951-\u0957\u0962-\u0963]/.test(char);
}

function latinVisemeAt(text: string, index: number): VisemeCode {
  const pair = text.slice(index, index + 2).toLowerCase();
  const char = text[index]?.toLowerCase() ?? '';
  if (!char.trim()) return 0;
  if (/[.!?,;:]/.test(char)) return 0;
  if (['ch', 'sh', 'jh', 'gy'].includes(pair)) return 7;
  if (pair === 'th') return 6;
  if (char === 'a') return 1;
  if ('eiy'.includes(char)) return 2;
  if ('ouw'.includes(char)) return 3;
  if ('pbm'.includes(char)) return 4;
  if ('fv'.includes(char)) return 5;
  if ('tdnlrsz'.includes(char)) return 6;
  if ('kgqcjx'.includes(char)) return 7;
  return 8;
}

function consumeSpeechCluster(text: string, index: number) {
  const char = text[index] ?? '';

  if (!char.trim() || /[.!?,;:]/.test(char)) {
    return { cluster: char, nextIndex: index + 1, kind: 'pause' as const };
  }

  if (isTeluguChar(char) || isHindiChar(char)) {
    let nextIndex = index + 1;
    while (nextIndex < text.length && isIndicMark(text[nextIndex] ?? '')) {
      nextIndex += 1;
    }

    return {
      cluster: text.slice(index, nextIndex),
      nextIndex,
      kind: isTeluguChar(char) ? ('telugu' as const) : ('hindi' as const),
    };
  }

  const pair = text.slice(index, index + 2).toLowerCase();
  if (['ch', 'sh', 'jh', 'gy', 'th'].includes(pair)) {
    return { cluster: text.slice(index, index + 2), nextIndex: index + 2, kind: 'latin' as const };
  }

  return { cluster: char, nextIndex: index + 1, kind: 'latin' as const };
}

function indicClusterVisemes(
  cluster: string,
  baseMap: Record<string, VisemeCode>,
  matraMap: Record<string, VisemeCode>
) {
  const base = baseMap[cluster[0] ?? ''] ?? 8;
  const matra = Array.from(cluster).find((char) => matraMap[char]);
  const vowel = matra ? matraMap[matra] : base === 4 || base === 5 || base === 6 || base === 7 ? 1 : base;

  if (base === vowel || base === 1 || base === 2 || base === 3) {
    return [{ viseme: vowel, weight: 1, intensity: vowel === 1 ? 0.95 : 0.72 }];
  }

  return [
    { viseme: base, weight: 0.38, intensity: base === 4 ? 0.32 : 0.55 },
    { viseme: vowel, weight: 0.82, intensity: vowel === 1 ? 0.95 : 0.74 },
  ];
}

function clusterToVisemeParts(text: string, index: number) {
  const token = consumeSpeechCluster(text, index);

  if (token.kind === 'pause') {
    const isPunctuation = /[.!?,;:]/.test(token.cluster);
    return {
      nextIndex: token.nextIndex,
      parts: [{ viseme: 0 as VisemeCode, weight: isPunctuation ? 2.5 : 0.95, intensity: 0 }],
    };
  }

  if (token.kind === 'telugu') {
    return {
      nextIndex: token.nextIndex,
      parts: indicClusterVisemes(token.cluster, TELUGU_VISEMES, TELUGU_MATRA_VISEMES),
    };
  }

  if (token.kind === 'hindi') {
    return {
      nextIndex: token.nextIndex,
      parts: indicClusterVisemes(token.cluster, HINDI_VISEMES, HINDI_MATRA_VISEMES),
    };
  }

  const viseme = latinVisemeAt(text, index);
  return {
    nextIndex: token.nextIndex,
    parts: [{ viseme, weight: token.cluster.length > 1 ? 1.18 : 1, intensity: viseme === 4 ? 0.34 : viseme === 1 ? 0.92 : 0.7 }],
  };
}

function buildVisemeTimeline(text: string, mode: VoiceLanguageMode, rate: number): VisemeFrame[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return [{ at: 0, viseme: 0, intensity: 0 }];

  const frames: VisemeFrame[] = [];
  let cursor = 0;
  const baseMs = mode === 'telugu' || mode === 'hindi' ? 118 : mode === 'mixed' ? 104 : 82;
  const msPerUnit = baseMs / Math.max(0.72, rate);

  let index = 0;
  while (index < clean.length) {
    const { nextIndex, parts } = clusterToVisemeParts(clean, index);

    for (const part of parts) {
      const previous = frames[frames.length - 1];
      if (!previous || previous.viseme !== part.viseme || part.viseme === 0) {
        frames.push({ at: cursor / 1000, viseme: part.viseme, intensity: part.intensity });
      }
      cursor += msPerUnit * part.weight;
    }

    index = Math.max(nextIndex, index + 1);
  }

  frames.push({ at: cursor / 1000, viseme: 0, intensity: 0 });
  return frames;
}

function getVisemeFrameAt(frames: VisemeFrame[], currentTime: number, actualDuration?: number) {
  if (!frames.length) {
    return { at: 0, viseme: 0 as VisemeCode, intensity: 0 };
  }

  const predictedDuration = frames[frames.length - 1]?.at ?? 0;
  const scaledTime =
    actualDuration && Number.isFinite(actualDuration) && actualDuration > 0 && predictedDuration > 0
      ? Math.min(predictedDuration, currentTime * (predictedDuration / actualDuration))
      : currentTime;

  let start = 0;
  let end = frames.length - 1;
  while (start < end) {
    const middle = Math.ceil((start + end) / 2);
    if ((frames[middle]?.at ?? 0) <= scaledTime) {
      start = middle;
    } else {
      end = middle - 1;
    }
  }

  return frames[start] ?? frames[0];
}

function detectVoiceLanguageMode(
  text: string,
  preference: VoiceLanguagePreference
): VoiceLanguageMode {
  const teluguChars = (text.match(/[\u0C00-\u0C7F]/g) ?? []).length;
  const hindiChars = (text.match(/[\u0900-\u097F]/g) ?? []).length;
  const latinChars = (text.match(/[A-Za-z]/g) ?? []).length;
  const words = new Set((text.toLowerCase().match(/[a-z]+/g) ?? []));

  if (hindiChars > 0) {
    return 'hindi';
  }
  if (teluguChars > 0 && latinChars > 0) {
    return 'mixed';
  }
  if (teluguChars > 0) {
    return 'telugu';
  }
  if (preference === 'hindi') return 'hindi';
  if (preference === 'telugu_english') return 'mixed';
  if (
    ['namaste', 'hindi', 'kaise', 'kya', 'mujhe', 'aap', 'hai', 'nahi', 'batao'].some((word) =>
      words.has(word)
    )
  ) {
    return 'hindi';
  }
  if (
    ['telugu', 'anna', 'andi', 'naku', 'naaku', 'meeru', 'ela', 'unnaru', 'cheppu'].some((word) =>
      words.has(word)
    )
  ) {
    return 'mixed';
  }
  return 'english';
}

function preferredLanguageMode(preference: VoiceLanguagePreference): VoiceLanguageMode {
  if (preference === 'hindi') return 'hindi';
  if (preference === 'telugu_english') return 'mixed';
  return 'english';
}

function languageMatches(lang: string, mode: VoiceLanguageMode) {
  const normalized = lang.toLowerCase();
  if (mode === 'hindi') {
    return normalized.startsWith('hi');
  }
  if (mode === 'telugu') {
    return normalized.startsWith('te');
  }
  if (mode === 'mixed') {
    return normalized.startsWith('te') || normalized.startsWith('en-in') || normalized.includes('india');
  }
  return normalized.startsWith('en');
}

export function useVoice() {
  const [state, setState] = useState<VoiceState>({
    isListening: false,
    isSpeaking: false,
    transcript: '',
    finalTranscript: '',
    speakingVolume: 0,
    viseme: 0,
  });
  const [availableVoices, setAvailableVoices] = useState<VoiceOption[]>([]);
  const [voiceGender, setVoiceGender] = useState<VoiceGender>('female');
  const [voiceTone, setVoiceTone] = useState<VoiceTone>('friendly');
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguagePreference>('telugu_english');
  const [backgroundListening, setBackgroundListening] = useState(false);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [voiceFrequencySignature, setVoiceFrequencySignature] =
    useState<VoiceFrequencySignature | null>(null);

  const recognitionRef = useRef<any>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const manuallyStoppedRef = useRef(false);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const visemeIntervalRef = useRef<number | null>(null);
  const sampleAudioRef = useRef<HTMLAudioElement | null>(null);
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null);
  const playbackUrlRef = useRef<string | null>(null);
  const speechQueueRef = useRef<QueuedSpeechItem[]>([]);
  const processingQueueRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const isSpeakingRef = useRef(false);
  const isListeningRef = useRef(false);
  const backgroundListeningRef = useRef(false);
  const recognitionStartingRef = useRef(false);
  const microphoneBlockedRef = useRef(false);
  const recognitionRestartTimerRef = useRef<number | null>(null);
  const recognitionLanguageIndexRef = useRef(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const sourceElementRef = useRef<HTMLAudioElement | null>(null);
  const audioFrameRef = useRef<number | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micAudioContextRef = useRef<AudioContext | null>(null);
  const micSourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const micFrameRef = useRef<number | null>(null);
  const micSignatureRef = useRef<VoiceFrequencySignature | null>(null);
  const visemeTimelineRef = useRef<VisemeFrame[]>([]);
  const visemeStartTimeRef = useRef(0);

  const stopSpeechNowRef = useRef<(nextState?: Partial<VoiceState>) => void>(() => undefined);

  useEffect(() => {
    isSpeakingRef.current = state.isSpeaking;
  }, [state.isSpeaking]);

  useEffect(() => {
    isListeningRef.current = state.isListening;
  }, [state.isListening]);

  useEffect(() => {
    backgroundListeningRef.current = backgroundListening;
  }, [backgroundListening]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    sampleAudioRef.current = new Audio(FEMALE_SAMPLE_PATH);
    playbackAudioRef.current = new Audio();

    const hydrateVoices = () => {
      const synth = window.speechSynthesis;
      synthRef.current = synth;
      const voices = [
        FEMALE_SAMPLE_OPTION,
        ...synth
          .getVoices()
          .map((voice) => ({
            id: voice.voiceURI,
            name: voice.name,
            lang: voice.lang,
            gender: inferGender(voice.name),
            kind: 'system' as const,
          }))
          .filter((voice) => {
            const normalized = voice.lang.toLowerCase();
            return (
              normalized.startsWith('en') ||
              normalized.startsWith('te') ||
              normalized.startsWith('hi') ||
              normalized.includes('india')
            );
          }),
      ];

      setAvailableVoices(voices);
      if (!selectedVoiceId && voices.length) {
        const preferred = voices.find((voice) => voice.gender === voiceGender) ?? voices[0];
        setSelectedVoiceId((current) => current || preferred.id);
      }
    };

    hydrateVoices();
    window.speechSynthesis.onvoiceschanged = hydrateVoices;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;
      recognition.lang = preferredRecognitionLanguage(
        voiceLanguage,
        recognitionLanguageIndexRef.current
      );

      recognition.onresult = (event: any) => {
        let interim = '';
        let finalResult = '';

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const alternatives = Array.from(event.results[i] ?? []) as SpeechRecognitionAlternative[];
          const strongestAlternative =
            alternatives.find((alternative) => alternative.confidence >= 0.45) ?? alternatives[0] ?? event.results[i][0];
          const value = strongestAlternative.transcript.trim();
          if (event.results[i].isFinal) {
            finalResult += `${value} `;
          } else {
            interim += `${value} `;
          }
        }

        const heardText = `${finalResult} ${interim}`.trim();
        const finalHeardText = finalResult.trim();
        if (isSpeakingRef.current && SPEECH_INTERRUPT_PATTERN.test(heardText)) {
          stopSpeechNowRef.current({ transcript: '', finalTranscript: '' });
          return;
        }

        if (isSpeakingRef.current && heardText.split(/\s+/).filter(Boolean).length >= 2) {
          stopSpeechNowRef.current();
          if (!finalHeardText) {
            setState((previous) => ({ ...previous, transcript: interim.trim() }));
            return;
          }
        }

        if (isSpeakingRef.current && finalHeardText) {
          stopSpeechNowRef.current();
          setState((previous) => ({
            ...previous,
            transcript: interim.trim(),
            finalTranscript: `${previous.finalTranscript} ${finalHeardText}`.trim(),
          }));
          return;
        }

        setState((previous) => {
          const nextFinal = finalResult.trim()
            ? `${previous.finalTranscript} ${finalResult.trim()}`.trim()
            : previous.finalTranscript;
          return {
            ...previous,
            transcript: interim.trim(),
            finalTranscript: nextFinal,
          };
        });
      };

      recognition.onstart = () => {
        manuallyStoppedRef.current = false;
        recognitionStartingRef.current = false;
        setState((previous) => ({ ...previous, isListening: true }));
      };

      recognition.onerror = (event: any) => {
        recognitionStartingRef.current = false;
        setState((previous) => ({ ...previous, isListening: false }));
        if (['not-allowed', 'service-not-allowed'].includes(event?.error)) {
          microphoneBlockedRef.current = true;
          manuallyStoppedRef.current = true;
          setBackgroundListening(false);
          return;
        }
        if (
          backgroundListeningRef.current &&
          !manuallyStoppedRef.current &&
          ['no-speech', 'audio-capture', 'network', 'aborted'].includes(event?.error)
        ) {
          if (['no-speech', 'network'].includes(event?.error)) {
            recognitionLanguageIndexRef.current += 1;
            recognition.lang = preferredRecognitionLanguage(
              voiceLanguage,
              recognitionLanguageIndexRef.current
            );
          }
          if (recognitionRestartTimerRef.current) {
            window.clearTimeout(recognitionRestartTimerRef.current);
          }
          recognitionRestartTimerRef.current = window.setTimeout(() => {
            try {
              recognitionStartingRef.current = true;
              recognition.start();
            } catch {
              recognitionStartingRef.current = false;
              // Browser may reject overlapping starts.
            }
          }, 240);
        }
      };

      recognition.onend = () => {
        recognitionStartingRef.current = false;
        setState((previous) => ({ ...previous, isListening: false }));
        if (backgroundListeningRef.current && !manuallyStoppedRef.current) {
          if (recognitionRestartTimerRef.current) {
            window.clearTimeout(recognitionRestartTimerRef.current);
          }
          recognitionRestartTimerRef.current = window.setTimeout(() => {
            try {
              recognitionStartingRef.current = true;
              recognition.start();
            } catch {
              recognitionStartingRef.current = false;
              // no-op; browser may reject overlapping starts
            }
          }, 220);
        }
      };

      recognitionRef.current = recognition;
    }

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
      try {
        recognitionRef.current?.abort?.();
      } catch {
        // Recognition can throw if the browser already stopped it.
      }
      recognitionRef.current = null;
      if (recognitionRestartTimerRef.current) {
        window.clearTimeout(recognitionRestartTimerRef.current);
        recognitionRestartTimerRef.current = null;
      }
    };
  }, [selectedVoiceId, voiceGender, voiceLanguage]);

  useEffect(() => {
    if (!availableVoices.length) return;

    const mode = preferredLanguageMode(voiceLanguage);
    const current = availableVoices.find((voice) => voice.id === selectedVoiceId);
    const genderMatched = availableVoices.find((voice) => voice.gender === voiceGender);
    const languageMatched = availableVoices.find(
      (voice) =>
        voice.gender === voiceGender &&
        languageMatches(voice.lang, mode)
    );
    const selected =
      current && current.gender === voiceGender && languageMatches(current.lang, mode)
        ? current
        : (languageMatched ?? genderMatched ?? current ?? availableVoices[0]);

    if (selected.id !== selectedVoiceId) {
      setSelectedVoiceId(selected.id);
    }

    if (typeof window !== 'undefined') {
      voiceRef.current =
        window.speechSynthesis.getVoices().find((voice) => voice.voiceURI === selected.id) ?? null;
    }
  }, [availableVoices, selectedVoiceId, voiceGender, voiceLanguage]);

  useEffect(() => {
    if (!recognitionRef.current) return;

    recognitionLanguageIndexRef.current = 0;
    recognitionRef.current.lang = preferredRecognitionLanguage(voiceLanguage);
  }, [voiceLanguage]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('akansha_voice_language', voiceLanguage);
  }, [voiceLanguage]);

  const voiceChoices = useMemo(
    () => {
      const filteredVoices = availableVoices.filter(
        (voice) =>
          voice.gender === voiceGender &&
          languageMatches(voice.lang, preferredLanguageMode(voiceLanguage))
      );

      return filteredVoices.length
        ? filteredVoices
        : availableVoices.filter((voice) => voice.gender === voiceGender);
    },
    [availableVoices, voiceGender, voiceLanguage]
  );

  const startVisemeAnimation = useCallback((text?: string, mode: VoiceLanguageMode = 'english', tone: VoiceTone = 'friendly') => {
    if (typeof window === 'undefined') return;
    if (visemeIntervalRef.current) {
      window.clearInterval(visemeIntervalRef.current);
    }

    const frames = text?.trim()
      ? buildVisemeTimeline(text, mode, TONE_CONFIG[tone].rate)
      : [];
    visemeTimelineRef.current = frames;
    visemeStartTimeRef.current = window.performance.now();

    visemeIntervalRef.current = window.setInterval(() => {
      if (visemeTimelineRef.current.length) {
        const elapsed = (window.performance.now() - visemeStartTimeRef.current) / 1000;
        const activeFrame = getVisemeFrameAt(visemeTimelineRef.current, elapsed);

        setState((previous) => ({
          ...previous,
          speakingVolume: activeFrame.intensity,
          viseme: activeFrame.viseme,
        }));
        return;
      }

      setState((previous) => ({
        ...previous,
        speakingVolume: 0.35 + Math.random() * 0.65,
        viseme: (previous.viseme + 1) % 5,
      }));
    }, frames.length ? 34 : 110);
  }, []);

  const stopVisemeAnimation = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (visemeIntervalRef.current) {
      window.clearInterval(visemeIntervalRef.current);
      visemeIntervalRef.current = null;
    }
    visemeTimelineRef.current = [];
    setState((previous) => ({ ...previous, speakingVolume: 0, viseme: 0 }));
  }, []);

  const stopAudioAnalysis = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (audioFrameRef.current) {
      window.cancelAnimationFrame(audioFrameRef.current);
      audioFrameRef.current = null;
    }
  }, []);

  const stopMicFrequencyCapture = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (micFrameRef.current) {
      window.cancelAnimationFrame(micFrameRef.current);
      micFrameRef.current = null;
    }
    try {
      micSourceNodeRef.current?.disconnect();
    } catch {
      // The browser may already have disconnected the node.
    }
    micSourceNodeRef.current = null;
    micAnalyserRef.current = null;
    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;
    void micAudioContextRef.current?.close().catch(() => undefined);
    micAudioContextRef.current = null;
  }, []);

  const startMicFrequencyCapture = useCallback(
    async (stream: MediaStream) => {
      if (typeof window === 'undefined') return;
      stopMicFrequencyCapture();

      const context = new window.AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.74;

      const source = context.createMediaStreamSource(stream);
      source.connect(analyser);

      micStreamRef.current = stream;
      micAudioContextRef.current = context;
      micSourceNodeRef.current = source;
      micAnalyserRef.current = analyser;

      const frequencyData = new Uint8Array(analyser.frequencyBinCount);
      const timeData = new Uint8Array(analyser.fftSize);
      const sampleRate = context.sampleRate || 48000;
      const binHz = sampleRate / analyser.fftSize;

      const tick = () => {
        analyser.getByteFrequencyData(frequencyData);
        analyser.getByteTimeDomainData(timeData);

        let weightedFrequency = 0;
        let totalEnergy = 0;
        let lowEnergy = 0;
        let midEnergy = 0;
        let highEnergy = 0;

        frequencyData.forEach((value, index) => {
          const energy = value / 255;
          const frequency = index * binHz;
          weightedFrequency += frequency * energy;
          totalEnergy += energy;
          if (frequency < 300) lowEnergy += energy;
          else if (frequency < 1800) midEnergy += energy;
          else highEnergy += energy;
        });

        const rms =
          Math.sqrt(
            timeData.reduce((sum, value) => {
              const centered = (value - 128) / 128;
              return sum + centered * centered;
            }, 0) / Math.max(1, timeData.length)
          ) || 0;

        const previous = micSignatureRef.current;
        const sampleCount = (previous?.sampleCount ?? 0) + 1;
        const centroid = totalEnergy ? weightedFrequency / totalEnergy : previous?.spectralCentroidHz ?? 0;
        const total = lowEnergy + midEnergy + highEnergy || 1;
        const next: VoiceFrequencySignature = {
          averageFrequencyHz: Math.round(centroid),
          spectralCentroidHz: Math.round(
            previous ? previous.spectralCentroidHz * 0.82 + centroid * 0.18 : centroid
          ),
          lowBandEnergy: Number(
            (previous ? previous.lowBandEnergy * 0.82 + (lowEnergy / total) * 0.18 : lowEnergy / total).toFixed(3)
          ),
          midBandEnergy: Number(
            (previous ? previous.midBandEnergy * 0.82 + (midEnergy / total) * 0.18 : midEnergy / total).toFixed(3)
          ),
          highBandEnergy: Number(
            (previous ? previous.highBandEnergy * 0.82 + (highEnergy / total) * 0.18 : highEnergy / total).toFixed(3)
          ),
          rmsLevel: Number((previous ? previous.rmsLevel * 0.82 + rms * 0.18 : rms).toFixed(4)),
          sampleCount,
          capturedAt: new Date().toISOString(),
        };

        micSignatureRef.current = next;
        if (sampleCount % 10 === 0) {
          setVoiceFrequencySignature(next);
        }
        micFrameRef.current = window.requestAnimationFrame(tick);
      };

      tick();
    },
    [stopMicFrequencyCapture]
  );

  const startSampleAudioAnalysis = useCallback(() => {
    if (typeof window === 'undefined' || !sampleAudioRef.current) return;

    const sampleAudio = sampleAudioRef.current;

    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new window.AudioContext();
      }

      const context = audioContextRef.current;

      if (context.state === 'suspended') {
        void context.resume();
      }

      if (!sourceNodeRef.current || sourceElementRef.current !== sampleAudio) {
        sourceNodeRef.current?.disconnect();
        sourceNodeRef.current = context.createMediaElementSource(sampleAudio);
        sourceElementRef.current = sampleAudio;
      }

      if (!analyserRef.current) {
        analyserRef.current = context.createAnalyser();
        analyserRef.current.fftSize = 256;
        analyserRef.current.smoothingTimeConstant = 0.82;
      }

      sourceNodeRef.current.disconnect();
      analyserRef.current.disconnect();
      sourceNodeRef.current.connect(analyserRef.current);
      analyserRef.current.connect(context.destination);

      const analyser = analyserRef.current;
      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteFrequencyData(dataArray);
        const average =
          dataArray.reduce((sum, value) => sum + value, 0) / Math.max(1, dataArray.length);
        const normalized = Math.min(1, Math.max(0.06, average / 72));

        setState((previous) => ({
          ...previous,
          speakingVolume: normalized,
          viseme: Math.max(0, Math.min(5, Math.round(normalized * 5))),
        }));

        audioFrameRef.current = window.requestAnimationFrame(tick);
      };

      stopAudioAnalysis();
      tick();
    } catch {
      startVisemeAnimation();
    }
  }, [startVisemeAnimation, stopAudioAnalysis]);

  const startPlaybackAudioAnalysis = useCallback((text?: string, mode: VoiceLanguageMode = 'english', tone: VoiceTone = 'friendly') => {
    if (typeof window === 'undefined' || !playbackAudioRef.current) return;

    const playbackAudio = playbackAudioRef.current;
    const textFrames = text?.trim()
      ? buildVisemeTimeline(text, mode, TONE_CONFIG[tone].rate)
      : [];

    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new window.AudioContext();
      }

      const context = audioContextRef.current;

      if (context.state === 'suspended') {
        void context.resume();
      }

      if (!sourceNodeRef.current || sourceElementRef.current !== playbackAudio) {
        sourceNodeRef.current?.disconnect();
        sourceNodeRef.current = context.createMediaElementSource(playbackAudio);
        sourceElementRef.current = playbackAudio;
      }

      if (!analyserRef.current) {
        analyserRef.current = context.createAnalyser();
        analyserRef.current.fftSize = 256;
        analyserRef.current.smoothingTimeConstant = 0.82;
      }

      sourceNodeRef.current.disconnect();
      analyserRef.current.disconnect();
      sourceNodeRef.current.connect(analyserRef.current);
      analyserRef.current.connect(context.destination);

      const analyser = analyserRef.current;
      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteFrequencyData(dataArray);
        const average =
          dataArray.reduce((sum, value) => sum + value, 0) / Math.max(1, dataArray.length);
        const normalized = Math.min(1, Math.max(0.06, average / 72));
        let activeViseme = Math.max(0, Math.min(5, Math.round(normalized * 5)));
        let activeVolume = normalized;

        if (textFrames.length) {
          const frame = getVisemeFrameAt(
            textFrames,
            playbackAudio.currentTime,
            playbackAudio.duration
          );

          activeViseme = frame.viseme;
          activeVolume = Math.max(normalized * 0.7, frame.intensity * 0.95);
        }

        setState((previous) => ({
          ...previous,
          speakingVolume: activeVolume,
          viseme: activeViseme,
        }));

        audioFrameRef.current = window.requestAnimationFrame(tick);
      };

      stopAudioAnalysis();
      tick();
    } catch {
      startVisemeAnimation(text, mode, tone);
    }
  }, [startVisemeAnimation, stopAudioAnalysis]);

  const stopAllSpeechPlayback = useCallback((nextState?: Partial<VoiceState>) => {
    stopRequestedRef.current = true;
    speechQueueRef.current = [];
    processingQueueRef.current = false;
    synthRef.current?.cancel();

    if (sampleAudioRef.current) {
      sampleAudioRef.current.pause();
      sampleAudioRef.current.currentTime = 0;
    }

    if (playbackAudioRef.current) {
      playbackAudioRef.current.pause();
      playbackAudioRef.current.currentTime = 0;
    }

    if (playbackUrlRef.current) {
      URL.revokeObjectURL(playbackUrlRef.current);
      playbackUrlRef.current = null;
    }

    stopAudioAnalysis();
    stopVisemeAnimation();
    setState((previous) => ({
      ...previous,
      isSpeaking: false,
      speakingVolume: 0,
      viseme: 0,
      ...nextState,
    }));
  }, [stopAudioAnalysis, stopVisemeAnimation]);

  const startListening = useCallback(() => {
    if (
      !recognitionRef.current ||
      isListeningRef.current ||
      recognitionStartingRef.current ||
      microphoneBlockedRef.current
    ) {
      return;
    }

    const startRecognition = () => {
      try {
        manuallyStoppedRef.current = false;
        recognitionStartingRef.current = true;
        if (recognitionRef.current) {
          recognitionRef.current.lang = preferredRecognitionLanguage(
            voiceLanguage,
            recognitionLanguageIndexRef.current
          );
        }
        recognitionRef.current?.start();
      } catch {
        recognitionStartingRef.current = false;
        // Browsers throw if start is called twice in a row.
      }
    };

    if (navigator.mediaDevices?.getUserMedia) {
      void navigator.mediaDevices
        .getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        })
        .then((stream) => {
          void startMicFrequencyCapture(stream);
          startRecognition();
        })
        .catch(() => {
          microphoneBlockedRef.current = true;
          manuallyStoppedRef.current = true;
          setBackgroundListening(false);
        });
      return;
    }

    startRecognition();
  }, [startMicFrequencyCapture, voiceLanguage]);

  useEffect(() => {
    stopSpeechNowRef.current = (nextState?: Partial<VoiceState>) => {
      stopAllSpeechPlayback(nextState);
      if (backgroundListeningRef.current && !manuallyStoppedRef.current) {
        window.setTimeout(() => startListening(), INTERRUPTION_RESTART_DELAY_MS);
      }
    };
  }, [startListening, stopAllSpeechPlayback]);

  const stopListening = useCallback(() => {
    manuallyStoppedRef.current = true;
    recognitionStartingRef.current = false;
    if (recognitionRestartTimerRef.current) {
      window.clearTimeout(recognitionRestartTimerRef.current);
      recognitionRestartTimerRef.current = null;
    }
    recognitionRef.current?.stop();
    stopMicFrequencyCapture();
    if (micSignatureRef.current) {
      setVoiceFrequencySignature(micSignatureRef.current);
    }
  }, [stopMicFrequencyCapture]);

  const setContinuousListening = useCallback((enabled: boolean) => {
    if (enabled) {
      microphoneBlockedRef.current = false;
      manuallyStoppedRef.current = false;
    }
    setBackgroundListening(enabled);
  }, []);

  const clearTranscript = useCallback(() => {
    setState((previous) => ({ ...previous, transcript: '', finalTranscript: '' }));
  }, []);

  const fetchSpeechBlob = useCallback(
    async (text: string, options?: SpeakOptions) => {
      const resolvedGender = options?.voiceGender ?? voiceGender;
      const resolvedTone = options?.voiceTone ?? voiceTone;
      const resolvedLanguagePreference = options?.voiceLanguage ?? voiceLanguage;
      const languageMode = detectVoiceLanguageMode(text, resolvedLanguagePreference);

      try {
        const ttsResponse = await fetch('http://localhost:8000/api/voice/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text,
            voice_gender: resolvedGender,
            voice_tone: resolvedTone,
            language_mode: languageMode,
          }),
        });

        if (!ttsResponse.ok) {
          return null;
        }

        return await ttsResponse.blob();
      } catch {
        return null;
      }
    },
    [voiceGender, voiceLanguage, voiceTone]
  );

  const playSpeechChunk = useCallback(
    async (item: QueuedSpeechItem) => {
      if (typeof window === 'undefined' || !synthRef.current) return;
      const text = item.text;
      const options = item.options;

      const resolvedGender = options?.voiceGender ?? voiceGender;
      synthRef.current.cancel();
      if (sampleAudioRef.current) {
        sampleAudioRef.current.pause();
        sampleAudioRef.current.currentTime = 0;
      }
      if (playbackAudioRef.current) {
        playbackAudioRef.current.pause();
        playbackAudioRef.current.currentTime = 0;
      }
      if (playbackUrlRef.current) {
        URL.revokeObjectURL(playbackUrlRef.current);
        playbackUrlRef.current = null;
      }

      const resolvedTone = options?.voiceTone ?? voiceTone;
      const resolvedLanguagePreference = options?.voiceLanguage ?? voiceLanguage;
      const languageMode = detectVoiceLanguageMode(text, resolvedLanguagePreference);

      try {
        const blob = shouldUseFastBrowserSpeech(text, options)
          ? null
          : item.preparedAudio
            ? await item.preparedAudio
            : await fetchSpeechBlob(text, options);
        if (blob && playbackAudioRef.current) {
          const playbackUrl = URL.createObjectURL(blob);
          playbackUrlRef.current = playbackUrl;

          const audio = playbackAudioRef.current;
          audio.src = playbackUrl;
          audio.currentTime = 0;

          audio.onplay = () => {
            setState((previous) => ({ ...previous, isSpeaking: true }));
            startPlaybackAudioAnalysis(text, languageMode, resolvedTone);
            if (backgroundListeningRef.current && !manuallyStoppedRef.current) {
              window.setTimeout(() => startListening(), INTERRUPTION_RESTART_DELAY_MS);
            }
          };

          await new Promise<void>((resolve, reject) => {
            audio.onended = () => {
              stopAudioAnalysis();
              stopVisemeAnimation();
              setState((previous) => ({
                ...previous,
                isSpeaking: false,
                speakingVolume: 0,
                viseme: 0,
              }));
              resolve();
            };

            audio.onerror = () => {
              stopAudioAnalysis();
              stopVisemeAnimation();
              setState((previous) => ({
                ...previous,
                isSpeaking: false,
                speakingVolume: 0,
                viseme: 0,
              }));
              reject(new Error('Audio playback failed'));
            };

            void audio.play().catch(reject);
          });
          return;
        }
      } catch {
        // fall back to browser speech synthesis below
      }

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang =
        languageMode === 'hindi' ? 'hi-IN' : languageMode === 'telugu' || languageMode === 'mixed' ? 'te-IN' : 'en-IN';
      const matchingVoice =
        (selectedVoiceId === FEMALE_SAMPLE_VOICE_ID
          ? null
          : window.speechSynthesis
              .getVoices()
              .find(
                (voice) =>
                  voice.voiceURI === selectedVoiceId && languageMatches(voice.lang, languageMode)
              )) ??
        window.speechSynthesis
          .getVoices()
          .find(
            (voice) =>
              inferGender(voice.name) === resolvedGender && languageMatches(voice.lang, languageMode)
          ) ??
        window.speechSynthesis
          .getVoices()
          .find((voice) => inferGender(voice.name) === resolvedGender) ??
        voiceRef.current;

      if (matchingVoice) {
        utterance.voice = matchingVoice;
      }

      utterance.rate = TONE_CONFIG[resolvedTone].rate;
      utterance.pitch = TONE_CONFIG[resolvedTone].pitch;
      utterance.volume = TONE_CONFIG[resolvedTone].volume;

      utterance.onstart = () => {
        setState((previous) => ({ ...previous, isSpeaking: true }));
        startVisemeAnimation(text, languageMode, resolvedTone);
        if (backgroundListeningRef.current && !manuallyStoppedRef.current) {
          window.setTimeout(() => startListening(), INTERRUPTION_RESTART_DELAY_MS);
        }
      };

      await new Promise<void>((resolve, reject) => {
        utterance.onend = () => {
          setState((previous) => ({ ...previous, isSpeaking: false }));
          stopVisemeAnimation();
          resolve();
        };

        utterance.onerror = () => {
          setState((previous) => ({ ...previous, isSpeaking: false }));
          stopVisemeAnimation();
          reject(new Error('Speech synthesis failed'));
        };

        synthRef.current?.speak(utterance);
      });
    },
    [
      selectedVoiceId,
      fetchSpeechBlob,
      startPlaybackAudioAnalysis,
      startListening,
      startVisemeAnimation,
      stopAudioAnalysis,
      stopVisemeAnimation,
      voiceGender,
      voiceLanguage,
      voiceTone,
    ]
  );

  const processSpeechQueue = useCallback(async () => {
    if (processingQueueRef.current) return;
    processingQueueRef.current = true;
    stopRequestedRef.current = false;

    while (!stopRequestedRef.current && speechQueueRef.current.length > 0) {
      const nextItem = speechQueueRef.current.shift();
      if (!nextItem?.text.trim()) continue;

      try {
        await playSpeechChunk(nextItem);
      } catch {
        // Skip failed chunks and keep the queue moving.
      }
    }

    processingQueueRef.current = false;
    if (!stopRequestedRef.current && backgroundListeningRef.current) {
      window.setTimeout(() => startListening(), INTERRUPTION_RESTART_DELAY_MS);
    }
  }, [playSpeechChunk, startListening]);

  const speak = useCallback(
    async (text: string, options?: QueueSpeakOptions) => {
      if (!text.trim()) return;

      if (!options?.queue) {
        stopAllSpeechPlayback();
      }

      stopRequestedRef.current = false;
      if (options?.queue && speechQueueRef.current.length > 0) {
        const lastIndex = speechQueueRef.current.length - 1;
        const lastQueuedItem = speechQueueRef.current[lastIndex];
        if ('preferBrowser' in (lastQueuedItem.options ?? {}) || options.preferBrowser) {
          speechQueueRef.current.push({
            text,
            options,
            preparedAudio:
              options?.queue && !shouldUseFastBrowserSpeech(text, options)
                ? fetchSpeechBlob(text, options)
                : undefined,
          });
          void processSpeechQueue();
          return;
        }
        const currentGender = options.voiceGender ?? voiceGender;
        const currentTone = options.voiceTone ?? voiceTone;
        const currentLanguage = options.voiceLanguage ?? voiceLanguage;
        const lastGender = lastQueuedItem.options?.voiceGender ?? voiceGender;
        const lastTone = lastQueuedItem.options?.voiceTone ?? voiceTone;
        const lastLanguage = lastQueuedItem.options?.voiceLanguage ?? voiceLanguage;

        if (
          lastGender === currentGender &&
          lastTone === currentTone &&
          lastLanguage === currentLanguage
        ) {
          const mergedText = `${lastQueuedItem.text.trim()} ${text.trim()}`.trim();
          speechQueueRef.current[lastIndex] = {
            ...lastQueuedItem,
            text: mergedText,
            preparedAudio: shouldUseFastBrowserSpeech(mergedText, lastQueuedItem.options)
              ? undefined
              : fetchSpeechBlob(mergedText, lastQueuedItem.options),
          };
          void processSpeechQueue();
          return;
        }
      }

      speechQueueRef.current.push({
        text,
        options,
        preparedAudio: options?.queue && !shouldUseFastBrowserSpeech(text, options) ? fetchSpeechBlob(text, options) : undefined,
      });
      void processSpeechQueue();
    },
    [
      fetchSpeechBlob,
      processSpeechQueue,
      stopAllSpeechPlayback,
      voiceGender,
      voiceLanguage,
      voiceTone,
    ]
  );

  const stopSpeaking = useCallback(() => {
    stopAllSpeechPlayback();
    if (backgroundListeningRef.current && !manuallyStoppedRef.current) {
      window.setTimeout(() => startListening(), INTERRUPTION_RESTART_DELAY_MS);
    }
  }, [startListening, stopAllSpeechPlayback]);

  useEffect(() => {
    if (!backgroundListening) return;

    manuallyStoppedRef.current = false;
    const keepAlive = window.setInterval(() => {
      if (
        backgroundListeningRef.current &&
        !manuallyStoppedRef.current &&
        !isListeningRef.current &&
        !recognitionStartingRef.current
      ) {
        startListening();
      }
    }, LISTENING_KEEPALIVE_MS);

    return () => window.clearInterval(keepAlive);
  }, [backgroundListening, startListening]);

  const previewSelectedVoice = useCallback(() => {
    if (selectedVoiceId === FEMALE_SAMPLE_VOICE_ID && sampleAudioRef.current) {
      const sampleAudio = sampleAudioRef.current;
      sampleAudio.pause();
      sampleAudio.currentTime = 0;
      stopVisemeAnimation();
      stopAudioAnalysis();
      setState((previous) => ({ ...previous, isSpeaking: true, speakingVolume: 0, viseme: 0 }));
      startSampleAudioAnalysis();

      sampleAudio.onended = () => {
        stopAudioAnalysis();
        setState((previous) => ({ ...previous, isSpeaking: false, speakingVolume: 0, viseme: 0 }));
      };

      void sampleAudio.play().catch(() => {
        stopAudioAnalysis();
        setState((previous) => ({ ...previous, isSpeaking: false, speakingVolume: 0, viseme: 0 }));
      });
      return;
    }

    speak("Hi, I'm Akansha. I'm ready to talk with you naturally.", {
      voiceGender,
      voiceTone,
    });
  }, [selectedVoiceId, speak, startSampleAudioAnalysis, stopAudioAnalysis, stopVisemeAnimation, voiceGender, voiceTone]);

  useEffect(() => {
    return () => {
      stopAudioAnalysis();
      if (sampleAudioRef.current) {
        sampleAudioRef.current.pause();
      }
      if (playbackAudioRef.current) {
        playbackAudioRef.current.pause();
      }
      if (playbackUrlRef.current) {
        URL.revokeObjectURL(playbackUrlRef.current);
      }
      stopMicFrequencyCapture();
      if (recognitionRestartTimerRef.current) {
        window.clearTimeout(recognitionRestartTimerRef.current);
      }
    };
  }, [stopAudioAnalysis, stopMicFrequencyCapture]);

  return {
    ...state,
    availableVoices,
    voiceChoices,
    voiceGender,
    voiceTone,
    voiceLanguage,
    backgroundListening,
    selectedVoiceId,
    voiceFrequencySignature,
    setVoiceGender,
    setVoiceTone,
    setVoiceLanguage,
    setBackgroundListening: setContinuousListening,
    setSelectedVoiceId,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    previewSelectedVoice,
    clearTranscript,
  };
}
