// webapp/frontend/src/pages/RunsPage.tsx
import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Plot from 'react-plotly.js'
import { api } from '../api'
import type { Run } from '../api'
import StatusBadge from '../components/StatusBadge'

const TRACE_COLORS = [
  '#38bdf8', '#fb923c', '#a78bfa', '#34d399',
  '#f472b6', '#facc15', '#e879f9', '#60a5fa',
]

const COL_LABELS: Record<string, string> = {
  model_temperature:   'Model room temp (°C)',
  sensor_temperature:  'Sensor feed to VT (°C)',
  current_temperature: 'VT current temp (°C)',
  target_temperature:  'Setpoint (°C)',
  power_percent: 'Power (%)',
  smartpi_a: 'SmartPI A',
  smartpi_b: 'SmartPI B',
  deadtime_heat_s: 'Deadtime heat (s)',
}

const AXIS_BASE = {
  gridcolor: '#334155',
  linecolor: '#334155',
  tickcolor: '#475569',
  zerolinecolor: '#475569',
}

type LivePoint = Record<string, number>

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([])
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  // Live graph state
  const [liveData, setLiveData] = useState<Record<string, LivePoint[]>>({})
  const [liveColumns, setLiveColumns] = useState<string[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string>>(
    new Set(['model_temperature', 'target_temperature'])
  )
  const esRefs = useRef<Record<string, EventSource>>({})

  const load = async () => {
    try {
      const data = await api.listRuns()
      setError(null)
      setRuns(data)
      return data
    } catch (err) {
      setError('Failed to load runs.')
      console.error(err)
      return [] as Run[]
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll while any run is running
  useEffect(() => {
    if (!runs.some(r => r.status === 'running')) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [runs]) // eslint-disable-line react-hooks/exhaustive-deps

  // Manage SSE subscriptions — one per running run
  useEffect(() => {
    const runningIds = new Set(runs.filter(r => r.status === 'running').map(r => r.id))

    // Close streams for runs no longer running
    for (const runId of Object.keys(esRefs.current)) {
      if (!runningIds.has(runId)) {
        esRefs.current[runId].close()
        delete esRefs.current[runId]
      }
    }

    // Open streams for newly running runs
    for (const run of runs.filter(r => r.status === 'running')) {
      if (esRefs.current[run.id]) continue
      const es = new EventSource(`/api/runs/${run.id}/stream`)
      esRefs.current[run.id] = es
      es.onmessage = (e) => {
        const evt = JSON.parse(e.data)
        if (evt.type !== 'temperature_point') return
        const key = `${run.id}/${evt.model}/${evt.version}/${evt.preset}`
        const point: LivePoint = {}
        for (const [k, v] of Object.entries(evt)) {
          if (['type', 'model', 'version', 'preset'].includes(k)) continue
          if (typeof v === 'number') point[k] = v as number
        }
        setLiveData(prev => ({ ...prev, [key]: [...(prev[key] ?? []), point] }))
        setLiveColumns(prev => {
          const newCols = Object.keys(point).filter(k => k !== 'elapsed_h' && !prev.includes(k))
          return newCols.length > 0 ? [...prev, ...newCols] : prev
        })
      }
    }

    return () => {
      for (const es of Object.values(esRefs.current)) es.close()
      esRefs.current = {}
    }
  }, [runs])

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this run and its results?')) return
    await api.deleteRun(id)
    setCheckedIds(prev => { const next = new Set(prev); next.delete(id); return next })
    load()
  }

  const handleDeleteSelected = async () => {
    if (checkedIds.size === 0) return
    if (!confirm(`Delete ${checkedIds.size} run(s) and their results?`)) return
    await Promise.all([...checkedIds].map(id => api.deleteRun(id)))
    setCheckedIds(new Set())
    load()
  }

  const handleCompare = () => navigate(`/compare?runs=${[...checkedIds].join(',')}`)

  const toggleMetric = (col: string) =>
    setSelectedMetrics(prev => {
      const next = new Set(prev)
      next.has(col) ? next.delete(col) : next.add(col)
      return next
    })

  // Running cells across all running runs, in stable order for color assignment
  const runningRuns = runs.filter(r => r.status === 'running')
  const cellEntries: { key: string; label: string; color: string }[] = []
  runningRuns.forEach(run =>
    run.cells.filter(c => c.status === 'running').forEach(cell => {
      const key = `${run.id}/${cell.model}/${cell.vt_version}/${cell.preset}`
      cellEntries.push({
        key,
        label: `${run.name} / ${cell.model} / ${cell.preset}`,
        color: TRACE_COLORS[cellEntries.length % TRACE_COLORS.length],
      })
    })
  )

  const selectedMetricsArr = [...selectedMetrics]
  const N = selectedMetricsArr.length

  const liveTraces: object[] = []
  selectedMetricsArr.forEach((metric, mi) => {
    const yRef = mi === 0 ? 'y' : `y${mi + 1}`
    const xRef = mi === 0 ? 'x' : `x${mi + 1}`
    cellEntries.forEach(({ key, label, color }) => {
      const points = liveData[key] ?? []
      liveTraces.push({
        x: points.map(p => p['elapsed_h']),
        y: points.map(p => p[metric] ?? null),
        name: label,
        type: 'scatter', mode: 'lines',
        line: { color, width: 1.5 },
        xaxis: xRef, yaxis: yRef,
        showlegend: mi === 0,
      })
    })
  })

  const layoutAxes: Record<string, object> = {}
  selectedMetricsArr.forEach((metric, mi) => {
    const xKey = mi === 0 ? 'xaxis' : `xaxis${mi + 1}`
    const yKey = mi === 0 ? 'yaxis' : `yaxis${mi + 1}`
    layoutAxes[xKey] = { ...AXIS_BASE, ...(mi === N - 1 ? { title: { text: 'Elapsed (h)' } } : {}) }
    layoutAxes[yKey] = { ...AXIS_BASE, title: { text: COL_LABELS[metric] ?? metric } }
  })

  const hasLiveData = Object.keys(liveData).length > 0

  return (
    <div>
      {error && (
        <div className="mb-4 px-4 py-2.5 rounded-md bg-red-900/40 border border-red-800 text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">Simulation Runs</h1>
        <div className="flex gap-3">
          <button
            disabled={checkedIds.size === 0}
            onClick={handleDeleteSelected}
            className="bg-slate-700 hover:bg-red-700 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Delete selected ({checkedIds.size})
          </button>
          <button
            disabled={checkedIds.size < 2}
            onClick={handleCompare}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Compare selected
          </button>
          <button onClick={() => navigate('/verify')} className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm">
            Verify vs HA
          </button>
          <button onClick={() => navigate('/runs/new')} className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
            New Run
          </button>
        </div>
      </div>

      {/* Live graph — shown only while runs are active */}
      {runningRuns.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
              Live
            </span>
            {liveColumns.length > 0 && (
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {liveColumns.map(col => (
                  <label key={col} className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      className="accent-sky-500 w-4 h-4"
                      checked={selectedMetrics.has(col)}
                      onChange={() => toggleMetric(col)}
                    />
                    <span className="text-xs text-slate-300 font-mono">{COL_LABELS[col] ?? col}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {hasLiveData
            ? <Plot
                data={liveTraces as Plotly.Data[]}
                layout={{
                  paper_bgcolor: '#0f172a',
                  plot_bgcolor: '#1e293b',
                  font: { color: '#e2e8f0' },
                  ...(N > 1 ? { grid: { rows: N, columns: 1, shared_xaxes: true } } : {}),
                  ...layoutAxes,
                  legend: { orientation: 'h', font: { color: '#94a3b8' } },
                  margin: { t: 10, r: 20, b: 50, l: 70 },
                  height: Math.max(250, 200 * N),
                  autosize: true,
                } as object}
                config={{ responsive: true }}
                style={{ width: '100%' }}
              />
            : <p className="text-slate-500 text-sm">Waiting for data…</p>
          }
        </div>
      )}

      {/* Runs table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-800/50">
            <tr>
              <th className="px-4 py-2 w-8"></th>
              {['Name', 'Status', 'Cells', 'Actions'].map(h => (
                <th key={h} className="px-4 py-2 text-slate-400 text-xs font-semibold uppercase tracking-wider text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500 text-sm">No runs yet.</td>
              </tr>
            ) : (
              runs.map(run => (
                <tr key={run.id} className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2.5">
                    <input type="checkbox" className="accent-sky-500 w-4 h-4"
                      checked={checkedIds.has(run.id)}
                      onChange={e => {
                        setCheckedIds(prev => {
                          const next = new Set(prev)
                          e.target.checked ? next.add(run.id) : next.delete(run.id)
                          return next
                        })
                      }}
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-slate-100">{run.name}</div>
                    <div className="text-slate-400 text-xs">{new Date(run.created_at).toLocaleString()}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 text-xs font-mono">{run.cells.length}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-4">
                      <button onClick={() => navigate(`/runs/${run.id}/results`)} className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Results</button>
                      <button onClick={() => navigate(`/compare?runs=${run.id}`)} className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Compare</button>
                      <button onClick={() => handleDelete(run.id)} className="text-slate-400 hover:text-red-400 text-sm transition-colors">Delete</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
