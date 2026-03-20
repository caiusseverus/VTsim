export default function StatusBadge({ status }: { status: string }) {
  const base = 'rounded-full px-2.5 py-0.5 text-xs font-medium inline-flex items-center gap-1.5'
  switch (status) {
    case 'running':
      return (
        <span className={`${base} bg-sky-900/60 text-sky-300`}>
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          running
        </span>
      )
    case 'complete':
      return <span className={`${base} bg-emerald-900/60 text-emerald-300`}>● complete</span>
    case 'partial_failure':
      return <span className={`${base} bg-amber-900/60 text-amber-300`}>● partial</span>
    case 'failed':
      return <span className={`${base} bg-red-900/60 text-red-300`}>● failed</span>
    default:
      return <span className={`${base} bg-slate-800 text-slate-400`}>● pending</span>
  }
}
