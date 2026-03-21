// webapp/frontend/src/components/PresetForm.tsx
import { useState } from 'react'
import type { Preset } from '../api'

// ── Helpers ────────────────────────────────────────────────────────────────

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .slice(0, 60)
}

const SLUG_RE = /^[a-z0-9-]+$/

function parseOpt(v: string): number | undefined {
  const n = parseFloat(v)
  return isNaN(n) ? undefined : n
}

// ── Types ──────────────────────────────────────────────────────────────────

interface FormState {
  id: string
  name: string
  // control
  proportional_function: string
  cycle_min: string
  minimal_activation_delay: string
  minimal_deactivation_delay: string
  // smartpi
  smart_pi_deadband: string
  smart_pi_hysteresis_on: string
  smart_pi_hysteresis_off: string
  smart_pi_use_setpoint_filter: string
  smart_pi_aggregation_mode: string
  smart_pi_use_ff3: string
  // regulation
  auto_regulation_dtemp: string
  auto_regulation_periode_min: string
  // temperatures
  eco_temp: string
  comfort_temp: string
  boost_temp: string
  frost_temp: string
  min_temp: string
  max_temp: string
}

function initFromPreset(p: Preset): FormState {
  const c = p.control || {}
  const t = p.temperatures || {}
  const str = (v: unknown) => v !== undefined && v !== null ? String(v) : ''
  return {
    id: p.id,
    name: p.name,
    proportional_function: str(c.proportional_function),
    cycle_min: str(c.cycle_min),
    minimal_activation_delay: str(c.minimal_activation_delay),
    minimal_deactivation_delay: str(c.minimal_deactivation_delay),
    smart_pi_deadband: str(c.smart_pi_deadband),
    smart_pi_hysteresis_on: str(c.smart_pi_hysteresis_on),
    smart_pi_hysteresis_off: str(c.smart_pi_hysteresis_off),
    smart_pi_use_setpoint_filter: str(c.smart_pi_use_setpoint_filter),
    smart_pi_aggregation_mode: str(c.smart_pi_aggregation_mode),
    smart_pi_use_ff3: str(c.smart_pi_use_ff3),
    auto_regulation_dtemp: str(c.auto_regulation_dtemp),
    auto_regulation_periode_min: str(c.auto_regulation_periode_min),
    eco_temp: str(t.eco_temp),
    comfort_temp: str(t.comfort_temp),
    boost_temp: str(t.boost_temp),
    frost_temp: str(t.frost_temp),
    min_temp: str(t.min_temp),
    max_temp: str(t.max_temp),
  }
}

const EMPTY: FormState = {
  id: '', name: '',
  proportional_function: '', cycle_min: '',
  minimal_activation_delay: '', minimal_deactivation_delay: '',
  smart_pi_deadband: '', smart_pi_hysteresis_on: '', smart_pi_hysteresis_off: '',
  smart_pi_use_setpoint_filter: '', smart_pi_aggregation_mode: '', smart_pi_use_ff3: '',
  auto_regulation_dtemp: '', auto_regulation_periode_min: '',
  eco_temp: '', comfort_temp: '', boost_temp: '',
  frost_temp: '', min_temp: '', max_temp: '',
}

function buildPreset(f: FormState): Omit<Preset, 'id'> & { id: string } {
  const control: Record<string, unknown> = {}
  if (f.proportional_function) control.proportional_function = f.proportional_function
  const cn = (k: string, v: string) => { const n = parseOpt(v); if (n !== undefined) control[k] = n }
  cn('cycle_min', f.cycle_min)
  cn('minimal_activation_delay', f.minimal_activation_delay)
  cn('minimal_deactivation_delay', f.minimal_deactivation_delay)
  cn('smart_pi_deadband', f.smart_pi_deadband)
  cn('smart_pi_hysteresis_on', f.smart_pi_hysteresis_on)
  cn('smart_pi_hysteresis_off', f.smart_pi_hysteresis_off)
  // boolean selects: serialize 'true'/'false' strings to actual booleans
  const cb = (k: string, v: string) => { if (v === 'true') control[k] = true; else if (v === 'false') control[k] = false }
  cb('smart_pi_use_setpoint_filter', f.smart_pi_use_setpoint_filter)
  cb('smart_pi_use_ff3', f.smart_pi_use_ff3)
  if (f.smart_pi_aggregation_mode) control.smart_pi_aggregation_mode = f.smart_pi_aggregation_mode
  cn('auto_regulation_dtemp', f.auto_regulation_dtemp)
  cn('auto_regulation_periode_min', f.auto_regulation_periode_min)

  const temperatures: Record<string, unknown> = {}
  const tn = (k: string, v: string) => { const n = parseOpt(v); if (n !== undefined) temperatures[k] = n }
  tn('eco_temp', f.eco_temp)
  tn('comfort_temp', f.comfort_temp)
  tn('boost_temp', f.boost_temp)
  tn('frost_temp', f.frost_temp)
  tn('min_temp', f.min_temp)
  tn('max_temp', f.max_temp)

  return { id: f.id, name: f.name, control, temperatures }
}

// ── Component ──────────────────────────────────────────────────────────────

interface Props {
  preset: Preset | null  // null = create mode
  onSave: (data: ReturnType<typeof buildPreset>) => Promise<void>
  onCancel: () => void
}

const INPUT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const INPUT_READONLY_CLS = 'bg-slate-800/40 border border-slate-700 text-slate-500 rounded-md px-3 py-1.5 text-sm w-full cursor-not-allowed font-mono'
const SELECT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const LABEL_CLS = 'text-sm text-slate-300 w-44 flex-shrink-0'

export default function PresetForm({ preset, onSave, onCancel }: Props) {
  const isCreate = preset === null
  const [f, setF] = useState<FormState>(() =>
    preset ? initFromPreset(preset) : EMPTY
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k: keyof FormState, v: string) => setF(prev => ({ ...prev, [k]: v }))

  // Auto-derive id from name in create mode
  const handleName = (v: string) => {
    setF(prev => ({
      ...prev,
      name: v,
      ...(isCreate ? { id: slugify(v) } : {}),
    }))
  }

  const idValid = isCreate ? SLUG_RE.test(f.id) : true
  const canSave = f.name.trim() !== '' && idValid && !saving

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await onSave(buildPreset(f))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const numRow = (label: string, key: keyof FormState) => (
    <div key={key} className="flex items-baseline gap-3 mb-3">
      <label className={LABEL_CLS}>{label}</label>
      <input type="number" className={INPUT_CLS}
        placeholder="(blank = omit)"
        value={f[key] as string}
        onChange={e => set(key, e.target.value)} />
    </div>
  )

  return (
    <div>
      {error && (
        <div className="bg-red-900/40 border border-red-800 text-red-300 text-sm rounded-md px-4 py-2 mb-4">
          {error}
        </div>
      )}

      {/* Identity */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3">Identity</h3>
      <div className="flex items-baseline gap-3 mb-3">
        <label className={LABEL_CLS}>name</label>
        <input type="text" className={INPUT_CLS}
          value={f.name} onChange={e => handleName(e.target.value)} />
      </div>
      <div className="flex items-baseline gap-3 mb-3">
        <label className={LABEL_CLS}>id</label>
        {isCreate ? (
          <div className="flex flex-col gap-0.5 flex-1">
            <input type="text"
              className={`${INPUT_CLS} font-mono`}
              value={f.id}
              onChange={e => set('id', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 60))}
            />
            {!idValid && f.id && <p className="text-red-400 text-xs">Lowercase letters, numbers and hyphens only</p>}
          </div>
        ) : (
          <input className={INPUT_READONLY_CLS} value={preset!.id} readOnly />
        )}
      </div>

      {/* Control */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Control <span className="normal-case font-normal text-slate-600">(all optional)</span>
      </h3>
      <div className="flex items-baseline gap-3 mb-3">
        <label className={LABEL_CLS}>proportional_function</label>
        <select className={SELECT_CLS}
          value={f.proportional_function}
          onChange={e => set('proportional_function', e.target.value)}>
          <option value="">(not set)</option>
          <option value="smart_pi">smart_pi</option>
          <option value="tpi">tpi</option>
        </select>
      </div>
      {numRow('cycle_min', 'cycle_min')}
      {numRow('minimal_activation_delay', 'minimal_activation_delay')}
      {numRow('minimal_deactivation_delay', 'minimal_deactivation_delay')}

      {/* SmartPI — shown when proportional_function is smart_pi or unset */}
      {(f.proportional_function === 'smart_pi' || f.proportional_function === '') && (
        <>
          <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
            SmartPI <span className="normal-case font-normal text-slate-600">(all optional)</span>
          </h3>
          {numRow('smart_pi_deadband', 'smart_pi_deadband')}
          {numRow('smart_pi_hysteresis_on', 'smart_pi_hysteresis_on')}
          {numRow('smart_pi_hysteresis_off', 'smart_pi_hysteresis_off')}
          <div className="flex items-baseline gap-3 mb-3">
            <label className={LABEL_CLS}>smart_pi_use_setpoint_filter</label>
            <select className={SELECT_CLS}
              value={f.smart_pi_use_setpoint_filter}
              onChange={e => set('smart_pi_use_setpoint_filter', e.target.value)}>
              <option value="">(not set)</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </div>
          <div className="flex items-baseline gap-3 mb-3">
            <label className={LABEL_CLS}>smart_pi_aggregation_mode</label>
            <select className={SELECT_CLS}
              value={f.smart_pi_aggregation_mode}
              onChange={e => set('smart_pi_aggregation_mode', e.target.value)}>
              <option value="">(not set)</option>
              <option value="weighted_median">weighted_median</option>
              <option value="median">median</option>
            </select>
          </div>
          <div className="flex items-baseline gap-3 mb-3">
            <label className={LABEL_CLS}>smart_pi_use_ff3</label>
            <select className={SELECT_CLS}
              value={f.smart_pi_use_ff3}
              onChange={e => set('smart_pi_use_ff3', e.target.value)}>
              <option value="">(not set)</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </div>
        </>
      )}

      {/* Regulation */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Regulation <span className="normal-case font-normal text-slate-600">(all optional)</span>
      </h3>
      {numRow('auto_regulation_dtemp', 'auto_regulation_dtemp')}
      {numRow('auto_regulation_periode_min', 'auto_regulation_periode_min')}

      {/* Temperatures */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Temperatures <span className="normal-case font-normal text-slate-600">(all optional)</span>
      </h3>
      {numRow('eco_temp', 'eco_temp')}
      {numRow('comfort_temp', 'comfort_temp')}
      {numRow('boost_temp', 'boost_temp')}
      {numRow('frost_temp', 'frost_temp')}
      {numRow('min_temp', 'min_temp')}
      {numRow('max_temp', 'max_temp')}

      {/* Footer */}
      <div className="flex justify-end gap-3 pt-4 border-t border-slate-800 mt-6">
        <button onClick={onCancel}
          className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm">
          Cancel
        </button>
        <button onClick={handleSave} disabled={!canSave}
          className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}
