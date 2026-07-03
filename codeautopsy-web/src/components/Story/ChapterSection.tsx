/**
 * ChapterSection.tsx — Immersive animated chapter wrapper with glowing number + icon
 */
import { ReactNode } from 'react';

interface ChapterSectionProps {
  label: string;
  icon: string;
  color: string;
  visible: boolean;
  children: ReactNode;
}

export function ChapterSection({ label, icon, color, visible, children }: ChapterSectionProps) {
  return (
    <div className="relative py-20">
      {/* Vertical connector line (above) */}
      <div
        className="absolute left-8 top-0 w-px"
        style={{
          height: 80,
          background: `linear-gradient(to bottom, transparent, ${color}44)`,
        }}
      />

      <div className="flex gap-8 items-start">
        {/* Chapter icon circle */}
        <div className="flex-shrink-0 relative" style={{ marginTop: 4 }}>
          {/* Glow ring */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `radial-gradient(circle, ${color}33 0%, transparent 70%)`,
              transform: 'scale(2)',
              transition: 'all 0.8s ease-out',
              opacity: visible ? 1 : 0,
            }}
          />
          <div
            className="relative flex items-center justify-center rounded-full"
            style={{
              width: 64,
              height: 64,
              background: `linear-gradient(135deg, ${color}22, ${color}11)`,
              border: `2px solid ${color}55`,
              boxShadow: visible ? `0 0 24px ${color}44, inset 0 0 20px ${color}11` : 'none',
              transition: 'box-shadow 1s ease-out 0.3s',
            }}
          >
            <span style={{ fontSize: 26 }}>{icon}</span>
          </div>
        </div>

        {/* Chapter content */}
        <div className="flex-1 min-w-0">
          {/* Label */}
          <div
            className="flex items-center gap-3 mb-6"
            style={{
              transform: visible ? 'translateX(0)' : 'translateX(-20px)',
              opacity: visible ? 1 : 0,
              transition: 'all 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.2s',
            }}
          >
            <div
              className="h-px flex-1 max-w-12"
              style={{ background: `linear-gradient(to right, ${color}, transparent)` }}
            />
            <span
              className="text-xs font-bold tracking-[0.2em] uppercase"
              style={{ color }}
            >
              {label}
            </span>
          </div>

          {/* Content block */}
          <div
            className="relative pl-6"
            style={{
              borderLeft: `2px solid ${color}33`,
              transform: visible ? 'translateY(0)' : 'translateY(20px)',
              opacity: visible ? 1 : 0,
              transition: 'all 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.4s',
            }}
          >
            {/* Accent dot on border */}
            <div
              className="absolute left-0 rounded-full"
              style={{
                width: 8,
                height: 8,
                top: 4,
                transform: 'translateX(-50%)',
                background: color,
                boxShadow: `0 0 12px ${color}88`,
              }}
            />
            {children}
          </div>
        </div>
      </div>

      {/* Vertical connector line (below) */}
      <div
        className="absolute left-8 bottom-0 w-px"
        style={{
          height: 80,
          background: `linear-gradient(to bottom, ${color}44, transparent)`,
        }}
      />
    </div>
  );
}
