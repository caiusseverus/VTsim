import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import ModelsPage from './pages/ModelsPage'
import VtVersionsPage from './pages/VtVersionsPage'
import PresetsPage from './pages/PresetsPage'
import SchedulesPage from './pages/SchedulesPage'
import NewRunPage from './pages/NewRunPage'
import RunsPage from './pages/RunsPage'
import ResultsPage from './pages/ResultsPage'
import ComparisonPage from './pages/ComparisonPage'
import HaComparePage from './pages/HaComparePage'
import VerifyPage from './pages/VerifyPage'

const navItem = ({ isActive }: { isActive: boolean }) =>
  `flex items-center h-full px-3 text-sm border-b-2 transition-colors ${
    isActive
      ? 'text-sky-400 border-sky-400'
      : 'text-slate-400 border-transparent hover:text-slate-100'
  }`

const groupLabel = 'flex items-center h-full px-2 text-xs uppercase tracking-widest text-slate-500 select-none'

function Nav() {
  return (
    <nav className="bg-slate-900 border-b border-slate-800 flex items-stretch h-11 px-6 gap-1 shrink-0">
      <span className="flex items-center mr-6 text-slate-100 font-bold text-sm tracking-wide">VTsim</span>

      {/* Config group */}
      <span className={groupLabel}>Config</span>
      <NavLink to="/models" className={navItem}>Models</NavLink>
      <NavLink to="/presets" className={navItem}>Presets</NavLink>
      <NavLink to="/schedules" className={navItem}>Schedules</NavLink>
      <NavLink to="/vt-versions" className={navItem}>Versions</NavLink>

      {/* Divider */}
      <div className="w-px bg-slate-800 my-2 mx-2" />

      {/* Simulate group */}
      <span className={groupLabel}>Simulate</span>
      <NavLink to="/runs/new" className={navItem}>New Run</NavLink>
      <NavLink to="/runs" end className={navItem}>Runs</NavLink>
      <NavLink to="/compare" className={navItem}>Compare</NavLink>
      <NavLink to="/ha-compare" className={navItem}>HA Compare</NavLink>
      <NavLink to="/verify" className={navItem}>Verify</NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#020617] flex flex-col">
        <Nav />
        <main className="flex-1">
          <div className="max-w-5xl mx-auto px-6 py-8">
            <Routes>
              <Route path="/" element={<ModelsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/vt-versions" element={<VtVersionsPage />} />
              <Route path="/presets" element={<PresetsPage />} />
              <Route path="/schedules" element={<SchedulesPage />} />
              <Route path="/runs/new" element={<NewRunPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId/results" element={<ResultsPage />} />
              <Route path="/compare" element={<ComparisonPage />} />
              <Route path="/ha-compare" element={<HaComparePage />} />
              <Route path="/verify" element={<VerifyPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
