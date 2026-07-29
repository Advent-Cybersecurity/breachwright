import { useRef, useEffect, useState } from 'react';

const NODE_COLORS = {
  user: { bg: '#3b82f620', border: '#3b82f6', text: '#3b82f6', icon: '\u{1F464}' },
  computer: { bg: '#22c55e20', border: '#22c55e', text: '#22c55e', icon: '\u{1F5A5}' },
  group: { bg: '#f9731620', border: '#f97316', text: '#f97316', icon: '\u{1F465}' },
  domain: { bg: '#dc262620', border: '#dc2626', text: '#dc2626', icon: '\u{1F3F0}' },
  ou: { bg: '#8b5cf620', border: '#8b5cf6', text: '#8b5cf6', icon: '\u{1F4C1}' },
  gpo: { bg: '#06b6d420', border: '#06b6d4', text: '#06b6d4', icon: '\u{1F4DC}' },
};

const RISK_COLORS = {
  critical: '#dc2626',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
};

export default function ADPathGraph({ path }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [hoveredNode, setHoveredNode] = useState(null);

  const nodes = path.path_nodes || [];
  if (nodes.length === 0) return null;

  const NODE_W = 140;
  const NODE_H = 56;
  const GAP_X = 80;
  const GAP_Y = 20;
  const PADDING = 30;

  const totalW = nodes.length * NODE_W + (nodes.length - 1) * GAP_X + PADDING * 2;
  const totalH = NODE_H + PADDING * 2 + 30; // extra for technique labels

  return (
    <div ref={containerRef} className="overflow-x-auto rounded mb-3 p-4"
      style={{ backgroundColor: 'var(--bg-900)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-1 mb-3">
        <span className="text-[10px] font-mono themed-text-muted uppercase tracking-wider">
          {path.name}
        </span>
        <span className="text-[10px] themed-text-muted">
          // {nodes.length} steps
        </span>
      </div>

      <svg width={totalW} height={totalH} style={{ minWidth: totalW }}>
        {/* Connection lines and technique labels */}
        {nodes.map((node, i) => {
          if (i === nodes.length - 1) return null;
          const x1 = PADDING + i * (NODE_W + GAP_X) + NODE_W;
          const x2 = PADDING + (i + 1) * (NODE_W + GAP_X);
          const y = PADDING + NODE_H / 2;
          const nextNode = nodes[i + 1];
          const technique = nextNode?.technique?.split('(')[0]?.trim() || '';

          return (
            <g key={`link-${i}`}>
              {/* Line */}
              <line
                x1={x1} y1={y} x2={x2} y2={y}
                stroke={RISK_COLORS[path.risk_level] || '#6b7280'}
                strokeWidth={2}
                strokeDasharray="6,3"
                opacity={0.5}
              />
              {/* Arrow */}
              <polygon
                points={`${x2-8},${y-5} ${x2},${y} ${x2-8},${y+5}`}
                fill={RISK_COLORS[path.risk_level] || '#6b7280'}
                opacity={0.6}
              />
              {/* Technique label */}
              {technique && (
                <text
                  x={(x1 + x2) / 2}
                  y={y + NODE_H / 2 + 14}
                  textAnchor="middle"
                  fill="var(--text-muted)"
                  fontSize="9"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {technique.length > 18 ? technique.substring(0, 16) + '..' : technique}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((node, i) => {
          const x = PADDING + i * (NODE_W + GAP_X);
          const y = PADDING;
          const colors = NODE_COLORS[node.type] || NODE_COLORS.user;
          const isHovered = hoveredNode === i;
          const shortName = (node.name || '').split('@')[0];
          const displayName = shortName.length > 14 ? shortName.substring(0, 12) + '..' : shortName;

          return (
            <g key={`node-${i}`}
              onMouseEnter={() => setHoveredNode(i)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{ cursor: 'pointer' }}
            >
              {/* Node background */}
              <rect
                x={x} y={y}
                width={NODE_W} height={NODE_H}
                rx={8} ry={8}
                fill={colors.bg}
                stroke={colors.border}
                strokeWidth={isHovered ? 2.5 : 1.5}
                opacity={isHovered ? 1 : 0.9}
              />

              {/* Step number circle */}
              <circle
                cx={x + 18} cy={y + NODE_H / 2}
                r={10}
                fill={colors.border + '30'}
                stroke={colors.border}
                strokeWidth={1}
              />
              <text
                x={x + 18} y={y + NODE_H / 2 + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={colors.text}
                fontSize="10"
                fontWeight="bold"
                fontFamily="'JetBrains Mono', monospace"
              >
                {i + 1}
              </text>

              {/* Type label */}
              <text
                x={x + 36} y={y + 18}
                fill={colors.text}
                fontSize="9"
                fontFamily="'JetBrains Mono', monospace"
                opacity={0.7}
                textTransform="uppercase"
              >
                {(node.type || '').toUpperCase()}
              </text>

              {/* Name */}
              <text
                x={x + 36} y={y + 36}
                fill="var(--text-primary)"
                fontSize="11"
                fontWeight="600"
                fontFamily="'IBM Plex Sans', sans-serif"
              >
                {displayName}
              </text>

              {/* Hover tooltip */}
              {isHovered && (
                <g>
                  <rect
                    x={x} y={y - 32}
                    width={Math.max(node.name?.length * 6.5 + 16, 120)}
                    height={24}
                    rx={4}
                    fill="var(--bg-700)"
                    stroke="var(--border)"
                    strokeWidth={1}
                  />
                  <text
                    x={x + 8} y={y - 16}
                    fill="var(--text-primary)"
                    fontSize="10"
                    fontFamily="'JetBrains Mono', monospace"
                  >
                    {node.name}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
