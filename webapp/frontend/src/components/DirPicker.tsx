// Filesystem directory picker modal — navigates the backend's filesystem.
import { useState, useEffect } from 'react'
import { api } from '../api'

interface DirNode {
  path: string
  dirs: string[]
  parent: string | null
}

interface Props {
  initialPath?: string
  onSelect: (path: string) => void
  onClose: () => void
}

export default function DirPicker({ initialPath, onSelect, onClose }: Props) {
  const [node, setNode] = useState<DirNode | null>(null)
  const [inputPath, setInputPath] = useState(initialPath || '')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const navigate = async (path: string) => {
    setLoading(true)
    setError('')
    try {
      const result = await api.browseFs(path)
      setNode(result)
      setInputPath(result.path)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { navigate(initialPath || '') }, [])

  const ROW_CLS = 'w-full text-left px-3 py-1.5 rounded text-sm font-mono hover:bg-slate-800 transition-colors'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-slate-900 border border-slate-700 rounded-lg w-[600px] max-h-[70vh] flex flex-col shadow-xl">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
          <h2 className="text-slate-100 font-semibold text-sm">Select Directory</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-xl leading-none">&times;</button>
        </div>

        {/* Path input bar */}
        <div className="flex gap-2 px-4 py-2 border-b border-slate-800">
          <input
            className="flex-1 bg-slate-800 border border-slate-700 text-slate-100 rounded px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
            value={inputPath}
            onChange={e => setInputPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && navigate(inputPath)}
          />
          <button
            onClick={() => navigate(inputPath)}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm px-3 py-1.5 rounded transition-colors">
            Go
          </button>
        </div>

        {/* Directory listing */}
        <div className="flex-1 overflow-y-auto px-4 py-2 min-h-0">
          {error && <p className="text-red-400 text-sm py-2">{error}</p>}
          {loading && <p className="text-slate-500 text-sm py-2">Loading...</p>}
          {!loading && node && (
            <ul className="space-y-px">
              {node.parent !== null && (
                <li>
                  <button onClick={() => navigate(node.parent!)} className={`${ROW_CLS} text-slate-400`}>
                    ..
                  </button>
                </li>
              )}
              {node.dirs.length === 0 && (
                <li className="px-3 py-2 text-slate-500 text-sm">No subdirectories</li>
              )}
              {node.dirs.map(d => (
                <li key={d}>
                  <button
                    onClick={() => navigate(`${node.path}/${d}`)}
                    className={`${ROW_CLS} text-slate-200`}>
                    {d}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800">
          <span className="text-slate-400 text-xs font-mono truncate max-w-[380px]">{node?.path || ''}</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-sm px-3 py-1.5 transition-colors">
              Cancel
            </button>
            <button
              onClick={() => node && onSelect(node.path)}
              disabled={!node}
              className="bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-sm font-medium rounded px-4 py-1.5 transition-colors">
              Select
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
