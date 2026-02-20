const getBaseUrl = () => import.meta.env.VITE_API_BASE_URL || ''

const getToken = () => localStorage.getItem('pp_token') || ''

export async function api(path, options = {}) {
  const url = `${getBaseUrl()}${path}`
  const headers = { ...options.headers }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(url, { ...options, headers })
  const contentType = res.headers.get('content-type') || ''
  const data = contentType.includes('application/json')
    ? await res.json().catch(() => ({}))
    : await res.text()

  if (!res.ok) {
    const err = new Error(data?.detail || data?.message || String(data) || 'Error')
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const authApi = {
  login: (usuario, contrasena) =>
    api('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, contrasena }),
    }),
  registro: (body) =>
    api('/api/v1/auth/registro', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  yo: () => api('/api/v1/auth/yo'),
  cerrarSesion: () => api('/api/v1/auth/cerrar-sesion', { method: 'POST' }),
}

export const historiasApi = {
  listar: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return api(`/api/v1/historias${q ? `?${q}` : ''}`)
  },
  crear: (body) =>
    api('/api/v1/historias', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  obtener: (consecutivo) => api(`/api/v1/historias/${consecutivo}`),
  actualizar: (consecutivo, body) =>
    api(`/api/v1/historias/${consecutivo}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  actualizarEstado: (consecutivo, estado) =>
    api(`/api/v1/historias/${consecutivo}/estado`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estado }),
    }),
  eliminar: (consecutivo) =>
    api(`/api/v1/historias/${consecutivo}`, { method: 'DELETE' }),
  estadisticas: () => api('/api/v1/historias/estadisticas/resumen'),
}

export const audioApi = {
  subir: (file) => {
    const form = new FormData()
    form.append('archivo', file)
    return api('/api/v1/audio/subir', { method: 'POST', body: form })
  },
  estado: (idAudio) => api(`/api/v1/audio/${idAudio}/estado`),
  listar: (limite = 50) =>
    api(`/api/v1/audio/usuario/listar?limite=${limite}`),
}

export const iaApi = {
  analizar: (texto, usar_cache = true) =>
    api('/api/v1/ia/analizar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto, tipo: 'historia_clinica', usar_cache }),
    }),
  estadisticas: () => api('/api/v1/ia/estadisticas'),
}
