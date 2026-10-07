import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, errMsg, fmtTime, IB_INTERVALS, INTERVALS, type PaperParams, type PaperStatus, type Source } from './api'
import { PriceChart } from './PriceChart'

const DEFAULTS: Record<Source, PaperParams> = {
  binance: { venue: 'binance', symbol: 'BTCUSDT', interval: '1m', fast_ema_period: 10, slow_ema_period: 20, trade_size: '0.001' },
  ib: { venue: 'ib', symbol: 'AAPL.NASDAQ', interval: '1m', fast_ema_period: 10, slow_ema_period: 20, trade_size: '1' },
}
const ENV_LABEL: Record<Source, string> = { binance: 'BINANCE SPOT TESTNET', ib: 'INTERACTIVE BROKERS PAPER' }

export function PaperView() {
  const [params, setParams] = useState<PaperParams>(DEFAULTS.binance)
  const [status, setStatus] = useState<PaperStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const tick = () => api.paper().then((s) => {
      if (!alive) return
      setStatus(s)
      if (s.running && s.params) setParams(s.params)
    }).catch(() => {})
    tick()
    const id = setInterval(tick, 3000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const set = <K extends keyof PaperParams>(k: K, v: PaperParams[K]) => setParams((p) => ({ ...p, [k]: v }))
  const running = status?.running ?? false
  const state = status?.state
  const waitingLong = running && !state && status?.started != null && Date.now() / 1000 - status.started > 30

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setStatus(running ? await api.paperStop() : await api.paperStart(params))
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  const trades = useMemo(
    () => (state?.orders ?? []).filter((o) => o.filled > 0).map((o) => ({ time: o.time, side: o.side })),
    [state],
  )
  const bars = useMemo(() => state?.bars ?? [], [state])

  return (
    <>
      <aside>
        <form onSubmit={submit}>
          <h2>Paper-Trading</h2>
          <p className="badge-line">
            <span className={`badge ${running ? 'live' : ''}`}>{running ? 'läuft' : 'gestoppt'}</span>
            <span className="muted">{running ? status?.environment : ENV_LABEL[params.venue]} · Spielgeld</span>
          </p>
          <label>
            Handelsplatz
            <select value={params.venue} disabled={running} onChange={(e) => setParams(DEFAULTS[e.target.value as Source])}>
              <option value="binance">Binance Testnet (Krypto)</option>
              <option value="ib">Interactive Brokers Paper (Aktien/ETFs)</option>
            </select>
          </label>
          <div className="row">
            <label>
              {params.venue === 'ib' ? 'Symbol.Börse' : 'Symbol'}
              <input value={params.symbol} disabled={running} onChange={(e) => set('symbol', e.target.value.toUpperCase())} />
            </label>
            <label>
              Intervall
              <select value={params.interval} disabled={running} onChange={(e) => set('interval', e.target.value)}>
                {(params.venue === 'ib' ? IB_INTERVALS : INTERVALS).map((i) => <option key={i}>{i}</option>)}
              </select>
            </label>
          </div>
          <div className="row">
            <label>
              Schnelle EMA
              <input type="number" min={2} max={200} value={params.fast_ema_period} disabled={running}
                onChange={(e) => set('fast_ema_period', Number(e.target.value))} />
            </label>
            <label>
              Langsame EMA
              <input type="number" min={3} max={500} value={params.slow_ema_period} disabled={running}
                onChange={(e) => set('slow_ema_period', Number(e.target.value))} />
            </label>
          </div>
          <label>
            Ordergröße{params.venue === 'ib' ? ' (Stück)' : ''}
            <input type="text" inputMode="decimal" value={params.trade_size} disabled={running}
              onChange={(e) => set('trade_size', e.target.value)} />
          </label>
          <button type="submit" className={running ? 'danger' : ''} disabled={busy}>
            {busy ? '…' : running ? 'Stoppen' : 'Paper-Trading starten'}
          </button>
          {error && <p className="error">{error}</p>}
          {!running && status?.exit_code != null && status.exit_code !== 0 && (
            <p className="error">Der Node hat sich mit Code {status.exit_code} beendet. Details im Log unten.</p>
          )}
          {waitingLong && (
            <p className="error">
              Noch keine Daten vom Node. {params.venue === 'ib'
                ? 'Läuft TWS oder IB Gateway im Paper-Modus mit aktivierter API?'
                : 'Ist das Binance-Testnet erreichbar?'} Details im Log.
            </p>
          )}
          <p className="muted small">
            {params.venue === 'ib'
              ? <>Nur Paper-Konten (Kennung beginnt mit DU). TWS/IB Gateway muss laufen; Zugang in <code>.env</code>.</>
              : <>Läuft nur gegen das Binance-Testnet. Keys gehören in die Datei <code>.env</code> im Projektordner.</>}
            {' '}Limits: max. 1.000 USD(T) pro Order, max. 5 Orders pro Sekunde.
          </p>
        </form>

        <section>
          <h2>Kontostand</h2>
          {!state?.balances.length && <p className="muted">Noch keine Daten.</p>}
          <ul className="balances">
            {state?.balances.filter((b) => b.total > 0).map((b) => (
              <li key={b.currency}><span>{b.currency}</span><strong>{b.total.toLocaleString('de-DE', { maximumFractionDigits: 6 })}</strong></li>
            ))}
          </ul>
        </section>
      </aside>

      <main>
        {!state && (
          <div className="empty">
            <p>{running ? 'Node startet, die ersten Daten erscheinen in ein paar Sekunden …' : 'Starte links das Paper-Trading. Live-Kerzen, Orders, Positionen und das Log erscheinen dann hier.'}</p>
          </div>
        )}
        {state && (
          <>
            <div className="card">
              <div className="card-head">
                <strong>{state.instrument}</strong>
                <span className="muted">Stand {new Date(state.ts * 1000).toLocaleTimeString('de-DE')}</span>
              </div>
              <PriceChart bars={bars} trades={trades} height={440} />
            </div>
            <div className="card">
              <div className="card-head"><strong>Offene Positionen</strong><span className="muted">{state.positions.length}</span></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Instrument</th><th>Richtung</th><th>Menge</th><th>Einstieg</th><th>Unreal. PnL</th><th>Real. PnL</th></tr></thead>
                  <tbody>
                    {state.positions.map((p, i) => (
                      <tr key={i}>
                        <td>{p.instrument}</td><td>{p.side}</td><td>{p.quantity}</td><td>{p.avg_open.toFixed(2)}</td>
                        <td className={p.unrealized_pnl >= 0 ? 'pos' : 'neg'}>{p.unrealized_pnl.toFixed(2)}</td>
                        <td className={p.realized_pnl >= 0 ? 'pos' : 'neg'}>{p.realized_pnl.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <div className="card-head"><strong>Orders</strong><span className="muted">{state.orders.length}</span></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Zeit</th><th>Seite</th><th>Typ</th><th>Menge</th><th>Gefüllt</th><th>Preis</th><th>Status</th></tr></thead>
                  <tbody>
                    {[...state.orders].reverse().map((o) => (
                      <tr key={o.id}>
                        <td>{fmtTime(o.time)}</td><td>{o.side}</td><td>{o.type}</td><td>{o.quantity}</td><td>{o.filled}</td>
                        <td>{o.avg_px?.toFixed(2) ?? '–'}</td><td>{o.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        {status && status.log.length > 0 && (
          <div className="card">
            <div className="card-head"><strong>Log</strong></div>
            <pre className="log">{status.log.join('\n')}</pre>
          </div>
        )}
      </main>
    </>
  )
}
