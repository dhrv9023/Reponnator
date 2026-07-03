/**
 * MetaphoreQuote.tsx — Cinematic blockquote with animated reveal
 */
import { useEffect, useState } from 'react';

interface MetaphoreQuoteProps {
  text: string;
  color: string;
}

export function MetaphoreQuote({ text, color }: MetaphoreQuoteProps) {
  const [lineWidth, setLineWidth] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setLineWidth(100), 300);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="relative py-6">
      {/* Decorative quote mark */}
      <div
        className="absolute -top-4 -left-2 font-serif"
        style={{
          fontSize: 120,
          lineHeight: 1,
          color,
          opacity: 0.08,
          fontFamily: 'Georgia, serif',
          userSelect: 'none',
        }}
      >
        "
      </div>

      {/* Animated top line */}
      <div
        className="mb-6 rounded-full"
        style={{
          height: 2,
          width: `${lineWidth}%`,
          background: `linear-gradient(to right, ${color}, ${color}44, transparent)`,
          transition: 'width 1.5s cubic-bezier(0.22, 1, 0.36, 1)',
          boxShadow: `0 0 12px ${color}66`,
        }}
      />

      {/* Quote text */}
      <blockquote
        className="relative font-serif italic leading-relaxed"
        style={{
          fontSize: 'clamp(1.3rem, 2.5vw, 1.9rem)',
          color: 'var(--text-primary)',
          fontFamily: 'Georgia, "Times New Roman", serif',
          textIndent: '1rem',
        }}
      >
        <span style={{ color, opacity: 0.6, fontStyle: 'normal', marginRight: 4 }}>"</span>
        {text}
        <span style={{ color, opacity: 0.6, fontStyle: 'normal', marginLeft: 4 }}>"</span>
      </blockquote>

      {/* Animated bottom line */}
      <div
        className="mt-6 ml-auto rounded-full"
        style={{
          height: 2,
          width: `${lineWidth}%`,
          background: `linear-gradient(to left, ${color}, ${color}44, transparent)`,
          transition: 'width 1.5s cubic-bezier(0.22, 1, 0.36, 1) 0.3s',
          boxShadow: `0 0 12px ${color}66`,
        }}
      />

      {/* Glowing backdrop */}
      <div
        className="absolute inset-0 pointer-events-none rounded-2xl"
        style={{
          background: `radial-gradient(ellipse 60% 80% at 50% 50%, ${color}08, transparent)`,
        }}
      />
    </div>
  );
}
