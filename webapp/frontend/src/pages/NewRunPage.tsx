import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import Plot from 'react-plotly.js'
import type Plotly from 'plotly.js'
import type { ModelSummary, VtVersion, Preset, Schedule, Run } from '../api'
import { api } from '../api'

const MAX_WORKERS = 4

const TRACE_COLORS = [
  '#38bdf8', '#fb923c', '#a78bfa', '#34d399',
  '#f472b6', '#facc15', '#e879f9', '#60a5fa',
]

const AXIS_BASE = {
  gridcolor: '#334155',
  linecolor: '#334155',
  tickcolor: '#475569',
  zerolinecolor: '#475569',
}

const CHART_SPECS = [
  {
    key: 'temperature',
    title: 'Model temperature + setpoint',
    yLabel: 'Temperature (°C)',
    metrics: ['model_temperature', 'target_temperature'],
  },
  {
    key: 'smartpi_a',
    title: 'SmartPI a',
    yLabel: 'SmartPI a',
    metrics: ['smartpi_a'],
  },
  {
    key: 'smartpi_b',
    title: 'SmartPI b',
    yLabel: 'SmartPI b',
    metrics: ['smartpi_b'],
  },
  {
    key: 'learn_count_a',
    title: 'Learn count A',
    yLabel: 'Learn count A',
    metrics: ['smartpi_learn_ok_count_a'],
  },
  {
    key: 'learn_count_b',
    title: 'Learn count B',
    yLabel: 'Learn count B',
    metrics: ['smartpi_learn_ok_count_b'],
  },
] as const

type LivePoint = Record<string, number>

type CellEntry = {
  key: string
  label: string
  color: string
}

function formatNumber(value: number | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
}

function formatElapsed(hours: number | undefined): string {
  if (typeof hours !== 'number' || !Number.isFinite(hours)) return '—'
  const totalMinutes = Math.floor(hours * 60)
  const hh = Math.floor(totalMinutes / 60)
  const mm = totalMinutes % 60
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

export default function NewRunPage() {
  const navigate = useNavigate()
  const [models, setModels] = useState<ModelSummary[]>([])
  const [versions, setVersions] = useState<VtVersion[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set())
  const [selectedVersions, setSelectedVersions] = useState<Set<string>>(new Set())
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(new Set())
  const [runName, setRunName] = useState('')
  const [error, setError] = useState('')
  const [launching, setLaunching] = useState(false)
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [selectedSchedule, setSelectedSchedule] = useState('')

  // Live monitoring state
  const [activeRun, setActiveRun] = useState<Run | null>(null)
  const [cellEntries, setCellEntries] = useState<CellEntry[]>([])
  const [liveData, setLiveData] = useState<Record<string, LivePoint[]>>({})
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    Promise.all([api.listModels(), api.listVtVersions(), api.listPresets(), api.listSchedules()])
      .then(([m, v, p, s]) => { setModels(m); setVersions(v); setPresets(p); setSchedules(s) })
      .catch(e => setError(String(e)))
  }, [])

  // Poll run status while active and running
  const pollRun = useCallback(async (runId: string) => {
    try {
      const run = await api.getRun(runId)
      setActiveRun(run)
      if (run.status !== 'running' && esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!activeRun || activeRun.status !== 'running') return
    const t = window.setInterval(() => void pollRun(activeRun.id), 3000)
    return () => clearInterval(t)
  }, [activeRun, pollRun])

  // SSE stream — open once per run, close when component unmounts or run changes
  useEffect(() => {
    if (!activeRun?.id) return
    if (esRef.current) { esRef.current.close(); esRef.current = null }

    const runId = activeRun.id
    const es = new EventSource(`/api/runs/${runId}/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      const evt = JSON.parse(e.data)
      if (evt.type !== 'temperature_point') return
      const key = `${runId}/${evt.model}/${evt.version}/${evt.preset}`
      const point: LivePoint = {}
      for (const [k, v] of Object.entries(evt)) {
        if (['type', 'model', 'version', 'preset'].includes(k)) continue
        if (typeof v === 'number') point[k] = v as number
      }
      setLiveData(prev => ({ ...prev, [key]: [...(prev[key] ?? []), point] }))
    }
    // Explicitly close on error to prevent EventSource auto-reconnect,
    // which would replay data from t=0 and corrupt the charts.
    es.onerror = () => { es.close(); esRef.current = null }
    return () => { es.close(); esRef.current = null }
  }, [activeRun?.id])

  const toggle = (_set: Set<string>, setFn: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) => {
    setFn(prev => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next })
  }

  const totalCells = selectedModels.size * selectedVersions.size * selectedPresets.size
  const canLaunch = totalCells > 0 && selectedSchedule !== '' && !launching && !activeRun

  const handleLaunch = async () => {
    if (selectedModels.size === 0 || selectedVersions.size === 0 || selectedPresets.size === 0) {
      setError('Select at least one model, one VT version, and one preset')
      return
    }
    if (!selectedSchedule) {
      setError('Select a schedule')
      return
    }
    setLaunching(true); setError('')
    try {
      const modelList = [...selectedModels]
      const versionList = [...selectedVersions]
      const presetList = [...selectedPresets]
      const { run_id } = await api.createRun(
        runName || `Run ${new Date().toLocaleTimeString()}`,
        modelList,
        versionList,
        presetList,
        selectedSchedule,
      )
      // Build stable cell entries for colour assignment
      const entries: CellEntry[] = []
      modelList.forEach(model =>
        versionList.forEach(version =>
          presetList.forEach(preset => {
            entries.push({
              key: `${run_id}/${model}/${version}/${preset}`,
              label: `${model} / ${preset}`,
              color: TRACE_COLORS[entries.length % TRACE_COLORS.length],
            })
          })
        )
      )
      setCellEntries(entries)
      setActiveRun(await api.getRun(run_id))
    } catch (e) {
      setError(String(e))
    } finally {
      setLaunching(false)
    }
  }

  const handleNewRun = () => {
    setActiveRun(null)
    setCellEntries([])
    setLiveData({})
  }

  const hasLiveData = cellEntries.some(({ key }) => (liveData[key] ?? []).length > 0)

  const chartLayouts = CHART_SPECS.map((spec, index) => {
    const traces: Plotly.Data[] = []

    if (spec.key === 'temperature') {
      cellEntries.forEach(({ key, label, color }) => {
        const points = liveData[key] ?? []
        traces.push({
          x: points.map(p => p.elapsed_h),
          y: points.map(p => p.model_temperature ?? null),
          name: label,
          type: 'scatter',
          mode: 'lines',
          line: { color, width: 1.8 },
          hovertemplate: '%{x:.2f}h<br>T_model=%{y:.2f}°C<extra>%{fullData.name}</extra>',
        })
      })
      const setpointSource = cellEntries
        .map(({ key }) => liveData[key] ?? [])
        .find(points => points.some(p => typeof p.target_temperature === 'number'))
      if (setpointSource) {
        traces.push({
          x: setpointSource.map(p => p.elapsed_h),
          y: setpointSource.map(p => p.target_temperature ?? null),
          name: 'Setpoint',
          type: 'scatter',
          mode: 'lines',
          line: { color: '#f8fafc', width: 1.5, dash: 'dash' },
          hovertemplate: '%{x:.2f}h<br>Setpoint=%{y:.2f}°C<extra>Setpoint</extra>',
        })
      }
    } else {
      const metric = spec.metrics[0]
      cellEntries.forEach(({ key, label, color }) => {
        const points = liveData[key] ?? []
        traces.push({
          x: points.map(p => p.elapsed_h),
          y: points.map(p => p[metric] ?? null),
          name: label,
          type: 'scatter',
          mode: 'lines',
          line: { color, width: 1.8 },
          hovertemplate: `%{x:.2f}h<br>%{y:.3f}<extra>${label}</extra>`,
          showlegend: false,
        })
      })
    }

    const lastChart = index === CHART_SPECS.length - 1

    return {
      spec,
      traces,
      layout: {
        paper_bgcolor: '#0f172a',
        plot_bgcolor: '#1e293b',
        font: { color: '#e2e8f0' },
        title: { text: spec.title, font: { size: 14, color: '#cbd5e1' }, x: 0.01, xanchor: 'left' },
        xaxis: {
          ...AXIS_BASE,
          title: lastChart ? { text: 'Elapsed (h)' } : undefined,
          showticklabels: lastChart,
        },
        yaxis: {
          ...AXIS_BASE,
          title: { text: spec.yLabel },
        },
        legend: index === 0
          ? { orientation: 'h', font: { color: '#94a3b8' }, y: 1.18, x: 0 }
          : undefined,
        margin: { t: 48, r: 20, b: lastChart ? 48 : 28, l: 72 },
        height: 220,
        autosize: true,
      } satisfies Partial<Plotly.Layout>,
    }
  })

  return (
    <div className="flex flex-col min-h-0">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">New Run</h1>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-800 text-red-300 text-sm rounded-md px-4 py-2 mb-4">
          {error}
        </div>
      )}

      {/* Run name */}
      <div className="flex items-center gap-3 mb-6">
        <label className="text-sm text-slate-300 w-32 flex-shrink-0">Run name</label>
        <input
          className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 disabled:opacity-50"
          placeholder="optional — auto-filled with timestamp"
          value={runName}
          onChange={e => setRunName(e.target.value)}
          disabled={!!activeRun}
        />
      </div>

      {/* Three-column selection grid */}
      <div className="grid grid-cols-3 gap-4 mb-6">

        {/* Models */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex flex-col">
          <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-3 py-2 z-10 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Models</span>
            <span className="text-xs text-slate-500">{selectedModels.size} selected</span>
          </div>
          <div className="overflow-y-auto max-h-72">
            {models.length === 0 && (
              <p className="px-3 py-2 text-sm text-slate-500">No models.</p>
            )}
            {models.map(m => (
              <div
                key={m.slug}
                onClick={() => !activeRun && toggle(selectedModels, setSelectedModels, m.slug)}
                className={`px-3 py-2 text-sm border-b border-slate-800 transition-colors ${
                  activeRun ? 'cursor-default' : 'cursor-pointer'
                } ${
                  selectedModels.has(m.slug)
                    ? 'bg-sky-900/40 border-l-2 border-l-sky-500 text-slate-100'
                    : 'text-slate-300 hover:bg-slate-800/40'
                }`}
              >
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-slate-500">{m.duration_hours}h · {m.model_type}</div>
              </div>
            ))}
          </div>
        </div>

        {/* VT Versions */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex flex-col">
          <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-3 py-2 z-10 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">VT Versions</span>
            <span className="text-xs text-slate-500">{selectedVersions.size} selected</span>
          </div>
          <div className="overflow-y-auto max-h-72">
            {versions.length === 0 && (
              <p className="px-3 py-2 text-sm text-slate-500">No versions registered.</p>
            )}
            {versions.map(v => (
              <div
                key={v.name}
                onClick={() => !activeRun && toggle(selectedVersions, setSelectedVersions, v.name)}
                className={`px-3 py-2 text-sm border-b border-slate-800 transition-colors ${
                  activeRun ? 'cursor-default' : 'cursor-pointer'
                } ${
                  selectedVersions.has(v.name)
                    ? 'bg-sky-900/40 border-l-2 border-l-sky-500 text-slate-100'
                    : 'text-slate-300 hover:bg-slate-800/40'
                }`}
              >
                <div className="font-medium">{v.name}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Presets */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex flex-col">
          <div className="sticky top-0 bg-slate-900 border-b border-slate-800 px-3 py-2 z-10 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Presets</span>
            <span className="text-xs text-slate-500">{selectedPresets.size} selected</span>
          </div>
          <div className="overflow-y-auto max-h-72">
            {presets.length === 0 && (
              <p className="px-3 py-2 text-sm text-slate-500">No presets.</p>
            )}
            {presets.map(p => (
              <div
                key={p.id}
                onClick={() => !activeRun && toggle(selectedPresets, setSelectedPresets, p.id)}
                className={`px-3 py-2 text-sm border-b border-slate-800 transition-colors ${
                  activeRun ? 'cursor-default' : 'cursor-pointer'
                } ${
                  selectedPresets.has(p.id)
                    ? 'bg-sky-900/40 border-l-2 border-l-sky-500 text-slate-100'
                    : 'text-slate-300 hover:bg-slate-800/40'
                }`}
              >
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-slate-500">{p.id}</div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Schedule selector */}
      <div className="flex items-center gap-3 mb-6">
        <label className="text-sm text-slate-300 w-32 flex-shrink-0">Schedule</label>
        {schedules.length === 0 ? (
          <p className="text-sm text-slate-500">
            No schedules. <Link to="/schedules" className="text-sky-400 hover:text-sky-300">Create one first.</Link>
          </p>
        ) : (
          <select
            className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 disabled:opacity-50"
            value={selectedSchedule}
            onChange={e => setSelectedSchedule(e.target.value)}
            disabled={!!activeRun}
          >
            <option value="">— select a schedule —</option>
            {schedules.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
      </div>

      {/* Live monitoring panel — shown after launch */}
      {activeRun && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mb-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              {activeRun.status === 'running' ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
                  Live
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-slate-400 inline-block" />
                  {activeRun.status}
                </>
              )}
            </span>
            <span className="text-xs text-slate-400">{activeRun.name}</span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {cellEntries.map(({ key, color, label }) => {
              const latest = (liveData[key] ?? []).at(-1)
              const statRows = [
                ['Elapsed time', formatElapsed(latest?.elapsed_h)],
                ['Temperature', `${formatNumber(latest?.model_temperature)}°C`],
                ['Power', `${formatNumber(latest?.power_percent, 1)}%`],
                ['SmartPI a', formatNumber(latest?.smartpi_a, 4)],
                ['SmartPI b', formatNumber(latest?.smartpi_b, 4)],
                ['Learn ok A', formatNumber(latest?.smartpi_learn_ok_count_a, 0)],
                ['Learn ok B', formatNumber(latest?.smartpi_learn_ok_count_b, 0)],
              ] as const

              return (
                <div key={key} className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
                  <div className="flex items-center gap-2 min-w-0 mb-3">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                    <div className="truncate text-sm font-semibold text-slate-100">{label}</div>
                  </div>
                  <div className="space-y-1.5">
                    {statRows.map(([name, value]) => (
                      <div key={name} className="grid grid-cols-[max-content_1fr] items-baseline gap-x-3 text-sm">
                        <span className="text-slate-400">{name}</span>
                        <span className="font-mono text-slate-200 text-right">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          {hasLiveData ? (
            <div className="space-y-4">
              {chartLayouts.map(({ spec, traces, layout }) => (
                <div key={spec.key} className="rounded-lg border border-slate-800 bg-slate-950/30 p-2">
                  <Plot
                    data={traces}
                    layout={layout}
                    config={{ responsive: true, displayModeBar: false }}
                    style={{ width: '100%' }}
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm">Waiting for data…</p>
          )}
        </div>
      )}

      {/* Sticky launch bar */}
      <div className="sticky bottom-0 bg-[#020617] border-t border-slate-800 py-4 mt-2 flex items-center justify-between">
        <div className="text-sm text-slate-400">
          {activeRun ? (
            <span className="text-slate-300">{activeRun.name} — {activeRun.status}</span>
          ) : (
            <>
              {totalCells} cell{totalCells !== 1 ? 's' : ''}
              {totalCells > MAX_WORKERS && (
                <span className="ml-2 text-amber-400">— exceeds {MAX_WORKERS} concurrent workers</span>
              )}
            </>
          )}
        </div>
        {activeRun ? (
          <div className="flex gap-3">
            <button
              onClick={() => navigate(`/runs/${activeRun.id}/results`)}
              className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-6 py-2 text-sm"
            >
              Go to Results
            </button>
            <button
              onClick={handleNewRun}
              className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-6 py-2 text-sm"
            >
              New Run
            </button>
          </div>
        ) : (
          <button
            onClick={handleLaunch}
            disabled={launching || !canLaunch}
            className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-6 py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {launching ? 'Launching…' : 'Launch Simulation'}
          </button>
        )}
      </div>
    </div>
  )
}
