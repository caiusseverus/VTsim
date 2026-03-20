import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import type Plotly from 'plotly.js'
import { api, type HaHistoryPoint } from '../api'
import { parseCsv, plottableColumns } from '../utils/csv'

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#1e293b',
  font: { color: '#e2e8f0' },
  xaxis: { gridcolor: '#334155', zerolinecolor: '#334155' },
  yaxis: { gridcolor: '#334155', zerolinecolor: '#334155' },
  yaxis2: { gridcolor: '#334155', zerolinecolor: '#334155' },
}

const TRACE_COLOURS = ['#38bdf8', '#fb923c', '#a78bfa', '#34d399', '#f472b6', '#facc15']

interface Props {
  runId: string
  model: string
  version: string   // VT version name
  preset: string    // preset id
  status: string    // RunCell status
}

// Columns that belong on the left (temperature) y-axis
const TEMP_COLS = new Set([
  'model_temperature',
  'sensor_temperature',
  'current_temperature',
  'target_temperature',
])

// Human-readable labels for known columns
const COL_LABELS: Record<string, string> = {
  model_temperature:   'Model room temp (°C)',   // physics ground truth
  sensor_temperature:  'Sensor feed to VT (°C)', // degraded/lagged — what VT receives
  current_temperature: 'VT current temp (°C)',   // VT's internal EMA/filtered value
  target_temperature:  'Setpoint (°C)',
  power_percent: 'Power (%)',
  smartpi_a: 'SmartPI A',
  smartpi_b: 'SmartPI B',
  deadtime_heat_s: 'Deadtime heat (s)',
}

export default function MultiMetricPlot({ runId, model, version, preset, status }: Props) {
  const versionPreset = `${version}_${preset}`
  const [rows, setRows] = useState<Record<string, number>[]>([])
  const [colOptions, setColOptions] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(
    new Set(['model_temperature', 'target_temperature'])
  )
  const [livePoints, setLivePoints] = useState<Record<string, number>[]>([])
  const [fetchError, setFetchError] = useState('')
  const [haHistory, setHaHistory] = useState<HaHistoryPoint[] | null>(null)
  const [showHaTrace, setShowHaTrace] = useState(true)

  useEffect(() => {
    setRows([])
    setLivePoints([])
    setFetchError('')
    setSelected(new Set())
    setHaHistory(null)

    if (status === 'complete') {
      const url = api.resultRecordsUrl(runId, model, versionPreset)
      fetch(url)
        .then(r => r.text())
        .then(csv => {
          const { headers, rows: parsed } = parseCsv(csv)
          const plottable = plottableColumns(headers, parsed)
          setRows(parsed)
          setColOptions(plottable)
          setSelected(new Set(plottable.filter(c => TEMP_COLS.has(c))))
        })
        .catch(e => setFetchError(String(e)))
      // Fetch HA history if available (404 means no overlay — that's fine)
      api.getHaHistory(runId)
        .then(data => setHaHistory(data))
        .catch(() => {})
      return
    }

    if (status === 'running') {
      const es = new EventSource(`/api/runs/${runId}/stream`)
      es.onmessage = e => {
        const evt = JSON.parse(e.data)
        if (
          evt.type === 'temperature_point' &&
          evt.model === model &&
          evt.version === version &&
          evt.preset === preset
        ) {
          const point: Record<string, number> = {}
          for (const [k, v] of Object.entries(evt)) {
            if (['type', 'model', 'version', 'preset'].includes(k)) continue
            if (typeof v === 'number') point[k] = v as number
          }
          setLivePoints(prev => [...prev, point])
          setColOptions(prev => {
            const newCols = Object.keys(point).filter(k => k !== 'elapsed_h' && !prev.includes(k))
            if (newCols.length === 0) return prev
            setSelected(s => {
              const next = new Set(s)
              newCols.filter(c => TEMP_COLS.has(c)).forEach(c => next.add(c))
              return next
            })
            return [...prev, ...newCols]
          })
        }
      }
      es.onerror = () => { es.close(); setFetchError('Live stream disconnected') }
      return () => es.close()
    }
  }, [runId, model, version, preset, status, versionPreset])

  const toggle = (col: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(col) ? next.delete(col) : next.add(col)
      return next
    })

  // --- Running: live SSE chart with metric checkboxes ---
  if (status === 'running') {
    const elapsed = livePoints.map(p => p['elapsed_h'])
    const hasSecondAxis = [...selected].some(c => !TEMP_COLS.has(c))
    const liveTraces = [...selected].map((col, i) => ({
      x: elapsed,
      y: livePoints.map(p => p[col] ?? null),
      name: COL_LABELS[col] ?? col,
      type: 'scatter' as const,
      mode: 'lines' as const,
      yaxis: TEMP_COLS.has(col) ? 'y' : 'y2',
      line: { color: TRACE_COLOURS[i % TRACE_COLOURS.length], width: 1.5 },
    }))
    return (
      <div>
        {colOptions.length > 0 && (
          <div className="flex flex-wrap gap-3 mb-3">
            {colOptions.map(col => (
              <label key={col} className="flex items-center gap-1.5 text-sm text-slate-300 cursor-pointer">
                <input type="checkbox" className="accent-sky-500 w-4 h-4"
                  checked={selected.has(col)} onChange={() => toggle(col)} />
                {COL_LABELS[col] ?? col}
              </label>
            ))}
          </div>
        )}
        <Plot
          data={liveTraces}
          layout={{
            ...DARK_LAYOUT,
            xaxis: { ...DARK_LAYOUT.xaxis, title: { text: 'Elapsed (h)' } },
            yaxis: { ...DARK_LAYOUT.yaxis, title: { text: '°C' } },
            ...(hasSecondAxis
              ? { yaxis2: { ...DARK_LAYOUT.yaxis2, overlaying: 'y', side: 'right', showgrid: false } }
              : {}),
            legend: { orientation: 'h' },
            margin: { t: 20, r: hasSecondAxis ? 60 : 20, b: 50, l: 50 },
            height: 300, autosize: true,
          }}
          config={{ responsive: true }}
          style={{ width: '100%' }}
        />
      </div>
    )
  }

  // --- Not complete or failed: render nothing (parent handles error/pending display) ---
  if (status !== 'complete') return null

  if (fetchError) return <p className="text-red-400 text-sm">{fetchError}</p>

  const elapsed = rows.map(r => r['elapsed_h'])
  const hasSecondAxis = [...selected].some(c => !TEMP_COLS.has(c))

  const traces: object[] = [...selected].map((col, i) => ({
    x: elapsed,
    y: rows.map(r => r[col]),
    name: COL_LABELS[col] ?? col,
    type: 'scatter' as const,
    mode: 'lines' as const,
    yaxis: TEMP_COLS.has(col) ? 'y' : 'y2',
    line: { color: TRACE_COLOURS[i % TRACE_COLOURS.length], width: 1.5 },
  }))

  if (haHistory && showHaTrace) {
    traces.push({
      x: haHistory.map(p => p.elapsed_h),
      y: haHistory.map(p => p.temperature),
      name: 'HA actual',
      type: 'scatter' as const,
      mode: 'lines' as const,
      yaxis: 'y',
      line: { color: '#94a3b8', width: 1.5, dash: 'dash' },
    })
  }

  return (
    <div>
      {/* Metric selector checkboxes */}
      {colOptions.length > 0 && (
        <div className="flex flex-wrap gap-3 mb-3">
          {colOptions.map(col => (
            <label key={col} className="flex items-center gap-1.5 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                className="accent-sky-500 w-4 h-4"
                checked={selected.has(col)}
                onChange={() => toggle(col)}
              />
              {COL_LABELS[col] ?? col}
            </label>
          ))}
          {haHistory && (
            <label className="flex items-center gap-1.5 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                className="accent-sky-500 w-4 h-4"
                checked={showHaTrace}
                onChange={() => setShowHaTrace(v => !v)}
              />
              <span style={{ color: '#94a3b8' }}>HA actual</span>
            </label>
          )}
        </div>
      )}

      <Plot
        data={traces as Plotly.Data[]}
        layout={{
          ...DARK_LAYOUT,
          xaxis: { ...DARK_LAYOUT.xaxis, title: { text: 'Elapsed (h)' } },
          yaxis: { ...DARK_LAYOUT.yaxis, title: { text: '°C' } },
          ...(hasSecondAxis
            ? { yaxis2: { ...DARK_LAYOUT.yaxis2, overlaying: 'y', side: 'right', showgrid: false } }
            : {}),
          legend: { orientation: 'h' },
          margin: { t: 20, r: hasSecondAxis ? 60 : 20, b: 50, l: 50 },
          height: 300, autosize: true,
        }}
        config={{ responsive: true }}
        style={{ width: '100%' }}
      />
    </div>
  )
}
