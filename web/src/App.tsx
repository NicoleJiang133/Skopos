import { useEffect, useRef } from 'react'
import { GenerativeBed } from './bed/GenerativeBed'
import { Finish } from './screens/Finish'
import { Landing } from './screens/Landing'
import { LiveOps } from './screens/LiveOps'
import { Setup } from './screens/Setup'
import { useStore } from './state/store'
import type { ScreenId } from './prompts/screens'

const SCREENS: Record<ScreenId, () => React.JSX.Element> = {
  landing: Landing,
  setup: Setup,
  live: LiveOps,
  finish: Finish,
}

export default function App() {
  const screen = useStore((s) => s.screen)
  const goto = useStore((s) => s.goto)
  const live = useStore((s) => s.live)
  const setLive = useStore((s) => s.setLive)
  const hashInitialized = useRef(false)
  const Screen = SCREENS[screen]

  useEffect(() => {
    const syncHash = () => {
      if (window.location.hash === '#finish') {
        if (useStore.getState().screen !== 'finish') goto('finish')
      } else if (useStore.getState().screen === 'finish') {
        goto('landing')
      }
    }
    const initial = window.setTimeout(() => {
      hashInitialized.current = true
      syncHash()
    })
    window.addEventListener('hashchange', syncHash)
    return () => {
      window.clearTimeout(initial)
      window.removeEventListener('hashchange', syncHash)
    }
  }, [goto])

  useEffect(() => {
    if (screen === 'finish') {
      hashInitialized.current = true
      if (window.location.hash !== '#finish') window.location.hash = 'finish'
    } else if (hashInitialized.current && window.location.hash === '#finish') {
      window.history.replaceState(null, '', window.location.pathname)
    }
  }, [screen])

  return (
    <>
      <GenerativeBed />
      <div style={{ position: 'relative', zIndex: 1, height: '100%' }}>
        <header
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '14px 24px',
            font: '11px var(--sk-font-mono)',
            letterSpacing: 2,
            color: 'var(--sk-text-dim)',
            zIndex: 2,
          }}
        >
          <span style={{ color: 'var(--sk-cyan)' }}>SKOPOS</span>
          <nav style={{ display: 'flex', gap: 18 }}>
            {(['landing', 'setup', 'live'] as ScreenId[]).map((id) => (
              <button
                key={id}
                onClick={() => goto(id)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: id === screen ? 'var(--sk-text)' : 'var(--sk-text-dim)',
                  font: 'inherit',
                  letterSpacing: 'inherit',
                  cursor: 'pointer',
                  borderBottom:
                    id === screen ? '1px solid var(--sk-cyan)' : '1px solid transparent',
                  paddingBottom: 2,
                }}
              >
                {id.toUpperCase()}
              </button>
            ))}
          </nav>
          <button
            onClick={() => setLive(!live)}
            style={{
              background: 'none',
              border: `1px solid ${live ? 'var(--sk-teal)' : 'var(--sk-edge)'}`,
              color: live ? 'var(--sk-teal)' : 'var(--sk-text-dim)',
              borderRadius: 'var(--sk-radius-sm)',
              padding: '4px 10px',
              font: 'inherit',
              letterSpacing: 1,
              cursor: 'pointer',
            }}
          >
            {live ? 'VISKO LIVE' : 'VISKO OFF'}
          </button>
        </header>
        <main
          key={screen}
          style={{
            height: '100%',
            paddingTop: 48,
            boxSizing: 'border-box',
            animation: 'sk-screen-in var(--sk-dur-morph) var(--sk-ease)',
          }}
        >
          <Screen />
        </main>
      </div>
    </>
  )
}
