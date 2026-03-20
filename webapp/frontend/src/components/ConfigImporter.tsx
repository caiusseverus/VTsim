import { useState } from 'react'
import { api } from '../api'
import type { ImportResult } from '../api'

interface Props {
  onSave: (name: string, overrides: Record<string, unknown>) => void
  onCancel: () => void
}

export default function ConfigImporter({ onSave, onCancel }: Props) {
  const [yamlText, setYamlText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [configName, setConfigName] = useState('')
  const [overrides, setOverrides] = useState<Record<string, unknown>>({})
  const [error, setError] = useState('')

  const handleParse = async () => {
    setError('')
    try {
      const r = await api.importHaState(yamlText)
      setResult(r)
      const initial: Record<string, unknown> = {}
      for (const [k, v] of r.mapped) {
        if (!['deadtime_heat_s', 'smartpi_a', 'smartpi_b'].includes(k)) {
          initial[k] = v
        }
      }
      setOverrides(initial)
    } catch (e) {
      setError(String(e))
    }
  }

  const handleSave = () => {
    if (!configName.trim()) { setError('Config name required'); return }
    onSave(configName.trim(), overrides)
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Paste the entity state YAML from HA Developer Tools → States → your VTherm climate entity.
      </p>

      <textarea
        className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-2 text-sm w-full font-mono placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500 h-48 resize-none"
        placeholder="Paste YAML here…"
        value={yamlText}
        onChange={e => setYamlText(e.target.value)}
      />

      <button onClick={handleParse}
        className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
        Parse
      </button>

      {error && (
        <div className="bg-red-900/40 border border-red-800 text-red-300 text-sm rounded-md px-4 py-2">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-semibold text-emerald-400 mb-1">Mapped ({result.mapped.length})</h4>
            <ul className="text-xs font-mono space-y-0.5">
              {result.mapped.map(([k, v]) => (
                <li key={k} className="text-emerald-400/80">{k}: {JSON.stringify(v)}</li>
              ))}
            </ul>
          </div>

          {result.unrecognised.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-amber-400 mb-1">
                Unrecognised ({result.unrecognised.length}) — new VTherm options?
              </h4>
              <ul className="text-xs font-mono space-y-0.5">
                {result.unrecognised.map(([k, v]) => (
                  <li key={k} className="text-amber-400/80">{k}: {JSON.stringify(v)}</li>
                ))}
              </ul>
            </div>
          )}

          {result.missing.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-500 mb-1">
                Missing — using defaults ({result.missing.length})
              </h4>
              <ul className="text-xs font-mono space-y-0.5">
                {result.missing.map(([k, v]) => (
                  <li key={k} className="text-slate-500">{k}: {JSON.stringify(v)}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2 border-t border-slate-800">
            <input
              className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
              placeholder="Config name (e.g. cycle_10)"
              value={configName}
              onChange={e => setConfigName(e.target.value)}
            />
            <button onClick={handleSave}
              className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
              Save Config
            </button>
            <button onClick={onCancel}
              className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
