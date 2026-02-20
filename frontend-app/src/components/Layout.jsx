import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authApi } from '../api/client'

const nav = [
  { to: '/', label: 'Dashboard' },
  { to: '/nueva-historia', label: 'Nueva historia' },
  { to: '/historias', label: 'Historias' },
  { to: '/estadisticas', label: 'Estadísticas' },
]

export default function Layout() {
  const navigate = useNavigate()
  const { setToken } = useAuth()

  const handleLogout = async () => {
    try {
      await authApi.cerrarSesion()
    } catch (_) {}
    setToken('')
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-700/50 bg-surface-800/50 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="font-display font-semibold text-lg text-white">
            Project Parallel
          </h1>
          <nav className="flex items-center gap-1">
            {nav.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-500/20 text-primary-400'
                      : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
            <button
              type="button"
              onClick={handleLogout}
              className="ml-2 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-700/50"
            >
              Salir
            </button>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
