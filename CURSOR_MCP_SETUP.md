# Configuración MCP para Cursor

Para que el agente pueda consultar documentación oficial de FastAPI, Docker, etc. en tiempo real usando Context7, agrega esta configuración a tu archivo de configuración de Cursor.

## Ubicación del archivo de configuración

La configuración MCP de Cursor generalmente se encuentra en uno de estos lugares:

1. **Windows**: `%APPDATA%\Cursor\User\settings.json` o en la configuración del workspace
2. **macOS/Linux**: `~/.config/Cursor/User/settings.json` o configuración del workspace

## Configuración a agregar

Agrega esta sección a tu archivo de configuración de Cursor (o crea/modifica el archivo correspondiente):

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

## Alternativa: Archivo de configuración MCP

Si Cursor soporta archivos de configuración MCP separados, también puedes usar el archivo `.cursor/mcp-config.json` que está en este proyecto.

## Verificación

Después de agregar la configuración:
1. Reinicia Cursor
2. El agente debería poder consultar documentación oficial de FastAPI, Docker, y otras tecnologías en tiempo real

## Nota

El archivo `.cursor/mcp-config.json` en este proyecto es una referencia. Asegúrate de agregar la configuración al lugar correcto según tu instalación de Cursor.
