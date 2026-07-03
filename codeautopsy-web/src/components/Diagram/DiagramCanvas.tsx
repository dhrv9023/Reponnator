import { useState, useEffect, useRef, useCallback } from 'react';

export interface CustomNode {
  id: string;
  label: string;
  type: string;
  complexity: number;
  lines: string;
  file: string;
  role: string;
  functionCount?: number;
  classCount?: number;
  callCount?: number;
}

export interface CustomLink {
  source: string;
  target: string;
}

interface DiagramCanvasProps {
  nodes: CustomNode[];
  links: CustomLink[];
  nodeCoords: Record<string, { x: number; y: number }>;
  highlightedElement: string | null;
  setHighlightedElement: (id: string | null) => void;
  selectedNode: CustomNode | null;
  setSelectedNode: (node: CustomNode | null) => void;
}

// ─── Design tokens ────────────────────────────────────────────────────────────
const CARD_W = 160;
const CARD_H = 80;
const CARD_R = 12; // border-radius

const TIER_CONFIG: Record<string, {
  bg: string; border: string; glow: string; badge: string; badgeText: string; icon: string; label: string;
}> = {
  entry_point: {
    bg: '#071f10', border: '#22c55e', glow: '#16a34a55',
    badge: '#14532d', badgeText: '#4ade80', icon: '▶', label: 'Entry Point',
  },
  core_utility: {
    bg: '#0f0f2e', border: '#818cf8', glow: '#6366f144',
    badge: '#1e1b4b', badgeText: '#a5b4fc', icon: '◆', label: 'Core Utility',
  },
  module: {
    bg: '#0c1625', border: '#38bdf8', glow: '#0284c733',
    badge: '#0c2233', badgeText: '#7dd3fc', icon: 'M', label: 'Module',
  },
};

function getTier(type: string) {
  return TIER_CONFIG[type] ?? TIER_CONFIG.module;
}

// Smooth bezier path between two card centres
function edgePath(
  sx: number, sy: number,
  tx: number, ty: number,
): string {
  // Exit from bottom-centre of source card, enter top-centre of target card
  const x1 = sx;
  const y1 = sy + CARD_H / 2;
  const x2 = tx;
  const y2 = ty - CARD_H / 2;

  const cpY = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${cpY}, ${x2} ${cpY}, ${x2} ${y2}`;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function DiagramCanvas({
  nodes, links, nodeCoords,
  highlightedElement, setHighlightedElement,
  selectedNode, setSelectedNode,
}: DiagramCanvasProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [zoom, setZoom] = useState(0.85);
  const [pan, setPan] = useState({ x: 40, y: 20 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });

  // ── Pan / zoom ──
  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as Element).closest('.node-card')) return;
    setIsPanning(true);
    panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isPanning) return;
    setPan({ x: e.clientX - panStartRef.current.x, y: e.clientY - panStartRef.current.y });
  };
  const handleMouseUp = () => setIsPanning(false);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    setZoom(z => Math.max(0.2, Math.min(3, z - e.deltaY * 0.001)));
  }, []);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  const handleZoom = (d: 'in' | 'out' | 'reset') => {
    if (d === 'in') setZoom(z => Math.min(3, z + 0.15));
    else if (d === 'out') setZoom(z => Math.max(0.2, z - 0.15));
    else { setZoom(0.85); setPan({ x: 40, y: 20 }); }
  };

  // ── Adjacency for hover highlight ──
  const activeId = hoveredNode ?? highlightedElement;
  const adjacentIds = new Set<string>();
  if (activeId) {
    links.forEach(l => {
      if (l.source === activeId) adjacentIds.add(l.target);
      if (l.target === activeId) adjacentIds.add(l.source);
    });
    adjacentIds.add(activeId);
  }

  // ── Compute canvas bounds for swimlane zones ──
  const tierBounds: Record<string, { minY: number; maxY: number }> = {};
  nodes.forEach(n => {
    const c = nodeCoords[n.id];
    if (!c) return;
    const t = n.type in TIER_CONFIG ? n.type : 'module';
    if (!tierBounds[t]) tierBounds[t] = { minY: c.y, maxY: c.y };
    tierBounds[t].minY = Math.min(tierBounds[t].minY, c.y);
    tierBounds[t].maxY = Math.max(tierBounds[t].maxY, c.y);
  });

  const allX = nodes.map(n => nodeCoords[n.id]?.x ?? 0);
  const canvasW = Math.max(...allX) + CARD_W / 2 + 80;

  return (
    <div style={{
      flex: 1, position: 'relative',
      background: '#050c18',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* ── Dot-grid CSS background ── */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: 'radial-gradient(circle, rgba(56,189,248,0.08) 1px, transparent 1px)',
        backgroundSize: '28px 28px',
      }} />

      {/* ── Top controls bar ── */}
      <div style={{
        position: 'absolute', top: 14, left: 14, zIndex: 20,
        display: 'flex', gap: 8, alignItems: 'center',
      }}>
        {(['in', 'out', 'reset'] as const).map(d => (
          <button key={d} onClick={() => handleZoom(d)} style={{
            padding: '5px 13px',
            background: 'rgba(255,255,255,0.05)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255,255,255,0.10)',
            borderRadius: 8, cursor: 'pointer', fontSize: 12, color: '#e2e8f0',
          }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.10)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
          >
            {d === 'in' ? '+ Zoom' : d === 'out' ? '– Zoom' : '↺ Reset'}
          </button>
        ))}
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', marginLeft: 4 }}>
          Scroll · Drag to pan
        </span>
      </div>

      {/* ── Search bar ── */}
      <div style={{ position: 'absolute', top: 14, right: 14, zIndex: 20 }}>
        <input
          type="text"
          placeholder="🔍  Search files…"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{
            padding: '6px 14px',
            background: 'rgba(255,255,255,0.05)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255,255,255,0.10)',
            borderRadius: 8, fontSize: 13, color: '#e2e8f0', outline: 'none', width: 200,
          }}
        />
      </div>

      {/* ── Node / edge count badge ── */}
      <div style={{
        position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)',
        zIndex: 20,
        background: 'rgba(5,12,24,0.8)', backdropFilter: 'blur(8px)',
        border: '1px solid rgba(255,255,255,0.07)', borderRadius: 999,
        padding: '4px 16px', fontSize: 11, color: 'rgba(255,255,255,0.45)',
        display: 'flex', gap: 16,
      }}>
        <span><strong style={{ color: '#38bdf8' }}>{nodes.length}</strong> nodes</span>
        <span><strong style={{ color: '#818cf8' }}>{links.length}</strong> edges</span>
      </div>

      {/* ── SVG Canvas ── */}
      <svg
        ref={svgRef}
        width="100%" height="100%"
        style={{ cursor: isPanning ? 'grabbing' : 'grab', flex: 1, position: 'relative', zIndex: 1 }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <defs>
          {/* Animated dash flow */}
          <style>{`
            @keyframes dash-flow { from { stroke-dashoffset: 20; } to { stroke-dashoffset: 0; } }
            @keyframes pulse-ring { 0%,100% { opacity:0.6; r:48; } 50% { opacity:1; r:56; } }
            .edge-animated { animation: dash-flow 1.2s linear infinite; }
            .pulse-ring { animation: pulse-ring 2s ease-in-out infinite; }
          `}</style>

          {/* Edge gradient */}
          <linearGradient id="edge-grad-green" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#22c55e" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#818cf8" stopOpacity="0.5" />
          </linearGradient>
          <linearGradient id="edge-grad-blue" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#818cf8" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.5" />
          </linearGradient>

          {/* Glow filter */}
          <filter id="glow-green" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feFlood floodColor="#22c55e" floodOpacity="0.5" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge><feMergeNode in="glow" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="glow-purple" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feFlood floodColor="#818cf8" floodOpacity="0.4" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge><feMergeNode in="glow" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="card-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="8" floodColor="#000" floodOpacity="0.5" />
          </filter>

          {/* Arrow markers */}
          <marker id="arr-default" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="rgba(99,102,241,0.5)" />
          </marker>
          <marker id="arr-active" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#818cf8" />
          </marker>
          <marker id="arr-green" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#22c55e" />
          </marker>
        </defs>

        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>

          {/* ── Swimlane zone backgrounds ── */}
          {(['entry_point', 'core_utility', 'module'] as const).map(tier => {
            const b = tierBounds[tier];
            const cfg = TIER_CONFIG[tier];
            if (!b) return null;
            return (
              <rect
                key={tier}
                x={-60}
                y={b.minY - CARD_H / 2 - 24}
                width={canvasW + 120}
                height={b.maxY - b.minY + CARD_H + 48}
                rx={16}
                fill={cfg.bg}
                opacity={0.35}
                stroke={cfg.border}
                strokeWidth={1}
                strokeOpacity={0.15}
              />
            );
          })}

          {/* ── Tier label badges (left margin) ── */}
          {(['entry_point', 'core_utility', 'module'] as const).map(tier => {
            const b = tierBounds[tier];
            const cfg = TIER_CONFIG[tier];
            if (!b) return null;
            const midY = (b.minY + b.maxY) / 2;
            return (
              <g key={`label-${tier}`} transform={`translate(-40, ${midY})`}>
                <text
                  textAnchor="middle"
                  style={{ fontSize: 10, fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.08em' }}
                  fill={cfg.border}
                  opacity={0.55}
                  transform="rotate(-90)"
                >
                  {cfg.label.toUpperCase()}
                </text>
              </g>
            );
          })}

          {/* ── Edges ── */}
          {links.map((link, idx) => {
            const s = nodeCoords[link.source];
            const t = nodeCoords[link.target];
            if (!s || !t) return null;

            const isActive = activeId
              ? (link.source === activeId || link.target === activeId)
              : false;
            const opacity = activeId ? (isActive ? 1 : 0.05) : 0.4;
            const d = edgePath(s.x, s.y, t.x, t.y);

            // Source node type determines colour
            const srcNode = nodes.find(n => n.id === link.source);
            const isFromEntry = srcNode?.type === 'entry_point';

            return (
              <g key={idx} style={{ opacity, transition: 'opacity 0.3s' }}>
                <path
                  d={d} fill="none"
                  stroke={isActive ? (isFromEntry ? '#22c55e' : '#818cf8') : 'rgba(99,102,241,0.35)'}
                  strokeWidth={isActive ? 2.5 : 1.5}
                  strokeLinecap="round"
                  markerEnd={isActive ? (isFromEntry ? 'url(#arr-green)' : 'url(#arr-active)') : 'url(#arr-default)'}
                  style={{ transition: 'stroke 0.3s, stroke-width 0.3s' }}
                />
                {isActive && (
                  <path
                    d={d} fill="none"
                    stroke={isFromEntry ? '#4ade80' : '#c7d2fe'}
                    strokeWidth="1.5"
                    strokeDasharray="6 6"
                    className="edge-animated"
                    strokeLinecap="round"
                  />
                )}
              </g>
            );
          })}

          {/* ── Nodes (card-style) ── */}
          {nodes.map(node => {
            const c = nodeCoords[node.id];
            if (!c) return null;
            const { x, y } = c;
            const cfg = getTier(node.type);

            const isSelected = selectedNode?.id === node.id;
            const isHovered = hoveredNode === node.id;
            const isSearchMatch = searchQuery.trim() !== '' &&
              node.label.toLowerCase().includes(searchQuery.toLowerCase());
            const isDimmed = !!(activeId && !adjacentIds.has(node.id));
            const isHighlighted = isSelected || isHovered || isSearchMatch;

            const cardX = x - CARD_W / 2;
            const cardY = y - CARD_H / 2;

            return (
              <g
                key={node.id}
                className="node-card"
                transform={`translate(${cardX}, ${cardY})`}
                style={{
                  cursor: 'pointer',
                  opacity: isDimmed ? 0.1 : 1,
                  transition: 'opacity 0.25s',
                  filter: isHighlighted && node.type === 'entry_point' ? 'url(#glow-green)'
                    : isHighlighted && node.type === 'core_utility' ? 'url(#glow-purple)'
                    : 'url(#card-shadow)',
                }}
                onClick={() => setSelectedNode(isSelected ? null : node)}
                onMouseEnter={() => { setHoveredNode(node.id); setHighlightedElement(node.id); }}
                onMouseLeave={() => { setHoveredNode(null); setHighlightedElement(null); }}
              >
                {/* Outer glow border when highlighted */}
                {isHighlighted && (
                  <rect
                    x={-3} y={-3}
                    width={CARD_W + 6} height={CARD_H + 6}
                    rx={CARD_R + 3}
                    fill="none"
                    stroke={cfg.border}
                    strokeWidth={2}
                    opacity={0.7}
                  />
                )}

                {/* Pulsing ring for entry points */}
                {node.type === 'entry_point' && (
                  <rect
                    x={-8} y={-8}
                    width={CARD_W + 16} height={CARD_H + 16}
                    rx={CARD_R + 8}
                    fill="none"
                    stroke="#22c55e"
                    strokeWidth={1.5}
                    opacity={isHovered ? 0.5 : 0.2}
                    style={{ transition: 'opacity 0.3s' }}
                  />
                )}

                {/* Card body */}
                <rect
                  x={0} y={0}
                  width={CARD_W} height={CARD_H}
                  rx={CARD_R}
                  fill={cfg.bg}
                  stroke={isHighlighted ? cfg.border : `${cfg.border}55`}
                  strokeWidth={isHighlighted ? 2 : 1}
                  style={{ transition: 'stroke-width 0.2s, stroke 0.2s' }}
                />

                {/* Top accent bar */}
                <rect
                  x={0} y={0}
                  width={CARD_W} height={3}
                  rx={CARD_R}
                  fill={cfg.border}
                  opacity={0.8}
                />

                {/* Icon + type badge */}
                <rect x={8} y={10} width={36} height={16} rx={4} fill={cfg.badge} />
                <text x={26} y={22} textAnchor="middle"
                  fill={cfg.badgeText}
                  style={{ fontSize: 9, fontWeight: 700, fontFamily: 'monospace', pointerEvents: 'none' }}
                >
                  {cfg.icon} {cfg.label.split(' ')[0]}
                </text>

                {/* File label */}
                <text
                  x={CARD_W / 2} y={44}
                  textAnchor="middle"
                  fill="#f1f5f9"
                  style={{
                    fontSize: node.label.length > 16 ? 11 : 13,
                    fontWeight: 700,
                    fontFamily: 'system-ui, sans-serif',
                    pointerEvents: 'none',
                  }}
                >
                  {node.label.length > 20 ? node.label.slice(0, 18) + '…' : node.label}
                </text>

                {/* Stats row */}
                <text x={10} y={64} fill="rgba(255,255,255,0.35)"
                  style={{ fontSize: 9, fontFamily: 'monospace', pointerEvents: 'none' }}
                >
                  {`ƒ ${node.functionCount ?? 0}  C ${node.classCount ?? 0}  ↙ ${node.callCount ?? 0}`}
                </text>

                {/* Search highlight indicator */}
                {isSearchMatch && (
                  <rect x={CARD_W - 18} y={8} width={10} height={10} rx={5}
                    fill="#fbbf24" opacity={0.9}
                  />
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* ── Selected Node Inspector Drawer ── */}
      {selectedNode && (() => {
        const cfg = getTier(selectedNode.type);
        return (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            background: 'rgba(5,12,24,0.97)',
            backdropFilter: 'blur(20px)',
            borderTop: `1px solid ${cfg.border}50`,
            padding: '16px 24px',
            zIndex: 30,
            display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
            boxShadow: `0 -12px 40px rgba(0,0,0,0.5), 0 -1px 0 ${cfg.border}30`,
          }}>
            <div style={{ flex: 1, marginRight: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <span style={{
                  padding: '2px 10px', borderRadius: 999,
                  background: cfg.badge, color: cfg.badgeText,
                  fontSize: 10, fontWeight: 700, fontFamily: 'monospace',
                }}>
                  {cfg.icon} {cfg.label}
                </span>
                <h4 style={{ fontSize: 15, fontWeight: 700, color: '#f1f5f9', margin: 0 }}>
                  {selectedNode.label}
                </h4>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: 'rgba(251,191,36,0.12)', color: '#fbbf24', fontWeight: 600 }}>
                  complexity {selectedNode.complexity}
                </span>
              </div>
              <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 8px', lineHeight: 1.55 }}>
                {selectedNode.role}
              </p>
              <div style={{ display: 'flex', gap: 20, fontSize: 12, color: '#475569' }}>
                <span>ƒ Functions: <strong style={{ color: cfg.badgeText }}>{selectedNode.functionCount ?? 0}</strong></span>
                <span>C Classes: <strong style={{ color: cfg.badgeText }}>{selectedNode.classCount ?? 0}</strong></span>
                <span>↙ Called: <strong style={{ color: cfg.badgeText }}>{selectedNode.callCount ?? 0}×</strong></span>
                <span>File: <code style={{ color: cfg.border }}>{selectedNode.file}</code></span>
              </div>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              style={{
                padding: '6px 14px',
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8, cursor: 'pointer', fontSize: 12, color: '#94a3b8', flexShrink: 0,
              }}
            >
              ✕ Close
            </button>
          </div>
        );
      })()}
    </div>
  );
}
