import { useCallback, useEffect, useMemo, useState } from 'react'
import { enterBackend } from '../backend/handoff'
import {
  promptFor,
  type ActionChoice,
  type SceneObjectLite,
  type Strategy,
} from '../play/actionPrompts'
import { tagPosition } from '../play/layout'
import { useStore } from '../state/store'

const DEMO_OBJECTS: SceneObjectLite[] = [
  { id: 't1', label: 'coffee table', material: 'oak', hazards: [] },
  { id: 'm1', label: 'mug', material: 'ceramic', hazards: ['fragile'] },
  { id: 's1', label: 'sofa', material: 'fabric', hazards: [] },
  {
    id: 'r1',
    label: 'rug',
    material: 'wool',
    hazards: ['trip', 'low_contrast'],
  },
  { id: 'c1', label: 'cable', material: 'rubber', hazards: ['trip'] },
  { id: 'd1', label: 'glass door', material: 'glass', hazards: ['reflective'] },
  {
    id: 'p1',
    label: 'plant pot',
    material: 'terracotta',
    hazards: ['fragile'],
  },
  { id: 'w1', label: 'water bowl', material: 'plastic', hazards: ['spill'] },
  { id: 'cat1', label: 'cat', material: '—', hazards: ['moving'] },
]

const STRATEGIES: { id: Strategy; label: string }[] = [
  { id: 'direct', label: 'Direct' },
  { id: 'careful', label: 'Careful' },
  { id: 'arc', label: 'Wide berth' },
  { id: 'ask', label: 'Ask a human' },
  { id: 'skip', label: 'Leave it' },
]

type Phase = 'walking' | 'prompt' | 'confirmed'

const initialCounts = (): Record<Strategy, number> => ({
  direct: 0,
  careful: 0,
  arc: 0,
  ask: 0,
  skip: 0,
})

export function Play() {
  const venuePhoto = useStore((s) => s.venuePhoto)
  const scan = useStore((s) => s.scan)
  const goto = useStore((s) => s.goto)
  const logInteraction = useStore((s) => s.logInteraction)
  const pushEvent = useStore((s) => s.pushEvent)
  const exportInteractions = useStore((s) => s.exportInteractions)
  const objects = scan?.objects.length ? scan.objects : DEMO_OBJECTS
  const [index, setIndex] = useState(0)
  const [phase, setPhase] = useState<Phase>('walking')
  const [promptShownAt, setPromptShownAt] = useState(0)
  const [confirmation, setConfirmation] = useState('')
  const [counts, setCounts] = useState<Record<Strategy, number>>(initialCounts)
  const currentObject = objects[index]
  const currentPrompt = useMemo(
    () => (currentObject ? promptFor(currentObject) : null),
    [currentObject],
  )
  const hasMug = objects.some((object) => object.label.toLowerCase().includes('mug'))
  const isSummary = index >= objects.length

  useEffect(() => {
    if (isSummary) return
    const timer = window.setTimeout(() => {
      setPromptShownAt(performance.now())
      setPhase('prompt')
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [index, isSummary])

  const choose = useCallback(
    (choice: ActionChoice) => {
      if (phase !== 'prompt' || !currentObject) return
      logInteraction('action', {
        object: currentObject.label,
        objectId: currentObject.id,
        choice: choice.id,
        strategy: choice.strategy,
        ms: Math.round(performance.now() - promptShownAt),
      })
      pushEvent(`${currentObject.label} — ${choice.label}`, 'action')
      setCounts((previous) => ({
        ...previous,
        [choice.strategy]: previous[choice.strategy] + 1,
      }))
      setConfirmation(`✓ ${choice.label}`)
      setPhase('confirmed')
      window.setTimeout(() => {
        setPhase('walking')
        setConfirmation('')
        setIndex((previous) => previous + 1)
      }, 700)
    },
    [currentObject, logInteraction, phase, promptShownAt, pushEvent],
  )

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (phase !== 'prompt' || event.target instanceof HTMLInputElement) return
      const choice = Number(event.key)
      if (!currentPrompt || choice < 1 || choice > currentPrompt.choices.length) return
      event.preventDefault()
      choose(currentPrompt.choices[choice - 1])
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [choose, currentPrompt, phase])

  const reset = () => {
    setIndex(0)
    setPhase('walking')
    setPromptShownAt(0)
    setConfirmation('')
    setCounts(initialCounts())
  }

  return (
    <div style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
      {venuePhoto && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background:
              'radial-gradient(ellipse 60% 55% at 50% 55%, rgba(20,17,13,0.55), rgba(20,17,13,0.15) 70%, rgba(20,17,13,0.6))',
            transform: phase === 'walking' ? 'scale(1.03)' : 'scale(1)',
            transition: 'transform 1200ms var(--sk-ease)',
            zIndex: 1,
            pointerEvents: 'none',
          }}
        />
      )}

      <button onClick={() => goto('landing')} style={backLink}>
        back to landing
      </button>

      {!isSummary && currentObject && phase === 'walking' && (
        <>
          <div style={hotspotPosition(index, objects.length)}>
            <span style={ping} />
            <span style={dot} />
          </div>
          <div style={walkingCaption}>approaching the {currentObject.label}…</div>
        </>
      )}

      {!isSummary && (
        <div className="sk-panel" style={hud}>
          <div style={hudLabel}>YOU ARE THE ROBOT</div>
          <div style={taskLine}>
            Task: {hasMug ? 'fetch the mug from the table' : 'explore your venue'}
          </div>
          <div
            style={progress}
          >{`${Math.min(index + 1, objects.length)} / ${objects.length} objects`}</div>
        </div>
      )}

      {isSummary ? (
        <Summary
          counts={counts}
          onPlayAgain={reset}
          onEnter={enterBackend}
          onExport={exportInteractions}
        />
      ) : (
        phase !== 'walking' &&
        currentObject &&
        currentPrompt && (
          <div className="sk-panel" style={promptCard}>
            {phase === 'confirmed' ? (
              <div style={confirmationStyle}>{confirmation}</div>
            ) : (
              <>
                <div style={situation}>{currentPrompt.situation}</div>
                <div style={question}>{currentPrompt.question}</div>
                <div style={choices}>
                  {currentPrompt.choices.map((choice, choiceIndex) => (
                    <button
                      key={choice.id}
                      onClick={() => choose(choice)}
                      onMouseEnter={(event) => {
                        event.currentTarget.style.borderColor = 'var(--sk-cyan)'
                      }}
                      onMouseLeave={(event) => {
                        event.currentTarget.style.borderColor = 'var(--sk-edge)'
                      }}
                      style={choiceButton}
                    >
                      <span style={choiceNumber}>{choiceIndex + 1}</span>
                      <span>
                        <span style={choiceLabel}>{choice.label}</span>
                        <span style={choiceHint}>{choice.hint}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )
      )}
    </div>
  )
}

function Summary({
  counts,
  onPlayAgain,
  onEnter,
  onExport,
}: {
  counts: Record<Strategy, number>
  onPlayAgain: () => void
  onEnter: () => void
  onExport: () => void
}) {
  const max = Math.max(1, ...Object.values(counts))
  return (
    <div className="sk-panel" style={summaryCard}>
      <div style={summaryTitle}>Your robot&apos;s style</div>
      <div style={bars}>
        {STRATEGIES.map((strategy) => (
          <div key={strategy.id} style={barRow}>
            <div style={barLabel}>
              <span>{strategy.label}</span>
              <span>{counts[strategy.id]}</span>
            </div>
            <div style={barTrack}>
              <div
                style={{
                  ...barFill,
                  width: `${(counts[strategy.id] / max) * 100}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div style={summaryActions}>
        <button onClick={onEnter} style={summaryPrimary}>
          Enter the live venue
        </button>
        <button onClick={onPlayAgain} style={summarySecondary}>
          Play again
        </button>
        <button onClick={onExport} style={exportButton}>
          Export ground truth
        </button>
      </div>
    </div>
  )
}

function hotspotPosition(index: number, total: number) {
  return {
    position: 'absolute' as const,
    ...tagPosition(index, total),
    zIndex: 2,
  }
}

const backLink = {
  position: 'absolute' as const,
  top: 18,
  right: 24,
  border: 0,
  padding: 0,
  background: 'transparent',
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
  textDecoration: 'underline',
  cursor: 'pointer',
  zIndex: 4,
}
const hud = {
  position: 'absolute' as const,
  left: 20,
  bottom: 20,
  zIndex: 3,
  maxWidth: 320,
  padding: 14,
}
const hudLabel = {
  font: '11px var(--sk-font-mono)',
  letterSpacing: 2,
  color: 'var(--sk-cyan)',
}
const taskLine = {
  marginTop: 10,
  color: 'var(--sk-text)',
  font: '16px var(--sk-font-display)',
}
const progress = {
  marginTop: 8,
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const walkingCaption = {
  position: 'absolute' as const,
  left: '50%',
  top: '43%',
  transform: 'translate(-50%, -50%)',
  color: 'var(--sk-text)',
  font: '11px var(--sk-font-mono)',
  letterSpacing: 0.5,
  zIndex: 3,
  whiteSpace: 'nowrap',
}
const ping = {
  position: 'absolute' as const,
  width: 14,
  height: 14,
  borderRadius: '50%',
  border: '1px solid var(--sk-cyan)',
  animation: 'sk-ping 1.6s var(--sk-ease) infinite',
}
const dot = {
  position: 'absolute' as const,
  width: 8,
  height: 8,
  borderRadius: '50%',
  background: 'var(--sk-cyan)',
  boxShadow: 'var(--sk-glow-cyan)',
  transform: 'translate(-50%, -50%)',
}
const promptCard = {
  position: 'absolute' as const,
  left: '50%',
  bottom: '9%',
  transform: 'translateX(-50%)',
  width: 'min(520px, calc(100% - 40px))',
  padding: 18,
  zIndex: 4,
  animation: 'sk-rise 420ms var(--sk-ease) both',
}
const situation = {
  color: 'var(--sk-text)',
  font: '18px var(--sk-font-display)',
  lineHeight: 1.2,
}
const question = {
  marginTop: 8,
  color: 'var(--sk-text-dim)',
  font: '13px var(--sk-font-display)',
}
const choices = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 7,
  marginTop: 16,
}
const choiceButton = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  width: '100%',
  border: '1px solid var(--sk-edge)',
  background: 'color-mix(in srgb, var(--sk-cyan) 4%, transparent)',
  color: 'var(--sk-text)',
  padding: '9px 10px',
  textAlign: 'left' as const,
  cursor: 'pointer',
  font: 'inherit',
}
const choiceNumber = {
  minWidth: 16,
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const choiceLabel = {
  display: 'block',
  font: '14px var(--sk-font-display)',
}
const choiceHint = {
  display: 'block',
  marginTop: 3,
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const confirmationStyle = {
  color: 'var(--sk-cyan)',
  font: '16px var(--sk-font-display)',
  textAlign: 'center' as const,
  padding: '20px 0',
}
const summaryCard = {
  position: 'absolute' as const,
  left: '50%',
  top: '50%',
  transform: 'translate(-50%, -50%)',
  width: 'min(520px, calc(100% - 40px))',
  padding: 20,
  zIndex: 4,
  animation: 'sk-rise 420ms var(--sk-ease) both',
}
const summaryTitle = {
  color: 'var(--sk-text)',
  font: '22px var(--sk-font-display)',
}
const bars = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 10,
  marginTop: 18,
}
const barRow = { display: 'flex', flexDirection: 'column' as const, gap: 4 }
const barLabel = {
  display: 'flex',
  justifyContent: 'space-between',
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const barTrack = {
  height: 5,
  background: 'rgba(242,198,109,0.12)',
  overflow: 'hidden' as const,
}
const barFill = {
  height: '100%',
  background: 'var(--sk-cyan)',
  transition: 'width 300ms var(--sk-ease)',
}
const summaryActions = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 8,
  marginTop: 20,
}
const summaryPrimary = {
  border: '1px solid var(--sk-cyan)',
  background: 'color-mix(in srgb, var(--sk-cyan) 12%, transparent)',
  color: 'var(--sk-cyan)',
  padding: '11px 14px',
  font: '14px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
const summarySecondary = {
  border: '1px solid var(--sk-edge)',
  background: 'transparent',
  color: 'var(--sk-text)',
  padding: '10px 14px',
  font: '13px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
const exportButton = {
  border: 0,
  background: 'transparent',
  color: 'var(--sk-text-dim)',
  padding: '4px 0',
  font: '11px var(--sk-font-mono)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
