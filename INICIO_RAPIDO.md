# 🚀 Inicio Rápido - Project Parallel

Guía para ejecutar el proyecto completo.

## 📋 Requisitos Previos

- **Docker** y **Docker Compose** instalados
- **Node.js 18+** (para el frontend)
- **Python 3.11+** (opcional, solo si ejecutas servicios localmente)

## 🐳 Opción 1: Todo con Docker (Recomendado)

### 1. Configurar variables de entorno

Crea o edita `.env` en la raíz del proyecto:

```bash
# Base de datos
DB_PASSWORD=tu_password_seguro_aqui

# JWT
JWT_SECRET=tu_secreto_jwt_muy_seguro_aqui

# MinIO
MINIO_USER=admin
MINIO_PASSWORD=tu_password_minio

# Gemini API (opcional, para servicio IA)
GEMINI_API_KEY=tu_api_key_de_gemini

# Grafana (solo si usas docker-compose.prod.yml)
GRAFANA_ADMIN_PASSWORD=tu_password_grafana
```

### 2. Levantar servicios backend

```bash
cd project-parallel
docker compose up -d
```

Esto levanta:
- PostgreSQL (puerto 5432)
- MongoDB (puerto 27017)
- Redis (puerto 6379)
- MinIO (puertos 9000, 9001)
- 4 microservicios (puertos 8001-8004)
- Nginx Gateway (puerto 80)

### 3. Verificar que todo está corriendo

```bash
docker compose ps
```

Todos los servicios deben estar "Up" y saludables.

### 4. Probar endpoints

- Gateway: http://localhost/health
- Auth docs: http://localhost:8001/docs
- Historias docs: http://localhost:8002/docs
- Audio docs: http://localhost:8003/docs
- IA docs: http://localhost:8004/docs

## 🎨 Opción 2: Frontend React

### 1. Instalar dependencias

```bash
cd frontend-app
npm install
```

### 2. Configurar API base URL

Crea `.env` en `frontend-app/`:

```bash
VITE_API_BASE_URL=http://localhost
```

O si no usas gateway:

```bash
VITE_API_BASE_URL=http://localhost:8001  # Solo para auth, otros servicios por separado
```

### 3. Ejecutar frontend

```bash
npm run dev
```

Abre http://localhost:5173

## 🔧 Opción 3: Servicios localmente (sin Docker)

### Requisitos adicionales

- PostgreSQL corriendo
- MongoDB corriendo
- Redis corriendo
- MinIO corriendo (o usar S3)

### Configurar .env

```bash
URL_BASE_DATOS=postgresql://user:pass@localhost:5432/project_parallel
URL_REDIS=redis://localhost:6379/0
URL_MONGODB=mongodb://localhost:27017
ENDPOINT_MINIO=localhost:9000
CLAVE_ACCESO_MINIO=admin
CLAVE_SECRETA_MINIO=password
SECRETO_JWT=tu_secreto
CLAVE_API_GEMINI=tu_api_key
```

### Instalar dependencias por servicio

```bash
cd servicios/autenticacion
pip install -r requirements.txt
python main.py

# En otra terminal
cd servicios/historias
pip install -r requirements.txt
python main.py

# Y así para audio e ia...
```

## 📝 Primeros Pasos

1. **Registrar usuario**:
   ```bash
   curl -X POST http://localhost/api/v1/auth/registro \
     -H "Content-Type: application/json" \
     -d '{"usuario":"test","contrasena":"password123","rol":"paramedico"}'
   ```

2. **Login**:
   ```bash
   curl -X POST http://localhost/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"usuario":"test","contrasena":"password123"}'
   ```

3. **Usar token** en requests:
   ```bash
   curl http://localhost/api/v1/auth/yo \
     -H "Authorization: Bearer TU_TOKEN_AQUI"
   ```

## 🐛 Solución de Problemas

### Los servicios no arrancan

- Verifica que los puertos 5432, 27017, 6379, 9000, 8001-8004, 80 no estén ocupados
- Revisa logs: `docker compose logs servicio-autenticacion`

### Frontend no conecta al backend

- Verifica `VITE_API_BASE_URL` en `.env` del frontend
- Asegúrate de que el gateway nginx esté corriendo en puerto 80
- Revisa CORS en el navegador (F12 → Console)

### Error de autenticación

- Verifica que `SECRETO_JWT` sea el mismo en todos los servicios
- Revisa que Redis esté accesible para la lista negra de tokens

## 📚 Documentación

- Cada servicio tiene docs en `/docs` (Swagger UI)
- Frontend: ver `frontend-app/README.md`
- Tests: ver `tests/README.md`
- Producción: usar `docker-compose.prod.yml` con Prometheus/Grafana

## ✅ Checklist de Ejecución

- [ ] Docker instalado y corriendo
- [ ] `.env` configurado con passwords seguros
- [ ] `docker compose up -d` ejecutado
- [ ] Servicios saludables (`docker compose ps`)
- [ ] Frontend instalado (`cd frontend-app && npm install`)
- [ ] Frontend corriendo (`npm run dev`)
- [ ] Navegador abierto en http://localhost:5173

¡Listo para usar! 🎉
