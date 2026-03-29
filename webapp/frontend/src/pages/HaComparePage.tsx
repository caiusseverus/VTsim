import { useCallback, useEffect, useRef, useState } from 'react'
import Plot from 'react-plotly.js'
import { api } from '../api'
import type { HaCompareCell, HaCompareResult, HaCompareSeries } from '../api'

// ---------------------------------------------------------------------------
// Field catalogue — categories, display labels, and defaults
// ---------------------------------------------------------------------------
interface FieldDef {
  key: string
  label: string
  defaultOn: boolean
}

const FIELD_CATEGORIES: { category: string; fields: FieldDef[] }[] = [
  {
    category: 'Thermostat',
    fields: [
      { key: 'device_power_w',        label: 'Device power (W)',          defaultOn: true  },
      { key: 'cycle_min',             label: 'Cycle time (min)',          defaultOn: true  },
      { key: 'near_band_deg',         label: 'Near-band (°C)',            defaultOn: true  },
      { key: 'near_band_source',      label: 'Near-band source',          defaultOn: true  },
      { key: 'tau_min',               label: 'Tau min (s)',               defaultOn: true  },
      { key: 'sat_persistent_cycles', label: 'Sat persistent cycles',     defaultOn: false },
    ],
  },
  {
    category: 'Safety',
    fields: [
      { key: 'safety_delay_min',       label: 'Safety delay (min)',        defaultOn: true  },
      { key: 'safety_min_on_pct',      label: 'Safety min on %',          defaultOn: true  },
      { key: 'safety_default_on_pct',  label: 'Safety default on %',      defaultOn: true  },
    ],
  },
  {
    category: 'Feedforward',
    fields: [
      { key: 'ff_scale_unreliable_max', label: 'FF scale unreliable max', defaultOn: true  },
      { key: 'ff_warmup_ok_count',      label: 'FF warmup ok count',      defaultOn: true  },
      { key: 'ff_taper_alpha',          label: 'FF taper alpha',          defaultOn: true  },
    ],
  },
  {
    category: 'Twin / SmartPI',
    fields: [
      { key: 'twin_control_enabled',   label: 'Twin control enabled',     defaultOn: true  },
      { key: 'twin_sp_filter_active',  label: 'Twin SP filter active',    defaultOn: false },
      { key: 'ki_near_factor',         label: 'Ki near factor',           defaultOn: false },
      { key: 'kp_near_factor',         label: 'Kp near factor',           defaultOn: false },
      { key: 'kp_source',              label: 'Kp source',                defaultOn: false },
    ],
  },
  {
    category: 'Identity',
    fields: [
      { key: 'entity_id',    label: 'Entity ID',    defaultOn: false },
      { key: 'friendly_name', label: 'Friendly name', defaultOn: false },
      { key: 'preset_mode',  label: 'Preset mode',  defaultOn: false },
    ],
  },
  {
    category: 'Emergent',
    fields: [
      { key: 'ab_confidence_state',    label: 'AB confidence state',      defaultOn: false },
      { key: 'calibration_state',      label: 'Calibration state',        defaultOn: false },
      { key: 'diag_ab_mode_effective', label: 'Diag AB mode effective',   defaultOn: false },
      { key: 'tau_reliable',           label: 'Tau reliable',             defaultOn: false },
    ],
  },
]

const ALL_FIELD_DEFS: FieldDef[] = FIELD_CATEGORIES.flatMap(c => c.fields)
const DEFAULT_FIELDS = new Set(ALL_FIELD_DEFS.filter(f => f.defaultOn).map(f => f.key))

// ---------------------------------------------------------------------------
// Colour palette
// ---------------------------------------------------------------------------
const PALETTE = [
  '#38bdf8', '#fb923c', '#a78bfa', '#34d399', '#f472b6',
  '#facc15', '#e879f9', '#60a5fa', '#f87171', '#4ade80',
  '#c084fc', '#fb7185', '#a3e635', '#22d3ee', '#fbbf24',
  '#818cf8', '#0ea5e9', '#84cc16', '#f97316', '#e11d48',
]

function valueColorMap(values: (string | null)[]): Record<string, string> {
  const unique = [...new Set(values.filter(Boolean))] as string[]
  return Object.fromEntries(unique.map((v, i) => [v, PALETTE[i % PALETTE.length]]))
}

function buildGlobalColorMap(result: HaCompareResult): Record<string, string> {
  const allValues: string[] = []
  for (const field of result.mode_fields) {
    const s = result.series[field]
    if (!s) continue
    allValues.push(...(s.a.values as (string | null)[]).filter(Boolean) as string[])
    allValues.push(...(s.b.values as (string | null)[]).filter(Boolean) as string[])
  }
  return valueColorMap(allValues)
}

// ---------------------------------------------------------------------------
// Gantt chart (categorical timeline)
// ---------------------------------------------------------------------------
function buildGanttTraces(
  series: HaCompareSeries,
  labelA: string,
  labelB: string,
  colorMap: Record<string, string>,
): object[] {
  const traces: object[] = []

  for (const [s, label] of [[series.a, labelA], [series.b, labelB]] as const) {
    const times = s.times_h as number[]
    const values = s.values as (string | null)[]
    const segs: Record<string, { base: number; width: number }[]> = {}

    for (let i = 0; i < times.length; i++) {
      const v = values[i]
      if (!v) continue
      const tEnd = i + 1 < times.length
        ? times[i + 1]
        : times[i] + (times[times.length - 1] - times[0]) / Math.max(times.length - 1, 1)
      if (!segs[v]) segs[v] = []
      segs[v].push({ base: times[i], width: Math.max(tEnd - times[i], 1e-9) })
    }

    for (const [val, segList] of Object.entries(segs)) {
      traces.push({
        type: 'bar', orientation: 'h',
        y: segList.map(() => label),
        x: segList.map(s => s.width),
        base: segList.map(s => s.base),
        name: val,
        legendgroup: val,
        showlegend: label === labelA,
        marker: { color: colorMap[val] ?? '#888' },
        hovertemplate: `<b>${val}</b><br>from %{base:.3f}h<extra>${label}</extra>`,
      })
    }
  }
  return traces
}

function GanttChart({ title, series, labelA, labelB, colorMap }: {
  title: string; series: HaCompareSeries; labelA: string; labelB: string
  colorMap: Record<string, string>
}) {
  const maxT = Math.max(...(series.a.times_h as number[]), ...(series.b.times_h as number[]), 1)
  return (
    <div className="mb-1">
      <div className="text-xs text-slate-400 font-mono pl-1 mb-0.5">{title}</div>
      <Plot
        data={buildGanttTraces(series, labelA, labelB, colorMap) as Plotly.Data[]}
        layout={{
          paper_bgcolor: 'transparent', plot_bgcolor: '#1e293b',
          font: { color: '#e2e8f0', size: 10 },
          height: 88, margin: { t: 2, b: 26, l: 130, r: 8 },
          barmode: 'overlay',
          xaxis: { range: [0, maxT], gridcolor: '#334155', tickcolor: '#475569', title: { text: 'h', font: { size: 9 } } },
          yaxis: { gridcolor: '#334155', tickcolor: '#475569', fixedrange: true },
          legend: { orientation: 'h', x: 0, y: 1.22, font: { size: 8 }, bgcolor: 'rgba(0,0,0,0)' },
          showlegend: true,
        } as object}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Numeric chart
// ---------------------------------------------------------------------------
const NUMERIC_YLABELS: Record<string, string> = {
  on_percent: 'On %', a: 'a', b: 'b', error: 'Error (°C)',
}

function NumericChart({ title, series, labelA, labelB }: {
  title: string; series: HaCompareSeries; labelA: string; labelB: string
}) {
  function toTrace(s: HaCompareSeries['a'], label: string, dash: 'solid' | 'dash') {
    const pairs = (s.times_h as number[])
      .map((t, i) => [t, s.values[i]] as [number, number | null])
      .filter(([, v]) => v != null) as [number, number][]
    if (!pairs.length) return null
    return { type: 'scatter', mode: 'lines', x: pairs.map(p => p[0]), y: pairs.map(p => p[1]), name: label, line: { width: 1.4, dash } }
  }
  const traces = [toTrace(series.a, labelA, 'solid'), toTrace(series.b, labelB, 'dash')].filter(Boolean)
  return (
    <div className="mb-1">
      <div className="text-xs text-slate-400 font-mono pl-1 mb-0.5">{title}</div>
      <Plot
        data={traces as Plotly.Data[]}
        layout={{
          paper_bgcolor: 'transparent', plot_bgcolor: '#1e293b',
          font: { color: '#e2e8f0', size: 10 },
          height: 110, margin: { t: 2, b: 26, l: 55, r: 8 },
          xaxis: { gridcolor: '#334155', tickcolor: '#475569', title: { text: 'h', font: { size: 9 } } },
          yaxis: { gridcolor: '#334155', tickcolor: '#475569', title: { text: NUMERIC_YLABELS[title] ?? title, font: { size: 9 } } },
          legend: { orientation: 'h', x: 0, y: 1.15, font: { size: 9 }, bgcolor: 'rgba(0,0,0,0)' },
        } as object}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: '100%' }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field selector panel
// ---------------------------------------------------------------------------
function FieldSelector({ selected, onChange }: {
  selected: Set<string>
  onChange: (s: Set<string>) => void
}) {
  const toggle = (key: string) => {
    const next = new Set(selected)
    next.has(key) ? next.delete(key) : next.add(key)
    onChange(next)
  }
  const setAll = (on: boolean) => onChange(on ? new Set(ALL_FIELD_DEFS.map(f => f.key)) : new Set())
  const resetDefaults = () => onChange(new Set(DEFAULT_FIELDS))

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 mb-3">
      <div className="flex items-center gap-3 mb-2">
        <span className="text-xs text-slate-300 font-semibold">Visible fields</span>
        <button onClick={() => setAll(true)}  className="text-xs text-sky-400 hover:text-sky-300">All</button>
        <button onClick={() => setAll(false)} className="text-xs text-sky-400 hover:text-sky-300">None</button>
        <button onClick={resetDefaults}       className="text-xs text-sky-400 hover:text-sky-300">Defaults</button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-0.5">
        {FIELD_CATEGORIES.map(cat => (
          <div key={cat.category}>
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mt-2 mb-0.5">
              {cat.category}
            </div>
            {cat.fields.map(f => (
              <label key={f.key} className="flex items-center gap-1.5 cursor-pointer hover:text-slate-100 py-0.5">
                <input
                  type="checkbox"
                  className="accent-sky-500 w-3 h-3"
                  checked={selected.has(f.key)}
                  onChange={() => toggle(f.key)}
                />
                <span className="text-xs text-slate-300">{f.label}</span>
              </label>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Config diff table
// ---------------------------------------------------------------------------
function ConfigDiffTable({ result, visibleFields, onToggleFields, showFieldSelector }: {
  result: HaCompareResult
  visibleFields: Set<string>
  onToggleFields: () => void
  showFieldSelector: boolean
}) {
  const fieldLabelMap = Object.fromEntries(ALL_FIELD_DEFS.map(f => [f.key, f.label]))
  const rows = result.config_diff.filter(r => visibleFields.has(r.field))

  return (
    <>
      <div className="flex items-center gap-2 px-4 py-2 bg-slate-800/50 border-b border-slate-800">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex-1">Configuration</span>
        <button
          onClick={onToggleFields}
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            showFieldSelector
              ? 'bg-sky-800 border-sky-600 text-sky-200'
              : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-500'
          }`}
        >
          ⚙ Fields ({visibleFields.size})
        </button>
      </div>
      {rows.length === 0
        ? <p className="text-slate-500 text-xs px-4 py-3 italic">No fields selected.</p>
        : (
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse w-full">
              <thead>
                <tr className="bg-slate-800/40">
                  <th className="px-3 py-1.5 text-left font-mono text-slate-400 border-b border-slate-700 w-40">Field</th>
                  <th className="px-3 py-1.5 text-left font-mono text-sky-400 border-b border-slate-700">{result.label_a}</th>
                  <th className="px-3 py-1.5 text-left font-mono text-amber-400 border-b border-slate-700">{result.label_b}</th>
                  <th className="px-3 py-1.5 text-center border-b border-slate-700 w-6"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.field} className={`border-b border-slate-800 ${row.match ? '' : 'bg-amber-950/25'}`}>
                    <td className="px-3 py-1 font-mono text-slate-400">{fieldLabelMap[row.field] ?? row.field}</td>
                    <td className="px-3 py-1 text-slate-200">{String(row.a ?? '—')}</td>
                    <td className="px-3 py-1 text-slate-200">{String(row.b ?? '—')}</td>
                    <td className="px-3 py-1 text-center">
                      {row.match
                        ? <span className="text-emerald-400">✓</span>
                        : <span className="text-amber-400">≠</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </>
  )
}

// ---------------------------------------------------------------------------
// Source selector panel
// ---------------------------------------------------------------------------
type SourceState =
  | { mode: 'none' }
  | { mode: 'run'; run_id: string; model: string; cell: string; label: string }
  | { mode: 'upload'; file_id: string; label: string }

function CellList({ cells, selected, onSelect }: {
  cells: HaCompareCell[]
  selected: SourceState
  onSelect: (c: HaCompareCell) => void
}) {
  const [filter, setFilter] = useState('')
  const filtered = filter.trim()
    ? cells.filter(c => c.label.toLowerCase().includes(filter.toLowerCase()))
    : cells

  const selectedKey = selected.mode === 'run'
    ? `${selected.run_id}|${selected.model}|${selected.cell}`
    : null

  return (
    <div>
      <input
        type="text"
        placeholder="Filter runs…"
        value={filter}
        onChange={e => setFilter(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 mb-1"
      />
      <div className="overflow-y-auto max-h-44 rounded border border-slate-700 divide-y divide-slate-800">
        {filtered.length === 0 && (
          <p className="text-slate-500 text-xs px-3 py-2 italic">
            {cells.length === 0 ? 'No ha_export.json files found. Run a simulation first.' : 'No matches.'}
          </p>
        )}
        {filtered.map(c => {
          const key = `${c.run_id}|${c.model}|${c.cell}`
          const isSelected = key === selectedKey
          return (
            <button
              key={key}
              onClick={() => onSelect(c)}
              className={`w-full text-left px-3 py-1.5 text-xs font-mono transition-colors ${
                isSelected
                  ? 'bg-sky-900/50 text-sky-300'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {c.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function SourcePanel({ cells, sideLabel, value, onChange }: {
  cells: HaCompareCell[]
  sideLabel: 'A' | 'B'
  value: SourceState
  onChange: (s: SourceState) => void
}) {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const uploadFile = useCallback(async (file: File) => {
    setUploading(true)
    setUploadError('')
    try {
      const { file_id } = await api.haCompareUpload(file)
      onChange({ mode: 'upload', file_id, label: file.name })
    } catch (e) {
      setUploadError(String(e))
    } finally {
      setUploading(false)
    }
  }, [onChange])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }, [uploadFile])

  const accentText  = sideLabel === 'A' ? 'text-sky-400'    : 'text-amber-400'
  const accentBorder = sideLabel === 'A' ? 'border-sky-600'  : 'border-amber-600'
  const accentBg    = sideLabel === 'A' ? 'bg-sky-900/20'    : 'bg-amber-900/20'

  const resolvedLabel = value.mode === 'run'    ? value.label
                      : value.mode === 'upload' ? value.label
                      : null

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden flex flex-col gap-0">
      {/* Header */}
      <div className="bg-slate-800/50 border-b border-slate-800 px-4 py-2 flex items-center gap-2">
        <span className={`text-xs font-bold ${accentText}`}>Source {sideLabel}</span>
        {resolvedLabel && (
          <span className="text-xs text-slate-400 font-mono truncate flex-1">{resolvedLabel}</span>
        )}
      </div>

      <div className="p-3 flex flex-col gap-3">
        {/* Run result picker */}
        <div>
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">From run result</div>
          <CellList
            cells={cells}
            selected={value}
            onSelect={c => onChange({ mode: 'run', run_id: c.run_id, model: c.model, cell: c.cell, label: c.label })}
          />
        </div>

        {/* Divider */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-slate-800" />
          <span className="text-xs text-slate-600">or upload</span>
          <div className="flex-1 h-px bg-slate-800" />
        </div>

        {/* File drop zone */}
        <div
          className={`border-2 border-dashed rounded-lg p-3 text-center cursor-pointer transition-colors
            ${dragOver ? `${accentBorder} ${accentBg}` : 'border-slate-700 hover:border-slate-600'}
            ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".json" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f) }} />
          {uploading
            ? <span className="text-slate-400 text-xs">Uploading…</span>
            : value.mode === 'upload'
              ? <span className="text-emerald-400 text-xs">✓ {value.label}</span>
              : <span className="text-slate-500 text-xs">Drop ha_export.json or click to browse</span>
          }
        </div>
        {uploadError && <p className="text-red-400 text-xs">{uploadError}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function HaComparePage() {
  const [cells, setCells] = useState<HaCompareCell[]>([])
  const [sourceA, setSourceA] = useState<SourceState>({ mode: 'none' })
  const [sourceB, setSourceB] = useState<SourceState>({ mode: 'none' })
  const [comparing, setComparing] = useState(false)
  const [compareError, setCompareError] = useState('')
  const [result, setResult] = useState<HaCompareResult | null>(null)
  const [visibleFields, setVisibleFields] = useState<Set<string>>(new Set(DEFAULT_FIELDS))
  const [showFieldSelector, setShowFieldSelector] = useState(false)

  useEffect(() => {
    api.haCompareCells().then(setCells).catch(console.error)
  }, [])

  function toApiSource(s: SourceState) {
    if (s.mode === 'run')    return { type: 'run_cell' as const, run_id: s.run_id, model: s.model, cell: s.cell }
    if (s.mode === 'upload') return { type: 'upload'   as const, file_id: s.file_id }
    return null
  }

  async function runCompare() {
    const a = toApiSource(sourceA), b = toApiSource(sourceB)
    if (!a || !b) return
    setComparing(true); setCompareError(''); setResult(null)
    try {
      setResult(await api.haCompare(
        a as Parameters<typeof api.haCompare>[0],
        b as Parameters<typeof api.haCompare>[1],
      ))
    } catch (e) {
      setCompareError(String(e))
    } finally {
      setComparing(false)
    }
  }

  const canCompare = sourceA.mode !== 'none' && sourceB.mode !== 'none'
  const globalColorMap = result ? buildGlobalColorMap(result) : {}

  return (
    <div className="-mx-6 max-w-7xl mx-auto px-6">
      <div className="mb-5">
        <h1 className="text-slate-100 text-xl font-semibold">HA Export Comparison</h1>
      </div>

      {/* Source selectors */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <SourcePanel cells={cells} sideLabel="A" value={sourceA} onChange={setSourceA} />
        <SourcePanel cells={cells} sideLabel="B" value={sourceB} onChange={setSourceB} />
      </div>

      {/* Compare button */}
      <div className="flex justify-center mb-6">
        <button
          disabled={!canCompare || comparing}
          onClick={runCompare}
          className="px-8 py-2 rounded bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
        >
          {comparing ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {compareError && <p className="text-red-400 text-sm mb-4">{compareError}</p>}

      {result && (
        <div className="space-y-5">

          {/* Config diff */}
          <section className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <ConfigDiffTable
              result={result}
              visibleFields={visibleFields}
              onToggleFields={() => setShowFieldSelector(v => !v)}
              showFieldSelector={showFieldSelector}
            />
            {showFieldSelector && (
              <div className="px-4 py-3 border-t border-slate-800">
                <FieldSelector selected={visibleFields} onChange={setVisibleFields} />
              </div>
            )}
          </section>

          {/* Mode timelines */}
          <section className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <div className="bg-slate-800/50 border-b border-slate-800 px-4 py-2 flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">SmartPI mode timelines</span>
              <span className="text-xs text-slate-500">
                <span className="text-sky-400">▬</span> {result.label_a} &nbsp;
                <span className="text-amber-400">▬</span> {result.label_b}
              </span>
            </div>
            <div className="p-3">
              {result.mode_fields.map(field => {
                const s = result.series[field]
                return s ? (
                  <GanttChart key={field} title={field} series={s}
                    labelA={result.label_a} labelB={result.label_b} colorMap={globalColorMap} />
                ) : null
              })}
            </div>
          </section>

          {/* Numeric signals */}
          <section className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <div className="bg-slate-800/50 border-b border-slate-800 px-4 py-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Key signals</span>
            </div>
            <div className="p-3">
              {result.numeric_fields.map(field => {
                const s = result.series[field]
                return s ? (
                  <NumericChart key={field} title={field} series={s}
                    labelA={result.label_a} labelB={result.label_b} />
                ) : null
              })}
            </div>
          </section>

        </div>
      )}
    </div>
  )
}
