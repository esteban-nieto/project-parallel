# Tests - Project Parallel

Tests con pytest para los 4 microservicios. Se usan mocks para Redis, MongoDB, MinIO, Gemini y Whisper.

## Instalación

Desde la raíz del proyecto (`project-parallel`):

```bash
pip install -r tests/requirements.txt
```

O desde `tests/`:

```bash
pip install -r requirements.txt
```

## Ejecución

Desde `project-parallel` (recomendado para que los imports de los servicios resuelvan bien):

```bash
cd project-parallel
pytest tests/ -v
```

Para un solo servicio:

```bash
pytest tests/test_autenticacion.py -v
pytest tests/test_historias.py -v
pytest tests/test_audio.py -v
pytest tests/test_ia.py -v
```

## Cobertura

- **Autenticación**: raíz, salud, registro, login, login inválido, /yo con y sin token, registro duplicado.
- **Historias**: raíz, salud, crear historia, listar, listar con filtro, estadísticas (con JWT).
- **Audio**: raíz, salud, subir audio (mock MinIO/Mongo/Whisper), listar sin token.
- **IA**: raíz, salud, analizar (mock Gemini/Mongo), analizar sin token, estadísticas, limpiar caché.

## Notas

- Auth e Historias usan SQLite en memoria en tests (env `URL_BASE_DATOS=sqlite:///:memory:`).
- Redis está mockeado en auth (exists, setex, ping).
- MongoDB, MinIO y Whisper están mockeados en audio e IA.
