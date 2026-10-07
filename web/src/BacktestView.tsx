import { useEffect, useState, type FormEvent } from 'react'
import { api, errMsg, fmtTime, IB_INTERVALS, INTERVALS, type BacktestParams, type DownloadParams, type Source, type BacktestResult, type Dataset, type RunSummary } from './api'
import { PriceChart } from './PriceChart'

const DEFAULTS: BacktestParams = {
  dataset: 'ethusdt-binance-trades',
  strategy: 'ema-cross',
  fast_ema_period: 10,
  slow_ema_period: 20,
  trade_size: '0.10',
  bar_ticks: 250,
}

const KEY_STATS: [string, string, (v: number) => string][] = [
  ['PnL (total)', 'PnL', (v) => v.toLocaleString('de-DE', { maximumFractionDigits: 2 })],
  ['Win Rate', 'Trefferquote', (v) => `${(v * 100).toFixed(0)} %`],
  ['Profit Factor', 'Profit-Faktor', (v) => v.toFixed(2)],
  ['Expectancy', 'Erwartungswert', (v) => v.toFixed(4)],
  ['Positions', 'Trades', (v) => String(v)],
  ['Sortino Ratio (252 days)', 'Sortino', (v) => v.toFixed(2)],
]

const today = () => new Date().toISOString().slice(0, 10)
const monthsAgo = (n: number) => {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return d.toISOString().slice(0, 10)
}

export function BacktestView() {
  const [params, setParams] = useState<BacktestParams>(DEFAULTS)
  const [datasets, setDatasets] = useState<Record<string, Dataset>>({})
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [dl, setDl] = useState<DownloadParams>({
    source: 'binance', symbol: 'BTCUSDT', exchange: 'NASDAQ', interval: '1h', start: monthsAgo(6), end: today(),
  })
  const setSource = (source: Source) =>
    setDl((d) => ({ ...d, source, symbol: source === 'ib' ? 'AAPL' : 'BTCUSDT', interval: d.interval === '4h' ? '1h' : d.interval }))
  const intervals = dl.source === 'ib' ? IB_INTERVALS : INTERVALS
  const [dlBusy, setDlBusy] = useState(false)
  const [dlMsg, setDlMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    api.datasets().then(setDatasets).catch((e) => setError(errMsg(e)))
    api.runs().then(setRuns).catch(() => {})
  }, [])

  const set = <K extends keyof BacktestParams>(k: K, v: BacktestParams[K]) => setParams((p) => ({ ...p, [k]: v }))
  const isTicks = datasets[params.dataset]?.kind !== 'bars'

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setResult(await api.backtest(params))
      setRuns(await api.runs())
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  async function download(e: FormEvent) {
    e.preventDefault()
    setDlBusy(true)
    setDlMsg(null)
    try {
      const r = await api.download(dl)
      setDatasets(await api.datasets())
      set('dataset', r.key)
      setDlMsg({ ok: true, text: `${r.bars.toLocaleString('de-DE')} Kerzen geladen und ausgewählt.` })
    } catch (err) {
      setDlMsg({ ok: false, text: errMsg(err) })
    } finally {
      setDlBusy(false)
    }
  }

  async function open(id: string) {
    setError(null)
    try {
      const r = await api.run(id)
      setResult(r)
      setParams(r.request)
    } catch (err) {
      setError(errMsg(err))
    }
  }

  return (
    <>
      <aside>
        <form onSubmit={submit}>
          <h2>Neuer Backtest</h2>
          <label>
            Daten
            <select value={params.dataset} onChange={(e) => set('dataset', e.target.value)}>
              {Object.entries(datasets).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
          </label>
          <label>
            Strategie
            <select value={params.strategy} onChange={(e) => set('strategy', e.target.value)}>
              <option value="ema-cross">EMA-Cross (Trendfolge)</option>
            </select>
          </label>
          <div className="row">
            <label>
              Schnelle EMA
              <input type="number" min={2} max={200} value={params.fast_ema_period}
                onChange={(e) => set('fast_ema_period', Number(e.target.value))} />
            </label>
            <label>
              Langsame EMA
              <input type="number" min={3} max={500} value={params.slow_ema_period}
                onChange={(e) => set('slow_ema_period', Number(e.target.value))} />
            </label>
          </div>
          <div className="row">
            <label>
              Ordergröße{datasets[params.dataset]?.label.includes(' IB ') ? ' (Stück)' : ''}
              <input type="text" inputMode="decimal" value={params.trade_size}
                onChange={(e) => set('trade_size', e.target.value)} />
            </label>
            {isTicks && (
              <label>
                Ticks pro Kerze
                <input type="number" min={10} max={5000} step={10} value={params.bar_ticks}
                  onChange={(e) => set('bar_ticks', Number(e.target.value))} />
              </label>
            )}
          </div>
          <button type="submit" disabled={busy}>{busy ? 'Läuft …' : 'Backtest starten'}</button>
          {error && <p className="error">{error}</p>}
        </form>

        <form onSubmit={download}>
          <h2>Daten laden</h2>
          <label>
            Quelle
            <select value={dl.source} onChange={(e) => setSource(e.target.value as Source)}>
              <option value="binance">Binance (Krypto, ohne Key)</option>
              <option value="ib">Interactive Brokers (Aktien/ETFs, braucht TWS/Gateway)</option>
            </select>
          </label>
          <div className="row">
            <label>
              Symbol
              <input value={dl.symbol} onChange={(e) => setDl({ ...dl, symbol: e.target.value.toUpperCase() })} />
            </label>
            {dl.source === 'ib' && (
              <label>
                Börse
                <input value={dl.exchange} onChange={(e) => setDl({ ...dl, exchange: e.target.value.toUpperCase() })} />
              </label>
            )}
            <label>
              Intervall
              <select value={dl.interval} onChange={(e) => setDl({ ...dl, interval: e.target.value })}>
                {intervals.map((i) => <option key={i}>{i}</option>)}
              </select>
            </label>
          </div>
          <div className="row">
            <label>
              Von
              <input type="date" value={dl.start} onChange={(e) => setDl({ ...dl, start: e.target.value })} />
            </label>
            <label>
              Bis
              <input type="date" value={dl.end} onChange={(e) => setDl({ ...dl, end: e.target.value })} />
            </label>
          </div>
          <button type="submit" className="secondary" disabled={dlBusy}>{dlBusy ? 'Lädt …' : 'Kerzen herunterladen'}</button>
          {dlMsg && <p className={dlMsg.ok ? 'ok' : 'error'}>{dlMsg.text}</p>}
        </form>

        <section className="history">
          <h2>Verlauf</h2>
          {runs.length === 0 && <p className="muted">Noch keine Läufe.</p>}
          <ul>
            {runs.map((r) => (
              <li key={r.id}>
                <button className={r.id === result?.id ? 'active' : ''} onClick={() => open(r.id)}>
                  <span className="ellipsis">{datasets[r.request.dataset]?.label.split(' (')[0] ?? r.request.dataset} · EMA {r.request.fast_ema_period}/{r.request.slow_ema_period}</span>
                  <span className={(r.pnl ?? 0) >= 0 ? 'pos' : 'neg'}>{r.pnl?.toFixed(2)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </aside>

      <main>
        {!result && (
          <div className="empty">
            <p>Starte links einen Backtest oder lade vorher echte Kerzen von Binance. Kurse, EMAs, Kauf- und Verkaufspunkte, Volumen und die PnL-Kurve erscheinen dann hier.</p>
          </div>
        )}
        {result && (
          <>
            <div className="stats">
              {KEY_STATS.map(([key, label, fmt]) => {
                const v = result.stats[key]
                const cls = key === 'PnL (total)' && v != null ? (v >= 0 ? 'pos' : 'neg') : ''
                return (
                  <div className="stat" key={key}>
                    <span className="muted">{key === 'PnL (total)' ? `${label} (${result.currency})` : label}</span>
                    <strong className={cls}>{v == null ? '–' : fmt(v)}</strong>
                  </div>
                )
              })}
            </div>
            <div className="card">
              <div className="card-head">
                <strong>{result.instrument}</strong>
                <span className="muted">Kerzen · EMAs · Trades | Volumen | realisierte PnL</span>
              </div>
              <PriceChart bars={result.bars} indicators={result.indicators} trades={result.fills}
                equity={result.equity} equityLabel={`PnL ${result.currency}`} />
            </div>
            <div className="card">
              <div className="card-head"><strong>Trades</strong><span className="muted">{result.positions.length}</span></div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Eröffnet</th><th>Geschlossen</th><th>Richtung</th><th>Einstieg</th><th>Ausstieg</th><th>PnL</th></tr>
                  </thead>
                  <tbody>
                    {result.positions.map((p, i) => (
                      <tr key={i}>
                        <td>{fmtTime(p.opened)}</td>
                        <td>{fmtTime(p.closed)}</td>
                        <td>{p.side === 'BUY' ? 'Long' : 'Short'}</td>
                        <td>{p.avg_open.toFixed(2)}</td>
                        <td>{p.avg_close.toFixed(2)}</td>
                        <td className={p.pnl >= 0 ? 'pos' : 'neg'}>{p.pnl.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  )
}
