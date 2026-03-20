export interface ModelSummary {
  slug: string
  name: string
  description: string
  model_type: string
  control_mode: string
  duration_hours: number
}

export interface ModelDetail {
  name: string
  description?: string
  model: Record<string, unknown>
  simulation: Record<string, unknown>
  sensor?: Record<string, unknown>
  disturbances?: Record<string, unknown>
}

export interface VtVersion {
  name: string
  path: string
}

export interface PresetParams {
  control: Record<string, unknown>
  temperatures: Record<string, unknown>
}

export interface Preset extends PresetParams {
  id: string
  name: string
}

export interface ScheduleEntry {
  at_hour: number
  target_temp: number
}

export interface Schedule {
  id: string
  name: string
  type: 'pattern' | 'explicit'
  interval_hours?: number
  high_temp?: number
  low_temp?: number
  entries?: ScheduleEntry[]
}

export interface RunCell {
  model: string
  vt_version: string
  preset: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  metrics?: Record<string, number | null>
  error?: string
}

export interface Run {
  id: string
  name: string
  created_at: string
  status: string
  schedule_id?: string
  cells: RunCell[]
}

export interface ImportResult {
  mapped: [string, unknown][]
  unrecognised: [string, unknown][]
  missing: [string, unknown][]
}

export interface HaHistoryPoint {
  elapsed_h: number
  temperature: number
  target: number | null
  on_percent: number
}

export interface VerifyParseResult {
  entity_id: string
  preset: {
    control: Record<string, unknown>
    temperatures: Record<string, number>
  }
  starting_conditions: {
    hvac_mode: string
    preset_mode: string
    initial_temperature: number
    ext_temperature: number | null
  }
  smartpi_seed: {
    deadtime_heat_s: number | null
    a: number | null
    b: number | null
  } | null
  duration_hours: number
  heater_power_watts: number | null
  schedule: Array<{ at_hour: number; target_temp: number }>
  history: HaHistoryPoint[]
}

const BASE = '/api'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, options)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const api = {
  // Models
  listModels: () => fetchJson<ModelSummary[]>('/models'),
  getModel: (slug: string) => fetchJson<ModelDetail>(`/models/${slug}`),
  saveModel: (slug: string, data: ModelDetail) =>
    fetchJson(`/models/${slug}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({data})}),
  createModel: (slug: string, data: ModelDetail) =>
    fetchJson(`/models/${slug}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({data})}),
  deleteModel: (slug: string) => fetchJson(`/models/${slug}`, {method: 'DELETE'}),
  cloneModel: (slug: string, newSlug: string) =>
    fetchJson(`/models/${slug}/clone`, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({new_slug: newSlug})}),

  // VT Versions
  listVtVersions: () => fetchJson<VtVersion[]>('/vt-versions'),
  registerVtVersion: (name: string, path: string) =>
    fetchJson('/vt-versions', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, path})}),
  removeVtVersion: (name: string) => fetchJson(`/vt-versions/${name}`, {method: 'DELETE'}),

  // Heating Simulator path
  getHeatingSim: () => fetchJson<{path: string}>('/heating-sim'),
  setHeatingSim: (path: string) =>
    fetchJson('/heating-sim', {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path})}),

  // Filesystem browser
  browseFs: (path: string) =>
    fetchJson<{path: string, dirs: string[], parent: string | null}>(
      `/fs/browse?path=${encodeURIComponent(path)}`),

  // Presets
  listPresets: () => fetchJson<Preset[]>('/presets'),
  getPreset: (id: string) => fetchJson<Preset>(`/presets/${id}`),
  createPreset: (preset: Preset) =>
    fetchJson('/presets', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(preset)}),
  updatePreset: (id: string, preset: Omit<Preset, 'id'>) =>
    fetchJson(`/presets/${id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(preset)}),
  deletePreset: (id: string) => fetchJson(`/presets/${id}`, {method: 'DELETE'}),
  clonePreset: (id: string, newId: string, newName: string) =>
    fetchJson(`/presets/${id}/clone`, {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({new_id: newId, new_name: newName})}),

  // Schedules
  listSchedules: () => fetchJson<Schedule[]>('/schedules'),
  getSchedule: (id: string) => fetchJson<Schedule>(`/schedules/${id}`),
  createSchedule: (schedule: Schedule) =>
    fetchJson('/schedules', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(schedule)}),
  updateSchedule: (id: string, schedule: Omit<Schedule, 'id'>) =>
    fetchJson(`/schedules/${id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(schedule)}),
  deleteSchedule: (id: string) => fetchJson(`/schedules/${id}`, {method: 'DELETE'}),

  // HA Importer
  importHaState: (yamlText: string) =>
    fetchJson<ImportResult>('/import/ha-state', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({yaml_text: yamlText})}),

  // Runs
  listRuns: () => fetchJson<Run[]>('/runs'),
  getRun: (id: string) => fetchJson<Run>(`/runs/${id}`),
  createRun: (name: string, modelNames: string[], versionNames: string[], presetIds: string[], scheduleId: string, haHistory?: HaHistoryPoint[], startingConditions?: Record<string, unknown>) =>
    fetchJson<{run_id: string}>('/runs', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, model_names: modelNames, version_names: versionNames, preset_ids: presetIds, schedule_id: scheduleId, ha_history: haHistory, starting_conditions: startingConditions})}),
  deleteRun: (id: string) => fetchJson(`/runs/${id}`, {method: 'DELETE'}),
  getHaHistory: (runId: string) => fetchJson<HaHistoryPoint[]>(`/runs/${runId}/ha-history`),

  // HA Log Verify
  verifyParse: async (file: File): Promise<VerifyParseResult> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/verify/parse`, {method: 'POST', body: form})
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
    return res.json()
  },

  resultPlotUrl: (runId: string, model: string, versionPreset: string) =>
    `${BASE}/results/${runId}/${model}/${versionPreset}/plot`,
  resultRecordsUrl: (runId: string, model: string, versionPreset: string) =>
    `${BASE}/results/${runId}/${model}/${versionPreset}/records`,
}
