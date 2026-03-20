// webapp/frontend/src/components/Modal.tsx
import { useEffect } from 'react'
import type { ReactNode } from 'react'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
}

export default function Modal({ title, onClose, children }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center p-4">
      <div aria-hidden="true" className="absolute inset-0" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-labelledby="modal-title" className="relative bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col z-10">
        <div className="bg-slate-800/50 border-b border-slate-700 px-6 py-4 flex items-center justify-between shrink-0">
          <h2 id="modal-title" className="text-slate-100 font-semibold text-base">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="text-slate-400 hover:text-slate-100 transition-colors text-xl leading-none">✕</button>
        </div>
        <div className="overflow-y-auto px-6 py-5 flex-1">
          {children}
        </div>
      </div>
    </div>
  )
}
