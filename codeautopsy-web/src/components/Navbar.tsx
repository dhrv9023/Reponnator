import { useState } from 'react';
import ThemeToggle from './ThemeToggle';

const NAV_LINKS = ['Diagram', 'Story', 'Q&A', 'Stack'] as const;

interface NavbarProps {
  currentView: string;
  setView: (view: 'hero' | 'ingestion' | 'workspace' | 'story') => void;
  isDark: boolean;
  toggleTheme: () => void;
}

export default function Navbar({
  currentView,
  setView,
  isDark,
  toggleTheme,
}: NavbarProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  const toggleMenu = () => setMenuOpen((v) => !v);

  // Dynamic layout colors depending on view mode and active theme state
  const isNavColored = currentView === 'workspace';
  const textColor = isNavColored ? 'var(--text-primary)' : isDark ? '#fff' : '#000';

  return (
    <>
      {/* Inject responsive media queries for bulletproof display layout controls */}
      <style>{`
        @media (max-width: 900px) {
          .desktop-nav {
            display: none !important;
          }
          .desktop-cta {
            display: none !important;
          }
          .mobile-hamburger {
            display: flex !important;
          }
        }
        @media (min-width: 901px) {
          .desktop-nav {
            display: flex !important;
          }
          .desktop-cta {
            display: inline-flex !important;
          }
          .mobile-hamburger {
            display: none !important;
          }
        }
      `}</style>

      {/* ============================================================
          FIXED NAVBAR WITH GLASSMORPHIC FROSTING
          ============================================================ */}
      <nav
        style={{
          zIndex:         10,
          position:       'fixed',
          top:            0,
          left:           0,
          right:          0,
          display:        'flex',
          alignItems:     'center',
          justifyContent: 'space-between',
          paddingLeft:    'clamp(20px, 5vw, 80px)',
          paddingRight:   'clamp(20px, 5vw, 80px)',
          paddingTop:     '14px',
          paddingBottom:  '14px',
          background:     isDark ? 'rgba(10, 10, 12, 0.45)' : 'rgba(255, 255, 255, 0.65)',
          borderBottom:   isDark ? '1px solid rgba(255, 255, 255, 0.05)' : '1px solid rgba(0, 0, 0, 0.05)',
          backdropFilter: 'blur(16px)',
          transition:     'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {/* ── Logo with clean bold tech aesthetic ── */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', transition: 'opacity 0.3s ease' }} 
          onClick={() => setView('hero')}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.85')}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = '1')}
        >
          <span
            style={{
              fontFamily:    'var(--font-heading)',
              fontSize:      '18px',
              letterSpacing: '-0.04em',
              fontWeight:    700,
              color:         textColor,
              transition:    'color 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
          >
            CodeAutopsy<span style={{ color: '#3B82F6' }}>.</span>
          </span>
        </div>

        {/* ── Desktop segmented glass nav dock (centered) ── */}
        <div
          className="desktop-nav"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            background: isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.03)',
            border: isDark ? '1px solid rgba(255, 255, 255, 0.06)' : '1px solid rgba(0, 0, 0, 0.05)',
            padding: '5px',
            borderRadius: '9999px',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        >
          {NAV_LINKS.map((link) => {
            const isActive = (link === 'Diagram' && currentView === 'workspace') || (link === 'Story' && currentView === 'story');
            return (
              <a
                key={link}
                href={`#${link.toLowerCase()}`}
                onClick={(e) => {
                  e.preventDefault();
                  if (link === 'Story') {
                    setView('story');
                  } else if (link === 'Diagram') {
                    setView('workspace');
                  } else if (link === 'Q&A') {
                    setView('workspace');
                  } else {
                    setView('hero');
                  }
                }}
                style={{
                  color: textColor,
                  textDecoration: 'none',
                  fontSize: '13px',
                  fontWeight: isActive ? 700 : 500,
                  letterSpacing: '-0.01em',
                  padding: '6px 16px',
                  borderRadius: '9999px',
                  background: isActive ? (isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.08)') : 'transparent',
                  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  opacity: isActive ? 1 : 0.75,
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
                    e.currentTarget.style.opacity = '1';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.opacity = '0.75';
                  }
                }}
              >
                {link}
              </a>
            );
          })}
        </div>

        {/* Right buttons row: Theme Toggles + CTA Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {/* Dark / Light Toggle */}
          <ThemeToggle isDark={isDark} toggleTheme={toggleTheme} />

          {/* Premium Capsule CTA Button */}
          <a
            href="#try"
            className="desktop-cta"
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: isDark ? '#000000' : '#ffffff',
              background: isDark ? '#ffffff' : '#000000',
              textDecoration: 'none',
              padding: '8px 20px',
              borderRadius: '9999px',
              transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-1.5px)';
              e.currentTarget.style.boxShadow = '0 6px 18px rgba(59, 130, 246, 0.25)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.06)';
            }}
          >
            Try it free
          </a>
        </div>

        {/* ── Mobile hamburger (hidden below 900px breakpoint) ── */}
        <button
          onClick={toggleMenu}
          className="mobile-hamburger"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          style={{
            display:        'none',
            flexDirection:  'column',
            justifyContent: 'center',
            alignItems:     'center',
            gap:            '5px',
            width:          '32px',
            height:         '32px',
            background:     'none',
            border:         'none',
            cursor:         'pointer',
            padding:        0,
          }}
        >
          {/* Top bar */}
          <span
            style={{
              display:         'block',
              width:           '24px',
              height:          '2px',
              backgroundColor: textColor,
              transition:      'transform 300ms ease, opacity 300ms ease',
              transformOrigin: 'center',
              transform:       menuOpen ? 'rotate(45deg) translateY(7px)' : 'none',
            }}
          />
          {/* Middle bar */}
          <span
            style={{
              display:         'block',
              width:           '24px',
              height:          '2px',
              backgroundColor: textColor,
              transition:      'opacity 300ms ease',
              opacity:         menuOpen ? 0 : 1,
            }}
          />
          {/* Bottom bar */}
          <span
            style={{
              display:         'block',
              width:           '24px',
              height:          '2px',
              backgroundColor: textColor,
              transition:      'transform 300ms ease',
              transformOrigin: 'center',
              transform:       menuOpen ? 'rotate(-45deg) translateY(-7px)' : 'none',
            }}
          />
        </button>
      </nav>

      {/* ============================================================
          MOBILE OVERLAY MENU
          ============================================================ */}
      <div
        style={{
          zIndex:         9,
          position:       'fixed',
          inset:          0,
          display:        'flex',
          flexDirection:  'column',
          justifyContent: 'center',
          paddingLeft:    '2rem',
          paddingRight:   '2rem',
          gap:            '2rem',
          background:     isDark ? 'rgba(9,9,11,0.95)' : 'rgba(255,255,255,0.95)',
          backdropFilter: 'blur(12px)',
          opacity:        menuOpen ? 1 : 0,
          pointerEvents:  menuOpen ? 'auto' : 'none',
          transition:     'opacity 300ms ease',
        }}
      >
        {NAV_LINKS.map((link) => (
          <a
            key={link}
            href={`#${link.toLowerCase()}`}
            onClick={(e) => {
              e.preventDefault();
              setMenuOpen(false);
              if (link === 'Story') {
                setView('story');
              } else if (link === 'Diagram') {
                setView('workspace');
              }
            }}
            style={{
              fontSize:       '32px',
              fontWeight:     500,
              color:          isDark ? '#fff' : '#000',
              textDecoration: 'none',
              cursor:         'pointer',
            }}
            className="transition-opacity duration-200 hover:opacity-60"
          >
            {link}
          </a>
        ))}
        <a
          href="#try"
          onClick={() => setMenuOpen(false)}
          style={{
            fontSize:          '32px',
            fontWeight:        500,
            color:             isDark ? '#fff' : '#000',
            textDecoration:    'underline',
            textUnderlineOffset: '3px',
          }}
          className="transition-opacity duration-200 hover:opacity-60"
        >
          Try it free
        </a>
      </div>
    </>
  );
}
