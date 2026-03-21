import type { RunCell } from '../api'

const METRIC_KEYS = [
  'steady_state_error_c', 'energy_kwh', 'switch_cycles',
  'max_overshoot_c', 'settling_time_h',
  'smartpi_a_final', 'smartpi_b_final', 'deadtime_heat_s', 'deadtime_cool_s',
]

const HIGH_PRECISION_KEYS = new Set(['smartpi_a_final', 'smartpi_b_final'])

function cellColor(key: string, value: number | null): string {
  if (value === null) return 'text-slate-300'
  if (key === 'steady_state_error_c') {
    return value < 0.2 ? 'text-emerald-400' : value < 0.5 ? 'text-amber-400' : 'text-red-400'
  }
  return 'text-slate-300'
}

interface Props {
  cells: RunCell[]
  onSelectCell: (cell: RunCell) => void
  selectedCell: RunCell | null
}

export default function MetricsTable({ cells, onSelectCell, selectedCell }: Props) {
  const models = [...new Set(cells.map(c => c.model))]
  const combos = [...new Set(cells.map(c => `${c.vt_version}::${c.preset}`))]

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-x-auto">
      <table className="border-collapse text-xs">
        <thead>
          <tr>
            <th className="bg-slate-800 text-slate-400 px-3 py-2 font-semibold text-left whitespace-nowrap border-b border-slate-700">Model</th>
            {combos.map(combo => (
              <th key={combo} className="bg-slate-800 text-slate-400 px-3 py-2 font-semibold text-left whitespace-nowrap border-b border-slate-700 font-mono">{combo.replace('::', '/')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map(model => (
            <tr key={model}>
              <td className="bg-slate-900 px-3 py-2 border-b border-slate-800 font-mono text-slate-300 whitespace-nowrap">{model}</td>
              {combos.map(combo => {
                const sepIdx = combo.indexOf('::')
                const vt_version = combo.slice(0, sepIdx)
                const preset = combo.slice(sepIdx + 2)
                const cell = cells.find(c => c.model === model &&
                  c.vt_version === vt_version && c.preset === preset)
                const isSelected = selectedCell?.model === model &&
                  selectedCell?.vt_version === vt_version && selectedCell?.preset === preset
                if (!cell) return (
                  <td key={combo} className="bg-slate-900 px-3 py-2 border-b border-slate-800 text-slate-600">—</td>
                )
                return (
                  <td key={combo}
                    onClick={() => onSelectCell(cell)}
                    className={isSelected
                      ? 'bg-sky-900/60 ring-1 ring-inset ring-sky-500 px-3 py-2 border-b border-slate-800 cursor-pointer'
                      : 'bg-slate-900 px-3 py-2 border-b border-slate-800 cursor-pointer transition-colors hover:bg-slate-800/40'
                    }>
                    {cell.status === 'running' && (
                      <span className="text-sky-300 animate-pulse">Running…</span>
                    )}
                    {cell.status === 'pending' && (
                      <span className="text-slate-500">Pending</span>
                    )}
                    {cell.status === 'failed' && (
                      <span className="text-red-400" title={cell.error}>Failed</span>
                    )}
                    {cell.status === 'complete' && cell.metrics && (
                      <div className="space-y-0.5">
                        {METRIC_KEYS.map(k => {
                          const v = cell.metrics![k] as number | null
                          if (v === null || v === undefined) return null
                          return (
                            <div key={k} className="flex justify-between gap-2">
                              <span className="text-slate-500">{k.replace(/_/g,' ')}</span>
                              <span className={`font-mono ${cellColor(k, v)}`}>{typeof v === 'number' ? v.toFixed(HIGH_PRECISION_KEYS.has(k) ? 6 : 4) : v}</span>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
