/**
 * StoryHero.tsx — Immersive parallax hero with typewriter primary commitment
 */
import { useEffect, useState, useRef } from 'react';
import type { StoryMetadata } from './useStoryData';

interface StoryHeroProps {
  meta: StoryMetadata;
  commitment: string;
}

function useTypewriter(text: string, speed = 38, delay = 800) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed('');
    setDone(false);
    let i = 0;
    const start = setTimeout(() => {
      const interval = setInterval(() => {
        i++;
        setDisplayed(text.slice(0, i));
        if (i >= text.length) {
          clearInterval(interval);
          setDone(true);
        }
      }, speed);
      return () => clearInterval(interval);
    }, delay);
    return () => clearTimeout(start);
  }, [text, speed, delay]);

  return { displayed, done };
}

export function StoryHero({ meta, commitment }: StoryHeroProps) {
  const { displayed, done } = useTypewriter(commitment, 35, 600);
  const heroRef = useRef<HTMLDivElement>(null);
  const [scrollY, setScrollY] = useState(0);
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setEntered(true), 100);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const repoLabel = `${meta.repo_owner} / ${meta.repo_name}`;

  return (
    <div
      ref={heroRef}
      className="relative flex flex-col items-center justify-center overflow-hidden"
      style={{ minHeight: '92vh', zIndex: 10 }}
    >
      {/* Parallax gradient background */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.08) 40%, transparent 70%)',
          transform: `translateY(${scrollY * 0.3}px)`,
          transition: 'transform 0.05s linear',
        }}
      />

      {/* Decorative rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {[1, 2, 3].map((n) => (
          <div
            key={n}
            className="absolute rounded-full"
            style={{
              width: n * 260,
              height: n * 260,
              border: `1px solid rgba(99,102,241,${0.12 - n * 0.03})`,
              animation: `heroRingPulse ${3 + n}s ease-in-out infinite`,
              animationDelay: `${n * 0.4}s`,
            }}
          />
        ))}
      </div>

      {/* Content */}
      <div
        className="relative z-10 text-center max-w-4xl mx-auto px-6"
        style={{
          transform: entered ? 'translateY(0)' : 'translateY(40px)',
          opacity: entered ? 1 : 0,
          transition: 'all 1.2s cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      >
        {/* Tag */}
        <div
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-8 text-sm font-semibold tracking-widest uppercase"
          style={{
            background: 'rgba(99,102,241,0.12)',
            border: '1px solid rgba(99,102,241,0.3)',
            color: '#6366f1',
            backdropFilter: 'blur(8px)',
            animationDelay: '200ms',
          }}
        >
          <span className="relative flex h-2 w-2">
            <span
              className="absolute inline-flex rounded-full h-full w-full opacity-75"
              style={{ background: '#6366f1', animation: 'ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite' }}
            />
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: '#6366f1' }} />
          </span>
          Architectural Story
        </div>

        {/* Repo name */}
        <div
          className="font-mono text-sm mb-4 tracking-wide"
          style={{ color: 'var(--text-secondary)' }}
        >
          {repoLabel}
        </div>

        {/* Founding Decision label */}
        <div
          className="text-xs font-semibold tracking-[0.25em] uppercase mb-6"
          style={{ color: 'rgba(139,92,246,0.7)' }}
        >
          The Founding Decision
        </div>

        {/* Typewriter commitment */}
        <h1
          className="font-bold leading-tight mb-10"
          style={{
            fontSize: 'clamp(1.8rem, 4vw, 3.2rem)',
            color: 'var(--text-primary)',
            minHeight: '3.6em',
          }}
        >
          {displayed}
          {!done && (
            <span
              className="inline-block w-0.5 ml-1 align-middle"
              style={{
                height: '0.85em',
                background: '#6366f1',
                animation: 'cursorBlink 0.9s step-end infinite',
                borderRadius: 2,
                boxShadow: '0 0 8px #6366f1',
              }}
            />
          )}
        </h1>

        {/* Meta chips */}
        <div className="flex flex-wrap justify-center gap-3 mb-12">
          {[
            { icon: '🤖', label: meta.model_used.split('/').pop() || meta.model_used },
            { icon: '📅', label: new Date(meta.generation_timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) },
            { icon: '⚡', label: `${meta.generation_duration_seconds.toFixed(1)}s generation` },
          ].map((chip) => (
            <div
              key={chip.label}
              className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium"
              style={{
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-secondary)',
                backdropFilter: 'blur(12px)',
              }}
            >
              <span>{chip.icon}</span>
              <span>{chip.label}</span>
            </div>
          ))}
        </div>

        {/* Scroll cue */}
        <div
          className="flex flex-col items-center gap-2"
          style={{ color: 'var(--text-secondary)', opacity: 0.6 }}
        >
          <span className="text-xs tracking-widest uppercase">Scroll to explore</span>
          <div style={{ animation: 'heroScrollBounce 1.8s ease-in-out infinite' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
            </svg>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes heroRingPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.04); opacity: 0.6; }
        }
        @keyframes heroScrollBounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(6px); }
        }
        @keyframes cursorBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @keyframes ping {
          75%, 100% { transform: scale(2); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
