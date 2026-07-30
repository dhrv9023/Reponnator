import { useState, useEffect } from 'react';
import { apiClient, RepoDetailResponse, NodeMetadata } from '../api/client';
import { DiagramCanvas, CustomNode, CustomLink } from './Diagram';

interface WorkspaceProps {
  repoKey?: string;
  isDark?: boolean;
}

export default function Workspace({ repoKey = "karpathy__nanogpt", isDark = true }: WorkspaceProps) {
  const [repoDetails, setRepoDetails] = useState<RepoDetailResponse | null>(null);
  const [nodes, setNodes] = useState<CustomNode[]>([]);
  const [links, setLinks] = useState<CustomLink[]>([]);
  const [nodeCoords, setNodeCoords] = useState<Record<string, { x: number; y: number }>>({});
  
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<CustomNode | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState<Array<{ sender: 'user' | 'assistant'; text: string; citation?: any }>>([]);
  const [activeCodeCitation, setActiveCodeCitation] = useState<{ code: string; lines: string } | null>(null);
  const [highlightedElement, setHighlightedElement] = useState<string | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | undefined>(undefined);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    const loadWorkspaceData = async () => {
      try {
        setLoading(true);
        
        // 1. Fetch Repository Details
        const details = await apiClient.getRepoDetail(repoKey);
        setRepoDetails(details);

        // 2. Fetch Diagram Graph
        const diag = await apiClient.getDiagramDetail(repoKey);
        const parsedNodes: CustomNode[] = diag.metadata.map((n: NodeMetadata) => ({
          id: n.id,
          label: n.label,
          type: n.type,
          complexity: n.call_count * 2 + 2,
          lines: "1-100",
          file: n.label,
          role: `AST module containing ${n.functions.length} functions and ${n.classes.length} classes. Called ${n.call_count} times in execution trees.`,
          functionCount: n.functions.length,
          classCount: n.classes.length,
          callCount: n.call_count,
        }));

        const parsedLinks: CustomLink[] = [];
        const mermaidLines = diag.mermaid_syntax.split('\n');
        mermaidLines.forEach(line => {
          // Match solid arrows '-->' and dashed arrows '-.->'
          const arrowMatch = line.match(/^\s*(\S+)\s+(?:-->|-\.->)\s+(\S+)/);
          if (arrowMatch) {
            const source = arrowMatch[1].replace(/[()[\]{}"']/g, '');
            const target = arrowMatch[2].replace(/[()[\]{}"']/g, '');
            if (source && target && source !== '%%') {
              parsedLinks.push({ source, target });
            }
          }
        });

        // 3. Hierarchical layered layout: entry_point → core_utility → module
        const CARD_W = 160, CARD_H = 80, H_GAP = 50, V_GAP = 100, CANVAS_CX = 520;
        const groups: Record<string, CustomNode[]> = { entry_point: [], core_utility: [], module: [] };
        parsedNodes.forEach(n => { (groups[n.type] ?? groups.module).push(n); });

        const coords: Record<string, { x: number; y: number }> = {};
        let currentY = 100;
        (['entry_point', 'core_utility', 'module'] as const).forEach(tier => {
          const tierNodes = groups[tier];
          if (!tierNodes.length) return;
          const COLS = tier === 'module' && tierNodes.length > 5 ? Math.ceil(Math.sqrt(tierNodes.length * 1.5)) : tierNodes.length;
          tierNodes.forEach((node, i) => {
            const col = i % COLS;
            const row = Math.floor(i / COLS);
            const rowCount = Math.min(COLS, tierNodes.length - row * COLS);
            const rowWidth = rowCount * CARD_W + (rowCount - 1) * H_GAP;
            coords[node.id] = {
              x: Math.round(CANVAS_CX - rowWidth / 2 + CARD_W / 2 + col * (CARD_W + H_GAP)),
              y: Math.round(currentY + row * (CARD_H + V_GAP)),
            };
          });
          const rows = Math.ceil(tierNodes.length / COLS);
          currentY += rows * (CARD_H + V_GAP) + 40;
        });

        setNodes(parsedNodes);
        setLinks(parsedLinks);
        setNodeCoords(coords);

        // Initial welcome chat
        setChatHistory([
          { 
            sender: 'assistant', 
            text: `Hello! I am your CodeAutopsy RAG Assistant. Ask me any design or architectural question about ${details.owner}/${details.name}!` 
          }
        ]);

      } catch (err) {
        console.error(`Failed to load workspace data for repo '${repoKey}':`, err);
        // Leave nodes/links empty — the empty-state UI will show below
        setNodes([]);
        setLinks([]);
        setNodeCoords({});
      } finally {
        setLoading(false);
      }
    };

    loadWorkspaceData();
  }, [repoKey]);

  const handleSendChat = async (text: string) => {
    if (!text.trim()) return;
    const userMsg = text.trim();
    setChatHistory(prev => [...prev, { sender: 'user', text: userMsg }]);
    setChatInput('');
    setIsTyping(true);

    try {
      const response = await apiClient.askQuestion(repoKey, userMsg, chatSessionId);
      setChatSessionId(response.session_id);
      
      const citationData = response.citations && response.citations.length > 0 ? {
        code: response.citations[0].snippet || "",
        lineRange: `${response.citations[0].filename} (Lines ${response.citations[0].line_start || 1}-${response.citations[0].line_end || 50})`
      } : undefined;

      setChatHistory(prev => [...prev, {
        sender: 'assistant',
        text: response.answer,
        citation: citationData
      }]);
    } catch (err: any) {
      console.error(err);
      setChatHistory(prev => [...prev, {
        sender: 'assistant',
        text: "Sorry, I had trouble retrieving information from the vector search space. Check your Groq connectivity."
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', justifyContent: 'center', alignItems: 'center', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
        <div className="cursor-blink" style={{ width: '40px', height: '40px', borderRadius: '50%', border: '4px solid var(--accent-glow)', borderTopColor: 'var(--accent-color)', animation: 'spin 1s linear infinite' }} />
        <h3 style={{ marginTop: '20px', fontWeight: 600, fontSize: '18px' }}>Loading CodeAutopsy Workspace...</h3>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '8px' }}>Fetching syntax definitions, layout links and LLM stories</span>
      </div>
    );
  }

  // Show a clear empty state if diagram data is missing (backend down or pipeline not run yet)
  if (nodes.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', paddingTop: '88px', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)', justifyContent: 'center', alignItems: 'center', gap: '16px' }}>
        <div style={{ fontSize: '48px' }}>🔬</div>
        <h2 style={{ fontSize: '22px', fontWeight: 700, margin: 0 }}>No diagram data for <code style={{ color: 'var(--accent-color)', background: 'var(--bg-secondary)', padding: '2px 8px', borderRadius: '6px' }}>{repoKey}</code></h2>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '480px', textAlign: 'center', lineHeight: 1.6 }}>
          The analysis pipeline hasn't run for this repository yet, or the backend is not reachable.<br />
          Make sure the FastAPI server is running on <strong>localhost:8000</strong>, then use the <strong>Analyse Repo</strong> flow on the home screen to generate the diagram and story.
        </p>
        <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
          <code style={{ fontSize: '12px', background: 'var(--bg-secondary)', padding: '8px 14px', borderRadius: '8px', border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
            cd codeautopsy && python3 -m uvicorn api.main:app --reload --port 8000
          </code>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        paddingTop: '88px',
        backgroundColor: 'var(--bg-primary)',
        color: 'var(--text-primary)',
        overflow: 'hidden',
        transition: 'background-color 0.4s cubic-bezier(0.4, 0, 0.2, 1), color 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      {/* Workspace Header Stats */}
      <div
        className="glass"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 28px',
          borderBottom: '1px solid var(--border-color)',
          transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '19px', fontWeight: 600, letterSpacing: '-0.02em' }}>📁 {repoDetails?.owner}/{repoDetails?.name}</span>
          <span
            style={{
              padding: '3px 10px',
              fontSize: '11px',
              borderRadius: '999px',
              backgroundColor: 'var(--accent-glow)',
              color: 'var(--accent-color)',
              fontWeight: 600,
              letterSpacing: '0.02em',
            }}
          >
            ACTIVE WORKSPACE
          </span>
        </div>
        <div style={{ display: 'flex', gap: '24px', fontSize: '14px', color: 'var(--text-secondary)', fontWeight: 500 }}>
          <span>Files: <strong style={{ color: 'var(--text-primary)' }}>{repoDetails?.total_files}</strong></span>
          <span>Language: <strong style={{ color: 'var(--text-primary)' }}>{repoDetails?.primary_language}</strong></span>
          <span>Phases: <strong style={{ color: 'var(--accent-green)' }}>{repoDetails?.phases_complete.join(', ')}</strong></span>
        </div>
      </div>

      {/* Main Workspace Panels Grid */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* ============================================================
            PANEL 1: DIAGRAM LEGEND & TOOLS
            ============================================================ */}
        <div
          className="custom-scrollbar"
          style={{
            width: '20%',
            borderRight: '1px solid var(--border-color)',
            overflowY: 'auto',
            padding: '24px',
            lineHeight: '1.6',
            fontSize: '14px',
          }}
        >
          <h2 style={{ fontSize: '21px', fontWeight: 600, marginBottom: '18px', letterSpacing: '-0.025em' }}>🎨 Diagram Tools</h2>
          
          {/* Color Legend */}
          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.05em' }}>Node Types</h4>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', borderRadius: '6px', background: 'var(--bg-secondary)' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 8px #16a34a' }}></div>
                <div>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>Entry Point</strong>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: 0 }}>Main entry files (▶)</p>
                </div>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', borderRadius: '6px', background: 'var(--bg-secondary)' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#818cf8', boxShadow: '0 0 8px #6366f1' }}></div>
                <div>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>Core Utility</strong>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: 0 }}>Heavily used (◆)</p>
                </div>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', borderRadius: '6px', background: 'var(--bg-secondary)' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#38bdf8', boxShadow: '0 0 8px #0284c7' }}></div>
                <div>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>Module</strong>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: 0 }}>Regular files (M)</p>
                </div>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', borderRadius: '6px', background: 'var(--bg-secondary)' }}>
                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#c084fc', boxShadow: '0 0 8px #a855f7' }}></div>
                <div>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>Class</strong>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: 0 }}>Class definitions (C)</p>
                </div>
              </div>
            </div>
          </div>

          <hr style={{ borderColor: 'var(--border-color)', margin: '24px 0' }} />

          {/* Interaction Guide */}
          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.05em' }}>Controls</h4>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '16px' }}>🖱️</span>
                <span>Click node for details</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '16px' }}>🔍</span>
                <span>Scroll to zoom</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '16px' }}>✋</span>
                <span>Drag to pan</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '16px' }}>🔎</span>
                <span>Search to highlight</span>
              </div>
            </div>
          </div>

          <hr style={{ borderColor: 'var(--border-color)', margin: '24px 0' }} />

          {/* Stats */}
          <div>
            <h4 style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.05em' }}>Diagram Stats</h4>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Total Nodes:</span>
                <strong style={{ color: 'var(--text-primary)' }}>{nodes.length}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Connections:</span>
                <strong style={{ color: 'var(--text-primary)' }}>{links.length}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Entry Points:</span>
                <strong style={{ color: '#22c55e' }}>{nodes.filter(n => n.type === 'entry_point').length}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Core Utils:</span>
                <strong style={{ color: '#818cf8' }}>{nodes.filter(n => n.type === 'core_utility').length}</strong>
              </div>
            </div>
          </div>

          <hr style={{ borderColor: 'var(--border-color)', margin: '24px 0' }} />

          {/* Quick Actions */}
          <div>
            <h4 style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.05em' }}>Export</h4>
            
            <button
              onClick={() => {
                alert('Diagram export feature coming soon! For now, use screenshot tools or browser print.');
              }}
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--accent-color)',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 600,
                marginBottom: '8px',
              }}
            >
              📸 Export as Image
            </button>
            
            <button
              onClick={() => {
                alert('Mermaid export feature coming soon!');
              }}
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              📄 Export Mermaid Code
            </button>
          </div>
        </div>

        {/* ============================================================
            PANEL 2: DIAGRAM CANVAS (CODEAUTOPSY)
            ============================================================ */}
        <DiagramCanvas
          nodes={nodes}
          links={links}
          nodeCoords={nodeCoords}
          highlightedElement={highlightedElement}
          setHighlightedElement={setHighlightedElement}
          selectedNode={selectedNode}
          setSelectedNode={setSelectedNode}
          isDark={isDark}
        />

        {/* ============================================================
            PANEL 3: AGENT ARCHITECT Q&A (THE CHAT WORKSPACE)
            ============================================================ */}
        <div
          style={{
            width: '28%',
            borderLeft: '1px solid var(--border-color)',
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-glass)' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 'bold' }}>💬 Codebase Q&A Assistant</h3>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Ask design, patterns, and code relationships</span>
          </div>

          {/* Quick suggestions */}
          <div style={{ padding: '10px 15px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '8px', overflowX: 'auto', whiteSpace: 'nowrap' }} className="custom-scrollbar">
            <button
              onClick={() => handleSendChat("What is the overall purpose of this codebase?")}
              style={{ fontSize: '11px', padding: '4px 10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '999px', cursor: 'pointer', color: 'var(--text-primary)' }}
            >
              🏗️ Codebase purpose
            </button>
            <button
              onClick={() => handleSendChat("What are the main entry points?")}
              style={{ fontSize: '11px', padding: '4px 10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '999px', cursor: 'pointer', color: 'var(--text-primary)' }}
            >
              ▶ Entry points
            </button>
            <button
              onClick={() => handleSendChat("Explain the key design patterns used.")}
              style={{ fontSize: '11px', padding: '4px 10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '999px', cursor: 'pointer', color: 'var(--text-primary)' }}
            >
              ◆ Design patterns
            </button>
          </div>

          {/* Messages */}
          <div
            className="custom-scrollbar"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {chatHistory.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  background: msg.sender === 'user' ? 'var(--accent-color)' : 'var(--bg-secondary)',
                  color: msg.sender === 'user' ? '#fff' : 'var(--text-primary)',
                  padding: '12px',
                  borderRadius: '12px',
                  borderTopRightRadius: msg.sender === 'user' ? '2px' : '12px',
                  borderTopLeftRadius: msg.sender === 'assistant' ? '2px' : '12px',
                  fontSize: '13px',
                  lineHeight: '1.5',
                }}
              >
                <div>{msg.text}</div>
                {msg.citation && (
                  <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-color)' }}>
                    <button
                      onClick={() => setActiveCodeCitation({ code: msg.citation.code, lines: msg.citation.lineRange })}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: msg.sender === 'user' ? '#fff' : 'var(--accent-color)',
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        fontSize: '11px',
                        fontWeight: 'bold',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      📄 Click to inspect citation: {msg.citation.lineRange}
                    </button>
                  </div>
                )}
              </div>
            ))}
            {isTyping && (
              <div style={{ alignSelf: 'flex-start', background: 'var(--bg-secondary)', padding: '12px', borderRadius: '12px', borderTopLeftRadius: '2px' }}>
                <span className="cursor-blink" style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Analyzing vector index spaces...</span>
              </div>
            )}
          </div>

          {/* Form */}
          <div style={{ padding: '15px', borderTop: '1px solid var(--border-color)', background: 'var(--bg-glass)' }}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendChat(chatInput);
              }}
              style={{ display: 'flex', gap: '10px' }}
            >
              <input
                type="text"
                placeholder="Ask about validation, serializers, etc..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                }}
              />
              <button
                type="submit"
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  background: 'var(--text-primary)',
                  color: 'var(--bg-primary)',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 'bold',
                  fontSize: '13px',
                }}
              >
                Send
              </button>
            </form>
          </div>
        </div>

      </div>

      {/* Citation Modal popup */}
      {activeCodeCitation && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999,
            backgroundColor: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '650px',
              backgroundColor: 'var(--card-bg)',
              borderRadius: '12px',
              border: '1px solid var(--border-color)',
              boxShadow: '0 20px 50px rgba(0,0,0,0.3)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={{ padding: '15px 20px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px' }}>📄 Code Citation Viewer — {activeCodeCitation.lines}</span>
              <button onClick={() => setActiveCodeCitation(null)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: 'var(--text-secondary)' }}>✕</button>
            </div>
            <div style={{ padding: '20px', background: '#09090b', color: '#f4f4f5', overflowX: 'auto', maxHeight: '400px' }}>
              <pre style={{ fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.6' }}>
                <code>{activeCodeCitation.code}</code>
              </pre>
            </div>
            <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setActiveCodeCitation(null)} style={{ padding: '8px 16px', background: 'var(--text-primary)', color: 'var(--bg-primary)', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', fontSize: '13px' }}>Close Viewer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
