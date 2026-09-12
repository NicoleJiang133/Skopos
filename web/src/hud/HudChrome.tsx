import type { ReactNode } from 'react'

export function Panel({
  title,
  children,
  style,
}: {
  title: string
  children: ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div className="sk-panel" style={{ padding: 14, ...style }}>
      <div
        style={{
          font: '11px var(--sk-font-mono)',
          letterSpacing: 1,
          color: 'var(--sk-text-dim)',
          marginBottom: 10,
        }}
      >
        {title.toUpperCase()}
      </div>
      {children}
    </div>
  )
}

export function CTA({
  children,
  onClick,
  tone = 'cyan',
  disabled = false,
}: {
  children: ReactNode
  onClick: () => void
  tone?: 'cyan' | 'amber'
  disabled?: boolean
}) {
  const color = tone === 'cyan' ? 'var(--sk-cyan)' : 'var(--sk-amber)'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        appearance: 'none',
        border: `1px solid ${color}`,
        background: `color-mix(in srgb, ${color} 12%, transparent)`,
        color,
        borderRadius: 'var(--sk-radius-md)',
        padding: '12px 22px',
        font: '14px var(--sk-font-display)',
        letterSpacing: 0.5,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        pointerEvents: disabled ? 'none' : undefined,
        boxShadow: tone === 'cyan' ? 'var(--sk-glow-cyan)' : 'var(--sk-glow-amber)',
        transition: 'transform var(--sk-dur-fast) var(--sk-ease)',
      }}
      onMouseDown={(e) => (e.currentTarget.style.transform = 'scale(0.97)')}
      onMouseUp={(e) => (e.currentTarget.style.transform = 'scale(1)')}
      onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
    >
      {children}
    </button>
  )
}
