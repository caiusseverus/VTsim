// webapp/frontend/src/pages/ModelsPage.tsx
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ModelSummary, ModelDetail } from '../api'
import Modal from '../components/Modal'
import ModelForm from '../components/ModelForm'

export default function ModelsPage() {
  const [models, setModels] = useState<ModelSummary[]>([])
  const [error, setError] = useState('')

  // Modal state
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null)
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [editData, setEditData] = useState<ModelDetail | null>(null)

  const load = () => api.listModels().then(setModels).catch(e => setError(String(e)))
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditSlug(null)
    setEditData(null)
    setModalMode('create')
  }

  const openEdit = async (slug: string) => {
    try {
      const data = await api.getModel(slug)
      setEditSlug(slug)
      setEditData(data)
      setModalMode('edit')
    } catch (e) {
      setError(String(e))
    }
  }

  const closeModal = () => {
    setModalMode(null)
    setEditSlug(null)
    setEditData(null)
  }

  const handleSave = async (slug: string, data: ModelDetail) => {
    if (modalMode === 'create') {
      await api.createModel(slug, data)
    } else {
      await api.saveModel(slug, data)
    }
    closeModal()
    load()
  }

  const handleDelete = async (slug: string) => {
    if (!confirm(`Delete model "${slug}"?`)) return
    await api.deleteModel(slug)
    load()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">Models</h1>
        <button onClick={openCreate}
          className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
          New Model
        </button>
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
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Slug</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Name</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Type</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Control</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Duration</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {models.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500 text-sm">
                  No models yet.
                </td>
              </tr>
            ) : (
              models.map(m => (
                <tr key={m.slug} className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-sky-400 text-xs">{m.slug}</span>
                  </td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{m.name}</td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{m.model_type}</td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{m.control_mode}</td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{m.duration_hours}h</td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-4">
                      <button onClick={() => openEdit(m.slug)}
                        className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Edit</button>
                      <button
                        onClick={async () => {
                          const newSlug = window.prompt(`Clone "${m.slug}" — enter new slug:`)
                          if (!newSlug?.trim()) return
                          try {
                            await api.cloneModel(m.slug, newSlug.trim())
                            load()
                          } catch (e) { setError(String(e)) }
                        }}
                        className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Clone</button>
                      <button onClick={() => handleDelete(m.slug)}
                        className="text-slate-400 hover:text-red-400 text-sm transition-colors">Delete</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {modalMode && (
        <Modal
          title={modalMode === 'create' ? 'New Model' : `Edit: ${editSlug}`}
          onClose={closeModal}
        >
          <ModelForm
            slug={modalMode === 'edit' ? editSlug : null}
            initial={editData}
            onSave={handleSave}
            onCancel={closeModal}
          />
        </Modal>
      )}
    </div>
  )
}
