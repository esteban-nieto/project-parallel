import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { authApi } from '../api/client'

export default function Login() {
  const navigate = useNavigate()
  const { setToken } = useAuth()
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [email, setEmail] = useState('')
  const [modoRegistro, setModoRegistro] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (modoRegistro) {
        await authApi.registro({
          usuario,
          contrasena,
          email: email || undefined,
          rol: 'paramedico',
        })
      }
      const res = await authApi.login(usuario, contrasena)
      setToken(res.token_acceso)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err?.data?.detail || err?.message || 'Error al iniciar sesión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-b from-surface-900 to-slate-900">
      <div className="card w-full max-w-md p-8">
        <h1 className="font-display text-2xl font-bold text-white mb-1">
          Project Parallel
        </h1>
        <p className="text-slate-400 text-sm mb-6">
          Historias clínicas de ambulancia
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Usuario</label>
            <input
              type="text"
              className="input"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              placeholder="usuario"
              required
              autoComplete="username"
            />
          </div>
          {modoRegistro && (
            <div>
              <label className="label">Email (opcional)</label>
              <input
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="correo@ejemplo.com"
                autoComplete="email"
              />
            </div>
          )}
          <div>
            <label className="label">Contraseña</label>
            <input
              type="password"
              className="input"
              value={contrasena}
              onChange={(e) => setContrasena(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              autoComplete={modoRegistro ? 'new-password' : 'current-password'}
            />
          </div>
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-3 py-2">
              {error}
            </div>
          )}
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={loading}
            >
              {loading ? 'Espera…' : modoRegistro ? 'Registrarme' : 'Entrar'}
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setModoRegistro(!modoRegistro)
                setError('')
              }}
            >
              {modoRegistro ? 'Ya tengo cuenta' : 'Crear cuenta'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
