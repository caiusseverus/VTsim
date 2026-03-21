// webapp/frontend/src/pages/ComparisonPage.tsx
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Plot from 'react-plotly.js'
import { api } from '../api'
import type { Run, RunCell } from '../api'
import { parseCsv, plottableColumns } from '../utils/csv'
import StatusBadge from '../components/StatusBadge'

const TRACE_COLORS = [
  '#38bdf8', '#fb923c', '#a78bfa', '#34d399',
  '#f472b6', '#facc15', '#e879f9', '#60a5fa',
]

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

const COLUMN_GROUPS: { label: string; cols: string[] }[] = [
  { label: 'Temperature',   cols: ['model_temperature', 'sensor_temperature', 'current_temperature', 'target_temperature'] },
  { label: 'Power / Duty',  cols: ['power_percent', 'on_percent', 'switch_state', 'model_effective_heater_power_w'] },
  { label: 'SmartPI A / B', cols: ['smartpi_a', 'smartpi_b'] },
  { label: 'Control',       cols: ['smartpi_u_ff', 'smartpi_u_pi', 'smartpi_u_cmd', 'smartpi_error'] },
  { label: 'Deadtime',      cols: ['deadtime_heat_s', 'deadtime_cool_s'] },
  { label: 'Learning',      cols: ['smartpi_learn_ok_count_a', 'smartpi_learn_ok_count_b', 'smartpi_learn_progress_percent'] },
  { label: 'Model physics', cols: ['model_heating_rate_c_per_s', 'model_heat_loss_rate_c_per_s', 'model_net_heat_rate_c_per_s'] },
]

function sseClass(val: number | null | undefined): string {
  if (val == null) return ''
  if (val < 0.2) return 'text-emerald-400'
  if (val < 0.5) return 'text-amber-400'
  return 'text-red-400'
}

// Unique key for a selected cell
function cellKey(runId: string, c: RunCell) {
  return `${runId}/${c.model}/${c.vt_version}/${c.preset}`
}

// Key used for CSV data cache
function csvKey(runId: string, c: RunCell) {
  return `${runId}/${c.model}/${c.vt_version}_${c.preset}`
}

const AXIS_BASE = {
  gridcolor: '#334155',
  linecolor: '#334155',
  tickcolor: '#475569',
  zerolinecolor: '#475569',
}

export default function ComparisonPage() {
  const [searchParams] = useSearchParams()
  const preselectedIds = (searchParams.get('runs') ?? '').split(',').filter(Boolean)

  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set(preselectedIds))

  // Selected cells: Set<"runId/model/vt_version/preset">
  const [selectedCellKeys, setSelectedCellKeys] = useState<Set<string>>(new Set())

  // CSV data keyed by csvKey()
  const [csvData, setCsvData] = useState<Record<string, Record<string, number>[]>>({})
  const [csvErrors, setCsvErrors] = useState<Record<string, string>>({})
  const [csvCols, setCsvCols] = useState<string[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string>>(new Set(['model_temperature']))

  useEffect(() => {
    api.listRuns()
      .then(data => { setRuns(data); setLoading(false) })
      .catch(e => { setLoadError(String(e)); setLoading(false) })
  }, [])

  const toggleRun = (id: string) =>
    setCheckedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleCell = (ck: string, run: Run, cell: RunCell) => {
    setSelectedCellKeys(prev => {
      const next = new Set(prev)
      if (next.has(ck)) { next.delete(ck); return next }
      next.add(ck)
      return next
    })
    // Fetch CSV if not already loaded
    const key = csvKey(run.id, cell)
    if (csvData[key] || csvErrors[key]) return
    const url = api.resultRecordsUrl(run.id, cell.model, `${cell.vt_version}_${cell.preset}`)
    fetch(url)
      .then(r => r.text())
      .then(csv => {
        const { headers, rows } = parseCsv(csv)
        setCsvData(prev => ({ ...prev, [key]: rows }))
        const plottable = plottableColumns(headers, rows)
        setCsvCols(prev => [...new Set([...prev, ...plottable])])
        // Auto-select first metric if nothing selected yet
        setSelectedMetrics(prev =>
          prev.size === 0 && plottable.length > 0 ? new Set([plottable[0]]) : prev
        )
      })
      .catch(e => setCsvErrors(prev => ({ ...prev, [key]: String(e) })))
  }

  const toggleMetric = (metric: string) =>
    setSelectedMetrics(prev => {
      const next = new Set(prev)
      next.has(metric) ? next.delete(metric) : next.add(metric)
      return next
    })

  const checkedRuns = runs.filter(r => checkedIds.has(r.id))

  // Stable color per cell, keyed by position across all checked runs
  const allCellEntries: { key: string; run: Run; cell: RunCell }[] = []
  checkedRuns.forEach(run =>
    run.cells.filter(c => c.status === 'complete').forEach(cell =>
      allCellEntries.push({ key: cellKey(run.id, cell), run, cell })
    )
  )
  const cellColorMap: Record<string, string> = {}
  allCellEntries.forEach(({ key }, i) => { cellColorMap[key] = TRACE_COLORS[i % TRACE_COLORS.length] })

  const activeCells = allCellEntries.filter(({ key }) => selectedCellKeys.has(key))
  const selectedMetricsArr = [...selectedMetrics]
  const N = selectedMetricsArr.length

  // Build Plotly traces — N subplots × M cells
  const traces: object[] = []
  selectedMetricsArr.forEach((metric, mi) => {
    const yaxisRef = mi === 0 ? 'y' : `y${mi + 1}`
    const xaxisRef = mi === 0 ? 'x' : `x${mi + 1}`
    activeCells.forEach(({ key, run, cell }) => {
      const rows = csvData[csvKey(run.id, cell)]
      if (!rows || rows.length === 0) return
      traces.push({
        x: rows.map(r => r['elapsed_h']),
        y: rows.map(r => r[metric]),
        name: `${run.name} / ${cell.model} / ${cell.preset}`,
        type: 'scatter',
        mode: 'lines',
        line: { color: cellColorMap[key], width: 1.5 },
        xaxis: xaxisRef,
        yaxis: yaxisRef,
        showlegend: mi === 0,  // one legend entry per cell, not per metric
      })
    })
  })

  // Build axis config dynamically
  const layoutAxes: Record<string, object> = {}
  selectedMetricsArr.forEach((metric, mi) => {
    const xKey = mi === 0 ? 'xaxis' : `xaxis${mi + 1}`
    const yKey = mi === 0 ? 'yaxis' : `yaxis${mi + 1}`
    layoutAxes[xKey] = {
      ...AXIS_BASE,
      ...(mi === N - 1 ? { title: { text: 'Elapsed (h)' } } : {}),
    }
    layoutAxes[yKey] = { ...AXIS_BASE, title: { text: COL_LABELS[metric] ?? metric } }
  })

  const allMetricKeys = [...new Set(
    activeCells.flatMap(({ cell }) => cell.metrics ? Object.keys(cell.metrics) : [])
  )]

  const csvLoadErrors = activeCells.flatMap(({ run, cell }) => {
    const ck = csvKey(run.id, cell)
    return csvErrors[ck] ? [`Could not load data for ${run.name} / ${cell.model} / ${cell.preset}`] : []
  })

  if (loading) return <p className="text-slate-400 text-sm">Loading…</p>
  if (loadError) return <p className="text-red-400">{loadError}</p>

  return (
    <div className="-mx-6 max-w-7xl mx-auto px-6">

      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">Compare Runs</h1>
      </div>

      {/* Two-panel selector grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">

        {/* Run selector */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="bg-slate-800/50 border-b border-slate-800 px-4 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Runs</span>
          </div>
          <div className="overflow-y-auto max-h-64 divide-y divide-slate-800">
            {runs.length === 0
              ? <p className="text-slate-500 text-sm px-4 py-3">No runs yet.</p>
              : runs.map(run => (
                  <label key={run.id} className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-slate-800/40">
                    <input
                      type="checkbox"
                      className="accent-sky-500 w-4 h-4"
                      checked={checkedIds.has(run.id)}
                      onChange={() => toggleRun(run.id)}
                    />
                    <span className="text-sm text-slate-200 flex-1">{run.name}</span>
                    <StatusBadge status={run.status} />
                  </label>
                ))
            }
          </div>
        </div>

        {/* Cell selector — checkbox per cell, grouped by run */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="bg-slate-800/50 border-b border-slate-800 px-4 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Cells</span>
          </div>
          <div className="overflow-y-auto max-h-64 divide-y divide-slate-800">
            {checkedRuns.length === 0
              ? <p className="text-slate-500 text-sm px-4 py-3">Select runs on the left.</p>
              : checkedRuns.map(run => {
                  const completedCells = run.cells.filter(c => c.status === 'complete')
                  return (
                    <div key={run.id} className="px-4 py-2">
                      <div className="text-xs text-sky-400 font-mono mb-1.5">{run.name}</div>
                      {completedCells.length === 0
                        ? <p className="text-slate-500 text-xs italic">(no completed cells)</p>
                        : completedCells.map(cell => {
                            const ck = cellKey(run.id, cell)
                            const color = cellColorMap[ck]
                            return (
                              <label key={ck} className="flex items-center gap-2 py-0.5 cursor-pointer hover:text-slate-100">
                                <input
                                  type="checkbox"
                                  className="w-4 h-4 flex-shrink-0"
                                  style={{ accentColor: color }}
                                  checked={selectedCellKeys.has(ck)}
                                  onChange={() => toggleCell(ck, run, cell)}
                                />
                                <span className="text-xs text-slate-300">
                                  {cell.model} / {cell.vt_version} / {cell.preset}
                                </span>
                              </label>
                            )
                          })
                      }
                    </div>
                  )
                })
            }
          </div>
        </div>
      </div>

      {/* Metrics comparison table */}
      {activeCells.length > 0 && allMetricKeys.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mb-4">
          <div className="overflow-x-auto">
            <table className="text-sm border-collapse w-full">
              <thead>
                <tr className="bg-slate-800/50">
                  <th className="px-3 py-2 text-left border-b border-slate-700 font-mono text-sky-400 text-xs">Metric</th>
                  {activeCells.map(({ key, run, cell }) => (
                    <th key={key} className="px-3 py-2 text-left border-b border-slate-700 font-semibold font-mono text-sky-400 text-xs">
                      {run.name} · {cell.model}/{cell.vt_version}/{cell.preset}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allMetricKeys.map(mk => (
                  <tr key={mk} className="border-b border-slate-800 hover:bg-slate-800/30">
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">{mk}</td>
                    {activeCells.map(({ key, cell }) => {
                      const val = cell.metrics?.[mk] ?? null
                      const display = (val == null || typeof val !== 'number') ? '—' : val.toFixed(3)
                      const colorClass = mk === 'steady_state_error_c' ? sseClass(val) : 'text-slate-200'
                      return <td key={key} className={`px-3 py-2 ${colorClass}`}>{display}</td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Time-series plot */}
      {activeCells.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">

          {/* Grouped metric checkboxes */}
          {csvCols.length > 0 && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 mb-4">
              {(() => {
                const availableSet = new Set(csvCols)
                const knownCols = new Set(COLUMN_GROUPS.flatMap(g => g.cols))
                const otherCols = csvCols.filter(c => !knownCols.has(c))
                const visibleGroups = [
                  ...COLUMN_GROUPS.map(g => ({ ...g, cols: g.cols.filter(c => availableSet.has(c)) }))
                    .filter(g => g.cols.length > 0),
                  ...(otherCols.length > 0 ? [{ label: 'Other', cols: otherCols }] : []),
                ]
                return visibleGroups.map(group => (
                  <div key={group.label} className="min-w-0">
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                      {group.label}
                    </div>
                    <div className="flex flex-col gap-0.5">
                      {group.cols.map(col => (
                        <label key={col} className="flex items-center gap-1.5 cursor-pointer hover:text-slate-100">
                          <input
                            type="checkbox"
                            className="accent-sky-500 w-3.5 h-3.5"
                            checked={selectedMetrics.has(col)}
                            onChange={() => toggleMetric(col)}
                          />
                          <span className="text-xs text-slate-300">{COL_LABELS[col] ?? col}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))
              })()}
            </div>
          )}

          {csvLoadErrors.map(err => (
            <p key={err} className="text-red-400 text-xs mb-1">{err}</p>
          ))}

          {traces.length > 0
            ? <Plot
                data={traces as Plotly.Data[]}
                layout={{
                  paper_bgcolor: '#0f172a',
                  plot_bgcolor: '#1e293b',
                  font: { color: '#e2e8f0' },
                  ...(N > 1 ? { grid: { rows: N, columns: 1, shared_xaxes: true } } : {}),
                  ...layoutAxes,
                  legend: { orientation: 'h', font: { color: '#94a3b8' } },
                  margin: { t: 20, r: 20, b: 50, l: 70 },
                  height: Math.max(280, 220 * N),
                  autosize: true,
                } as object}
                config={{ responsive: true }}
                style={{ width: '100%' }}
              />
            : <p className="text-slate-500 text-sm">Select cells and metrics above to see time-series data.</p>
          }
        </div>
      )}
    </div>
  )
}
