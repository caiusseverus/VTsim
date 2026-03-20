// webapp/frontend/src/pages/PresetsPage.tsx
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Preset } from '../api'
import Modal from '../components/Modal'
import PresetForm from '../components/PresetForm'
import ConfigImporter from '../components/ConfigImporter'

export default function PresetsPage() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [error, setError] = useState('')

  // Modal state
  const [modalMode, setModalMode] = useState<'create' | 'edit' | 'import' | null>(null)
  const [editPreset, setEditPreset] = useState<Preset | null>(null)

  const load = () => api.listPresets().then(setPresets).catch(e => setError(String(e)))
  useEffect(() => { load() }, [])

  const closeModal = () => {
    setModalMode(null)
    setEditPreset(null)
  }

  const handleSave = async (data: { id: string; name: string; control: Record<string, unknown>; temperatures: Record<string, unknown> }) => {
    if (modalMode === 'create') {
      await api.createPreset(data as Preset)
    } else {
      const { id, ...rest } = data
      await api.updatePreset(id, rest)
    }
    closeModal()
    load()
  }

  const handleSaveImport = async (name: string, overrides: Record<string, unknown>) => {
    const id = name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
    const control: Record<string, unknown> = {}
    const temperatures: Record<string, unknown> = {}
    const tempKeys = ['eco_temp','comfort_temp','boost_temp','frost_temp','min_temp','max_temp','target_temp',
                      'eco_away_temp','comfort_away_temp','boost_away_temp','frost_away_temp','temp_min','temp_max']
    for (const [k, v] of Object.entries(overrides)) {
      if (tempKeys.includes(k)) temperatures[k] = v
      else control[k] = v
    }
    try {
      await api.createPreset({ id, name, control, temperatures })
      closeModal()
      load()
    } catch (e) { setError(String(e)) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete preset "${id}"?`)) return
    await api.deletePreset(id)
    load()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">Presets</h1>
        <div className="flex gap-2">
          <button onClick={() => setModalMode('import')}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-md px-4 py-1.5 text-sm">
            Import from HA State
          </button>
          <button onClick={() => { setEditPreset(null); setModalMode('create') }}
            className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
            New Preset
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-800 text-red-300 text-sm rounded-md px-4 py-2 mb-4">
          {error}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-slate-800/50">
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">ID</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Name</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Control</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Temperatures</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {presets.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500 text-sm">
                  No presets yet.
                </td>
              </tr>
            ) : (
              presets.map(p => (
                <tr key={p.id} className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-sky-400 text-xs">{p.id}</span>
                  </td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{p.name}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-400 space-x-2">
                    {Object.entries(p.control || {}).map(([k, v]) => (
                      <span key={k}><span className="text-slate-500">{k}:</span> {String(v)}</span>
                    ))}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-400 space-x-2">
                    {Object.entries(p.temperatures || {}).map(([k, v]) => (
                      <span key={k}><span className="text-slate-500">{k}:</span> {String(v)}</span>
                    ))}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-4">
                      <button onClick={() => { setEditPreset(p); setModalMode('edit') }}
                        className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Edit</button>
                      <button
                        onClick={async () => {
                          const newId = window.prompt(`Clone "${p.id}" — enter new ID:`)
                          if (!newId?.trim()) return
                          const newName = window.prompt('Name for the clone:', `${p.name} (copy)`) ?? `${p.name} (copy)`
                          try {
                            await api.clonePreset(p.id, newId.trim(), newName.trim() || newId.trim())
                            load()
                          } catch (e) { setError(String(e)) }
                        }}
                        className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Clone</button>
                      <button onClick={() => handleDelete(p.id)}
                        className="text-slate-400 hover:text-red-400 text-sm transition-colors">Delete</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* New / Edit preset modal */}
      {(modalMode === 'create' || modalMode === 'edit') && (
        <Modal
          title={modalMode === 'create' ? 'New Preset' : `Edit: ${editPreset?.id}`}
          onClose={closeModal}
        >
          <PresetForm
            preset={editPreset}
            onSave={handleSave}
            onCancel={closeModal}
          />
        </Modal>
      )}

      {/* Import from HA State modal */}
      {modalMode === 'import' && (
        <Modal title="Import from HA State" onClose={closeModal}>
          <ConfigImporter
            onSave={handleSaveImport}
            onCancel={closeModal}
          />
        </Modal>
      )}
    </div>
  )
}
