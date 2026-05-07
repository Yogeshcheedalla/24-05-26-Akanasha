'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type VoiceGender = 'male' | 'female';
export type VoiceTone = 'friendly' | 'professional' | 'energetic' | 'calm';
export type VoiceLanguagePreference = 'telugu_english' | 'english' | 'hindi';

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
  if (preference === 'english') return 'english';
  if (preference === 'hindi') return 'hindi';

  const teluguChars = (text.match(/[\u0C00-\u0C7F]/g) ?? []).length;
  const hindiChars = (text.match(/[\u0900-\u097F]/g) ?? []).length;
  const latinChars = (text.match(/[A-Za-z]/g) ?? []).length;

  if (hindiChars > 0) {
    return 'hindi';
  }
  if (teluguChars > 0 && latinChars > 0) {
    return 'mixed';
  }
  if (teluguChars > 0) {
    return 'telugu';
  }
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
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const sourceElementRef = useRef<HTMLAudioElement | null>(null);
  const audioFrameRef = useRef<number | null>(null);
  const visemeTimelineRef = useRef<VisemeFrame[]>([]);
  const visemeStartTimeRef = useRef(0);

  useEffect(() => {
    isSpeakingRef.current = state.isSpeaking;
  }, [state.isSpeaking]);

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
        setSelectedVoiceId(preferred.id);
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
      recognition.lang =
        voiceLanguage === 'english'
          ? 'en-IN'
          : voiceLanguage === 'hindi'
            ? 'hi-IN'
            : 'te-IN';

      recognition.onresult = (event: any) => {
        let interim = '';
        let finalResult = '';

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const value = event.results[i][0].transcript.trim();
          if (event.results[i].isFinal) {
            finalResult += `${value} `;
          } else {
            interim += `${value} `;
          }
        }

        const heardText = `${finalResult} ${interim}`.trim();
        if (isSpeakingRef.current && SPEECH_INTERRUPT_PATTERN.test(heardText)) {
          stopRequestedRef.current = true;
          speechQueueRef.current = [];
          processingQueueRef.current = false;
          synthRef.current?.cancel();

          const sampleAudio = sampleAudioRef.current;
          if (sampleAudio) {
            sampleAudio.pause();
            sampleAudio.currentTime = 0;
          }

          const playbackAudio = playbackAudioRef.current;
          if (playbackAudio) {
            playbackAudio.pause();
            playbackAudio.currentTime = 0;
          }

          if (playbackUrlRef.current) {
            URL.revokeObjectURL(playbackUrlRef.current);
            playbackUrlRef.current = null;
          }

          if (audioFrameRef.current) {
            window.cancelAnimationFrame(audioFrameRef.current);
            audioFrameRef.current = null;
          }

          if (visemeIntervalRef.current) {
            window.clearInterval(visemeIntervalRef.current);
            visemeIntervalRef.current = null;
          }

          setState((previous) => ({
            ...previous,
            isSpeaking: false,
            speakingVolume: 0,
            viseme: 0,
            transcript: '',
            finalTranscript: '',
          }));
          return;
        }

        setState((previous) => ({
          ...previous,
          transcript: interim.trim(),
          finalTranscript: finalResult.trim() || previous.finalTranscript,
        }));
      };

      recognition.onstart = () => {
        manuallyStoppedRef.current = false;
        setState((previous) => ({ ...previous, isListening: true }));
      };

      recognition.onerror = () => {
        setState((previous) => ({ ...previous, isListening: false }));
      };

      recognition.onend = () => {
        setState((previous) => ({ ...previous, isListening: false }));
        if (backgroundListening && !manuallyStoppedRef.current) {
          window.setTimeout(() => {
            try {
              recognition.start();
            } catch {
              // no-op; browser may reject overlapping starts
            }
          }, 250);
        }
      };

      recognitionRef.current = recognition;
    }

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, [backgroundListening, selectedVoiceId, voiceGender, voiceLanguage]);

  useEffect(() => {
    if (!availableVoices.length) return;

    const current = availableVoices.find((voice) => voice.id === selectedVoiceId);
    const genderMatched = availableVoices.find((voice) => voice.gender === voiceGender);
    const languageMatched = availableVoices.find(
      (voice) =>
        voice.gender === voiceGender &&
        languageMatches(
          voice.lang,
          voiceLanguage === 'english'
            ? 'english'
            : voiceLanguage === 'hindi'
              ? 'hindi'
              : 'mixed'
        )
    );
    const selected =
      current && current.gender === voiceGender
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

    recognitionRef.current.lang =
      voiceLanguage === 'english'
        ? 'en-IN'
        : voiceLanguage === 'hindi'
          ? 'hi-IN'
          : 'te-IN';
  }, [voiceLanguage]);

  const voiceChoices = useMemo(
    () => {
      const filteredVoices = availableVoices.filter(
        (voice) =>
          voice.gender === voiceGender &&
          languageMatches(
            voice.lang,
            voiceLanguage === 'english'
              ? 'english'
              : voiceLanguage === 'hindi'
                ? 'hindi'
                : 'mixed'
          )
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
        const normalized = Math.min(1, average / 110);

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
        const normalized = Math.min(1, average / 110);
        let activeViseme = Math.max(0, Math.min(5, Math.round(normalized * 5)));
        let activeVolume = normalized;

        if (textFrames.length) {
          const frame = getVisemeFrameAt(
            textFrames,
            playbackAudio.currentTime,
            playbackAudio.duration
          );

          activeViseme = frame.viseme;
          activeVolume = Math.max(normalized * 0.55, frame.intensity * 0.9);
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

  const startListening = useCallback(() => {
    if (!recognitionRef.current || state.isListening) return;
    if (state.isSpeaking) {
      synthRef.current?.cancel();
    }

    try {
      manuallyStoppedRef.current = false;
      recognitionRef.current.start();
    } catch {
      // Browsers throw if start is called twice in a row.
    }
  }, [state.isListening, state.isSpeaking]);

  const stopListening = useCallback(() => {
    manuallyStoppedRef.current = true;
    recognitionRef.current?.stop();
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
        const blob = item.preparedAudio ? await item.preparedAudio : await fetchSpeechBlob(text, options);
        if (blob && playbackAudioRef.current) {
          const playbackUrl = URL.createObjectURL(blob);
          playbackUrlRef.current = playbackUrl;

          const audio = playbackAudioRef.current;
          audio.src = playbackUrl;
          audio.currentTime = 0;

          audio.onplay = () => {
            setState((previous) => ({ ...previous, isSpeaking: true }));
            startPlaybackAudioAnalysis(text, languageMode, resolvedTone);
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
    if (!stopRequestedRef.current && backgroundListening) {
      startListening();
    }
  }, [backgroundListening, playSpeechChunk, startListening]);

  const speak = useCallback(
    async (text: string, options?: QueueSpeakOptions) => {
      if (!text.trim()) return;

      if (!options?.queue) {
        stopRequestedRef.current = true;
        speechQueueRef.current = [];
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
      }

      stopRequestedRef.current = false;
      if (options?.queue && speechQueueRef.current.length > 0) {
        const lastIndex = speechQueueRef.current.length - 1;
        const lastQueuedItem = speechQueueRef.current[lastIndex];
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
            preparedAudio: fetchSpeechBlob(mergedText, lastQueuedItem.options),
          };
          void processSpeechQueue();
          return;
        }
      }

      speechQueueRef.current.push({
        text,
        options,
        preparedAudio: options?.queue ? fetchSpeechBlob(text, options) : undefined,
      });
      void processSpeechQueue();
    },
    [
      fetchSpeechBlob,
      processSpeechQueue,
      stopAudioAnalysis,
      stopVisemeAnimation,
      voiceGender,
      voiceLanguage,
      voiceTone,
    ]
  );

  const stopSpeaking = useCallback(() => {
    stopRequestedRef.current = true;
    speechQueueRef.current = [];
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
    setState((previous) => ({ ...previous, isSpeaking: false }));
    stopVisemeAnimation();
    stopAudioAnalysis();
  }, [stopAudioAnalysis, stopVisemeAnimation]);

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
    };
  }, [stopAudioAnalysis]);

  return {
    ...state,
    availableVoices,
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
  };
}
