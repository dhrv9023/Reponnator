/**
 * ModuleGrid.tsx — 3D-tilt module cards with glow trails and staggered entrance
 */
import { useState, useRef } from 'react';
import type { KeyModule } from './useStoryData';

interface ModuleGridProps {
  modules: KeyModule[];
  onNodeHighlight?: (moduleId: string) => void;
  visible: boolean;
}

const ROLE_COLORS: Record<string, { bg: string; border: string; glow: string; icon: string }> = {
  gateway:     { bg: 'rgba(99,102,241,0.08)',  border: 'rgba(99,102,241,0.3)',  glow: '#6366f1', icon: '🚪' },
  orchestrator:{ bg: 'rgba(139,92,246,0.08)', border: 'rgba(139,92,246,0.3)', glow: '#8b5cf6', icon: '🎭' },
  conductor:   { bg: 'rgba(139,92,246,0.08)', border: 'rgba(139,92,246,0.3)', glow: '#8b5cf6', icon: '🎭' },
  ledger:      { bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.3)',  glow: '#3b82f6', icon: '📚' },
  store:       { bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.3)',  glow: '#3b82f6', icon: '📚' },
  translator:  { bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.3)', glow: '#10b981', icon: '🔄' },
  adapter:     { bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.3)', glow: '#10b981', icon: '🔄' },
  signatory:   { bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.3)', glow: '#f59e0b', icon: '✍️' },
  encoder:     { bg: 'rgba(236,72,153,0.08)', border: 'rgba(236,72,153,0.3)', glow: '#ec4899', icon: '🔐' },
  validator:   { bg: 'rgba(34,197,94,0.08)',  border: 'rgba(34,197,94,0.3)',  glow: '#22c55e', icon: '✅' },
  builder:     { bg: 'rgba(251,146,60,0.08)', border: 'rgba(251,146,60,0.3)', glow: '#fb923c', icon: '🏗️' },
  router:      { bg: 'rgba(234,179,8,0.08)',  border: 'rgba(234,179,8,0.3)',  glow: '#eab308', icon: '🧭' },
  guardian:    { bg: 'rgba(99,102,241,0.08)', border: 'rgba(99,102,241,0.3)', glow: '#6366f1', icon: '🛡️' },
};

function getStyle(roleTitle: string) {
  const lower = (roleTitle || '').toLowerCase();
  for (const [key, val] of Object.entries(ROLE_COLORS)) {
    if (lower.includes(key)) return val;
  }
  return { bg: 'rgba(99,102,241,0.06)', border: 'rgba(99,102,241,0.2)', glow: '#6366f1', icon: '📦' };
}

function TiltCard({
  module,
  onNodeHighlight,
  index,
  visible,
}: {
  module: KeyModule;
  onNodeHighlight?: (id: string) => void;
  index: number;
  visible: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);
  const [glowPos, setGlowPos] = useState({ x: 50, y: 50 });

  const style = getStyle(module.role_title || '');

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setTilt({ x: (y - 0.5) * 12, y: (x - 0.5) * -12 });
    setGlowPos({ x: x * 100, y: y * 100 });
  };

  const onMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
    setHovered(false);
  };

  const filename = (module.module_id || '').replace(/_/g, '.').replace(/\//g, ' / ');

  return (
    <div
      ref={cardRef}
      onClick={() => onNodeHighlight?.(module.module_id || '')}
      onMouseMove={onMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={onMouseLeave}
      className="cursor-pointer select-none"
      style={{
        transform: visible
          ? `perspective(800px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg) translateY(0) scale(${hovered ? 1.02 : 1})`
          : 'perspective(800px) translateY(30px) scale(0.95)',
        opacity: visible ? 1 : 0,
        transition: hovered
          ? 'transform 0.1s ease-out, opacity 0.6s ease-out, box-shadow 0.3s ease'
          : 'transform 0.5s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.6s ease-out, box-shadow 0.5s ease',
        transitionDelay: `${index * 80}ms`,
        borderRadius: 16,
        background: style.bg,
        border: `1px solid ${hovered ? style.border.replace('0.3', '0.7') : style.border}`,
        boxShadow: hovered
          ? `0 20px 60px ${style.glow}33, 0 0 0 1px ${style.glow}22, inset 0 1px 0 rgba(255,255,255,0.08)`
          : `0 4px 20px rgba(0,0,0,0.12)`,
        padding: 28,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Radial glow that follows cursor */}
      {hovered && (
        <div
          className="absolute pointer-events-none"
          style={{
            inset: 0,
            borderRadius: 'inherit',
            background: `radial-gradient(circle 180px at ${glowPos.x}% ${glowPos.y}%, ${style.glow}18, transparent 70%)`,
          }}
        />
      )}

      {/* Icon + role */}
      <div className="flex items-start gap-4 mb-4">
        <div
          className="flex-shrink-0 flex items-center justify-center rounded-xl"
          style={{
            width: 52, height: 52,
            background: `linear-gradient(135deg, ${style.glow}22, ${style.glow}11)`,
            border: `1px solid ${style.glow}33`,
            fontSize: 24,
            transition: 'transform 0.3s ease',
            transform: hovered ? 'scale(1.1) rotate(-5deg)' : 'scale(1) rotate(0)',
            boxShadow: hovered ? `0 0 20px ${style.glow}44` : 'none',
          }}
        >
          {style.icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className="font-bold text-lg leading-snug mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            {module.role_title}
          </h3>
          <code
            className="text-xs px-2 py-1 rounded-md font-mono"
            style={{
              background: `${style.glow}15`,
              color: style.glow,
              border: `1px solid ${style.glow}30`,
            }}
          >
            {filename}
          </code>
        </div>
      </div>

      {/* Explanation */}
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--text-secondary)', lineHeight: 1.75 }}
      >
        {module.explanation}
      </p>

      {/* Hover CTA */}
      <div
        className="mt-4 flex items-center gap-2 text-xs font-semibold tracking-wide"
        style={{
          color: style.glow,
          opacity: hovered ? 1 : 0,
          transform: hovered ? 'translateX(0)' : 'translateX(-8px)',
          transition: 'all 0.3s ease',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
        View in diagram
      </div>
    </div>
  );
}

export function ModuleGrid({ modules, onNodeHighlight, visible }: ModuleGridProps) {
  return (
    <div
      className="grid gap-5"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}
    >
      {modules.map((module, i) => (
        <TiltCard
          key={module.module_id}
          module={module}
          onNodeHighlight={onNodeHighlight}
          index={i}
          visible={visible}
        />
      ))}
    </div>
  );
}
