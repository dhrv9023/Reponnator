import { useState } from 'react';
import useTypewriter from '../hooks/useTypewriter';
import IngestionConsole from './IngestionConsole';

const TYPEWRITER_TEXT =
  'Most tools answer "What does this code do?" — we answer "Why was it built this way?" Drop any public GitHub repo. Get the architecture back.';


interface HeroSectionProps {
  currentView: 'hero' | 'ingestion' | 'workspace';
  setView: (view: 'hero' | 'ingestion' | 'workspace') => void;
  isDark: boolean;
  onIngestComplete?: (repoKey: string) => void;
}

interface StageData {
  id: string;
  num: string;
  title: string;
  shortTitle: string;
  metaphor: string;
  metaphorDesc: string;
  description: string;
  color: string;
}

const STAGES: StageData[] = [
  {
    id: 'connect',
    num: '01',
    title: 'Connect & Download',
    shortTitle: '1. Connect',
    metaphor: 'Opening a new book.',
    metaphorDesc: 'You hand us a link; we crack open the cover to see what lies inside.',
    description: 'Paste any public GitHub repository link. Our high-speed ingestion system instantly connects to GitHub, clones all the source files, checks rate limits, and creates a neat index folder of the entire codebase.',
    color: '#3B82F6', // Blue
  },
  {
    id: 'parse',
    num: '02',
    title: 'Read & Map',
    shortTitle: '2. Parse',
    metaphor: 'Building a family tree.',
    metaphorDesc: 'Tracing the heritage and relationships of every function in the code.',
    description: 'We do not read code like basic text. Our compiler engine analyzes the syntax, building a deep map of every class, function, and import. This shows exactly who is calling whom and where every definition lives.',
    color: '#8B5CF6', // Purple
  },
  {
    id: 'embed',
    num: '03',
    title: 'Slice & Remember',
    shortTitle: '3. Embed',
    metaphor: 'Storing in a memory vault.',
    metaphorDesc: 'Indexing short snippets mathematically so they can be retrieved instantly.',
    description: 'We slice your files into bite-sized code chunks at clean logical boundaries (like a function). Then, we convert these chunks into multi-dimensional mathematical vectors and index them in ChromaDB so our AI remembers everything.',
    color: '#10B981', // Green
  },
  {
    id: 'ask',
    num: '04',
    title: 'Ask & Answer',
    shortTitle: '4. Ask AI',
    metaphor: 'Chatting with the architect.',
    metaphorDesc: 'Having a smart engineer explain how everything fits together in plain English.',
    description: 'Ask any question. Our retriever searches the vector vault, links the results to our code family tree to confirm accuracy, and hands this combined context to our Groq-powered AI to write a perfect architectural story.',
    color: '#F59E0B', // Amber
  },
];

export default function HeroSection({ currentView, setView, isDark, onIngestComplete }: HeroSectionProps) {
  const { displayed, done } = useTypewriter({
    text:       TYPEWRITER_TEXT,
    speed:      32,
    startDelay: 600,
  });

  const [repoInput, setRepoInput] = useState('');
  const [inputError, setInputError] = useState('');
  const [activeStage, setActiveStage] = useState<number>(0);
  const [submittedUrl, setSubmittedUrl] = useState('https://github.com/pallets/itsdangerous');

  const handleAnalyse = () => {
    const url = repoInput.trim();
    if (!url) {
      setInputError('Please enter a GitHub repository URL.');
      return;
    }
    if (!url.startsWith('https://github.com/') && !url.startsWith('http://github.com/')) {
      setInputError('URL must start with https://github.com/');
      return;
    }
    setInputError('');
    setSubmittedUrl(url);
    setView('ingestion');
  };

  const activeTextColor = isDark ? '#fff' : '#000';

  return (
    <>
      <style>{`
        /* Tab Selector */
        .tab-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 36px;
          background: ${isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.02)'};
          border: 1px solid ${isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.05)'};
          padding: 5px;
          borderRadius: 9999px;
          width: fit-content;
          backdrop-filter: blur(12px);
        }

        .tab-btn {
          font-size: 13px;
          font-weight: 600;
          color: ${isDark ? '#a3a3a3' : '#6b7280'};
          background: transparent;
          border: none;
          padding: 8px 18px;
          border-radius: 9999px;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .tab-btn.active {
          color: ${isDark ? '#fff' : '#000'};
          background: ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'};
          box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

        /* Showcase Panel */
        .showcase-panel {
          display: grid;
          grid-template-columns: 1.2fr 1fr;
          gap: 40px;
          margin-top: 36px;
          background: ${isDark ? 'rgba(255, 255, 255, 0.015)' : 'rgba(255, 255, 255, 0.4)'};
          border: 1px solid ${isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'};
          border-radius: 24px;
          padding: 40px;
          backdrop-filter: blur(16px);
          transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @media (max-width: 900px) {
          .showcase-panel {
            grid-template-columns: 1fr;
            padding: 24px;
          }
          .tab-row {
            flex-wrap: wrap;
            border-radius: 16px;
            padding: 8px;
          }
        }

        /* Console visual mock layout */
        .console-mock {
          background: #08080a;
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 14px;
          padding: 20px;
          font-family: var(--font-mono);
          font-size: 13px;
          line-height: 1.6;
          color: #3b82f6;
          box-shadow: inset 0 2px 10px rgba(0,0,0,0.8);
          position: relative;
          overflow: hidden;
          min-height: 220px;
          display: flex;
          flex-direction: column;
        }

        .console-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
          margin-right: 6px;
        }
      `}</style>

      {/* ============================================================
          SECTION 1: HERO VIEW
          ============================================================ */}
      <section
        id="hero"
        style={{
          position:      'relative',
          zIndex:        1,
          minHeight:     '100vh',
          display:       'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          paddingTop:    '80px',
          paddingBottom: '3rem',
          paddingLeft:   'clamp(20px, 5vw, 80px)',
          paddingRight:  'clamp(20px, 5vw, 80px)',
          overflow:      'hidden',
        }}
      >
        <div style={{ maxWidth: '650px', position: 'relative', zIndex: 10 }}>

          {currentView === 'hero' ? (
            <>
              {/* ── 1. Premium sharp tagline ── */}
              <div
                aria-hidden="true"
                className="fade-in"
                style={{
                  pointerEvents: 'none',
                  userSelect:    'none',
                  marginBottom:  'clamp(12px, 2vw, 18px)',
                  fontSize:      'clamp(11px, 1.2vw, 13px)',
                  lineHeight:    1.5,
                  fontWeight:    600,
                  color:         isDark ? '#3B82F6' : '#2563EB',
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  transition:    'color 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                  opacity:       0.9,
                }}
              >
                  Drop a repo. Get the architecture back.
              </div>

              {/* ── 2. Typewriter text ── */}
              <p
                className="slide-in-left"
                style={{
                  color:       activeTextColor,
                  fontSize:    'clamp(20px, 4vw, 28px)',
                  lineHeight:  1.4,
                  fontWeight:  400,
                  minHeight:   '60px',
                  marginBottom:'clamp(24px, 3vw, 32px)',
                  transition:  'color 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                  letterSpacing: '-0.015em',
                }}
              >
                {displayed}
                {!done && (
                  <span
                    className="cursor-blink"
                    aria-hidden="true"
                    style={{
                      backgroundColor: activeTextColor,
                      display: 'inline-block',
                      width: '3px',
                      height: '22px',
                      marginLeft: '4px',
                      verticalAlign: 'middle',
                    }}
                  />
                )}
              </p>

              {/* ── 4. GitHub URL Input ── */}
              <div className="fade-in" style={{ animationDelay: '0.5s', marginTop: '28px', width: '100%', maxWidth: '560px' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0,
                  background: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)',
                  border: `1.5px solid ${inputError ? '#ef4444' : isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)'}`,
                  borderRadius: 14,
                  overflow: 'hidden',
                  backdropFilter: 'blur(12px)',
                  transition: 'border-color 0.2s',
                }}>
                  {/* GitHub icon */}
                  <div style={{ padding: '0 14px', color: isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)', flexShrink: 0 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.335-1.755-1.335-1.755-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z"/>
                    </svg>
                  </div>
                  <input
                    id="repo-url-input"
                    type="url"
                    placeholder="https://github.com/owner/repository"
                    value={repoInput}
                    onChange={e => { setRepoInput(e.target.value); setInputError(''); }}
                    onKeyDown={e => e.key === 'Enter' && handleAnalyse()}
                    style={{
                      flex: 1,
                      border: 'none',
                      background: 'transparent',
                      outline: 'none',
                      padding: '13px 8px',
                      fontSize: 14,
                      color: isDark ? '#f1f5f9' : '#0f172a',
                      fontFamily: 'var(--font-mono, monospace)',
                      minWidth: 0,
                    }}
                    aria-label="GitHub repository URL"
                  />
                  <button
                    onClick={handleAnalyse}
                    style={{
                      padding: '10px 20px',
                      margin: 4,
                      background: isDark ? '#fff' : '#0f172a',
                      color: isDark ? '#000' : '#fff',
                      border: 'none',
                      borderRadius: 10,
                      fontWeight: 700,
                      fontSize: 13,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      flexShrink: 0,
                      transition: 'opacity 0.2s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
                    onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                  >
                    Analyse Repo →
                  </button>
                </div>
                {inputError && (
                  <p style={{ fontSize: 12, color: '#ef4444', marginTop: 6, marginLeft: 4 }}>{inputError}</p>
                )}
                <p style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)', marginTop: 8, marginLeft: 4 }}>
                  Paste any public GitHub repo URL · Press Enter or click Analyse
                </p>
              </div>
            </>
          ) : (
            /* ── Ingestion Console Panel ── */
            <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: '700px' }}>
              <h2 style={{ 
                fontSize: 'clamp(22px, 3vw, 30px)', 
                color: activeTextColor, 
                fontWeight: 600, 
                marginBottom: '24px', 
                letterSpacing: '-0.03em', 
                textAlign: 'center', 
                transition: 'color 0.4s cubic-bezier(0.4, 0, 0.2, 1)' 
              }}>
                ⏳ Deconstructing Codebase Architecture...
              </h2>
              <IngestionConsole
                repoUrl={submittedUrl}
                onComplete={(key) => {
                  if (onIngestComplete) onIngestComplete(key);
                  else setView('workspace');
                }}
                onCancel={() => setView('hero')}
              />
            </div>
          )}

        </div>
      </section>

      {/* ============================================================
          SECTION 2: HOW IT WORKS (TABBED INTERACTIVE DECK)
          ============================================================ */}
      {currentView === 'hero' && (
        <section
          id="how-it-works"
          style={{
            position: 'relative',
            zIndex: 2,
            paddingLeft: 'clamp(20px, 5vw, 80px)',
            paddingRight: 'clamp(20px, 5vw, 80px)',
            paddingTop: '100px',
            paddingBottom: '120px',
            background: isDark ? 'rgba(10, 10, 12, 0.3)' : 'rgba(255, 255, 255, 0.3)',
            borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'}`,
          }}
        >
          {/* Section Header */}
          <div style={{ maxWidth: '800px', marginBottom: '40px' }}>
            <span style={{
              fontSize: '12px',
              fontWeight: 600,
              color: '#3B82F6',
              textTransform: 'uppercase',
              letterSpacing: '0.15em',
            }}>
              Interactive Overview
            </span>
            <h2 style={{
              fontSize: 'clamp(28px, 4vw, 42px)',
              fontWeight: 700,
              color: activeTextColor,
              letterSpacing: '-0.03em',
              marginTop: '12px',
              marginBottom: '20px',
            }}>
              How CodeAutopsy Works
            </h2>
            <p style={{
              fontSize: 'clamp(15px, 1.8vw, 18px)',
              color: isDark ? '#a3a3a3' : '#6b7280',
              lineHeight: 1.6,
            }}>
              Click through the stages below to see how our engineering pipeline takes complex code folders and turns them into simple, clear explanations.
            </p>
          </div>

          {/* Horizontal Tab bar Selector */}
          <div className="tab-row">
            {STAGES.map((s, idx) => (
              <button
                key={s.id}
                onClick={() => setActiveStage(idx)}
                className={`tab-btn ${activeStage === idx ? 'active' : ''}`}
                style={{
                  borderLeft: activeStage === idx ? `2px solid ${s.color}` : 'none',
                }}
              >
                {s.shortTitle}
              </button>
            ))}
          </div>

          {/* Unified Showcase Panel */}
          <div className="showcase-panel">
            
            {/* Left Column: Easy Story text */}
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <span style={{
                fontSize: '12px',
                fontWeight: 700,
                color: STAGES[activeStage].color,
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}>
                STAGE {STAGES[activeStage].num} / 04
              </span>
              
              <h3 style={{
                fontSize: 'clamp(22px, 3vw, 32px)',
                fontWeight: 700,
                color: activeTextColor,
                marginTop: '8px',
                marginBottom: '16px',
                letterSpacing: '-0.02em',
              }}>
                {STAGES[activeStage].title}
              </h3>

              {/* Metaphor Quote capsule */}
              <div
                style={{
                  borderLeft: `3px solid ${STAGES[activeStage].color}`,
                  paddingLeft: '16px',
                  background: isDark ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)',
                  borderRadius: '0 8px 8px 0',
                  paddingTop: '10px',
                  paddingBottom: '10px',
                  marginBottom: '20px',
                }}
              >
                <div style={{ fontSize: '13px', fontWeight: 700, color: STAGES[activeStage].color, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
                  Metaphor: {STAGES[activeStage].metaphor}
                </div>
                <div style={{ fontSize: '14px', color: isDark ? '#d4d4d8' : '#3f3f46', fontStyle: 'italic', lineHeight: 1.4 }}>
                  "{STAGES[activeStage].metaphorDesc}"
                </div>
              </div>

              <p style={{
                fontSize: '15px',
                color: isDark ? '#a3a3a3' : '#52525b',
                lineHeight: 1.7,
              }}>
                {STAGES[activeStage].description}
              </p>
            </div>

            {/* Right Column: Live Mock Visual Console */}
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div className="console-mock">
                
                {/* Console header */}
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '14px', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px' }}>
                  <span className="console-dot" style={{ backgroundColor: '#ef4444' }} />
                  <span className="console-dot" style={{ backgroundColor: '#eab308' }} />
                  <span className="console-dot" style={{ backgroundColor: '#22c55e' }} />
                  <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', fontWeight: 600, marginLeft: '10px' }}>stage-{STAGES[activeStage].id}-console</span>
                </div>

                {/* Stage-specific Visual Simulation */}
                {activeStage === 0 && (
                  <div style={{ color: '#60a5fa' }}>
                    <div style={{ color: '#888', marginBottom: '6px' }}>$ git clone https://github.com/owner/repo</div>
                    <div><span style={{ color: '#10b981' }}>✓</span> Repository connected successfully</div>
                    <div><span style={{ color: '#10b981' }}>✓</span> 24 files discovered in tree manifest</div>
                    <div style={{ color: '#a78bfa', marginTop: '10px', animation: 'blink 1s step-end infinite' }}>
                      [Ingested] signer.py ... 100% OK
                    </div>
                    <div style={{ color: '#888', marginTop: '6px' }}>Files cataloged, proceeding to parsing registry...</div>
                  </div>
                )}

                {activeStage === 1 && (
                  <div style={{ color: '#c084fc' }}>
                    <div style={{ color: '#888', marginBottom: '6px' }}>$ python analyze_ast.py --file signer.py</div>
                    <div><span style={{ color: '#38bdf8' }}>class</span> Signer:</div>
                    <div style={{ paddingLeft: '16px' }}><span style={{ color: '#f472b6' }}>def</span> __init__(key)</div>
                    <div style={{ paddingLeft: '16px' }}><span style={{ color: '#f472b6' }}>def</span> sign(data) ──▶ <span style={{ color: '#fbbf24' }}>calls HMAC</span></div>
                    <div style={{ paddingLeft: '16px' }}><span style={{ color: '#f472b6' }}>def</span> unsign(signed)</div>
                    <div style={{ color: '#888', marginTop: '10px' }}>[OK] AST relationships parsed successfully.</div>
                  </div>
                )}

                {activeStage === 2 && (
                  <div style={{ color: '#34d399' }}>
                    <div style={{ color: '#888', marginBottom: '6px' }}>$ python embed.py --chunk-boundaries</div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '6px', borderRadius: '4px', borderLeft: '3px solid #10B981', color: '#ccc', fontSize: '11px', marginBottom: '8px' }}>
                      class Signer:<br />
                      &nbsp;&nbsp;def __init__(self, key): ...
                    </div>
                    <div>→ Encrypted Chunk Size: 184 tokens</div>
                    <div style={{ color: '#fbbf24' }}>→ Embed coordinate: [0.142, -0.923, 0.405, ...]</div>
                    <div style={{ color: '#10b981', marginTop: '6px' }}>✓ Chunks securely loaded into local ChromaDB vault.</div>
                  </div>
                )}

                {activeStage === 3 && (
                  <div style={{ color: '#fbbf24' }}>
                    <div style={{ color: '#888', marginBottom: '6px' }}>$ ask "How does Signer work?"</div>
                    <div style={{ color: '#fff', marginBottom: '6px' }}><span style={{ color: '#38bdf8' }}>User:</span> How does Signer work?</div>
                    <div style={{ color: '#60a5fa' }}><span style={{ color: '#a78bfa' }}>AI Context:</span> (Retrieved signer.py:L10-L40)</div>
                    <div style={{ color: '#ccc', marginTop: '4px', lineHeight: 1.5 }}>
                      "The <strong>Signer</strong> class uses <strong>HMAC</strong> to sign data. It ensures your variables haven't been tampered with..."
                    </div>
                  </div>
                )}

              </div>
            </div>

          </div>
        </section>
      )}

      {/* ============================================================
          SECTION 3: WHO IS THIS FOR — 3 Personas
          ============================================================ */}
      {currentView === 'hero' && (
        <section
          id="who-is-this-for"
          style={{
            position: 'relative',
            zIndex: 2,
            paddingLeft: 'clamp(20px, 5vw, 80px)',
            paddingRight: 'clamp(20px, 5vw, 80px)',
            paddingTop: '100px',
            paddingBottom: '100px',
            background: isDark ? 'rgba(6,8,15,0.4)' : 'rgba(248,250,252,0.6)',
            borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'}`,
          }}
        >
          <div style={{ maxWidth: '900px', margin: '0 auto' }}>
            <span style={{
              fontSize: '12px',
              fontWeight: 600,
              color: '#8B5CF6',
              textTransform: 'uppercase' as const,
              letterSpacing: '0.15em',
            }}>
              Who Is This For
            </span>
            <h2 style={{
              fontSize: 'clamp(28px, 4vw, 42px)',
              fontWeight: 700,
              color: activeTextColor,
              letterSpacing: '-0.03em',
              marginTop: '12px',
              marginBottom: '12px',
            }}>
              Built for people dropped into complex codebases
            </h2>
            <p style={{
              fontSize: 'clamp(15px, 1.8vw, 18px)',
              color: isDark ? '#a3a3a3' : '#6b7280',
              lineHeight: 1.6,
              marginBottom: '40px',
              maxWidth: '640px',
            }}>
              No tool gives you architecture-first onboarding. Most give you code search.
              CodeAutopsy reverses the direction — it tells you the story first.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
              {[
                {
                  icon: '🧑‍💻',
                  title: 'New engineer on the team',
                  sub: 'Day 1, 100k-line repo, no docs.',
                  body: 'Get the full architecture story + interactive call graph in minutes. Ship confidently in week 1 instead of week 4.',
                  color: '#3B82F6',
                },
                {
                  icon: '🤝',
                  title: 'Open-source contributor',
                  sub: 'Want to contribute but lost in the structure.',
                  body: 'See the founding metaphor, design tensions, and module relationships before writing a single line.',
                  color: '#8B5CF6',
                },
                {
                  icon: '🔍',
                  title: 'Tech lead / interviewer',
                  sub: 'Evaluating a candidate's OSS project.',
                  body: 'Get an architectural audit — story + diagram — in 90 seconds. See decisions, not just output.',
                  color: '#10B981',
                },
              ].map((p) => (
                <div
                  key={p.title}
                  style={{
                    background: isDark ? 'rgba(255,255,255,0.025)' : 'rgba(255,255,255,0.7)',
                    border: `1px solid ${isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)'}`,
                    borderRadius: '20px',
                    padding: '28px',
                    backdropFilter: 'blur(12px)',
                    position: 'relative' as const,
                    overflow: 'hidden',
                  }}
                >
                  <div style={{ position: 'absolute' as const, top: 0, left: 0, right: 0, height: '3px', background: p.color, borderRadius: '20px 20px 0 0' }} />
                  <div style={{ fontSize: '28px', marginBottom: '14px' }}>{p.icon}</div>
                  <div style={{ fontSize: '16px', fontWeight: 700, color: activeTextColor, marginBottom: '6px', lineHeight: 1.3 }}>{p.title}</div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: p.color, marginBottom: '12px', textTransform: 'uppercase' as const, letterSpacing: '0.06em' }}>{p.sub}</div>
                  <div style={{ fontSize: '14px', color: isDark ? '#a3a3a3' : '#52525b', lineHeight: 1.6 }}>{p.body}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ============================================================
          SECTION 4: VS ALTERNATIVES
          ============================================================ */}
      {currentView === 'hero' && (
        <section
          id="vs-alternatives"
          style={{
            position: 'relative',
            zIndex: 2,
            paddingLeft: 'clamp(20px, 5vw, 80px)',
            paddingRight: 'clamp(20px, 5vw, 80px)',
            paddingTop: '100px',
            paddingBottom: '120px',
            background: isDark ? 'rgba(10,10,12,0.3)' : 'rgba(255,255,255,0.3)',
            borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'}`,
          }}
        >
          <div style={{ maxWidth: '900px', margin: '0 auto' }}>
            <span style={{
              fontSize: '12px',
              fontWeight: 600,
              color: '#F59E0B',
              textTransform: 'uppercase' as const,
              letterSpacing: '0.15em',
            }}>
              Why Not Just Use Gemini?
            </span>
            <h2 style={{
              fontSize: 'clamp(28px, 4vw, 42px)',
              fontWeight: 700,
              color: activeTextColor,
              letterSpacing: '-0.03em',
              marginTop: '12px',
              marginBottom: '14px',
            }}>
              How CodeAutopsy is different
            </h2>
            <p style={{
              fontSize: 'clamp(15px, 1.8vw, 17px)',
              color: isDark ? '#a3a3a3' : '#6b7280',
              lineHeight: 1.6,
              marginBottom: '36px',
              maxWidth: '600px',
            }}>
              Gemini reads code text. CodeAutopsy builds a structured knowledge representation first —
              a real AST call graph, pattern detector, and persistent vector store.
            </p>

            <div style={{
              background: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.8)',
              border: `1px solid ${isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)'}`,
              borderRadius: '20px',
              overflow: 'hidden',
              backdropFilter: 'blur(16px)',
            }}>
              {/* Table header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '2fr 1fr 1fr 1fr',
                padding: '14px 24px',
                background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}`,
                gap: '8px',
              }}>
                {['Capability', 'CodeAutopsy', 'Gemini / ChatGPT', 'GitHub Copilot'].map((h, i) => (
                  <div key={h} style={{
                    fontSize: '11px',
                    fontWeight: 700,
                    textTransform: 'uppercase' as const,
                    letterSpacing: '0.08em',
                    color: i === 1 ? '#10B981' : isDark ? '#6b7280' : '#9ca3af',
                    textAlign: i === 0 ? 'left' : 'center' as const,
                  }}>{h}</div>
                ))}
              </div>

              {/* Table rows */}
              {[
                [
                  'Architecture-first output (not just code search)',
                  '✅ Story + Diagram + Q&A',
                  '❌ Chat only',
                  '❌ Inline suggestions',
                ],
                [
                  'Persists index — pay ingestion cost once',
                  '✅ ChromaDB + BM25',
                  '❌ Re-reads on every query',
                  '❌ No persistence',
                ],
                [
                  'Works on 200k+ line repos (no context limit)',
                  '✅ Chunk retrieval',
                  '⚠️ Context window cap',
                  '⚠️ Limited scope',
                ],
                [
                  'Real AST call graph (not just text similarity)',
                  '✅ Tree-sitter + NetworkX',
                  '❌ Token similarity only',
                  '❌ Token similarity only',
                ],
                [
                  'Design decisions + architectural trade-offs',
                  '✅ Repponator story',
                  '⚠️ Only if you prompt well',
                  '❌ Not its purpose',
                ],
              ].map((row, ri) => (
                <div
                  key={ri}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '2fr 1fr 1fr 1fr',
                    padding: '16px 24px',
                    gap: '8px',
                    borderBottom: ri < 4
                      ? `1px solid ${isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.05)'}`
                      : 'none',
                    background: ri % 2 === 0
                      ? 'transparent'
                      : isDark ? 'rgba(255,255,255,0.01)' : 'rgba(0,0,0,0.01)',
                  }}
                >
                  {row.map((cell, ci) => (
                    <div
                      key={ci}
                      style={{
                        fontSize: ci === 0 ? '13px' : '12px',
                        fontWeight: ci === 0 ? 400 : 600,
                        color: ci === 0
                          ? isDark ? '#d4d4d8' : '#3f3f46'
                          : ci === 1
                            ? '#10B981'
                            : isDark ? '#71717a' : '#9ca3af',
                        textAlign: ci === 0 ? 'left' : 'center' as const,
                        lineHeight: 1.4,
                      }}
                    >
                      {cell}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </>
  );
}
