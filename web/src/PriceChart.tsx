import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar, Point } from './api'

const LINE_COLORS = ['#f5a524', '#7c8cff', '#2ec4b6', '#e05fd0']

export type TradeMark = { time: number; side: string }

type Props = {
  bars: Bar[]
  indicators?: Record<string, Point[]>
  trades?: TradeMark[]
  equity?: Point[]
  equityLabel?: string
  height?: number
}

type Handles = {
  chart: IChartApi
  candles: ISeriesApi<'Candlestick'>
  volume: ISeriesApi<'Histogram'>
  lines: ISeriesApi<'Line'>[]
  equity?: ISeriesApi<'Line'>
  markers: ISeriesMarkersPluginApi<Time>
  fitted: boolean
}

const readVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const t = (s: number) => s as UTCTimestamp

export function PriceChart({ bars, indicators = {}, trades = [], equity, equityLabel = 'PnL', height = 580 }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const h = useRef<Handles | null>(null)
  const names = Object.keys(indicators)
  // Chart nur neu aufbauen, wenn sich seine Struktur ändert, damit Zoom/Scroll bei Live-Updates erhalten bleiben
  const structure = `${names.join('|')}#${equity ? 1 : 0}`

  useEffect(() => {
    if (!el.current) return
    const grid = readVar('--grid')
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: readVar('--muted'), fontFamily: 'inherit' },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: grid },
      rightPriceScale: { borderColor: grid },
      crosshair: { mode: 0 },
      localization: { locale: 'de-DE' },
    })
    const up = readVar('--up')
    const down = readVar('--down')
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down,
    })
    const lines = names.map((name, i) =>
      chart.addSeries(LineSeries, {
        color: LINE_COLORS[i % LINE_COLORS.length], lineWidth: 1, title: name, priceLineVisible: false, lastValueVisible: false,
      }),
    )
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, color: grid }, 1)
    const eq = equity ? chart.addSeries(LineSeries, { color: readVar('--accent'), lineWidth: 2, title: equityLabel }, 2) : undefined
    const panes = chart.panes()
    panes[0]?.setHeight(eq ? height - 240 : height - 100)
    panes[1]?.setHeight(80)
    panes[2]?.setHeight(140)
    h.current = { chart, candles, volume, lines, equity: eq, markers: createSeriesMarkers(candles, []), fitted: false }
    return () => {
      chart.remove()
      h.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure, height])

  useEffect(() => {
    const c = h.current
    if (!c) return
    const up = readVar('--up')
    const down = readVar('--down')
    c.candles.setData(bars.map((b) => ({ ...b, time: t(b.time) })))
    c.volume.setData(bars.map((b) => ({ time: t(b.time), value: b.volume, color: (b.close >= b.open ? up : down) + '66' })))
    Object.values(indicators).forEach((pts, i) => c.lines[i]?.setData(pts.map((p) => ({ ...p, time: t(p.time) }))))

    // Bei Positionswechsel (Netting) fallen Schließen und Neueröffnen auf denselben Zeitpunkt: ein Marker reicht
    const seen = new Set<string>()
    const markers: SeriesMarker<Time>[] = []
    for (const f of [...trades].sort((a, b) => a.time - b.time)) {
      const key = `${f.time}-${f.side}`
      if (seen.has(key)) continue
      seen.add(key)
      const buy = f.side === 'BUY'
      markers.push({ time: t(f.time), position: buy ? 'belowBar' : 'aboveBar', color: buy ? up : down,
        shape: buy ? 'arrowUp' : 'arrowDown', size: 2 })
    }
    c.markers.setMarkers(markers)

    if (c.equity && equity) {
      const start = bars[0]?.time
      const curve = start != null && (equity[0]?.time ?? Infinity) > start ? [{ time: start, value: 0 }, ...equity] : equity
      c.equity.setData(curve.map((p) => ({ ...p, time: t(p.time) })))
    }
    if (!c.fitted && bars.length) {
      c.chart.timeScale().fitContent()
      c.fitted = true
    }
  }, [bars, indicators, trades, equity, structure])

  return <div ref={el} className="chart" style={{ height }} />
}
