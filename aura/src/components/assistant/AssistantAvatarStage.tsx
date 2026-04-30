'use client';

import React, { useEffect, useMemo, useRef } from 'react';

type AssistantEmotion = 'happy' | 'neutral' | 'thinking' | 'sad' | 'surprised';
type VoiceGender = 'male' | 'female';

interface AssistantAvatarStageProps {
  isListening: boolean;
  isSpeaking: boolean;
  speakingVolume: number;
  viseme: number;
  emotion: AssistantEmotion;
  listenerEmotion: AssistantEmotion;
  voiceGender: VoiceGender;
}

const FEMALE_VIDEO_SRC = '/video/realistic-girl-avatar.mp4';
const ENHANCED_FEMALE_VIDEO_SRC = '/video/realistic-facial-animation.mp4';

const VIDEO_SEGMENTS = {
  idle: { start: 0.25, end: 1.3 },
  listening: { start: 1.35, end: 2.25 },
  speaking: {
    start: 2.35,
    end: 6.9,
    anchors: [2.46, 2.72, 3.02, 3.33, 3.68, 4.02, 4.32, 4.66, 5.04, 5.4, 5.82, 6.18, 6.52],
  },
} as const;

const VISEME_ANCHORS: Record<number, number[]> = {
  0: [2.38, 6.52],
  1: [3.02, 3.33, 4.02],
  2: [2.72, 5.4],
  3: [3.68, 6.18],
  4: [2.46, 6.52],
  5: [4.66],
  6: [5.04],
  7: [5.82],
  8: [4.32],
};

const STAGE_VARIANTS: Record<
  VoiceGender,
  {
    accent: string;
    glow: string;
    mediaType: 'video' | 'image';
    mediaSrc: string;
  }
> = {
  female: {
    accent: '#f472b6',
    glow: 'rgba(244,114,182,0.24)',
    mediaType: 'video',
    mediaSrc: ENHANCED_FEMALE_VIDEO_SRC,
  },
  male: {
    accent: '#38bdf8',
    glow: 'rgba(56,189,248,0.22)',
    mediaType: 'image',
    mediaSrc:
      'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=1200&q=80',
  },
};

const EMOTION_COPY: Record<AssistantEmotion, string> = {
  happy: 'Warm and engaged',
  neutral: 'Balanced and steady',
  thinking: 'Reflective and attentive',
  sad: 'Gentle and supportive',
  surprised: 'Bright and alert',
};

export function AssistantAvatarStage({
  isListening,
  isSpeaking,
  speakingVolume,
  viseme,
  emotion,
  listenerEmotion,
  voiceGender,
}: AssistantAvatarStageProps) {
  const variant = STAGE_VARIANTS[voiceGender];
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const phaseRef = useRef(0);
  const metadataReadyRef = useRef(false);
  const interactionMode = isSpeaking ? 'speaking' : isListening ? 'listening' : 'idle';
  const activeEmotion = interactionMode === 'listening' ? listenerEmotion : emotion;

  useEffect(() => {
    if (variant.mediaType !== 'video' || !videoRef.current) return;

    const video = videoRef.current;
    video.pause();

    if (!metadataReadyRef.current) {
      return;
    }

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    const tick = () => {
      if (!metadataReadyRef.current) {
        animationFrameRef.current = requestAnimationFrame(tick);
        return;
      }

      if (interactionMode === 'speaking') {
        const visemeKey = Math.max(0, Math.min(8, Math.round(viseme)));
        const anchors = VISEME_ANCHORS[visemeKey] ?? VIDEO_SEGMENTS.speaking.anchors;
        phaseRef.current = (phaseRef.current + 0.18 + speakingVolume * 0.04) % 1;
        const anchorIndex = Math.min(
          anchors.length - 1,
          Math.floor(phaseRef.current * anchors.length)
        );
        const microMotion = Math.sin(phaseRef.current * Math.PI * 2) * 0.018;
        const targetTime = Math.max(
          VIDEO_SEGMENTS.speaking.start,
          Math.min(VIDEO_SEGMENTS.speaking.end, anchors[anchorIndex] + microMotion)
        );

        if (Math.abs(video.currentTime - targetTime) > 0.018) {
          video.currentTime = targetTime;
        }
      } else if (interactionMode === 'listening') {
        const span = VIDEO_SEGMENTS.listening.end - VIDEO_SEGMENTS.listening.start;
        phaseRef.current = (phaseRef.current + 0.012) % 1;
        const targetTime =
          VIDEO_SEGMENTS.listening.start +
          (Math.sin(phaseRef.current * Math.PI * 2) * 0.5 + 0.5) * span;

        if (Math.abs(video.currentTime - targetTime) > 0.05) {
          video.currentTime = targetTime;
        }
      } else {
        const span = VIDEO_SEGMENTS.idle.end - VIDEO_SEGMENTS.idle.start;
        phaseRef.current = (phaseRef.current + 0.008) % 1;
        const targetTime =
          VIDEO_SEGMENTS.idle.start +
          (Math.sin(phaseRef.current * Math.PI * 2) * 0.5 + 0.5) * span;

        if (Math.abs(video.currentTime - targetTime) > 0.05) {
          video.currentTime = targetTime;
        }
      }

      animationFrameRef.current = requestAnimationFrame(tick);
    };

    animationFrameRef.current = requestAnimationFrame(tick);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [interactionMode, speakingVolume, variant.mediaType, viseme]);

  useEffect(() => {
    if (variant.mediaType !== 'video' || !videoRef.current) return;
    const video = videoRef.current;
    video.pause();
    video.currentTime = VIDEO_SEGMENTS.idle.start;
    metadataReadyRef.current = false;
    phaseRef.current = 0;
  }, [voiceGender, variant.mediaType]);

  const emotionTint = useMemo(() => {
    if (activeEmotion === 'happy') return 'from-emerald-400/15 via-transparent to-fuchsia-400/10';
    if (activeEmotion === 'sad') return 'from-sky-400/14 via-transparent to-slate-400/8';
    if (activeEmotion === 'thinking') return 'from-amber-300/14 via-transparent to-violet-400/10';
    if (activeEmotion === 'surprised') return 'from-rose-400/12 via-transparent to-cyan-300/10';
    return 'from-white/10 via-transparent to-white/5';
  }, [activeEmotion]);

  const mediaTransform =
    interactionMode === 'speaking'
      ? `scale(${1.014 + speakingVolume * 0.012}) translateY(-2px)`
      : interactionMode === 'listening'
        ? 'scale(1.025) translateY(-4px)'
        : 'scale(1.005) translateY(0px)';

  const mediaFilter = useMemo(() => {
    if (interactionMode === 'speaking') {
      if (activeEmotion === 'happy') return 'saturate(1.08) contrast(1.03) brightness(1.01)';
      if (activeEmotion === 'sad') return 'saturate(0.9) contrast(1.04) brightness(0.94)';
      if (activeEmotion === 'thinking') return 'saturate(0.98) contrast(1.08) brightness(0.97)';
      if (activeEmotion === 'surprised') return 'saturate(1.1) contrast(1.08) brightness(1.02)';
      return 'saturate(1.02) contrast(1.04) brightness(0.99)';
    }

    if (interactionMode === 'listening') {
      return 'saturate(0.96) contrast(1.06) brightness(0.95)';
    }

    return 'saturate(0.98) contrast(1.02) brightness(0.96)';
  }, [activeEmotion, interactionMode]);

  const objectPosition =
    interactionMode === 'listening'
      ? 'center 20%'
      : activeEmotion === 'thinking'
        ? 'center 18%'
        : 'center center';

  const ringOpacity = interactionMode === 'speaking' ? 0.9 : interactionMode === 'listening' ? 0.6 : 0.35;
  const ringScale = interactionMode === 'speaking' ? 1.05 + speakingVolume * 0.02 : 1;
  const statusLabel =
    interactionMode === 'speaking'
      ? `Speaking - ${EMOTION_COPY[activeEmotion]}`
      : interactionMode === 'listening'
        ? `Listening - ${EMOTION_COPY[activeEmotion]}`
        : `Ready - ${EMOTION_COPY[activeEmotion]}`;

  return (
    <div className="relative h-full overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(108,71,255,0.24),_transparent_38%),radial-gradient(circle_at_bottom,_rgba(34,197,94,0.12),_transparent_28%),linear-gradient(180deg,_#030712_0%,_#0b1120_100%)]">
      <style jsx>{`
        .stage-float {
          animation: stageFloat 6s ease-in-out infinite;
        }

        .glass-sheen {
          animation: glassSheen 10s linear infinite;
        }

        .ambient-pulse {
          animation: ambientPulse 4.8s ease-in-out infinite;
        }

        @keyframes stageFloat {
          0%,
          100% {
            transform: translateY(0px);
          }
          50% {
            transform: translateY(-8px);
          }
        }

        @keyframes glassSheen {
          0% {
            transform: translateX(-120%) rotate(16deg);
          }
          100% {
            transform: translateX(120%) rotate(16deg);
          }
        }

        @keyframes ambientPulse {
          0%,
          100% {
            opacity: 0.5;
          }
          50% {
            opacity: 0.9;
          }
        }

        .idle-breathe {
          animation: idleBreathe 7.5s ease-in-out infinite;
        }

        @keyframes idleBreathe {
          0%,
          100% {
            transform: scale(1);
          }
          50% {
            transform: scale(1.018);
          }
        }
      `}</style>

      <div className="absolute inset-0 opacity-60">
        <div className="ambient-pulse absolute left-[10%] top-[14%] h-36 w-36 rounded-full bg-fuchsia-500/14 blur-3xl" />
        <div className="ambient-pulse absolute right-[12%] top-[28%] h-28 w-28 rounded-full bg-sky-400/14 blur-3xl" />
        <div className="ambient-pulse absolute bottom-[10%] left-[20%] h-44 w-44 rounded-full bg-emerald-400/10 blur-3xl" />
      </div>

      <div className="absolute inset-x-0 top-10 z-10 flex justify-center px-6">
        <div className="rounded-full border border-white/10 bg-slate-950/72 px-4 py-2 text-sm text-slate-100 backdrop-blur-xl">
          {statusLabel}
        </div>
      </div>

      <div className="absolute inset-x-0 bottom-0 top-24 flex items-center justify-center px-7 pb-14">
        <div
          className="stage-float relative h-[560px] w-[392px] max-w-full overflow-hidden rounded-[42px] border border-white/15 bg-white/5 p-3 backdrop-blur-xl transition-all duration-300"
          style={{
            boxShadow: `0 0 0 1px rgba(255,255,255,0.06), 0 24px 90px ${variant.glow}`,
          }}
        >
          <div className="relative h-full overflow-hidden rounded-[34px] border border-white/10 bg-slate-950/40">
            <div className={`absolute inset-0 bg-gradient-to-b ${emotionTint}`} />
            <div
              className="absolute inset-5 z-[1] rounded-[28px] border border-white/10 transition-all duration-200"
              style={{
                boxShadow: `0 0 0 1px rgba(255,255,255,0.03), 0 0 48px ${variant.glow}`,
                opacity: ringOpacity,
                transform: `scale(${ringScale})`,
              }}
            />

            <div className="absolute inset-0 overflow-hidden">
              {variant.mediaType === 'video' ? (
                <video
                  src={variant.mediaSrc}
                  muted
                  loop
                  playsInline
                  preload="auto"
                  className="idle-breathe h-full w-full scale-110 object-cover object-center blur-3xl opacity-35"
                />
              ) : (
                <img
                  src={variant.mediaSrc}
                  alt=""
                  className="idle-breathe h-full w-full scale-110 object-cover object-center blur-3xl opacity-30"
                />
              )}
            </div>

            {variant.mediaType === 'video' ? (
              <video
                ref={videoRef}
                src={variant.mediaSrc}
                muted
                playsInline
                preload="auto"
                onLoadedMetadata={(event) => {
                  metadataReadyRef.current = true;
                  event.currentTarget.currentTime = VIDEO_SEGMENTS.idle.start;
                }}
                className="relative z-[2] h-full w-full object-cover transition-transform duration-200"
                style={{ transform: mediaTransform, filter: mediaFilter, objectPosition }}
              />
            ) : (
              <img
                src={variant.mediaSrc}
                alt="Assistant portrait"
                className="relative z-[2] h-full w-full object-cover transition-transform duration-300"
                style={{ transform: mediaTransform, filter: mediaFilter, objectPosition }}
              />
            )}

            <div className="absolute inset-0 z-[3] bg-[linear-gradient(180deg,rgba(2,6,23,0.05)_0%,rgba(2,6,23,0.12)_44%,rgba(2,6,23,0.38)_100%)]" />
            <div className="absolute inset-0 z-[3] bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.18),_transparent_30%),radial-gradient(circle_at_bottom,_rgba(17,24,39,0.28),_transparent_45%)]" />
            <div className="glass-sheen absolute -left-1/3 top-0 h-full w-1/3 bg-white/10 blur-2xl" />
            <div className="absolute inset-x-[10%] top-[10%] z-[3] h-20 rounded-full bg-white/8 blur-3xl" />

            <div className="absolute inset-x-0 bottom-0 z-[3] h-40 bg-gradient-to-t from-[#040812] via-[#040812]/70 to-transparent" />

            <div className="absolute inset-x-0 bottom-4 z-[4] flex justify-center">
              <div className="rounded-full border border-white/10 bg-slate-950/72 px-4 py-2 text-xs uppercase tracking-[0.26em] text-slate-200 backdrop-blur-xl">
                {voiceGender === 'female' ? 'Real presence mode' : 'Studio presence mode'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-12 z-10 flex justify-center">
        <div className="flex items-end gap-2">
          {Array.from({ length: 7 }).map((_, index) => {
            const height = isSpeaking
              ? 14 + Math.max(4, speakingVolume * 40) - index * 1.4
              : 10 + ((index + 1) % 3) * 4;
            return (
              <span
                key={`presence-wave-${index}`}
                className="w-2 rounded-full bg-gradient-to-t from-[#6c47ff] via-[#818cf8] to-[#34d399] opacity-80 transition-all duration-100"
                style={{ height }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
