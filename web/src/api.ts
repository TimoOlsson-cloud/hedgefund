export type Bar = { time: number; open: number; high: number; low: number; close: number; volume: number }
export type Point = { time: number; value: number }
export type Fill = { time: number; side: string; price: number; quantity: number }
export type Position = { opened: number; closed: number; side: string; avg_open: number; avg_close: number; pnl: number }
export type Dataset = { label: string; kind: 'ticks' | 'bars' }

export type BacktestParams = {
  dataset: string
  strategy: string
  fast_ema_period: number
  slow_ema_period: number
  trade_size: string
  bar_ticks: number
}

export type BacktestResult = {
  id: string
  request: BacktestParams
  instrument: string
  currency: string
  bars: Bar[]
  fills: Fill[]
  equity: Point[]
  positions: Position[]
  indicators: Record<string, Point[]>
  stats: Record<string, number | null>
}

export type RunSummary = { id: string; request: BacktestParams; pnl: number | null }

export type Source = 'binance' | 'ib'
export type DownloadParams = { source: Source; symbol: string; exchange: string; interval: string; start: string; end: string }

export type PaperParams = {
  venue: Source
  symbol: string
  interval: string
  fast_ema_period: number
  slow_ema_period: number
  trade_size: string
}

export type PaperState = {
  ts: number
  stopped: boolean
  instrument: string
  bars: Bar[]
  balances: { currency: string; total: number; free: number; locked: number }[]
  positions: { instrument: string; side: string; quantity: number; avg_open: number; unrealized_pnl: number; realized_pnl: number }[]
  orders: { time: number; id: string; side: string; type: string; quantity: number; filled: number; avg_px: number | null; status: string }[]
}

export type PaperStatus = {
  running: boolean
  exit_code: number | null
  params: PaperParams | null
  started: number | null
  environment: string
  state: PaperState | null
  log: string[]
}

export const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']
export const IB_INTERVALS = ['1m', '5m', '15m', '1h', '1d']

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? res.statusText)
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body?: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

export const api = {
  datasets: () => fetch('/api/datasets').then(json<Record<string, Dataset>>),
  download: ({ source, ...p }: DownloadParams) => post(`/api/data/${source}`, p).then(json<{ key: string; label: string; bars: number }>),
  runs: () => fetch('/api/backtests').then(json<RunSummary[]>),
  run: (id: string) => fetch(`/api/backtests/${id}`).then(json<BacktestResult>),
  backtest: (p: BacktestParams) => post('/api/backtests', p).then(json<BacktestResult>),
  paper: () => fetch('/api/paper').then(json<PaperStatus>),
  paperStart: (p: PaperParams) => post('/api/paper/start', p).then(json<PaperStatus>),
  paperStop: () => post('/api/paper/stop').then(json<PaperStatus>),
}

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))
export const fmtTime = (s: number) => new Date(s * 1000).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
