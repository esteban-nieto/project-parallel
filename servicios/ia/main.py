# servicios/ia/main.py
"""
Microservicio de Análisis con IA - Project Parallel
Integración con Gemini para corrección de texto y extracción de campos médicos
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict
import google.generativeai as genai
import json
import re
from datetime import datetime
import jwt
import os
from motor.motor_asyncio import AsyncIOMotorClient
import hashlib
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

# ==================== CONFIGURACIÓN ====================
CLAVE_API_GEMINI = os.getenv("CLAVE_API_GEMINI", os.getenv("GEMINI_API_KEY", ""))
URL_MONGODB = os.getenv("URL_MONGODB", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", "cambia-esto-en-produccion-abc123xyz"))

# Configurar Gemini
if CLAVE_API_GEMINI:
    genai.configure(api_key=CLAVE_API_GEMINI)
else:
    print("⚠️ ADVERTENCIA: CLAVE_API_GEMINI no configurada")

# Resolver modelos disponibles (si hay API key)
def _resolver_modelos_disponibles() -> list:
    """Obtiene modelos válidos para generateContent. Usa la API si está disponible."""
    try:
        modelos = []
        for m in genai.list_models():
            if "generateContent" in getattr(m, "supported_generation_methods", []):
                nombre = getattr(m, "name", "")
                if nombre.startswith("models/"):
                    nombre = nombre.replace("models/", "", 1)
                if nombre:
                    modelos.append(nombre)
        return modelos
    except Exception:
        return []

MODELOS_GEMINI_PREFERIDOS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

MODELOS_GEMINI_DISPONIBLES = _resolver_modelos_disponibles() if CLAVE_API_GEMINI else []
if MODELOS_GEMINI_DISPONIBLES:
    print(f"✅ Modelos Gemini disponibles: {MODELOS_GEMINI_DISPONIBLES}")
else:
    print("⚠️ No se pudo listar modelos Gemini. Se usarán modelos por defecto.")

# ==================== CLIENTES ====================
app = FastAPI(
    title="Project Parallel - Servicio de IA",
    version="1.0.0",
    description="Microservicio de análisis con IA usando Google Gemini"
)

# CORS
_origenes = {o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()}
_origenes.add("http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_origenes),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente MongoDB para caché
cliente_mongo = AsyncIOMotorClient(URL_MONGODB)
bd = cliente_mongo.project_parallel
coleccion_cache_ia = bd.cache_ia
coleccion_logs_ia = bd.logs_ia

# ==================== ESQUEMAS ====================
class SolicitudAnalisis(BaseModel):
    texto: str = Field(..., min_length=10, description="Texto a analizar")
    tipo: str = Field(default="historia_clinica", description="Tipo de análisis")
    usar_cache: bool = Field(default=True, description="Usar caché si está disponible")

class CamposExtraidos(BaseModel):
    paciente: str
    edad: int
    motivo: str
    diagnostico: str
    tratamiento: str

class RespuestaAnalisis(BaseModel):
    texto_corregido: str = Field(..., description="Texto corregido y mejorado")
    campos_extraidos: CamposExtraidos = Field(..., description="Campos médicos extraídos")
    confianza: float = Field(..., ge=0.0, le=1.0, description="Nivel de confianza del análisis")
    modelo_usado: str = Field(..., description="Modelo de IA utilizado")
    tiempo_procesamiento_ms: int = Field(..., description="Tiempo de procesamiento en milisegundos")
    desde_cache: bool = Field(default=False, description="Si el resultado vino del caché")

# ==================== FUNCIONES AUXILIARES ====================

def verificar_token(authorization: Optional[str] = Header(None)) -> dict:
    """Verificar token JWT"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
    try:
        esquema, token = authorization.split()
        if esquema.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Esquema inválido")
        
        payload = jwt.decode(token, SECRETO_JWT, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

def generar_hash_cache(texto: str) -> str:
    """Generar hash para caché"""
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()

async def obtener_desde_cache(hash_texto: str) -> Optional[dict]:
    """Intentar obtener resultado desde caché"""
    doc = await coleccion_cache_ia.find_one({"hash": hash_texto})
    if doc:
        # Verificar que no sea muy antiguo (7 días)
        if (datetime.utcnow() - doc["fecha_creacion"]).days < 7:
            return doc["resultado"]
    return None

async def guardar_en_cache(hash_texto: str, resultado: dict, texto_original: str):
    """Guardar resultado en caché"""
    await coleccion_cache_ia.update_one(
        {"hash": hash_texto},
        {
            "$set": {
                "hash": hash_texto,
                "resultado": resultado,
                "texto_original": texto_original[:500],  # Solo primeros 500 chars
                "fecha_creacion": datetime.utcnow()
            }
        },
        upsert=True
    )

async def registrar_log_ia(
    id_usuario: int,
    texto_entrada: str,
    resultado: dict,
    tiempo_ms: int,
    desde_cache: bool,
    modelo: str
):
    """Registrar uso de IA para análisis"""
    await coleccion_logs_ia.insert_one({
        "id_usuario": id_usuario,
        "longitud_texto": len(texto_entrada),
        "modelo": modelo,
        "tiempo_ms": tiempo_ms,
        "desde_cache": desde_cache,
        "fecha": datetime.utcnow()
    })

def analizar_con_gemini(texto: str) -> dict:
    """
    Analizar texto con Gemini y extraer campos médicos
    Incluye fallback heurístico si Gemini falla
    """
    
    prompt = f"""
Eres un asistente médico especializado en historias clínicas de ambulancia. 
Recibirás una transcripción en español que puede contener errores de reconocimiento de voz.

Tu tarea:
1. Corregir el texto para que sea coherente y profesional
2. Extraer los siguientes campos médicos:
   - paciente: nombre del paciente (o "No especificado")
   - edad: edad en años (número entero, 0 si no se menciona)
   - motivo: motivo de atención o consulta
   - diagnostico: diagnóstico o impresión diagnóstica
   - tratamiento: tratamiento realizado en el lugar

IMPORTANTE: Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura:
{{
  "texto_corregido": "versión corregida del texto",
  "paciente": "nombre o No especificado",
  "edad": 0,
  "motivo": "descripción del motivo",
  "diagnostico": "diagnóstico",
  "tratamiento": "tratamiento realizado"
}}

NO incluyas markdown, explicaciones adicionales ni texto fuera del JSON.

Texto a analizar:
\"\"\"
{texto}
\"\"\"
"""
    
    # Elegir modelos válidos
    if MODELOS_GEMINI_DISPONIBLES:
        modelos = [m for m in MODELOS_GEMINI_PREFERIDOS if m in MODELOS_GEMINI_DISPONIBLES]
        if not modelos:
            modelos = MODELOS_GEMINI_DISPONIBLES[:3]
    else:
        modelos = MODELOS_GEMINI_PREFERIDOS
    
    for modelo_id in modelos:
        try:
            modelo = genai.GenerativeModel(modelo_id)
            respuesta = modelo.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.15,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
            
            salida = respuesta.text.strip()
            
            # Extraer JSON del texto
            if "{" in salida and "}" in salida:
                inicio = salida.find("{")
                fin = salida.rfind("}") + 1
                bloque_json = salida[inicio:fin]
                
                try:
                    datos = json.loads(bloque_json)
                    
                    # Validar y normalizar campos
                    resultado = {
                        "texto_corregido": str(datos.get("texto_corregido", texto)),
                        "paciente": str(datos.get("paciente", "No especificado")),
                        "edad": int(datos.get("edad", 0)) if str(datos.get("edad", "")).isdigit() else 0,
                        "motivo": str(datos.get("motivo", "No especificado")),
                        "diagnostico": str(datos.get("diagnostico", "No especificado")),
                        "tratamiento": str(datos.get("tratamiento", "No especificado")),
                        "modelo_usado": modelo_id,
                        "confianza": 0.9
                    }
                    
                    return resultado
                    
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"❌ Error con {modelo_id}: {str(e)}")
            continue
    
    # Fallback: análisis heurístico si Gemini falla
    print("⚠️ Gemini falló, usando análisis heurístico")
    return analisis_heuristico(texto)

def analisis_heuristico(texto: str) -> dict:
    """
    Análisis de respaldo usando expresiones regulares
    cuando Gemini no está disponible
    """
    
    texto_lower = texto.lower()
    
    # Extraer paciente
    paciente = "No especificado"
    match = re.search(r"(?:paciente|nombre)[\s:]+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]{3,50})", texto, re.IGNORECASE)
    if match:
        paciente = match.group(1).strip()
    
    # Extraer edad
    edad = 0
    match = re.search(r"edad[\s:]+(\d{1,3})", texto_lower)
    if match:
        edad = int(match.group(1))
    
    # Extraer motivo
    motivo = "No especificado"
    if "motivo" in texto_lower:
        partes = re.split(r"motivo(?:\s+de)?(?:\s+atención)?[\s:]?", texto_lower, maxsplit=1)
        if len(partes) > 1:
            motivo_raw = partes[1].split("diagnos")[0].split("tratamiento")[0].strip()
            motivo = motivo_raw[:200]
    else:
        # Buscar palabras clave médicas
        palabras_clave = ["caída", "trauma", "dolor", "síncope", "hemorragia", "fractura", "quemadura"]
        for palabra in palabras_clave:
            if palabra in texto_lower:
                motivo = f"Posible {palabra}"
                break
    
    # Extraer diagnóstico
    diagnostico = "No especificado"
    if "diagnos" in texto_lower or "diagnós" in texto_lower:
        partes = re.split(r"diagn[oó]stic[oa]?[\s:]?", texto_lower, maxsplit=1)
        if len(partes) > 1:
            diagnostico = partes[1].split("tratamiento")[0].strip()[:200]
    
    # Extraer tratamiento
    tratamiento = "No especificado"
    if "tratamiento" in texto_lower:
        partes = re.split(r"tratamiento(?:\s+realizado)?[\s:]?", texto_lower, maxsplit=1)
        if len(partes) > 1:
            tratamiento = partes[1].strip()[:200]
    
    return {
        "texto_corregido": texto.strip(),
        "paciente": paciente,
        "edad": edad,
        "motivo": motivo,
        "diagnostico": diagnostico,
        "tratamiento": tratamiento,
        "modelo_usado": "heuristico",
        "confianza": 0.6
    }

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz():
    return {
        "servicio": "Project Parallel - Servicio de IA",
        "version": "1.0.0",
        "estado": "funcionando"
    }

@app.get("/salud", tags=["General"])
async def verificar_salud():
    try:
        await bd.command("ping")
        gemini_ok = bool(CLAVE_API_GEMINI)
        return {
            "estado": "saludable",
            "mongodb": "ok",
            "gemini_configurado": gemini_ok
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/api/v1/ia/analizar", response_model=RespuestaAnalisis, tags=["Análisis IA"])
async def analizar_texto(
    solicitud: SolicitudAnalisis,
    datos_usuario: dict = Depends(verificar_token)
):
    """
    Analizar texto médico con IA:
    - Corregir errores de transcripción
    - Extraer campos estructurados
    - Mejorar legibilidad
    """
    
    inicio = datetime.utcnow()
    
    # Verificar caché
    hash_texto = generar_hash_cache(solicitud.texto)
    desde_cache = False
    
    if solicitud.usar_cache:
        resultado_cache = await obtener_desde_cache(hash_texto)
        if resultado_cache:
            desde_cache = True
            resultado = resultado_cache
            tiempo_ms = 10  # Caché es casi instantáneo
        else:
            # Analizar con IA
            resultado = analizar_con_gemini(solicitud.texto)
            tiempo_ms = int((datetime.utcnow() - inicio).total_seconds() * 1000)
            
            # Guardar en caché
            await guardar_en_cache(hash_texto, resultado, solicitud.texto)
    else:
        # Forzar análisis sin caché
        resultado = analizar_con_gemini(solicitud.texto)
        tiempo_ms = int((datetime.utcnow() - inicio).total_seconds() * 1000)
    
    # Registrar uso
    await registrar_log_ia(
        id_usuario=int(datos_usuario.get("sub")),
        texto_entrada=solicitud.texto,
        resultado=resultado,
        tiempo_ms=tiempo_ms,
        desde_cache=desde_cache,
        modelo=resultado.get("modelo_usado", "desconocido")
    )
    
    return {
        "texto_corregido": resultado["texto_corregido"],
        "campos_extraidos": CamposExtraidos(
            paciente=resultado["paciente"],
            edad=resultado["edad"],
            motivo=resultado["motivo"],
            diagnostico=resultado["diagnostico"],
            tratamiento=resultado["tratamiento"]
        ),
        "confianza": resultado.get("confianza", 0.85),
        "modelo_usado": resultado.get("modelo_usado", "desconocido"),
        "tiempo_procesamiento_ms": tiempo_ms,
        "desde_cache": desde_cache
    }

@app.get("/api/v1/ia/estadisticas", tags=["Estadísticas"])
async def obtener_estadisticas_ia(
    datos_usuario: dict = Depends(verificar_token)
):
    """Obtener estadísticas de uso de IA del usuario"""
    
    id_usuario = int(datos_usuario.get("sub"))
    
    # Contar análisis totales
    total = await coleccion_logs_ia.count_documents({"id_usuario": id_usuario})
    
    # Contar desde caché
    desde_cache = await coleccion_logs_ia.count_documents({
        "id_usuario": id_usuario,
        "desde_cache": True
    })
    
    # Tiempo promedio
    pipeline = [
        {"$match": {"id_usuario": id_usuario}},
        {"$group": {
            "_id": None,
            "tiempo_promedio": {"$avg": "$tiempo_ms"}
        }}
    ]
    resultado = await coleccion_logs_ia.aggregate(pipeline).to_list(1)
    tiempo_promedio = int(resultado[0]["tiempo_promedio"]) if resultado else 0
    
    return {
        "total_analisis": total,
        "desde_cache": desde_cache,
        "nuevos_analisis": total - desde_cache,
        "tiempo_promedio_ms": tiempo_promedio,
        "porcentaje_cache": round((desde_cache / total * 100), 2) if total > 0 else 0
    }

@app.delete("/api/v1/ia/cache/limpiar", tags=["Cache"])
async def limpiar_cache(
    datos_usuario: dict = Depends(verificar_token)
):
    """Limpiar caché antiguo (más de 7 días)"""
    
    fecha_limite = datetime.utcnow()
    from datetime import timedelta
    fecha_limite = fecha_limite - timedelta(days=7)
    
    resultado = await coleccion_cache_ia.delete_many({
        "fecha_creacion": {"$lt": fecha_limite}
    })
    
    return {
        "mensaje": "Caché limpiado",
        "documentos_eliminados": resultado.deleted_count
    }

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
