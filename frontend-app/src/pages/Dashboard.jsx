import { Link } from 'react-router-dom'

export default function Dashboard() {
  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-2">
        Dashboard
      </h1>
      <p className="text-slate-400 mb-8">
        Acceso rápido a historias, audio y estadísticas.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Link
          to="/nueva-historia"
          className="card p-6 block hover:border-primary-500/50 transition-colors"
        >
          <h2 className="font-display font-semibold text-lg text-white mb-1">
            Nueva historia clínica
          </h2>
          <p className="text-slate-400 text-sm">
            Crear historia con formulario o desde audio transcrito.
          </p>
        </Link>
        <Link
          to="/historias"
          className="card p-6 block hover:border-primary-500/50 transition-colors"
        >
          <h2 className="font-display font-semibold text-lg text-white mb-1">
            Ver historias
          </h2>
          <p className="text-slate-400 text-sm">
            Listar, filtrar y editar historias por estado.
          </p>
        </Link>
        <Link
          to="/estadisticas"
          className="card p-6 block hover:border-primary-500/50 transition-colors"
        >
          <h2 className="font-display font-semibold text-lg text-white mb-1">
            Estadísticas
          </h2>
          <p className="text-slate-400 text-sm">
            Resumen de historias y uso de IA.
          </p>
        </Link>
      </div>
    </div>
  )
}
