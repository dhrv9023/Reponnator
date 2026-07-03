/**
 * CinematicLoader.tsx — Stunning loading screen for the story page
 */
import { useEffect, useState } from 'react';

interface CinematicLoaderProps {
  phase: 'loading' | 'reveal';
}

const MESSAGES = [
  'Parsing architectural DNA...',
  'Mapping module relationships...',
  'Synthesizing narrative threads...',
  'Weaving the origin story...',
  'Uncovering design tensions...',
  'Crafting the verdict...',
  'Story ready.',
];

export function CinematicLoader({ phase }: CinematicLoaderProps) {
  const [msgIndex, setMsgIndex] = useState(0);
  const [opacity, setOpacity] = useState(1);
  const [dots, setDots] = useState('');

  // Cycle through loading messages
  useEffect(() => {
    if (phase === 'reveal') return;
    const interval = setInterval(() => {
      setMsgIndex((i) => Math.min(i + 1, MESSAGES.length - 1));
    }, 900);
    return () => clearInterval(interval);
  }, [phase]);

  // Animate dots
  useEffect(() => {
    const interval = setInterval(() => {
      setDots((d) => (d.length >= 3 ? '' : d + '.'));
    }, 400);
    return () => clearInterval(interval);
  }, []);

  // Fade out on reveal
  useEffect(() => {
    if (phase === 'reveal') {
      setOpacity(0);
    }
  }, [phase]);

  return (
    <div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center"
      style={{
        background: 'var(--bg-primary)',
        opacity,
        transition: 'opacity 1.2s cubic-bezier(0.4, 0, 0.2, 1)',
        pointerEvents: phase === 'reveal' ? 'none' : 'all',
      }}
    >
      {/* Ambient gradient blobs */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ filter: 'blur(100px)', opacity: 0.4 }}
      >
        <div
          className="absolute rounded-full"
          style={{
            width: 500, height: 500,
            top: '5%', left: '-10%',
            background: 'radial-gradient(circle, #6366f1 0%, transparent 70%)',
            animation: 'loaderBlob1 8s ease-in-out infinite',
          }}
        />
        <div
          className="absolute rounded-full"
          style={{
            width: 400, height: 400,
            bottom: '5%', right: '-10%',
            background: 'radial-gradient(circle, #ec4899 0%, transparent 70%)',
            animation: 'loaderBlob2 10s ease-in-out infinite',
          }}
        />
        <div
          className="absolute rounded-full"
          style={{
            width: 300, height: 300,
            top: '40%', left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'radial-gradient(circle, #8b5cf6 0%, transparent 70%)',
            animation: 'loaderBlob3 6s ease-in-out infinite',
          }}
        />
      </div>

      {/* Central loader ring */}
      <div className="relative flex items-center justify-center mb-12" style={{ width: 140, height: 140 }}>
        {/* Outer spinning ring */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            border: '2px solid transparent',
            borderTopColor: '#6366f1',
            borderRightColor: '#8b5cf6',
            animation: 'loaderSpin 1.2s linear infinite',
            boxShadow: '0 0 30px rgba(99, 102, 241, 0.4)',
          }}
        />
        {/* Middle ring (reverse) */}
        <div
          className="absolute rounded-full"
          style={{
            inset: 16,
            border: '2px solid transparent',
            borderBottomColor: '#ec4899',
            borderLeftColor: '#f59e0b',
            animation: 'loaderSpin 2s linear infinite reverse',
          }}
        />
        {/* Inner pulsing core */}
        <div
          className="relative flex items-center justify-center rounded-full"
          style={{
            width: 72, height: 72,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            boxShadow: '0 0 40px rgba(139, 92, 246, 0.6)',
            animation: 'loaderPulse 2s ease-in-out infinite',
          }}
        >
          <span style={{ fontSize: 28 }}>📖</span>
        </div>
      </div>

      {/* Title */}
      <h1
        className="text-2xl font-bold mb-3 tracking-wide"
        style={{
          background: 'linear-gradient(135deg, #6366f1, #ec4899)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}
      >
        CodeAutopsy
      </h1>

      {/* Status message */}
      <div className="h-7 flex items-center justify-center">
        <p
          className="text-base font-medium transition-all duration-700"
          style={{
            color: 'var(--text-secondary)',
            minWidth: 280,
            textAlign: 'center',
          }}
        >
          {MESSAGES[msgIndex]}{phase === 'loading' && msgIndex < MESSAGES.length - 1 ? dots : ''}
        </p>
      </div>

      {/* Progress bar */}
      <div
        className="mt-8 rounded-full overflow-hidden"
        style={{ width: 240, height: 3, background: 'var(--border-color)' }}
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${((msgIndex + 1) / MESSAGES.length) * 100}%`,
            background: 'linear-gradient(90deg, #6366f1, #ec4899)',
            transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
            boxShadow: '0 0 12px rgba(99, 102, 241, 0.6)',
          }}
        />
      </div>

      {/* Keyframes injected inline */}
      <style>{`
        @keyframes loaderSpin {
          to { transform: rotate(360deg); }
        }
        @keyframes loaderPulse {
          0%, 100% { transform: scale(1); box-shadow: 0 0 40px rgba(139,92,246,0.5); }
          50% { transform: scale(1.08); box-shadow: 0 0 60px rgba(139,92,246,0.8); }
        }
        @keyframes loaderBlob1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(60px, 40px) scale(1.1); }
          66% { transform: translate(-30px, 80px) scale(0.9); }
        }
        @keyframes loaderBlob2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(-80px, -50px) scale(1.15); }
          66% { transform: translate(40px, -30px) scale(0.85); }
        }
        @keyframes loaderBlob3 {
          0%, 100% { transform: translate(-50%, -50%) scale(1); }
          50% { transform: translate(-50%, -50%) scale(1.2); }
        }
      `}</style>
    </div>
  );
}
