import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { VerifyParseResult, ModelSummary, VtVersion } from '../api'
import { api } from '../api'

function fmt(v: number | null | undefined, digits = 2): string {
  return v != null ? v.toFixed(digits) : '—'
}

function KVTable({ rows }: { rows: [string, string][] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k} className="border-b border-slate-700/50 last:border-0">
            <td className="py-1 pr-4 text-slate-400 whitespace-nowrap">{k}</td>
            <td className="py-1 text-slate-200 font-mono">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4 last:mb-0">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-2">{title}</h3>
      {children}
    </div>
  )
}

export default function VerifyPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [parsed, setParsed] = useState<VerifyParseResult | null>(null)
  const [models, setModels] = useState<ModelSummary[]>([])
  const [versions, setVersions] = useState<VtVersion[]>([])

  const [runName, setRunName] = useState('')
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedVersions, setSelectedVersions] = useState<string[]>([])
  const [savePreset, setSavePreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [saveSchedule, setSaveSchedule] = useState(false)
  const [scheduleName, setScheduleName] = useState('')

  useEffect(() => {
    api.listModels().then(setModels).catch(() => {})
    api.listVtVersions().then(setVersions).catch(() => {})
  }, [])

  async function handleFile(file: File) {
    setLoading(true)
    setError(null)
    try {
      const result = await api.verifyParse(file)
      setParsed(result)
      const entity = result.entity_id.split('.').pop() ?? 'run'
      setRunName(`verify_${entity}_${new Date().toISOString().slice(0, 10)}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function toggleModel(slug: string) {
    setSelectedModels(prev =>
      prev.includes(slug) ? prev.filter(s => s !== slug) : [...prev, slug]
    )
  }

  function toggleVersion(name: string) {
    setSelectedVersions(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    )
  }

  async function handleCreateRun() {
    if (!parsed) return
    setLoading(true)
    setError(null)
    try {
      if (savePreset && presetName.trim()) {
        const id = presetName.trim().toLowerCase().replace(/\s+/g, '_')
        await api.createPreset({
          id, name: presetName.trim(),
          control: parsed.preset.control,
          temperatures: parsed.preset.temperatures,
        })
      }
      if (saveSchedule && scheduleName.trim()) {
        const id = scheduleName.trim().toLowerCase().replace(/\s+/g, '_')
        await api.createSchedule({
          id, name: scheduleName.trim(),
          type: 'explicit',
          entries: parsed.schedule,
        })
      }

      const { run_id } = await api.verifyRun({
        name: runName,
        model_names: selectedModels,
        version_names: selectedVersions,
        thermostat_params: { ...parsed.preset.control, ...parsed.preset.temperatures },
        schedule_entries: parsed.schedule,
        ha_history: parsed.history,
        starting_conditions: {
          ...parsed.starting_conditions,
          duration_hours: parsed.duration_hours,
        },
      })
      navigate(`/runs/${run_id}/results`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const canCreate =
    !!parsed &&
    selectedModels.length > 0 &&
    selectedVersions.length > 0 &&
    runName.trim().length > 0

  // --- Upload screen ---
  if (!parsed) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="w-full max-w-md">
          <h2 className="text-lg font-semibold text-slate-100 mb-1">Verify vs Home Assistant</h2>
          <p className="text-sm text-slate-400 mb-6">
            Upload a HA recorder JSON export to compare a simulation run against real data.
          </p>
          <div
            className="border-2 border-dashed border-slate-600 rounded-lg p-12 text-center cursor-pointer hover:border-slate-400 transition-colors"
            onClick={() => inputRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              const file = e.dataTransfer.files[0]
              if (file) handleFile(file)
            }}
          >
            {loading ? (
              <p className="text-slate-400">Parsing…</p>
            ) : (
              <>
                <p className="text-slate-300 font-medium mb-1">Drop JSON file here</p>
                <p className="text-slate-500 text-sm">or click to browse</p>
              </>
            )}
          </div>
          <input
            ref={inputRef} type="file" accept=".json" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
          />
          {error && <p className="mt-4 text-red-400 text-sm">{error}</p>}
        </div>
      </div>
    )
  }

  // --- Review + configure screen ---
  const controlRows = Object.entries(parsed.preset.control).map(
    ([k, v]) => [k, String(v)] as [string, string]
  )
  const tempRows = Object.entries(parsed.preset.temperatures).map(
    ([k, v]) => [`${k}`, `${v} °C`] as [string, string]
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Verify vs HA</h2>
          <p className="text-sm text-slate-400">
            {parsed.entity_id} · {parsed.duration_hours.toFixed(1)} h · {parsed.history.length} points
          </p>
        </div>
        <button
          onClick={() => { setParsed(null); setError(null) }}
          className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          ← Upload different file
        </button>
      </div>

      <div className="grid grid-cols-2 gap-6 items-start">
        {/* Left: parsed data summary */}
        <div className="space-y-4">
          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="Starting Conditions">
              <KVTable rows={[
                ['HVAC mode', parsed.starting_conditions.hvac_mode],
                ['Preset', parsed.starting_conditions.preset_mode],
                ['Room temp', `${fmt(parsed.starting_conditions.initial_temperature)} °C`],
                ['Ext temp', parsed.starting_conditions.ext_temperature != null
                  ? `${fmt(parsed.starting_conditions.ext_temperature)} °C` : '—'],
              ]} />
            </Section>
          </div>

          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="VT Config — Control">
              {controlRows.length > 0
                ? <KVTable rows={controlRows} />
                : <p className="text-slate-500 text-sm">No control params extracted</p>}
            </Section>
            <Section title="VT Config — Temperatures">
              {tempRows.length > 0
                ? <KVTable rows={tempRows} />
                : <p className="text-slate-500 text-sm">No temperature params extracted</p>}
            </Section>
          </div>

          {parsed.smartpi_seed && (
            <div className="bg-slate-800 rounded-lg p-4">
              <Section title="SmartPI Seed (settled tail avg)">
                <KVTable rows={[
                  ['a', fmt(parsed.smartpi_seed.a, 4)],
                  ['b', fmt(parsed.smartpi_seed.b, 4)],
                  ['deadtime_heat_s', fmt(parsed.smartpi_seed.deadtime_heat_s, 1)],
                ]} />
              </Section>
            </div>
          )}

          <div className="bg-slate-800 rounded-lg p-4">
            <Section title={`Schedule (${parsed.schedule.length} changes)`}>
              <div className="max-h-48 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500">
                      <th className="pb-1 pr-4 font-medium">Hour</th>
                      <th className="pb-1 font-medium">Target °C</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.schedule.map((e, i) => (
                      <tr key={i} className="border-b border-slate-700/50 last:border-0">
                        <td className="py-0.5 pr-4 font-mono text-slate-300">{e.at_hour.toFixed(2)}</td>
                        <td className="py-0.5 font-mono text-slate-300">{e.target_temp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>
        </div>

        {/* Right: configure */}
        <div className="space-y-4">
          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="Run Name">
              <input
                value={runName}
                onChange={e => setRunName(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
              />
            </Section>
          </div>

          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="Model">
              {models.length === 0
                ? <p className="text-slate-500 text-sm">No models available</p>
                : models.map(m => (
                  <label key={m.slug} className="flex items-center gap-2 py-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedModels.includes(m.slug)}
                      onChange={() => toggleModel(m.slug)}
                      className="accent-sky-500"
                    />
                    <span className="text-sm text-slate-200">{m.name || m.slug}</span>
                  </label>
                ))}
            </Section>
          </div>

          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="VT Version">
              {versions.length === 0
                ? <p className="text-slate-500 text-sm">No versions registered</p>
                : versions.map(v => (
                  <label key={v.name} className="flex items-center gap-2 py-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedVersions.includes(v.name)}
                      onChange={() => toggleVersion(v.name)}
                      className="accent-sky-500"
                    />
                    <span className="text-sm text-slate-200">{v.name}</span>
                  </label>
                ))}
            </Section>
          </div>

          <div className="bg-slate-800 rounded-lg p-4">
            <Section title="Save Options">
              <div className="space-y-3">
                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox" checked={savePreset}
                      onChange={e => setSavePreset(e.target.checked)}
                      className="accent-sky-500"
                    />
                    <span className="text-sm text-slate-200">Save as preset</span>
                  </label>
                  {savePreset && (
                    <input
                      value={presetName}
                      onChange={e => setPresetName(e.target.value)}
                      placeholder="Preset name"
                      className="mt-2 w-full bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                    />
                  )}
                </div>
                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox" checked={saveSchedule}
                      onChange={e => setSaveSchedule(e.target.checked)}
                      className="accent-sky-500"
                    />
                    <span className="text-sm text-slate-200">Save schedule</span>
                  </label>
                  {saveSchedule && (
                    <input
                      value={scheduleName}
                      onChange={e => setScheduleName(e.target.value)}
                      placeholder="Schedule name"
                      className="mt-2 w-full bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                    />
                  )}
                </div>
              </div>
            </Section>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            onClick={handleCreateRun}
            disabled={!canCreate || loading}
            className="w-full bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg px-4 py-2 text-sm transition-colors"
          >
            {loading ? 'Creating…' : 'Create Run'}
          </button>
        </div>
      </div>
    </div>
  )
}
