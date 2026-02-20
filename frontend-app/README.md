# Project Parallel - Frontend (React + Tailwind)

Frontend web para el sistema de historias clínicas de ambulancia.

## Requisitos

- Node.js 18+
- Backend y gateway NGINX en marcha

## Desarrollo

```bash
npm install
npm run dev
```

Abre http://localhost:5173. Por defecto las peticiones API se hacen al mismo host (configura proxy en `vite.config.js` o usa `VITE_API_BASE_URL`).

## Build

```bash
npm run build
```

Salida en `dist/`. Para producción sirve con cualquier servidor estático; en desarrollo con gateway usa el proxy de Vite.

## Variables de entorno

- `VITE_API_BASE_URL`: Base URL del API (gateway). Ej: `http://localhost`. Si vacío, se usa el mismo origen (proxy en dev).

## Pantallas

- **Login**: Inicio de sesión y registro.
- **Dashboard**: Accesos rápidos.
- **Nueva historia**: Formulario + grabador de audio + análisis IA.
- **Historias**: Listado con filtros y cambio de estado.
- **Estadísticas**: Resumen de historias y uso de IA.
