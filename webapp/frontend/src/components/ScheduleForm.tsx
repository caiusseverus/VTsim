// webapp/frontend/src/components/ScheduleForm.tsx
import { useState } from 'react'
import type { Schedule } from '../api'

interface EntryRow { at_hour: string; target_temp: string }

interface FormState {
  id: string
  name: string
  type: 'pattern' | 'explicit'
  interval_hours: string
  high_temp: string
  low_temp: string
  entries: EntryRow[]
}

const DEFAULTS: FormState = {
  id: '',
  name: '',
  type: 'pattern',
  interval_hours: '12',
  high_temp: '20',
  low_temp: '17.5',
  entries: [{ at_hour: '0', target_temp: '20' }],
}

function initFromSchedule(s: Schedule): FormState {
  return {
    id: s.id,
    name: s.name,
    type: s.type,
    interval_hours: s.interval_hours != null ? String(s.interval_hours) : '',
    high_temp: s.high_temp != null ? String(s.high_temp) : '',
    low_temp: s.low_temp != null ? String(s.low_temp) : '',
    entries: s.entries
      ? s.entries.map(e => ({ at_hour: String(e.at_hour), target_temp: String(e.target_temp) }))
      : [{ at_hour: '0', target_temp: '20' }],
  }
}

function buildPayload(f: FormState): Omit<Schedule, 'id'> {
  if (f.type === 'pattern') {
    return {
      name: f.name,
      type: 'pattern',
      interval_hours: parseFloat(f.interval_hours),
      high_temp: parseFloat(f.high_temp),
      low_temp: parseFloat(f.low_temp),
    }
  }
  return {
    name: f.name,
    type: 'explicit',
    entries: f.entries.map(e => ({
      at_hour: parseFloat(e.at_hour),
      target_temp: parseFloat(e.target_temp),
    })),
  }
}

interface Props {
  schedule: Schedule | null  // null = create mode
  onSave: (id: string, data: Omit<Schedule, 'id'>) => Promise<void>
  onCancel: () => void
}

const INPUT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const INPUT_READONLY_CLS = 'bg-slate-800/40 border border-slate-700 text-slate-500 rounded-md px-3 py-1.5 text-sm w-full cursor-not-allowed font-mono'
const SELECT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const LABEL_CLS = 'text-sm text-slate-300 w-44 flex-shrink-0'

export default function ScheduleForm({ schedule, onSave, onCancel }: Props) {
  const isCreate = schedule === null
  const [f, setF] = useState<FormState>(isCreate ? DEFAULTS : initFromSchedule(schedule))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const numValid = (v: string) => v.trim() !== '' && !isNaN(parseFloat(v))
  const slugValid = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/.test(f.id) && f.id.length <= 60

  const patternOk = f.type !== 'pattern' || (
    numValid(f.interval_hours) && parseFloat(f.interval_hours) > 0 &&
    numValid(f.high_temp) && numValid(f.low_temp)
  )
  const explicitOk = f.type !== 'explicit' || (
    f.entries.length >= 1 &&
    f.entries.every(e => numValid(e.at_hour) && numValid(e.target_temp))
  )
  const canSave = f.name.trim() !== '' && (isCreate ? slugValid : true) && patternOk && explicitOk && !saving

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF(prev => ({ ...prev, [k]: v }))

  const handleSlug = (v: string) => set('id', v.replace(/[^a-z0-9-]/g, '').slice(0, 60))

  const addEntry = () => set('entries', [...f.entries, { at_hour: '', target_temp: '' }])
  const removeEntry = (i: number) => set('entries', f.entries.filter((_, idx) => idx !== i))
  const updateEntry = (i: number, k: keyof EntryRow, v: string) =>
    set('entries', f.entries.map((e, idx) => idx === i ? { ...e, [k]: v } : e))

  const handleSave = async () => {
    setSaving(true); setError('')
    try {
      await onSave(f.id, buildPayload(f))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const inp = (label: string, value: string, onChange: (v: string) => void) => (
    <div className="flex items-baseline gap-3 mb-3">
      <label className={LABEL_CLS}>{label}</label>
      <input className={INPUT_CLS}
        value={value} onChange={e => onChange(e.target.value)} />
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
        <label className={LABEL_CLS}>ID (slug)</label>
        {isCreate
          ? <div className="flex flex-col gap-0.5 flex-1">
              <input className={`${INPUT_CLS} font-mono`}
                value={f.id} onChange={e => handleSlug(e.target.value)} />
              {!slugValid && f.id && <p className="text-red-400 text-xs">Lowercase letters, numbers and hyphens only</p>}
            </div>
          : <input className={INPUT_READONLY_CLS} value={f.id} readOnly />
        }
      </div>

      {inp('Name', f.name, v => set('name', v))}

      <div className="flex items-baseline gap-3 mb-3">
        <label className={LABEL_CLS}>Type</label>
        <select className={SELECT_CLS}
          value={f.type} onChange={e => set('type', e.target.value as 'pattern' | 'explicit')}>
          <option value="pattern">pattern</option>
          <option value="explicit">explicit</option>
        </select>
      </div>

      {f.type === 'pattern' && <>
        {inp('Interval (hours)', f.interval_hours, v => set('interval_hours', v))}
        {inp('High temp (°C)', f.high_temp, v => set('high_temp', v))}
        {inp('Low temp (°C)', f.low_temp, v => set('low_temp', v))}
      </>}

      {f.type === 'explicit' && (
        <div className="mb-3">
          <table className="w-full border-collapse mb-2">
            <thead>
              <tr className="bg-slate-800/50">
                <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-3 py-1.5">Hour</th>
                <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-3 py-1.5">Temp (°C)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {f.entries.map((e, i) => (
                <tr key={i} className="border-b border-slate-800">
                  <td className="px-1 py-1">
                    <input
                      className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-2 py-1 text-sm w-full placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
                      value={e.at_hour}
                      onChange={ev => updateEntry(i, 'at_hour', ev.target.value)}
                    />
                  </td>
                  <td className="px-1 py-1">
                    <input
                      className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-2 py-1 text-sm w-full placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
                      value={e.target_temp}
                      onChange={ev => updateEntry(i, 'target_temp', ev.target.value)}
                    />
                  </td>
                  <td className="px-1 py-1 text-right">
                    <button onClick={() => removeEntry(i)}
                      className="text-slate-400 hover:text-red-400 text-sm">✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={addEntry}
            className="text-sky-400 hover:text-sky-300 text-sm">+ Add row</button>
        </div>
      )}

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
