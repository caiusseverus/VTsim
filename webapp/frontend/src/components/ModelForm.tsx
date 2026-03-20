// webapp/frontend/src/components/ModelForm.tsx
import { useState } from 'react'
import type { ModelDetail } from '../api'

// ── Types ──────────────────────────────────────────────────────────────────

type ModelType = 'simple' | 'r2c2' | 'radiator' | 'r2c2_radiator'

interface FormState {
  slug: string
  name: string
  description: string
  // model — common
  model_type: ModelType
  control_mode: string
  initial_temperature: string
  external_temperature_fixed: string
  // model — simple
  heater_power_watts: string
  heat_loss_coefficient: string
  thermal_mass: string
  thermal_inertia: string
  // model — r2c2
  heater_power_watts_r2c2: string
  c_air: string
  c_fabric: string
  r_fabric: string
  r_ext: string
  r_infiltration: string
  // model — r2c2 / r2c2_radiator solar
  window_area_m2: string
  window_transmittance: string
  solar_irradiance_fixed: string
  // sensor pipeline
  sensor_lag_tau: string
  sensor_bias: string
  sensor_noise_std_dev: string
  sensor_quantisation: string
  sensor_update_rate_s: string
  sensor_min_interval_s: string
  sensor_max_interval_s: string
  sensor_delta: string
  // disturbances — ext_temp_profile
  ext_temp_enabled: string
  ext_temp_base: string
  ext_temp_amplitude: string
  ext_temp_min_hour: string
  ext_temp_max_hour: string
  // disturbances — occupancy
  occ_enabled: string
  occ_max_occupants: string
  occ_cooking_power_w: string
  occ_cooking_duration_s: string
  occ_cooking_events_per_day: string
  occ_seed: string
  // disturbances — weather
  weather_wind_speed_m_s: string
  weather_wind_coefficient: string
  weather_rain_intensity: string
  weather_rain_moisture_factor: string
  // model — radiator / r2c2_radiator
  flow_temperature: string
  c_radiator: string
  k_radiator: string
  radiator_exponent: string
  radiator_convective_fraction: string
  flow_rate_max_kg_s: string
  heat_loss_coefficient_rad: string
  c_room_rad: string
  pipe_delay_seconds: string
  valve_characteristic: string
  // simulation
  duration_hours: string
  step_seconds: string
  record_every_seconds: string
  initial_hvac_mode: string
  initial_preset_mode: string
  max_acceptable_steady_state_error_c: string
}

const DEFAULTS: FormState = {
  slug: '',
  name: '',
  description: '',
  model_type: 'r2c2',
  control_mode: 'pwm',
  initial_temperature: '18.0',
  external_temperature_fixed: '5.0',
  heater_power_watts: '1500',
  heat_loss_coefficient: '30.0',
  thermal_mass: '500000',
  thermal_inertia: '0.0',
  heater_power_watts_r2c2: '1000',
  c_air: '1000000',
  c_fabric: '75000000',
  r_fabric: '0.008',
  r_ext: '0.0321',
  r_infiltration: '0.25',
  window_area_m2: '2.0',
  window_transmittance: '0.6',
  solar_irradiance_fixed: '0.0',
  sensor_lag_tau: '0',
  sensor_bias: '0.0',
  sensor_noise_std_dev: '0.0',
  sensor_quantisation: '0.0',
  sensor_update_rate_s: '0',
  sensor_min_interval_s: '0',
  sensor_max_interval_s: '0',
  sensor_delta: '0.0',
  ext_temp_enabled: 'false',
  ext_temp_base: '5.0',
  ext_temp_amplitude: '3.0',
  ext_temp_min_hour: '5.5',
  ext_temp_max_hour: '14.5',
  occ_enabled: 'false',
  occ_max_occupants: '2',
  occ_cooking_power_w: '0.0',
  occ_cooking_duration_s: '1200.0',
  occ_cooking_events_per_day: '2.0',
  occ_seed: '42',
  weather_wind_speed_m_s: '0.0',
  weather_wind_coefficient: '0.0',
  weather_rain_intensity: '0.0',
  weather_rain_moisture_factor: '0.0',
  flow_temperature: '70.0',
  c_radiator: '15000.0',
  k_radiator: '12.0',
  radiator_exponent: '1.3',
  radiator_convective_fraction: '0.75',
  flow_rate_max_kg_s: '0.06',
  heat_loss_coefficient_rad: '30.0',
  c_room_rad: '4060638.9',
  pipe_delay_seconds: '0.0',
  valve_characteristic: 'linear',
  duration_hours: '48',
  step_seconds: '10',
  record_every_seconds: '60',
  initial_hvac_mode: 'heat',
  initial_preset_mode: 'eco',
  max_acceptable_steady_state_error_c: '',
}

// ── Helpers ────────────────────────────────────────────────────────────────

function initFromDetail(slug: string, d: ModelDetail): FormState {
  const m = (d.model || {}) as Record<string, unknown>
  const s = (d.simulation || {}) as Record<string, unknown>
  const s2 = (d.sensor || {}) as Record<string, unknown>
  const dist = (d.disturbances || {}) as Record<string, unknown>
  const ext = (dist.ext_temp_profile || {}) as Record<string, unknown>
  const occ = (dist.occupancy || {}) as Record<string, unknown>
  const wx = (dist.weather || {}) as Record<string, unknown>
  const str = (v: unknown, fallback: string) =>
    v !== undefined && v !== null ? String(v) : fallback
  return {
    ...DEFAULTS,
    slug,
    name: d.name || '',
    description: d.description || '',
    model_type: (m.model_type as ModelType) || 'r2c2',
    control_mode: str(m.control_mode, 'pwm'),
    initial_temperature: str(m.initial_temperature, '18.0'),
    external_temperature_fixed: str(m.external_temperature_fixed, '5.0'),
    heater_power_watts: str(m.heater_power_watts, '1500'),
    heat_loss_coefficient: str(m.heat_loss_coefficient, '30.0'),
    thermal_mass: str(m.thermal_mass, '500000'),
    thermal_inertia: str(m.thermal_inertia, '0.0'),
    heater_power_watts_r2c2: str(m.heater_power_watts_r2c2, '1000'),
    c_air: str(m.c_air, '1000000'),
    c_fabric: str(m.c_fabric, '75000000'),
    r_fabric: str(m.r_fabric, '0.008'),
    r_ext: str(m.r_ext, '0.0321'),
    r_infiltration: str(m.r_infiltration, '0.25'),
    window_area_m2: str(m.window_area_m2, '2.0'),
    window_transmittance: str(m.window_transmittance, '0.6'),
    solar_irradiance_fixed: str(m.solar_irradiance_fixed, '0.0'),
    sensor_lag_tau: str(s2.lag_tau, '0'),
    sensor_bias: str(s2.bias, '0.0'),
    sensor_noise_std_dev: str(s2.noise_std_dev, '0.0'),
    sensor_quantisation: str(s2.quantisation, '0.0'),
    sensor_update_rate_s: str(s2.update_rate_s, '0'),
    sensor_min_interval_s: str(s2.min_interval_s, '0'),
    sensor_max_interval_s: str(s2.max_interval_s, '0'),
    sensor_delta: str(s2.delta, '0.0'),
    ext_temp_enabled: ext.enabled ? 'true' : 'false',
    ext_temp_base: str(ext.base, '5.0'),
    ext_temp_amplitude: str(ext.amplitude, '3.0'),
    ext_temp_min_hour: str(ext.min_hour, '5.5'),
    ext_temp_max_hour: str(ext.max_hour, '14.5'),
    occ_enabled: occ.enabled ? 'true' : 'false',
    occ_max_occupants: str(occ.max_occupants, '2'),
    occ_cooking_power_w: str(occ.cooking_power_w, '0.0'),
    occ_cooking_duration_s: str(occ.cooking_duration_s, '1200.0'),
    occ_cooking_events_per_day: str(occ.cooking_events_per_day, '2.0'),
    occ_seed: str(occ.seed, '42'),
    weather_wind_speed_m_s: str(wx.wind_speed_m_s, '0.0'),
    weather_wind_coefficient: str(wx.wind_coefficient, '0.0'),
    weather_rain_intensity: str(wx.rain_intensity, '0.0'),
    weather_rain_moisture_factor: str(wx.rain_moisture_factor, '0.0'),
    flow_temperature: str(m.flow_temperature, '70.0'),
    c_radiator: str(m.c_radiator, '15000.0'),
    k_radiator: str(m.k_radiator, '12.0'),
    radiator_exponent: str(m.radiator_exponent, '1.3'),
    radiator_convective_fraction: str(m.radiator_convective_fraction, '0.75'),
    flow_rate_max_kg_s: str(m.flow_rate_max_kg_s, '0.06'),
    heat_loss_coefficient_rad: str(m.heat_loss_coefficient_rad, '30.0'),
    c_room_rad: str(m.c_room_rad, '4060638.9'),
    pipe_delay_seconds: str(m.pipe_delay_seconds, '0.0'),
    valve_characteristic: str(m.valve_characteristic, 'linear'),
    duration_hours: str(s.duration_hours, '48'),
    step_seconds: str(s.step_seconds, '10'),
    record_every_seconds: str(s.record_every_seconds, '60'),
    initial_hvac_mode: str(s.initial_hvac_mode, 'heat'),
    initial_preset_mode: str(s.initial_preset_mode, 'eco'),
    max_acceptable_steady_state_error_c: str(s.max_acceptable_steady_state_error_c, ''),
  }
}

function buildDetail(f: FormState): ModelDetail {
  const num = (v: string) => parseFloat(v)
  const model: Record<string, unknown> = {
    model_type: f.model_type,
    control_mode: f.control_mode,
    initial_temperature: num(f.initial_temperature),
    external_temperature_fixed: num(f.external_temperature_fixed),
  }
  if (f.model_type === 'simple') {
    model.heater_power_watts = num(f.heater_power_watts)
    model.heat_loss_coefficient = num(f.heat_loss_coefficient)
    model.thermal_mass = num(f.thermal_mass)
    model.thermal_inertia = num(f.thermal_inertia)
  }
  if (f.model_type === 'r2c2') {
    model.heater_power_watts_r2c2 = num(f.heater_power_watts_r2c2)
    model.c_air = num(f.c_air)
    model.c_fabric = num(f.c_fabric)
    model.r_fabric = num(f.r_fabric)
    model.r_ext = num(f.r_ext)
    model.r_infiltration = num(f.r_infiltration)
    model.window_area_m2 = num(f.window_area_m2)
    model.window_transmittance = num(f.window_transmittance)
    model.solar_irradiance_fixed = num(f.solar_irradiance_fixed)
  }
  if (f.model_type === 'radiator' || f.model_type === 'r2c2_radiator') {
    model.flow_temperature = num(f.flow_temperature)
    model.c_radiator = num(f.c_radiator)
    model.k_radiator = num(f.k_radiator)
    model.radiator_exponent = num(f.radiator_exponent)
    model.flow_rate_max_kg_s = num(f.flow_rate_max_kg_s)
    model.pipe_delay_seconds = num(f.pipe_delay_seconds)
    model.valve_characteristic = f.valve_characteristic
  }
  if (f.model_type === 'r2c2_radiator') {
    model.radiator_convective_fraction = num(f.radiator_convective_fraction)
    model.c_air = num(f.c_air)
    model.c_fabric = num(f.c_fabric)
    model.r_fabric = num(f.r_fabric)
    model.r_ext = num(f.r_ext)
    model.r_infiltration = num(f.r_infiltration)
    model.window_area_m2 = num(f.window_area_m2)
    model.window_transmittance = num(f.window_transmittance)
    model.solar_irradiance_fixed = num(f.solar_irradiance_fixed)
  }
  if (f.model_type === 'radiator') {
    model.heat_loss_coefficient_rad = num(f.heat_loss_coefficient_rad)
    model.c_room_rad = num(f.c_room_rad)
  }
  const simulation: Record<string, unknown> = {
    duration_hours: num(f.duration_hours),
    step_seconds: num(f.step_seconds),
    record_every_seconds: num(f.record_every_seconds),
    initial_hvac_mode: f.initial_hvac_mode,
    initial_preset_mode: f.initial_preset_mode,
  }
  if (f.max_acceptable_steady_state_error_c.trim()) {
    simulation.max_acceptable_steady_state_error_c = num(f.max_acceptable_steady_state_error_c)
  }
  const sensor: Record<string, unknown> = {
    lag_tau: num(f.sensor_lag_tau),
    bias: num(f.sensor_bias),
    noise_std_dev: num(f.sensor_noise_std_dev),
    quantisation: num(f.sensor_quantisation),
    update_rate_s: num(f.sensor_update_rate_s),
    min_interval_s: num(f.sensor_min_interval_s),
    max_interval_s: num(f.sensor_max_interval_s),
    delta: num(f.sensor_delta),
  }
  const disturbances: Record<string, unknown> = {
    ext_temp_profile: {
      enabled: f.ext_temp_enabled === 'true',
      base: num(f.ext_temp_base),
      amplitude: num(f.ext_temp_amplitude),
      min_hour: num(f.ext_temp_min_hour),
      max_hour: num(f.ext_temp_max_hour),
    },
    occupancy: {
      enabled: f.occ_enabled === 'true',
      max_occupants: num(f.occ_max_occupants),
      cooking_power_w: num(f.occ_cooking_power_w),
      cooking_duration_s: num(f.occ_cooking_duration_s),
      cooking_events_per_day: num(f.occ_cooking_events_per_day),
      seed: num(f.occ_seed),
    },
    weather: {
      wind_speed_m_s: num(f.weather_wind_speed_m_s),
      wind_coefficient: num(f.weather_wind_coefficient),
      rain_intensity: num(f.weather_rain_intensity),
      rain_moisture_factor: num(f.weather_rain_moisture_factor),
    },
  }
  return { name: f.name, description: f.description || undefined, model, simulation, sensor, disturbances }
}

const SLUG_RE = /^[a-z0-9-]+$/

// ── Shared class constants ──────────────────────────────────────────────────

const INPUT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const INPUT_READONLY_CLS = 'bg-slate-800/40 border border-slate-700 text-slate-500 rounded-md px-3 py-1.5 text-sm w-full cursor-not-allowed'
const SELECT_CLS = 'bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500'
const LABEL_CLS = 'text-sm text-slate-300 w-44 flex-shrink-0'

// ── Component ──────────────────────────────────────────────────────────────

interface Props {
  slug: string | null        // null = create mode (slug editable)
  initial: ModelDetail | null // null = use defaults
  onSave: (slug: string, data: ModelDetail) => Promise<void>
  onCancel: () => void
}

export default function ModelForm({ slug, initial, onSave, onCancel }: Props) {
  const isCreate = slug === null
  const [f, setF] = useState<FormState>(() =>
    initial && slug ? initFromDetail(slug, initial) : DEFAULTS
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k: keyof FormState, v: string) => setF(prev => ({ ...prev, [k]: v }))

  const handleSlug = (v: string) =>
    set('slug', v.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 60))

  const slugValid = SLUG_RE.test(f.slug) && f.slug.length <= 60

  const mt = f.model_type

  const numValid = (v: string) => v.trim() !== '' && !isNaN(parseFloat(v))

  const modelNumericsValid = (() => {
    if (!numValid(f.initial_temperature) || !numValid(f.external_temperature_fixed)) return false
    if (mt === 'simple') {
      return numValid(f.heater_power_watts) && numValid(f.heat_loss_coefficient) &&
             numValid(f.thermal_mass) && numValid(f.thermal_inertia)
    }
    if (mt === 'r2c2') {
      return numValid(f.heater_power_watts_r2c2) && numValid(f.c_air) && numValid(f.c_fabric) &&
             numValid(f.r_fabric) && numValid(f.r_ext) && numValid(f.r_infiltration) &&
             numValid(f.window_area_m2) && numValid(f.window_transmittance) && numValid(f.solar_irradiance_fixed)
    }
    if (mt === 'radiator') {
      return numValid(f.flow_temperature) && numValid(f.c_radiator) && numValid(f.k_radiator) &&
             numValid(f.radiator_exponent) && numValid(f.flow_rate_max_kg_s) &&
             numValid(f.heat_loss_coefficient_rad) && numValid(f.c_room_rad) && numValid(f.pipe_delay_seconds)
    }
    if (mt === 'r2c2_radiator') {
      return numValid(f.flow_temperature) && numValid(f.c_radiator) && numValid(f.k_radiator) &&
             numValid(f.radiator_exponent) && numValid(f.radiator_convective_fraction) &&
             numValid(f.flow_rate_max_kg_s) && numValid(f.pipe_delay_seconds) &&
             numValid(f.c_air) && numValid(f.c_fabric) && numValid(f.r_fabric) &&
             numValid(f.r_ext) && numValid(f.r_infiltration) &&
             numValid(f.window_area_m2) && numValid(f.window_transmittance) && numValid(f.solar_irradiance_fixed)
    }
    return false
  })()

  const simNumericsValid = numValid(f.duration_hours) && numValid(f.step_seconds) && numValid(f.record_every_seconds)

  const canSave = f.name.trim() !== '' && (isCreate ? slugValid : true) &&
                  modelNumericsValid && simNumericsValid && !saving

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await onSave(isCreate ? f.slug : slug!, buildDetail(f))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  // ── Field helpers ──────────────────────────────────────────────────────

  const row = (label: string, key: keyof FormState, type: 'text' | 'number' = 'number') => (
    <div key={key} className="flex items-baseline gap-3 mb-3">
      <label className={LABEL_CLS}>{label}</label>
      <input
        type={type}
        className={INPUT_CLS}
        value={f[key] as string}
        onChange={e => set(key, e.target.value)}
      />
    </div>
  )

  const sel = (label: string, key: keyof FormState, opts: string[]) => (
    <div key={key} className="flex items-baseline gap-3 mb-3">
      <label className={LABEL_CLS}>{label}</label>
      <select
        className={SELECT_CLS}
        value={f[key] as string}
        onChange={e => set(key, e.target.value)}
      >
        {opts.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )

  const chk = (label: string, key: keyof FormState) => (
    <div key={key} className="flex items-center gap-3 mb-3">
      <label className={LABEL_CLS}>{label}</label>
      <input
        type="checkbox"
        className="accent-sky-500 w-4 h-4"
        checked={f[key] === 'true'}
        onChange={e => set(key, e.target.checked ? 'true' : 'false')}
      />
    </div>
  )

  const isRadiator = mt === 'radiator' || mt === 'r2c2_radiator'
  const isR2C2 = mt === 'r2c2' || mt === 'r2c2_radiator'

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
        <label className={LABEL_CLS}>slug</label>
        {isCreate ? (
          <div className="flex flex-col gap-0.5 flex-1">
            <input
              type="text"
              className={`${INPUT_CLS} font-mono`}
              placeholder="e.g. my-r2c2-room"
              value={f.slug}
              onChange={e => handleSlug(e.target.value)}
            />
            {!slugValid && f.slug && <p className="text-red-400 text-xs">Lowercase letters, numbers and hyphens only</p>}
          </div>
        ) : (
          <input className={INPUT_READONLY_CLS + ' font-mono'} value={slug!} readOnly />
        )}
      </div>
      {row('name', 'name', 'text')}
      {row('description (optional)', 'description', 'text')}

      {/* Model */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Model
      </h3>
      {sel('model_type', 'model_type', ['simple', 'r2c2', 'radiator', 'r2c2_radiator'])}
      {sel('control_mode', 'control_mode', ['pwm', 'linear'])}
      {row('initial_temperature', 'initial_temperature')}
      {row('external_temperature_fixed', 'external_temperature_fixed')}
      {mt === 'simple' && <>
        {row('heater_power_watts', 'heater_power_watts')}
        {row('heat_loss_coefficient', 'heat_loss_coefficient')}
        {row('thermal_mass', 'thermal_mass')}
        {row('thermal_inertia', 'thermal_inertia')}
      </>}
      {mt === 'r2c2' && row('heater_power_watts_r2c2', 'heater_power_watts_r2c2')}
      {isR2C2 && <>
        {row('c_air', 'c_air')}
        {row('c_fabric', 'c_fabric')}
        {row('r_fabric', 'r_fabric')}
        {row('r_ext', 'r_ext')}
        {row('r_infiltration', 'r_infiltration')}
        {row('window_area_m2', 'window_area_m2')}
        {row('window_transmittance', 'window_transmittance')}
        {row('solar_irradiance_fixed', 'solar_irradiance_fixed')}
      </>}
      {isRadiator && <>
        {row('flow_temperature', 'flow_temperature')}
        {row('c_radiator', 'c_radiator')}
        {row('k_radiator', 'k_radiator')}
        {row('radiator_exponent', 'radiator_exponent')}
        {mt === 'r2c2_radiator' && row('radiator_convective_fraction', 'radiator_convective_fraction')}
        {row('flow_rate_max_kg_s', 'flow_rate_max_kg_s')}
        {mt === 'radiator' && <>
          {row('heat_loss_coefficient_rad', 'heat_loss_coefficient_rad')}
          {row('c_room_rad', 'c_room_rad')}
        </>}
        {row('pipe_delay_seconds', 'pipe_delay_seconds')}
        {sel('valve_characteristic', 'valve_characteristic', ['linear', 'quick_opening'])}
      </>}

      {/* Sensor Pipeline */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Sensor Pipeline
      </h3>
      <p className="text-xs text-slate-500 mb-3">
        Stage 5 (update_rate_s) and Stage 6 (min/max/delta) are mutually exclusive — set the unused group to 0.
      </p>
      {row('lag_tau (s)', 'sensor_lag_tau')}
      {row('bias (°C)', 'sensor_bias')}
      {row('noise_std_dev (°C σ)', 'sensor_noise_std_dev')}
      {row('quantisation (°C)', 'sensor_quantisation')}
      {row('update_rate_s (Stage 5)', 'sensor_update_rate_s')}
      {row('min_interval_s (Stage 6)', 'sensor_min_interval_s')}
      {row('max_interval_s (Stage 6)', 'sensor_max_interval_s')}
      {row('delta (°C, Stage 6)', 'sensor_delta')}

      {/* Disturbances */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Disturbances
      </h3>

      <p className="text-xs text-slate-400 mb-2">External temperature profile</p>
      {chk('enabled', 'ext_temp_enabled')}
      {f.ext_temp_enabled === 'true' && <>
        {row('base (°C)', 'ext_temp_base')}
        {row('amplitude (°C)', 'ext_temp_amplitude')}
        {row('min_hour', 'ext_temp_min_hour')}
        {row('max_hour', 'ext_temp_max_hour')}
      </>}

      <p className="text-xs text-slate-400 mb-2 mt-4">Occupancy &amp; internal gains</p>
      {chk('enabled', 'occ_enabled')}
      {f.occ_enabled === 'true' && <>
        {row('max_occupants', 'occ_max_occupants')}
        {row('cooking_power_w', 'occ_cooking_power_w')}
        {row('cooking_duration_s', 'occ_cooking_duration_s')}
        {row('cooking_events_per_day', 'occ_cooking_events_per_day')}
        {row('seed', 'occ_seed')}
      </>}

      <p className="text-xs text-slate-400 mb-2 mt-4">Weather (0 = disabled)</p>
      {row('wind_speed_m_s', 'weather_wind_speed_m_s')}
      {row('wind_coefficient', 'weather_wind_coefficient')}
      {row('rain_intensity', 'weather_rain_intensity')}
      {row('rain_moisture_factor', 'weather_rain_moisture_factor')}

      {/* Simulation */}
      <h3 className="text-xs uppercase tracking-widest text-slate-500 mb-3 mt-6 pt-5 border-t border-slate-800">
        Simulation
      </h3>
      {row('duration_hours', 'duration_hours')}
      {row('step_seconds', 'step_seconds')}
      {row('record_every_seconds', 'record_every_seconds')}
      {sel('initial_hvac_mode', 'initial_hvac_mode', ['heat', 'cool', 'off'])}
      {sel('initial_preset_mode', 'initial_preset_mode',
        ['none', 'eco', 'comfort', 'boost', 'frost', 'activity', 'away'])}
      {row('max_acceptable_steady_state_error_c (optional)', 'max_acceptable_steady_state_error_c')}

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
