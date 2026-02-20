# Monitoreo - Project Parallel

Configuración de Prometheus, Blackbox Exporter y Grafana para el stack de producción.

## Uso con docker-compose.prod.yml

Los servicios de monitoreo se levantan con:

```bash
docker compose -f docker-compose.prod.yml up -d
```

- **Prometheus**: http://localhost:9090  
  - Scrape de health de los 4 microservicios y nginx vía Blackbox.
- **Blackbox Exporter**: http://localhost:9115  
  - Sonda HTTP a `/salud` y `/health`.
- **Grafana**: http://localhost:3000  
  - Usuario/contraseña: `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` (env obligatorio en prod).

## Variables de entorno

En producción define al menos:

- `DB_PASSWORD`
- `JWT_SECRET`
- `MINIO_USER` / `MINIO_PASSWORD`
- `GRAFANA_ADMIN_PASSWORD`

Opcional: `GEMINI_API_KEY` para el servicio de IA.

## Dashboards

Tras el primer login en Grafana, añade el datasource **Prometheus** (ya provisionado en `grafana/provisioning/datasources/`). Puedes crear dashboards con la métrica `probe_success` (job `service-health`) para ver el estado de cada endpoint.
