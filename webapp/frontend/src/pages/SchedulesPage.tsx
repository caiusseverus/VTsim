// webapp/frontend/src/pages/SchedulesPage.tsx
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Schedule } from '../api'
import Modal from '../components/Modal'
import ScheduleForm from '../components/ScheduleForm'

function summarise(s: Schedule): string {
  if (s.type === 'pattern') {
    return `pattern · ${s.interval_hours}h · ${s.low_temp}→${s.high_temp}°C`
  }
  return `explicit · ${s.entries?.length ?? 0} entries`
}

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [error, setError] = useState('')
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null)
  const [editSchedule, setEditSchedule] = useState<Schedule | null>(null)

  const load = () => api.listSchedules().then(setSchedules).catch(e => setError(String(e)))
  useEffect(() => { load() }, [])

  const closeModal = () => { setModalMode(null); setEditSchedule(null) }

  const handleSave = async (id: string, data: Omit<Schedule, 'id'>) => {
    if (modalMode === 'create') {
      await api.createSchedule({ id, ...data } as Schedule)
    } else {
      await api.updateSchedule(id, data)
    }
    closeModal()
    load()
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete schedule "${id}"?`)) return
    try {
      await api.deleteSchedule(id)
      load()
    } catch (e) { setError(String(e)) }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-slate-100 text-xl font-semibold">Schedules</h1>
        <button onClick={() => { setEditSchedule(null); setModalMode('create') }}
          className="bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-md px-4 py-1.5 text-sm">
          New Schedule
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
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">ID</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Name</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Summary</th>
              <th className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500 text-sm">
                  No schedules yet.
                </td>
              </tr>
            ) : (
              schedules.map(s => (
                <tr key={s.id} className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-sky-400 text-xs">{s.id}</span>
                  </td>
                  <td className="px-4 py-2.5 text-sm text-slate-200">{s.name}</td>
                  <td className="px-4 py-2.5 text-sm text-slate-400">{summarise(s)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-4">
                      <button onClick={() => { setEditSchedule(s); setModalMode('edit') }}
                        className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Edit</button>
                      <button onClick={() => handleDelete(s.id)}
                        className="text-slate-400 hover:text-red-400 text-sm transition-colors">Delete</button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {(modalMode === 'create' || modalMode === 'edit') && (
        <Modal
          title={modalMode === 'create' ? 'New Schedule' : `Edit: ${editSchedule?.id}`}
          onClose={closeModal}
        >
          <ScheduleForm
            schedule={editSchedule}
            onSave={handleSave}
            onCancel={closeModal}
          />
        </Modal>
      )}
    </div>
  )
}
