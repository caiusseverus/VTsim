import { useEffect, useState } from 'react'
import Plot from 'react-plotly.js'
import type Plotly from 'plotly.js'
import { api, type HaHistoryPoint } from '../api'
import { parseCsv, plottableColumns } from '../utils/csv'

const AXIS_BASE = {
  gridcolor: '#334155',
  linecolor: '#334155',
  tickcolor: '#475569',
  zerolinecolor: '#475569',
}

const DARK_BG = { paper_bgcolor: '#0f172a', plot_bgcolor: '#1e293b', font: { color: '#e2e8f0' } }

const TRACE_COLOURS = ['#38bdf8', '#fb923c', '#a78bfa', '#34d399', '#f472b6', '#facc15']

// Temperature columns — HA history overlay is added to any chart containing one of these
const TEMP_COLS = new Set([
  'model_temperature', 'sensor_temperature', 'current_temperature', 'target_temperature',
])

// Default selection when a completed run loads
const DEFAULT_SELECTED = new Set([
  'model_temperature', 'target_temperature',
])

// Human-readable labels
const COL_LABELS: Record<string, string> = {
  model_temperature:              'Model room temp (°C)',
  sensor_temperature:             'Sensor feed to VT (°C)',
  current_temperature:            'VT current temp (°C)',
  target_temperature:             'Setpoint (°C)',
  power_percent:                  'Power (%)',
  on_percent:                     'On percent (%)',
  switch_state:                   'Switch state',
  smartpi_a:                      'SmartPI a',
  smartpi_b:                      'SmartPI b',
  smartpi_u_ff:                   'u_ff (feed-forward)',
  smartpi_u_pi:                   'u_pi (PI output)',
  smartpi_u_cmd:                  'u_cmd',
  smartpi_error:                  'Control error',
  deadtime_heat_s:                'Deadtime heat (s)',
  deadtime_cool_s:                'Deadtime cool (s)',
  smartpi_learn_ok_count_a:       'Learn count A',
  smartpi_learn_ok_count_b:       'Learn count B',
  smartpi_learn_progress_percent: 'Learn progress (%)',
  model_effective_heater_power_w: 'Heater power (W)',
  model_heating_rate_c_per_s:     'Heating rate (°C/s)',
  model_heat_loss_rate_c_per_s:   'Heat loss rate (°C/s)',
  model_net_heat_rate_c_per_s:    'Net heat rate (°C/s)',
}

// Grouped column order for the checkbox panel
const COLUMN_GROUPS: { label: string; cols: string[] }[] = [
  { label: 'Temperature',    cols: ['model_temperature', 'sensor_temperature', 'current_temperature', 'target_temperature'] },
  { label: 'Power / Duty',   cols: ['power_percent', 'on_percent', 'switch_state', 'model_effective_heater_power_w'] },
  { label: 'SmartPI A / B',  cols: ['smartpi_a', 'smartpi_b'] },
  { label: 'Control',        cols: ['smartpi_u_ff', 'smartpi_u_pi', 'smartpi_u_cmd', 'smartpi_error'] },
  { label: 'Deadtime',       cols: ['deadtime_heat_s', 'deadtime_cool_s'] },
  { label: 'Learning',       cols: ['smartpi_learn_ok_count_a', 'smartpi_learn_ok_count_b', 'smartpi_learn_progress_percent'] },
  { label: 'Model physics',  cols: ['model_heating_rate_c_per_s', 'model_heat_loss_rate_c_per_s', 'model_net_heat_rate_c_per_s'] },
]

interface Props {
  runId: string
  model: string
  version: string
  preset: string
  status: string
}

// Build Plotly traces + layout for N selected metrics as aligned subplots.
function buildSubplotData(
  selectedArr: string[],
  getX: () => number[],
  getY: (col: string) => (number | null)[],
  haHistory: HaHistoryPoint[] | null,
  showHaTrace: boolean,
): { traces: object[]; layoutAxes: Record<string, object>; height: number } {
  const N = selectedArr.length
  const traces: object[] = []
  const layoutAxes: Record<string, object> = {}

  selectedArr.forEach((col, mi) => {
    const xKey = mi === 0 ? 'xaxis' : `xaxis${mi + 1}`
    const yKey = mi === 0 ? 'yaxis' : `yaxis${mi + 1}`
    const xRef = mi === 0 ? 'x' : `x${mi + 1}`
    const yRef = mi === 0 ? 'y' : `y${mi + 1}`

    traces.push({
      x: getX(),
      y: getY(col),
      name: COL_LABELS[col] ?? col,
      type: 'scatter',
      mode: 'lines',
      line: { color: TRACE_COLOURS[mi % TRACE_COLOURS.length], width: 1.5 },
      xaxis: xRef,
      yaxis: yRef,
    })

    // Overlay HA history on whichever temperature panel is first
    if (haHistory && showHaTrace && TEMP_COLS.has(col)) {
      traces.push({
        x: haHistory.map(p => p.elapsed_h),
        y: haHistory.map(p => p.temperature),
        name: 'HA actual',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#94a3b8', width: 1.5, dash: 'dash' },
        xaxis: xRef,
        yaxis: yRef,
        showlegend: true,
      })
    }

    layoutAxes[xKey] = {
      ...AXIS_BASE,
      ...(mi === N - 1 ? { title: { text: 'Elapsed (h)' } } : { showticklabels: false }),
    }
    layoutAxes[yKey] = {
      ...AXIS_BASE,
      title: { text: COL_LABELS[col] ?? col, font: { size: 11 } },
    }
  })

  return {
    traces,
    layoutAxes,
    height: Math.max(260, 180 * N),
  }
}

export default function MultiMetricPlot({ runId, model, version, preset, status }: Props) {
  const versionPreset = `${version}_${preset}`
  const [rows, setRows] = useState<Record<string, number>[]>([])
  const [colOptions, setColOptions] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_SELECTED))
  const [livePoints, setLivePoints] = useState<Record<string, number>[]>([])
  const [fetchError, setFetchError] = useState('')
  const [haHistory, setHaHistory] = useState<HaHistoryPoint[] | null>(null)
  const [showHaTrace, setShowHaTrace] = useState(true)

  useEffect(() => {
    setRows([])
    setLivePoints([])
    setFetchError('')
    setSelected(new Set(DEFAULT_SELECTED))
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
          setSelected(new Set(plottable.filter(c => DEFAULT_SELECTED.has(c))))
        })
        .catch(e => setFetchError(String(e)))
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
              newCols.filter(c => DEFAULT_SELECTED.has(c)).forEach(c => next.add(c))
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

  if (status !== 'complete' && status !== 'running') return null
  if (fetchError) return <p className="text-red-400 text-sm">{fetchError}</p>

  const dataPoints = status === 'running' ? livePoints : rows
  const selectedArr = [...selected]
  const N = selectedArr.length

  const { traces, layoutAxes, height } = buildSubplotData(
    selectedArr,
    () => dataPoints.map(p => p['elapsed_h']),
    (col) => dataPoints.map(p => p[col] ?? null),
    haHistory,
    showHaTrace,
  )

  // Ordered checkbox groups — only show groups that have at least one available column
  const availableSet = new Set(colOptions)
  const knownCols = new Set(COLUMN_GROUPS.flatMap(g => g.cols))
  const otherCols = colOptions.filter(c => !knownCols.has(c))

  const visibleGroups = [
    ...COLUMN_GROUPS.map(g => ({ ...g, cols: g.cols.filter(c => availableSet.has(c)) }))
      .filter(g => g.cols.length > 0),
    ...(otherCols.length > 0 ? [{ label: 'Other', cols: otherCols }] : []),
  ]

  return (
    <div>
      {/* Grouped metric checkboxes */}
      {colOptions.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-2 mb-3">
          {visibleGroups.map(group => (
            <div key={group.label} className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                {group.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {group.cols.map(col => (
                  <label key={col} className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer hover:text-slate-100">
                    <input
                      type="checkbox"
                      className="accent-sky-500 w-3.5 h-3.5"
                      checked={selected.has(col)}
                      onChange={() => toggle(col)}
                    />
                    {COL_LABELS[col] ?? col}
                  </label>
                ))}
              </div>
            </div>
          ))}

          {haHistory && (
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                Overlay
              </div>
              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer hover:text-slate-100">
                <input
                  type="checkbox"
                  className="accent-sky-500 w-3.5 h-3.5"
                  checked={showHaTrace}
                  onChange={() => setShowHaTrace(v => !v)}
                />
                <span style={{ color: '#94a3b8' }}>HA actual</span>
              </label>
            </div>
          )}
        </div>
      )}

      {N === 0
        ? <p className="text-slate-500 text-sm">Select metrics above to plot.</p>
        : <Plot
            data={traces as Plotly.Data[]}
            layout={{
              ...DARK_BG,
              ...(N > 1 ? { grid: { rows: N, columns: 1, subplots: selectedArr.map((_, mi) => [`x${mi === 0 ? '' : mi + 1}y${mi === 0 ? '' : mi + 1}`]) } } : {}),
              ...layoutAxes,
              legend: { orientation: 'h', font: { color: '#94a3b8' } },
              margin: { t: 10, r: 20, b: 50, l: 90 },
              height,
              autosize: true,
            } as object}
            config={{ responsive: true }}
            style={{ width: '100%' }}
          />
      }
    </div>
  )
}
