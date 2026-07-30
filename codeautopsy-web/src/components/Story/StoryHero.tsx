/**
 * StoryHero.tsx — Immersive parallax hero
 *
 * Shows:
 *  1. "What is this project?" card  — plain-English project_summary
 *  2. Tech stack icon row           — real devicon SVGs for detected libs
 *  3. "The Founding Decision"       — typewriter primary_commitment
 */
import { useEffect, useState, useRef } from 'react';
import type { StoryMetadata } from './useStoryData';

interface StoryHeroProps {
  meta: StoryMetadata;
  commitment: string;
  projectSummary?: string;
  techStack?: string[];
}

// ── Devicon name map ──────────────────────────────────────────────────────────
// Maps display name → devicon slug (used in CDN URL)
const DEVICON_MAP: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  react: 'react',
  fastapi: 'fastapi',
  flask: 'flask',
  django: 'django',
  pytorch: 'pytorch',
  tensorflow: 'tensorflow',
  numpy: 'numpy',
  pandas: 'pandas',
  scikit: 'scikitlearn',
  'scikit-learn': 'scikitlearn',
  sklearn: 'scikitlearn',
  nodejs: 'nodejs',
  node: 'nodejs',
  express: 'express',
  nextjs: 'nextjs',
  vuejs: 'vuejs',
  vue: 'vuejs',
  angular: 'angularjs',
  go: 'go',
  rust: 'rust',
  java: 'java',
  spring: 'spring',
  kotlin: 'kotlin',
  swift: 'swift',
  ruby: 'ruby',
  rails: 'rails',
  php: 'php',
  laravel: 'laravel',
  docker: 'docker',
  kubernetes: 'kubernetes',
  redis: 'redis',
  postgresql: 'postgresql',
  postgres: 'postgresql',
  mysql: 'mysql',
  mongodb: 'mongodb',
  graphql: 'graphql',
  tailwind: 'tailwindcss',
  tailwindcss: 'tailwindcss',
  sass: 'sass',
  webpack: 'webpack',
  vite: 'vite',
  jest: 'jest',
  celery: 'celery',
  sqlalchemy: 'sqlalchemy',
  opencv: 'opencv',
  librosa: 'python',    // no devicon → use Python icon
  onnx: 'python',
  streamlit: 'streamlit',
  gradio: 'python',
  transformers: 'python',
  langchain: 'python',
  openai: 'python',
  uvicorn: 'fastapi',
  pydantic: 'python',
  aiohttp: 'python',
  httpx: 'python',
};

// Color accent per tech (for the pill border glow)
const TECH_COLORS: Record<string, string> = {
  python: '#3776ab',
  javascript: '#f7df1e',
  typescript: '#3178c6',
  react: '#61dafb',
  fastapi: '#009688',
  flask: '#ffffff',
  django: '#092e20',
  pytorch: '#ee4c2c',
  tensorflow: '#ff6f00',
  numpy: '#4dabcf',
  pandas: '#150458',
  sklearn: '#f89939',
  nodejs: '#339933',
  express: '#ffffff',
  nextjs: '#ffffff',
  vuejs: '#4fc08d',
  go: '#00add8',
  rust: '#dea584',
  java: '#ed8b00',
  docker: '#2496ed',
  redis: '#dc382d',
  postgresql: '#4169e1',
  mysql: '#4479a1',
  mongodb: '#47a248',
  graphql: '#e10098',
  tailwindcss: '#06b6d4',
  streamlit: '#ff4b4b',
  opencv: '#5c3ee8',
  librosa: '#3776ab',
  onnx: '#71a8d9',
  default: '#6366f1',
};

function getDeviconUrl(name: string): string {
  const key = name.toLowerCase().replace(/[^a-z0-9-]/g, '');
  const slug = DEVICON_MAP[key] ?? DEVICON_MAP[name.toLowerCase()] ?? null;
  if (!slug) return '';
  return `https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/${slug}/${slug}-original.svg`;
}

function getTechColor(name: string): string {
  const key = name.toLowerCase().replace(/[^a-z]/g, '');
  return TECH_COLORS[key] ?? TECH_COLORS.default;
}

// ── Tech Stack Icon ───────────────────────────────────────────────────────────
function TechBadge({ name, index }: { name: string; index: number }) {
  const [imgOk, setImgOk] = useState(true);
  const url = getDeviconUrl(name);
  const color = getTechColor(name);

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold"
      style={{
        background: `${color}14`,
        border: `1px solid ${color}44`,
        color: 'var(--text-primary)',
        backdropFilter: 'blur(8px)',
        animation: `techBadgeIn 0.4s ease both`,
        animationDelay: `${index * 60}ms`,
        boxShadow: `0 2px 12px ${color}22`,
      }}
    >
      {url && imgOk ? (
        <img
          src={url}
          alt={name}
          width={18}
          height={18}
          style={{ flexShrink: 0 }}
          onError={() => setImgOk(false)}
        />
      ) : (
        <span
          className="w-4 h-4 rounded-sm flex items-center justify-center text-xs font-bold"
          style={{ background: color, color: '#fff', fontSize: '0.6rem', flexShrink: 0 }}
        >
          {name[0].toUpperCase()}
        </span>
      )}
      <span style={{ color: 'var(--text-primary)' }}>{name}</span>
    </div>
  );
}

// ── Typewriter hook ───────────────────────────────────────────────────────────
function useTypewriter(text: string, speed = 35, delay = 900) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  useEffect(() => {
    setDisplayed('');
    setDone(false);
    let i = 0;
    const start = setTimeout(() => {
      const iv = setInterval(() => {
        i++;
        setDisplayed(text.slice(0, i));
        if (i >= text.length) { clearInterval(iv); setDone(true); }
      }, speed);
      return () => clearInterval(iv);
    }, delay);
    return () => clearTimeout(start);
  }, [text, speed, delay]);
  return { displayed, done };
}

// ── Main component ────────────────────────────────────────────────────────────
export function StoryHero({ meta, commitment, projectSummary, techStack = [] }: StoryHeroProps) {
  const { displayed, done } = useTypewriter(commitment, 35, 600);
  const heroRef = useRef<HTMLDivElement>(null);
  const [scrollY, setScrollY] = useState(0);
  const [entered, setEntered] = useState(false);
  const [summaryVisible, setSummaryVisible] = useState(false);

  useEffect(() => { const t = setTimeout(() => setEntered(true), 100); return () => clearTimeout(t); }, []);
  useEffect(() => { const t = setTimeout(() => setSummaryVisible(true), 450); return () => clearTimeout(t); }, []);
  useEffect(() => {
    const fn = () => setScrollY(window.scrollY);
    window.addEventListener('scroll', fn, { passive: true });
    return () => window.removeEventListener('scroll', fn);
  }, []);

  const repoLabel = `${meta.repo_owner} / ${meta.repo_name}`;

  return (
    <div
      ref={heroRef}
      className="relative flex flex-col items-center justify-center overflow-hidden"
      style={{ minHeight: '96vh', zIndex: 10 }}
    >
      {/* Parallax gradient */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.08) 40%, transparent 70%)',
          transform: `translateY(${scrollY * 0.3}px)`,
        }}
      />

      {/* Decorative rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {[1, 2, 3].map((n) => (
          <div key={n} className="absolute rounded-full" style={{
            width: n * 280, height: n * 280,
            border: `1px solid rgba(99,102,241,${0.12 - n * 0.03})`,
            animation: `heroRingPulse ${3 + n}s ease-in-out infinite`,
            animationDelay: `${n * 0.4}s`,
          }} />
        ))}
      </div>

      {/* Content */}
      <div
        className="relative z-10 text-center max-w-4xl mx-auto px-6 w-full"
        style={{
          transform: entered ? 'translateY(0)' : 'translateY(40px)',
          opacity: entered ? 1 : 0,
          transition: 'all 1.2s cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      >
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-8 text-sm font-semibold tracking-widest uppercase" style={{
          background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
          color: '#6366f1', backdropFilter: 'blur(8px)',
        }}>
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex rounded-full h-full w-full opacity-75" style={{ background: '#6366f1', animation: 'ping 1.5s cubic-bezier(0,0,0.2,1) infinite' }} />
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: '#6366f1' }} />
          </span>
          Architectural Story
        </div>

        {/* Repo name */}
        <div className="font-mono text-sm mb-7 tracking-wide" style={{ color: 'var(--text-secondary)' }}>
          {repoLabel}
        </div>

        {/* ── "What is this project?" card ── */}
        {projectSummary && (
          <div
            className="mb-8 mx-auto rounded-2xl overflow-hidden text-left"
            style={{
              maxWidth: '680px',
              opacity: summaryVisible ? 1 : 0,
              transform: summaryVisible ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.98)',
              transition: 'opacity 0.7s ease, transform 0.7s cubic-bezier(0.22,1,0.36,1)',
              background: 'var(--bg-glass)',
              border: '1px solid rgba(99,102,241,0.25)',
              backdropFilter: 'blur(16px)',
              boxShadow: '0 8px 32px rgba(99,102,241,0.12), inset 0 1px 0 rgba(255,255,255,0.06)',
            }}
          >
            {/* Card header */}
            <div className="flex items-center gap-2.5 px-5 py-3" style={{
              borderBottom: '1px solid rgba(99,102,241,0.15)',
              background: 'rgba(99,102,241,0.08)',
            }}>
              <span style={{ fontSize: '1rem' }}>📋</span>
              <span className="text-xs font-bold tracking-[0.18em] uppercase" style={{ color: '#818cf8' }}>
                What is this project?
              </span>
            </div>

            {/* Summary text */}
            <div className="px-5 pt-4 pb-3">
              <p className="text-base leading-relaxed" style={{ color: 'var(--text-primary)', lineHeight: '1.78' }}>
                {projectSummary}
              </p>
            </div>

            {/* ── Tech Stack icons ── */}
            {techStack.length > 0 && (
              <div className="px-5 pb-4">
                <div className="text-xs font-semibold tracking-[0.15em] uppercase mb-2.5" style={{ color: 'rgba(139,92,246,0.6)' }}>
                  Tech Stack
                </div>
                <div className="flex flex-wrap gap-2">
                  {techStack.map((tech, i) => (
                    <TechBadge key={tech} name={tech} index={i} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Founding Decision label */}
        <div className="text-xs font-semibold tracking-[0.25em] uppercase mb-6" style={{ color: 'rgba(139,92,246,0.7)' }}>
          The Founding Decision
        </div>

        {/* Typewriter commitment */}
        <h1 className="font-bold leading-tight mb-10" style={{
          fontSize: 'clamp(1.7rem, 3.8vw, 3rem)',
          color: 'var(--text-primary)',
          minHeight: '3.6em',
        }}>
          {displayed}
          {!done && (
            <span className="inline-block w-0.5 ml-1 align-middle" style={{
              height: '0.85em', background: '#6366f1',
              animation: 'cursorBlink 0.9s step-end infinite',
              borderRadius: 2, boxShadow: '0 0 8px #6366f1',
            }} />
          )}
        </h1>

        {/* Meta chips */}
        <div className="flex flex-wrap justify-center gap-3 mb-12">
          {[
            { icon: '🤖', label: meta.model_used.split('/').pop() || meta.model_used },
            { icon: '📅', label: new Date(meta.generation_timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) },
            { icon: '⚡', label: `${meta.generation_duration_seconds.toFixed(1)}s generation` },
          ].map((chip) => (
            <div key={chip.label} className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium" style={{
              background: 'var(--bg-glass)', border: '1px solid var(--border-color)',
              color: 'var(--text-secondary)', backdropFilter: 'blur(12px)',
            }}>
              <span>{chip.icon}</span>
              <span>{chip.label}</span>
            </div>
          ))}
        </div>

        {/* Scroll cue */}
        <div className="flex flex-col items-center gap-2" style={{ color: 'var(--text-secondary)', opacity: 0.6 }}>
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
        @keyframes techBadgeIn {
          from { opacity: 0; transform: translateY(8px) scale(0.9); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
