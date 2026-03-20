// webapp/frontend/src/pages/VtVersionsPage.tsx
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { VtVersion } from '../api'

export default function VtVersionsPage() {
  const [versions, setVersions] = useState<VtVersion[]>([])
  const [newName, setNewName] = useState('')
  const [newPath, setNewPath] = useState('')
  const [error, setError] = useState('')

  const load = () => api.listVtVersions().then(setVersions).catch(e => setError(String(e)))
  useEffect(() => { load() }, [])

  const handleRegister = async () => {
    setError('')
    try {
      await api.registerVtVersion(newName.trim(), newPath.trim())
      setNewName(''); setNewPath('')
      load()
    } catch (e) { setError(String(e)) }
  }

  const handleRemove = async (name: string) => {
    if (!confirm(`Remove VT version "${name}"?`)) return
    await api.removeVtVersion(name)
    load()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">VT Versions</h1>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-800 text-red-300 text-sm rounded-md px-4 py-2 mb-4">
          {error}
        </div>
      )}

      {/* Registration form */}
      <div className="flex gap-3 mb-6">
        <input
          className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
          placeholder="Name (e.g. v9.1.0)"
          value={newName}
          onChange={e => setNewName(e.target.value)}
        />
        <input
          className="bg-slate-800 border border-slate-700 text-slate-100 rounded-md px-3 py-1.5 text-sm flex-1 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500 focus:border-sky-500"
          placeholder="/path/to/versatile_thermostat"
          value={newPath}
          onChange={e => setNewPath(e.target.value)}
        />
        <button onClick={handleRegister}
          className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
          Register
        </button>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-slate-800/50">
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Name</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Path</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-slate-500 text-sm">
                  No VT versions registered yet.
                </td>
              </tr>
            ) : (
              versions.map(v => (
                <tr key={v.name} className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2.5 text-sm text-slate-200">{v.name}</td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-sky-400 text-xs">{v.path}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-4">
                      <button onClick={() => handleRemove(v.name)}
                        className="text-slate-400 hover:text-red-400 text-sm transition-colors">Remove</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
