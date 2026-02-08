






# Frontend Project Parallel

## Inicio rápido

1. Levanta los servicios backend y el gateway NGINX.
2. Abre `frontend/index.html` en el navegador.
3. En "Configuración de API", confirma:
   - Con gateway: Base URL `http://localhost` y "Usar gateway único" activado.
   - Sin gateway: desactiva "Usar gateway único" y usa `http://localhost:8001..8004`.

## Flujo principal

1. Registrar usuario o iniciar sesión en **Autenticación**.
2. Crear y listar historias en **Historias Clínicas**.
3. Analizar texto con **IA**.
4. Subir y consultar audios en **Audio**.

## Notas

- El token se guarda en `localStorage` como `pp_token`.
- La Base URL se guarda como `pp_api_base`.
- Para evitar problemas de CORS, usa el gateway NGINX.
