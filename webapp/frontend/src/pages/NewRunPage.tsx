import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import type { ModelSummary, VtVersion, Preset, Schedule } from '../api'
import { api } from '../api'

const MAX_WORKERS = 4

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

  useEffect(() => {
    Promise.all([api.listModels(), api.listVtVersions(), api.listPresets(), api.listSchedules()])
      .then(([m, v, p, s]) => { setModels(m); setVersions(v); setPresets(p); setSchedules(s) })
      .catch(e => setError(String(e)))
  }, [])

  const toggle = (_set: Set<string>, setFn: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) => {
    setFn(prev => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next })
  }

  const totalCells = selectedModels.size * selectedVersions.size * selectedPresets.size
  const canLaunch = totalCells > 0 && selectedSchedule !== '' && !launching

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
      const { run_id } = await api.createRun(
        runName || `Run ${new Date().toLocaleTimeString()}`,
        [...selectedModels],
        [...selectedVersions],
        [...selectedPresets],
        selectedSchedule,
      )
      navigate(`/runs/${run_id}/results`)
    } catch (e) { setError(String(e)); setLaunching(false) }
  }

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
          className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
          placeholder="optional — auto-filled with timestamp"
          value={runName}
          onChange={e => setRunName(e.target.value)}
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
                onClick={() => toggle(selectedModels, setSelectedModels, m.slug)}
                className={`px-3 py-2 cursor-pointer text-sm border-b border-slate-800 transition-colors ${
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
                onClick={() => toggle(selectedVersions, setSelectedVersions, v.name)}
                className={`px-3 py-2 cursor-pointer text-sm border-b border-slate-800 transition-colors ${
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
                onClick={() => toggle(selectedPresets, setSelectedPresets, p.id)}
                className={`px-3 py-2 cursor-pointer text-sm border-b border-slate-800 transition-colors ${
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
            className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
            value={selectedSchedule}
            onChange={e => setSelectedSchedule(e.target.value)}
          >
            <option value="">— select a schedule —</option>
            {schedules.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
      </div>

      {/* Sticky launch bar */}
      <div className="sticky bottom-0 bg-[#020617] border-t border-slate-800 py-4 mt-2 flex items-center justify-between">
        <div className="text-sm text-slate-400">
          {totalCells} cell{totalCells !== 1 ? 's' : ''}
          {totalCells > MAX_WORKERS && (
            <span className="ml-2 text-amber-400">— exceeds {MAX_WORKERS} concurrent workers</span>
          )}
        </div>
        <button
          onClick={handleLaunch}
          disabled={launching || !canLaunch}
          className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-6 py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {launching ? 'Launching…' : 'Launch Simulation'}
        </button>
      </div>
    </div>
  )
}
