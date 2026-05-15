'use client';

import React, { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Group, Mesh } from 'three';

type AvatarEmotion = 'happy' | 'neutral' | 'thinking' | 'sad' | 'surprised';

interface AvatarProps {
  isSpeaking: boolean;
  speakingVolume?: number;
  viseme?: number;
  emotion?: AvatarEmotion;
}

const EMOTION_COLORS: Record<
  AvatarEmotion,
  { skin: string; skinWarm: string; aura: string; blush: string; lip: string; eye: string }
> = {
  neutral: { skin: '#efc8b3', skinWarm: '#dca78d', aura: '#8b5cf6', blush: '#f4a7a7', lip: '#b84c62', eye: '#5da5d8' },
  happy: { skin: '#f4cdb7', skinWarm: '#e8ab93', aura: '#ec4899', blush: '#ff9fb6', lip: '#d14d70', eye: '#58b9d5' },
  thinking: { skin: '#efc7b0', skinWarm: '#dba489', aura: '#38bdf8', blush: '#efb0a4', lip: '#a9435e', eye: '#7aa7dd' },
  sad: { skin: '#e7b59f', skinWarm: '#cd9078', aura: '#64748b', blush: '#d99898', lip: '#92445a', eye: '#6f91bd' },
  surprised: { skin: '#f5d1ba', skinWarm: '#e8ac91', aura: '#f59e0b', blush: '#ffb4a2', lip: '#c94b63', eye: '#65c3df' },
};

function HairStrand({
  position,
  rotation,
  scale,
}: {
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
}) {
  return (
    <mesh position={position} rotation={rotation} scale={scale}>
      <sphereGeometry args={[0.34, 32, 16]} />
      <meshStandardMaterial color="#211827" roughness={0.72} metalness={0.04} />
    </mesh>
  );
}

export function Avatar({
  isSpeaking,
  speakingVolume = 0,
  viseme = 0,
  emotion = 'neutral',
}: AvatarProps) {
  const rootRef = useRef<Group>(null);
  const headRef = useRef<Group>(null);
  const jawRef = useRef<Group>(null);
  const mouthRef = useRef<Mesh>(null);
  const upperLipRef = useRef<Mesh>(null);
  const lowerLipRef = useRef<Mesh>(null);
  const leftEyeRef = useRef<Group>(null);
  const rightEyeRef = useRef<Group>(null);
  const leftPupilRef = useRef<Mesh>(null);
  const rightPupilRef = useRef<Mesh>(null);
  const leftBrowRef = useRef<Mesh>(null);
  const rightBrowRef = useRef<Mesh>(null);
  const chestRef = useRef<Group>(null);
  const hairRef = useRef<Group>(null);
  const auraRef = useRef<Mesh>(null);

  const palette = useMemo(() => EMOTION_COLORS[emotion], [emotion]);

  useFrame(({ clock }) => {
    const elapsed = clock.elapsedTime;
    const energy = Math.max(0, Math.min(1, speakingVolume));
    const blinkPhase = (Math.sin(elapsed * 0.58) + 1) * 0.5;
    const blink = blinkPhase > 0.982 ? 0.08 : emotion === 'surprised' ? 1.24 : 1;
    const gazeX = Math.sin(elapsed * 0.32) * 0.035;
    const gazeY = Math.cos(elapsed * 0.25) * 0.024;
    const breath = Math.sin(elapsed * 0.82) * 0.045;
    const turn = Math.sin(elapsed * 0.22) * 0.12;
    const nod = Math.sin(elapsed * 0.44) * 0.025;
    const roundedViseme = Math.max(0, Math.min(8, Math.round(viseme)));
    const vowelOpen = [1, 3, 7].includes(roundedViseme) ? 1 : [2, 5, 8].includes(roundedViseme) ? 0.64 : 0.38;
    const speakingOpen = isSpeaking ? 0.045 + energy * 0.16 + vowelOpen * 0.052 : 0.014;
    const happyLift = emotion === 'happy' ? 0.05 : 0;
    const sadDrop = emotion === 'sad' ? -0.055 : 0;
    const thinkingTilt = emotion === 'thinking' ? 0.08 : 0;

    if (rootRef.current) {
      rootRef.current.position.y = -0.18 + breath;
      rootRef.current.rotation.y = turn;
      rootRef.current.rotation.x = sadDrop * 0.45 + thinkingTilt * 0.18 + nod;
    }

    if (headRef.current) {
      headRef.current.rotation.z = emotion === 'thinking' ? 0.055 : emotion === 'sad' ? -0.025 : 0;
      headRef.current.position.y = 0.5 + happyLift + (isSpeaking ? energy * 0.015 : 0);
    }

    if (chestRef.current) {
      chestRef.current.scale.y = 1 + Math.sin(elapsed * 1.3) * 0.012;
    }

    if (hairRef.current) {
      hairRef.current.rotation.z = Math.sin(elapsed * 0.5) * 0.018;
    }

    if (leftEyeRef.current && rightEyeRef.current) {
      leftEyeRef.current.scale.y = blink;
      rightEyeRef.current.scale.y = blink;
      leftEyeRef.current.position.set(-0.26 + gazeX, 0.18 + gazeY, 0.73);
      rightEyeRef.current.position.set(0.26 + gazeX, 0.18 + gazeY, 0.73);
    }

    if (leftPupilRef.current && rightPupilRef.current) {
      leftPupilRef.current.position.set(gazeX * 0.72, gazeY * 0.62, 0.063);
      rightPupilRef.current.position.set(gazeX * 0.72, gazeY * 0.62, 0.063);
    }

    if (jawRef.current) {
      jawRef.current.rotation.x = speakingOpen;
      jawRef.current.position.y = -0.3 - speakingOpen * 0.11;
    }

    if (mouthRef.current) {
      mouthRef.current.scale.x = emotion === 'happy' ? 1.08 : emotion === 'sad' ? 0.82 : roundedViseme === 3 ? 0.78 : 0.92;
      mouthRef.current.scale.y = 0.26 + speakingOpen * 2.35;
      mouthRef.current.position.y = emotion === 'happy' ? -0.095 : emotion === 'sad' ? -0.13 : -0.115;
    }

    if (upperLipRef.current && lowerLipRef.current) {
      upperLipRef.current.position.y = -0.075 + (emotion === 'happy' ? 0.018 : 0);
      lowerLipRef.current.position.y = -0.15 - speakingOpen * 0.05;
      lowerLipRef.current.scale.y = 0.18 + speakingOpen * 0.62;
    }

    if (leftBrowRef.current && rightBrowRef.current) {
      const browLift = emotion === 'surprised' ? 0.09 : emotion === 'happy' ? 0.025 : emotion === 'sad' ? -0.045 : 0;
      leftBrowRef.current.position.y = 0.45 + browLift;
      rightBrowRef.current.position.y = 0.45 + browLift;
      leftBrowRef.current.rotation.z = emotion === 'thinking' ? 0.24 : emotion === 'sad' ? -0.14 : 0.08;
      rightBrowRef.current.rotation.z = emotion === 'thinking' ? -0.08 : emotion === 'sad' ? 0.14 : -0.08;
    }

    if (auraRef.current) {
      const auraPulse = isSpeaking ? 1.08 + energy * 0.18 : 1 + Math.sin(elapsed) * 0.035;
      auraRef.current.scale.set(auraPulse, auraPulse, auraPulse);
      auraRef.current.rotation.z = elapsed * 0.18;
    }
  });

  return (
    <group ref={rootRef} position={[0, -0.18, 0]}>
      <mesh ref={auraRef} position={[0, 0.48, -0.22]}>
        <torusGeometry args={[1.46, 0.032, 28, 140]} />
        <meshBasicMaterial color={palette.aura} transparent opacity={0.42} />
      </mesh>

      <group ref={chestRef} position={[0, -1.78, 0]}>
        <mesh scale={[1.18, 0.74, 0.72]}>
          <sphereGeometry args={[1.08, 48, 24]} />
          <meshStandardMaterial color="#111827" roughness={0.76} metalness={0.14} />
        </mesh>
        <mesh position={[0, 0.2, 0.38]} scale={[0.82, 0.36, 0.14]}>
          <sphereGeometry args={[0.58, 36, 18]} />
          <meshStandardMaterial color="#e5e7eb" roughness={0.6} metalness={0.04} />
        </mesh>
        <mesh position={[-0.7, -0.1, 0.05]} rotation={[0, 0, -0.18]} scale={[0.5, 0.24, 0.36]}>
          <sphereGeometry args={[0.86, 32, 18]} />
          <meshStandardMaterial color="#111827" roughness={0.8} />
        </mesh>
        <mesh position={[0.7, -0.1, 0.05]} rotation={[0, 0, 0.18]} scale={[0.5, 0.24, 0.36]}>
          <sphereGeometry args={[0.86, 32, 18]} />
          <meshStandardMaterial color="#111827" roughness={0.8} />
        </mesh>
      </group>

      <group ref={headRef} position={[0, 0.5, 0]}>
        <mesh position={[0, -0.72, 0.02]}>
          <cylinderGeometry args={[0.17, 0.25, 0.42, 28]} />
          <meshStandardMaterial color={palette.skinWarm} roughness={0.54} metalness={0.03} />
        </mesh>

        <mesh scale={[0.78, 1.04, 0.74]}>
          <sphereGeometry args={[0.92, 80, 64]} />
          <meshStandardMaterial color={palette.skin} roughness={0.44} metalness={0.04} />
        </mesh>

        <mesh position={[0, -0.16, 0.69]} scale={[0.54, 0.45, 0.14]}>
          <sphereGeometry args={[0.58, 48, 24]} />
          <meshStandardMaterial color={palette.skinWarm} roughness={0.52} transparent opacity={0.36} />
        </mesh>

        <group ref={hairRef}>
          <mesh position={[0, 0.55, -0.06]} scale={[0.82, 0.34, 0.72]}>
            <sphereGeometry args={[0.9, 64, 32]} />
            <meshStandardMaterial color="#211827" roughness={0.72} metalness={0.04} />
          </mesh>
          <HairStrand position={[-0.58, 0.04, 0.18]} rotation={[0.08, -0.05, 0.08]} scale={[0.3, 1.12, 0.2]} />
          <HairStrand position={[0.58, 0.04, 0.18]} rotation={[0.08, 0.05, -0.08]} scale={[0.3, 1.12, 0.2]} />
          <HairStrand position={[-0.18, 0.72, 0.44]} rotation={[0.28, 0.04, -0.18]} scale={[0.24, 0.68, 0.12]} />
          <HairStrand position={[0.16, 0.7, 0.44]} rotation={[0.28, -0.04, 0.16]} scale={[0.24, 0.64, 0.12]} />
        </group>

        <mesh position={[-0.79, -0.05, 0.03]} rotation={[0, 0, -0.08]} scale={[0.68, 0.92, 0.48]}>
          <sphereGeometry args={[0.16, 24, 18]} />
          <meshStandardMaterial color={palette.skin} roughness={0.52} />
        </mesh>
        <mesh position={[0.79, -0.05, 0.03]} rotation={[0, 0, 0.08]} scale={[0.68, 0.92, 0.48]}>
          <sphereGeometry args={[0.16, 24, 18]} />
          <meshStandardMaterial color={palette.skin} roughness={0.52} />
        </mesh>

        <mesh position={[-0.38, -0.05, 0.76]} scale={[1.25, 0.72, 0.34]}>
          <sphereGeometry args={[0.11, 24, 14]} />
          <meshStandardMaterial color={palette.blush} transparent opacity={0.3} roughness={0.5} />
        </mesh>
        <mesh position={[0.38, -0.05, 0.76]} scale={[1.25, 0.72, 0.34]}>
          <sphereGeometry args={[0.11, 24, 14]} />
          <meshStandardMaterial color={palette.blush} transparent opacity={0.3} roughness={0.5} />
        </mesh>

        <group ref={leftEyeRef} position={[-0.26, 0.18, 0.73]}>
          <mesh scale={[1.08, 0.58, 0.22]}>
            <sphereGeometry args={[0.105, 36, 18]} />
            <meshStandardMaterial color="#fff7ed" roughness={0.18} metalness={0.02} />
          </mesh>
          <mesh position={[0, 0, 0.036]} scale={[0.78, 0.78, 0.22]}>
            <sphereGeometry args={[0.046, 32, 16]} />
            <meshStandardMaterial color={palette.eye} roughness={0.18} metalness={0.06} />
          </mesh>
          <mesh ref={leftPupilRef} position={[0, 0, 0.05]} scale={[0.72, 0.72, 0.18]}>
            <sphereGeometry args={[0.021, 24, 12]} />
            <meshStandardMaterial color="#020617" roughness={0.12} />
          </mesh>
        </group>

        <group ref={rightEyeRef} position={[0.26, 0.18, 0.73]}>
          <mesh scale={[1.08, 0.58, 0.22]}>
            <sphereGeometry args={[0.105, 36, 18]} />
            <meshStandardMaterial color="#fff7ed" roughness={0.18} metalness={0.02} />
          </mesh>
          <mesh position={[0, 0, 0.036]} scale={[0.78, 0.78, 0.22]}>
            <sphereGeometry args={[0.046, 32, 16]} />
            <meshStandardMaterial color={palette.eye} roughness={0.18} metalness={0.06} />
          </mesh>
          <mesh ref={rightPupilRef} position={[0, 0, 0.05]} scale={[0.72, 0.72, 0.18]}>
            <sphereGeometry args={[0.021, 24, 12]} />
            <meshStandardMaterial color="#020617" roughness={0.12} />
          </mesh>
        </group>

        <mesh ref={leftBrowRef} position={[-0.27, 0.45, 0.74]} rotation={[0, 0, 0.08]} scale={[1, 0.5, 0.4]}>
          <boxGeometry args={[0.24, 0.026, 0.018]} />
          <meshStandardMaterial color="#17111e" roughness={0.7} />
        </mesh>
        <mesh ref={rightBrowRef} position={[0.27, 0.45, 0.74]} rotation={[0, 0, -0.08]} scale={[1, 0.5, 0.4]}>
          <boxGeometry args={[0.24, 0.026, 0.018]} />
          <meshStandardMaterial color="#17111e" roughness={0.7} />
        </mesh>

        <mesh position={[0, -0.04, 0.78]} rotation={[0.08, 0, 0]} scale={[0.46, 0.68, 0.36]}>
          <coneGeometry args={[0.07, 0.18, 18]} />
          <meshStandardMaterial color={palette.skinWarm} roughness={0.52} />
        </mesh>

        <group ref={jawRef} position={[0, -0.3, 0.02]}>
          <mesh position={[0, -0.12, 0.16]} scale={[0.66, 0.46, 0.58]}>
            <sphereGeometry args={[0.68, 48, 26]} />
            <meshStandardMaterial color={palette.skin} roughness={0.48} metalness={0.04} />
          </mesh>
          <mesh ref={mouthRef} position={[0, -0.115, 0.74]} scale={[0.92, 0.26, 0.42]}>
            <sphereGeometry args={[0.14, 32, 16]} />
            <meshStandardMaterial color="#3f0f18" roughness={0.38} metalness={0.02} />
          </mesh>
          <mesh ref={upperLipRef} position={[0, -0.075, 0.79]} scale={[1.12, 0.13, 0.36]}>
            <sphereGeometry args={[0.112, 28, 14]} />
            <meshStandardMaterial color={palette.lip} roughness={0.34} metalness={0.02} />
          </mesh>
          <mesh ref={lowerLipRef} position={[0, -0.15, 0.79]} scale={[1, 0.18, 0.38]}>
            <sphereGeometry args={[0.112, 28, 14]} />
            <meshStandardMaterial color={palette.lip} roughness={0.32} metalness={0.03} />
          </mesh>
        </group>
      </group>
    </group>
  );
}
