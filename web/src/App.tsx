import { useState } from 'react'
import { BacktestView } from './BacktestView'
import { PaperView } from './PaperView'

type Tab = 'backtest' | 'paper'

function initialTab(): Tab {
  try {
    return localStorage.getItem('tab') === 'paper' ? 'paper' : 'backtest'
  } catch {
    return 'backtest'
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>(initialTab)
  const choose = (t: Tab) => {
    setTab(t)
    try {
      localStorage.setItem('tab', t)
    } catch {
      /* Speicher nicht verfügbar */
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Hedgefund</h1>
        <nav>
          <button className={tab === 'backtest' ? 'active' : ''} onClick={() => choose('backtest')}>Backtest</button>
          <button className={tab === 'paper' ? 'active' : ''} onClick={() => choose('paper')}>Paper-Trading</button>
        </nav>
        <span className="tag">NautilusTrader</span>
      </header>
      {tab === 'backtest' ? <BacktestView /> : <PaperView />}
    </div>
  )
}
