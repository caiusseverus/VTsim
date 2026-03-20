import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import type { Run, RunCell } from '../api'
import MetricsTable from '../components/MetricsTable'
import MultiMetricPlot from '../components/MultiMetricPlot'
import StatusBadge from '../components/StatusBadge'

export default function ResultsPage() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const [selectedCell, setSelectedCell] = useState<RunCell | null>(null)
  const [viewAll, setViewAll] = useState(false)

  const load = useCallback(() => {
    if (!runId) return
    api.getRun(runId).then(r => {
      setRun(r)
      if (!selectedCell && r.cells.length > 0) setSelectedCell(r.cells[0])
    }).catch(console.error)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  useEffect(load, [load])

  useEffect(() => {
    if (!run || run.status === 'complete' || run.status === 'partial_failure') return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [run, load])

  if (!run) return <p className="text-slate-400">Loading…</p>

  const versionPreset = selectedCell
    ? `${selectedCell.vt_version}_${selectedCell.preset}` : ''

  const completedCells = run.cells.filter(c => c.status === 'complete')

  return (
    <div className="-mx-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6 px-6">
        <div>
          <h1 className="text-slate-100 text-xl font-semibold">{run.name}</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            <StatusBadge status={run.status} /> · {run.cells?.length ?? 0} cells
          </p>
        </div>
      </div>

      <div className="px-6 space-y-6">
        <MetricsTable cells={run.cells} onSelectCell={setSelectedCell} selectedCell={selectedCell} />

        {selectedCell && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mt-4">
            {/* Cell identity breadcrumb */}
            <div className="flex items-center gap-2 mb-3">
              <span className="font-mono text-sky-400 text-xs">{selectedCell.model}</span>
              <span className="text-slate-600">/</span>
              <span className="font-mono text-sky-400 text-xs">{selectedCell.vt_version}</span>
              <span className="text-slate-600">/</span>
              <span className="font-mono text-sky-400 text-xs">{selectedCell.preset}</span>
            </div>

            <MultiMetricPlot
              runId={runId!}
              model={selectedCell.model}
              version={selectedCell.vt_version}
              preset={selectedCell.preset}
              status={selectedCell.status}
            />

            {selectedCell.status === 'complete' && (
              <div className="mt-4">
                <img
                  src={api.resultPlotUrl(runId!, selectedCell.model, versionPreset)}
                  alt="Full simulation plot"
                  className="w-full rounded border border-slate-700"
                />
                <div className="mt-2">
                  <a
                    className="text-sky-400 hover:text-sky-300 text-sm underline"
                    href={api.resultPlotUrl(runId!, selectedCell.model, versionPreset)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View full plot
                  </a>
                  <a
                    className="text-sky-400 hover:text-sky-300 text-sm underline ml-4"
                    href={api.resultRecordsUrl(runId!, selectedCell.model, versionPreset)}
                    download
                  >
                    Download CSV
                  </a>
                </div>
              </div>
            )}

            {selectedCell.status === 'failed' && (
              <div className="mt-3 bg-red-900/40 border border-red-800 rounded p-3">
                <pre className="text-red-300 text-xs overflow-auto max-h-40">
                  {selectedCell.error}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* Show all plots toggle */}
        <div>
          <button
            onClick={() => setViewAll(v => !v)}
            className="text-slate-400 hover:text-slate-100 text-sm mt-6 mb-4"
          >
            {viewAll ? '▲ Hide all plots' : '▼ Show all plots'}
          </button>

          {viewAll && (
            <div className="grid grid-cols-2 gap-4">
              {completedCells.map(cell => {
                const cellVersionPreset = `${cell.vt_version}_${cell.preset}`
                const plotUrl = api.resultPlotUrl(runId!, cell.model, cellVersionPreset)
                return (
                  <div
                    key={`${cell.model}-${cell.vt_version}-${cell.preset}`}
                    className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden"
                  >
                    <img src={plotUrl} className="w-full" alt={cell.model} />
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
