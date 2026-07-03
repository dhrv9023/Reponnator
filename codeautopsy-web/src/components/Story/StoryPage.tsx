/**
 * StoryPage.tsx — Cinematic Architectural Story Experience
 *
 * Features:
 * - Animated cinematic loading screen
 * - Parallax hero with animated gradient
 * - Typewriter reveal for primary commitment
 * - Scroll-driven chapter entrances with staggered animations
 * - 3D-tilt module cards with glow effects
 * - Floating ambient particle field
 * - Animated chapter timeline
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import { useStoryData } from './useStoryData';
import { CinematicLoader } from './CinematicLoader';
import { StoryHero } from './StoryHero';
import { ChapterSection } from './ChapterSection';
import { ModuleGrid } from './ModuleGrid';
import { MetaphoreQuote } from './MetaphoreQuote';
import { StoryFooter } from './StoryFooter';
import { ParticleField } from './ParticleField';

interface StoryPageProps {
  repoKey?: string;
  onNodeHighlight?: (moduleId: string) => void;
}

export function StoryPage({ repoKey, onNodeHighlight }: StoryPageProps) {
  const { story, meta, isLoading, error } = useStoryData(repoKey);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [loadingPhase, setLoadingPhase] = useState<'loading' | 'reveal' | 'done'>('loading');
  const [visibleChapters, setVisibleChapters] = useState<Set<number>>(new Set());
  const contentRef = useRef<HTMLDivElement>(null);

  // Cinematic loading: wait for data then play reveal
  useEffect(() => {
    if (!isLoading && (story || error)) {
      const t = setTimeout(() => {
        setLoadingPhase('reveal');
        setTimeout(() => setLoadingPhase('done'), 1200);
      }, 600);
      return () => clearTimeout(t);
    }
  }, [isLoading, story, error]);

  // Scroll progress
  useEffect(() => {
    const handleScroll = () => {
      const winH = window.innerHeight;
      const docH = document.documentElement.scrollHeight;
      const top = window.scrollY;
      setScrollProgress(Math.min(100, Math.max(0, (top / (docH - winH)) * 100)));
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // IntersectionObserver for chapter reveals
  const chapterRefs = useRef<(HTMLDivElement | null)[]>([]);
  const setChapterRef = useCallback((i: number) => (el: HTMLDivElement | null) => {
    chapterRefs.current[i] = el;
  }, []);

  useEffect(() => {
    if (loadingPhase !== 'done') return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const idx = Number(entry.target.getAttribute('data-chapter'));
            setVisibleChapters((prev) => new Set([...prev, idx]));
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -80px 0px' }
    );
    chapterRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [loadingPhase, story]);

  // ── Loading Screen ──
  if (loadingPhase === 'loading' || (loadingPhase === 'reveal' && isLoading)) {
    return <CinematicLoader phase={isLoading ? 'loading' : 'reveal'} />;
  }

  // ── Error State ──
  if (error || !story || !meta) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-primary)' }}>
        <div className="text-center max-w-md px-6">
          <div className="text-7xl mb-6 animate-bounce">📖</div>
          <h2 className="text-3xl font-bold mb-3" style={{ color: 'var(--text-primary)' }}>
            Story Not Found
          </h2>
          <p className="mb-8 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {error || 'No architectural story available for this repository.'}
          </p>
          <button
            onClick={() => window.history.back()}
            className="px-8 py-3 rounded-xl font-semibold text-white transition-all duration-300 hover:scale-105 active:scale-95"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const chapters = [
    { id: 0, label: 'Origin Story',       content: story.origin_story,     color: '#6366f1', icon: '🌱' },
    { id: 1, label: 'How It Flows',        content: story.how_it_flows,      color: '#8b5cf6', icon: '🌊' },
    { id: 2, label: 'Key Modules',         content: null,                   color: '#3b82f6', icon: '🧩' },
    { id: 3, label: 'Design Tensions',     content: story.design_tensions,   color: '#f59e0b', icon: '⚖️' },
    { id: 4, label: 'Founding Metaphor',   content: null,                   color: '#10b981', icon: '🔮' },
    { id: 5, label: 'Verdict',             content: story.verdict,           color: '#ec4899', icon: '🏁' },
  ];

  return (
    <div
      className="relative min-h-screen overflow-x-hidden"
      style={{ background: 'var(--bg-primary)' }}
    >
      {/* ── Scroll Progress Bar ── */}
      <div
        className="fixed top-0 left-0 h-0.5 z-50 transition-all duration-150"
        style={{
          width: `${scrollProgress}%`,
          background: 'linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899)',
          boxShadow: '0 0 12px rgba(139, 92, 246, 0.8)',
        }}
      />

      {/* ── Ambient Particle Field ── */}
      <ParticleField />

      {/* ── Hero Section ── */}
      <StoryHero meta={meta} commitment={story.primary_commitment} />

      {/* ── Chapter Timeline + Content ── */}
      <div ref={contentRef} className="relative z-10 max-w-5xl mx-auto px-6 pb-32">

        {/* Chapter Nav Dots (sticky sidebar) */}
        <div className="fixed right-6 top-1/2 -translate-y-1/2 z-40 hidden xl:flex flex-col gap-3">
          {chapters.map((ch) => (
            <button
              key={ch.id}
              onClick={() => chapterRefs.current[ch.id]?.scrollIntoView({ behavior: 'smooth' })}
              title={ch.label}
              className="group relative flex items-center justify-end gap-2"
            >
              <span
                className="hidden group-hover:block text-xs font-medium px-2 py-1 rounded-md whitespace-nowrap"
                style={{
                  background: 'var(--bg-glass)',
                  color: 'var(--text-primary)',
                  backdropFilter: 'blur(8px)',
                  border: '1px solid var(--border-color)',
                }}
              >
                {ch.label}
              </span>
              <div
                className="w-2.5 h-2.5 rounded-full transition-all duration-300"
                style={{
                  background: visibleChapters.has(ch.id) ? ch.color : 'var(--border-color)',
                  boxShadow: visibleChapters.has(ch.id) ? `0 0 10px ${ch.color}88` : 'none',
                  transform: visibleChapters.has(ch.id) ? 'scale(1.3)' : 'scale(1)',
                }}
              />
            </button>
          ))}
        </div>

        {/* ── Chapters ── */}
        <div className="space-y-0">
          {chapters.map((ch, idx) => (
            <div
              key={ch.id}
              ref={setChapterRef(ch.id)}
              data-chapter={ch.id}
              className="transition-all duration-1000 ease-out"
              style={{
                opacity: visibleChapters.has(ch.id) ? 1 : 0,
                transform: visibleChapters.has(ch.id) ? 'translateY(0)' : 'translateY(60px)',
                transitionDelay: `${idx * 80}ms`,
              }}
            >
              {ch.id === 2 ? (
                /* Key Modules */
                <ChapterSection label={ch.label} icon={ch.icon} color={ch.color} visible={visibleChapters.has(ch.id)}>
                  <ModuleGrid
                    modules={story.key_modules}
                    onNodeHighlight={onNodeHighlight}
                    visible={visibleChapters.has(ch.id)}
                  />
                </ChapterSection>
              ) : ch.id === 4 ? (
                /* Founding Metaphor */
                <ChapterSection label={ch.label} icon={ch.icon} color={ch.color} visible={visibleChapters.has(ch.id)}>
                  <MetaphoreQuote text={story.founding_metaphor} color={ch.color} />
                </ChapterSection>
              ) : (
                /* Regular text chapter */
                <ChapterSection label={ch.label} icon={ch.icon} color={ch.color} visible={visibleChapters.has(ch.id)}>
                  <p
                    className="text-lg leading-relaxed"
                    style={{ color: 'var(--text-secondary)', fontSize: '1.125rem', lineHeight: '1.85' }}
                  >
                    {ch.content}
                  </p>
                </ChapterSection>
              )}
            </div>
          ))}
        </div>

        {/* ── Footer ── */}
        <div
          className="mt-24 transition-all duration-1000 ease-out"
          style={{ opacity: visibleChapters.size > 3 ? 1 : 0, transform: visibleChapters.size > 3 ? 'translateY(0)' : 'translateY(40px)' }}
        >
          <StoryFooter meta={meta} />
        </div>
      </div>

      {/* Print Styles */}
      <style>{`
        @media print {
          .fixed, .particle-field { display: none !important; }
          body { background: white !important; }
          * { color: black !important; background: white !important; }
        }
      `}</style>
    </div>
  );
}
