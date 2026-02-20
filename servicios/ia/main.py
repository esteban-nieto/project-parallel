# servicios/ia/main.py
"""
Microservicio de Análisis con IA - Project Parallel
Integración con Gemini para corrección de texto y extracción de campos médicos
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import google.generativeai as genai
import json
import re
from datetime import datetime, timezone
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
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", ""))
if not SECRETO_JWT:
    raise RuntimeError("SECRETO_JWT/JWT_SECRET es obligatorio")

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
_origenes.add("http://localhost:5174")
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

# ==================== ESQUEMAS EXTRA ====================
class SolicitudExtraccion(BaseModel):
    texto: str = Field(..., min_length=5, description="Texto a analizar")
    tipo: str = Field(..., description="personales|acompanante|representante")
    usar_cache: bool = Field(default=True, description="Usar cache si esta disponible")

class RespuestaExtraccion(BaseModel):
    campos: Dict[str, Any] = Field(..., description="Campos extraidos del texto")
    modelo_usado: str = Field(..., description="Modelo de IA utilizado")
    confianza: float = Field(..., ge=0.0, le=1.0, description="Nivel de confianza del analisis")
    tiempo_procesamiento_ms: int = Field(..., description="Tiempo de procesamiento en milisegundos")
    desde_cache: bool = Field(default=False, description="Si el resultado vino del cache")

def respuesta_ok(datos: Dict[str, Any], mensaje: str = "Operaci?n exitosa") -> Dict[str, Any]:
    return {"estado": "ok", "datos": datos, "mensaje": mensaje}

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
        if (datetime.now(timezone.utc) - doc["fecha_creacion"]).days < 7:
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
                "fecha_creacion": datetime.now(timezone.utc)
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
        "fecha": datetime.now(timezone.utc)
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

# ==================== EXTRACCION GENERICA ====================

def _extraer_json_salida(salida: str) -> Optional[dict]:
    if "{" in salida and "}" in salida:
        inicio = salida.find("{")
        fin = salida.rfind("}") + 1
        bloque = salida[inicio:fin]
        try:
            return json.loads(bloque)
        except json.JSONDecodeError:
            return None
    return None

def _normalizar_tipo_doc(texto: str) -> str:
    texto = texto.lower()
    if "cedula" in texto or "c.c" in texto or "cc" in texto:
        return "CC"
    if "tarjeta" in texto or "ti" in texto:
        return "TI"
    if "registro" in texto or "rc" in texto:
        return "RC"
    if "extranj" in texto or "ce" in texto:
        return "CE"
    return ""

def _extraer_numero_documento(texto: str) -> str:
    match = re.search(r"\b(\d{5,15})\b", texto)
    return match.group(1) if match else ""

def _extraer_numero_documento_flexible(texto: str) -> str:
    # 1) intento directo
    directo = _extraer_numero_documento(texto)
    if directo:
        return directo

    # 2) intentar en ventana cercana a "documento"
    lower = texto.lower()
    ancla = max(lower.find("documento"), lower.find("cedula"), lower.find("cédula"))
    if ancla != -1:
        ventana = texto[ancla : min(len(texto), ancla + 120)]
    else:
        ventana = texto

    # Une digitos separados: "1 0 0 7 8 4..."
    grupos = re.findall(r"(?:\d[\s,.-]*){6,20}", ventana)
    if grupos:
        candidato = re.sub(r"\D", "", max(grupos, key=len))
        if 6 <= len(candidato) <= 16:
            return candidato
    return ""

def _solo_letras(texto: str) -> str:
    limpio = re.sub(r"[^A-Za-zÃÃ‰ÃÃ“ÃšÃ‘Ã¡Ã©Ã­Ã³ÃºÃ±\s]", " ", texto)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio

def _capitalizar_nombre(texto: str) -> str:
    return " ".join([p.capitalize() for p in texto.split()]) if texto else ""

def _solo_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)

def _limpiar_muletillas_nombre(texto: str) -> str:
    texto = re.sub(r"\b(el\s+)?(nombre|paciente)\s*(es|seria|serÃ­a|:)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\bse\s+llama\b\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^\s*es\s+", "", texto, flags=re.IGNORECASE)
    return texto.strip()

def _extraer_email(texto: str) -> str:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", texto, re.IGNORECASE)
    return match.group(0) if match else ""

def _email_valido(texto: str) -> str:
    correo = _extraer_email(texto)
    if correo:
        return correo
    return _normalizar_email_hablado(texto)

def _normalizar_email_hablado(texto: str) -> str:
    t = texto.lower().strip()
    t = t.replace(" arroba ", "@")
    t = t.replace(" a roba ", "@")
    t = t.replace(" aroba ", "@")
    t = t.replace(" punto ", ".")
    t = t.replace(" gmail", "@gmail")
    t = t.replace(" jimail", "@gmail")
    t = t.replace(" hotmail", "@hotmail")
    t = t.replace(" outlook", "@outlook")
    t = re.sub(r"\s+", "", t)
    m = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", t)
    return m.group(0) if m else ""

def _extraer_fecha_nacimiento_global(texto: str) -> tuple[str, str, str]:
    # Busca patrones robustos: "dia 24 ... mes 08 ... anio 2000"
    t = texto.lower()
    t = t.replace("año", "anio")
    t = t.replace("día", "dia")
    m = re.search(r"dia\D{0,10}(\d{1,2}).{0,40}?mes\D{0,10}(\d{1,2}).{0,40}?anio\D{0,10}(\d{2,4})", t)
    if m:
        dia = m.group(1).zfill(2)
        mes = m.group(2).zfill(2)
        anio = m.group(3)
        if len(anio) == 2:
            anio = f"20{anio}"
        return dia, mes, anio
    return "", "", ""

def _extraer_telefono(texto: str) -> str:
    match = re.search(r"\b\d{7,15}\b", texto)
    return match.group(0) if match else ""

def _extraer_nombre(texto: str) -> str:
    match = re.search(r"(?:nombre|paciente)[\s:]+([A-Za-z\s]{3,60})", texto, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _recortar_contenido_contaminado(texto: str) -> str:
    if not texto:
        return texto
    cortes = [
        "aseguradora", "eps", "correo", "email", "telefono", "teléfono", "municipio",
        "estado civil", "tipo de documento", "numero de documento", "número de documento"
    ]
    t = texto
    t_lower = t.lower()
    idxs = [t_lower.find(k) for k in cortes if t_lower.find(k) != -1]
    if idxs:
        t = t[: min(idxs)]
    return t.strip(" ,.-")

def construir_prompt_extraccion(texto: str, tipo: str) -> str:
    if tipo == "personales":
        campos = [
            "nombre", "edad", "tipo_documento", "numero_documento", "sexo",
            "dia_nacimiento", "mes_nacimiento", "anio_nacimiento",
            "estado_civil", "lugar_nacimiento", "aseguradora",
            "correo", "telefono", "municipio"
        ]
        reglas = (
            "tipo_documento debe ser CC, TI, RC o CE. "
            "estado_civil debe ser S, C, V, TV o UL. "
            "sexo debe ser M o F. "
            "edad puede ser numero con unidad (ej: '25 aÃ±os' o '10 meses'). "
            "dia_nacimiento, mes_nacimiento, anio_nacimiento deben ser solo numeros. "
            "nombre, lugar_nacimiento, aseguradora, municipio deben ser solo letras y espacios. "
            "Si lugar_nacimiento o municipio vienen con error de voz, corrige a la ciudad o municipio mas probable."
        )
    elif tipo == "acompanante":
        campos = ["nombre", "tipo_documento", "numero_documento", "telefono"]
        reglas = "tipo_documento debe ser CC, TI, RC o CE."
    else:
        campos = ["nombre", "tipo_documento", "numero_documento", "telefono"]
        reglas = "tipo_documento debe ser CC, TI, RC o CE."

    return f"""
You are extracting structured data from Spanish speech transcription.
Return ONLY a valid JSON object with this structure:
{{
  "campos": {{
    {", ".join([f'"{c}": ""' for c in campos])}
  }}
}}
Rules: {reglas}
If a field is not present, leave it as empty string.
Text:
\"\"\"
{texto}
\"\"\"
"""

def _heuristica_extraccion(texto: str, tipo: str) -> dict:
    campos: Dict[str, Any] = {}
    nombre = _extraer_nombre(texto)
    tipo_doc = _normalizar_tipo_doc(texto)
    num_doc = _extraer_numero_documento_flexible(texto)
    telefono = _extraer_telefono(texto)

    if tipo == "personales":
        edad = ""
        match = re.search(r"edad[\s:]+([0-9]{1,3})(\s*(aÃ±os|meses))?", texto.lower())
        if match:
            edad = match.group(1)
            if match.group(3):
                edad = f"{edad} {match.group(3)}"
        sexo = "M" if re.search(r"\b(masculino|hombre|m)\b", texto.lower()) else ""
        if re.search(r"\b(femenino|mujer|f)\b", texto.lower()):
            sexo = "F"
        estado = ""
        if "soltero" in texto.lower():
            estado = "S"
        elif "casado" in texto.lower():
            estado = "C"
        elif "viudo" in texto.lower():
            estado = "V"
        elif "union libre" in texto.lower():
            estado = "UL"

        dia = ""
        mes = ""
        anio = ""
        d2, m2, a2 = _extraer_fecha_nacimiento_global(texto)
        if d2 and m2 and a2:
            dia, mes, anio = d2, m2, a2
        match = re.search(r"dia\s*(\d{1,2})", texto.lower())
        if match:
            dia = match.group(1)
        match = re.search(r"mes\s*(\d{1,2})", texto.lower())
        if match:
            mes = match.group(1)
        match = re.search(r"aÃ±o\s*(\d{2,4})", texto.lower())
        if match:
            anio = match.group(1)

        campos = {
            "nombre": nombre,
            "edad": edad,
            "tipo_documento": tipo_doc,
            "numero_documento": num_doc,
            "sexo": sexo,
            "dia_nacimiento": dia,
            "mes_nacimiento": mes,
            "anio_nacimiento": anio,
            "estado_civil": estado,
            "lugar_nacimiento": "",
            "aseguradora": "",
            "correo": _extraer_email(texto) or _normalizar_email_hablado(texto),
            "telefono": telefono,
            "municipio": "",
        }
    else:
        campos = {
            "nombre": nombre,
            "tipo_documento": tipo_doc,
            "numero_documento": num_doc,
            "telefono": telefono,
        }

    return {
        "campos": campos,
        "modelo_usado": "heuristico",
        "confianza": 0.55,
    }

def _capturar_por_clave(texto: str, claves: list[str], todas_claves: list[str]) -> str:
    texto_lower = texto.lower()
    for clave in claves:
        if clave in texto_lower:
            partes = re.split(rf"{re.escape(clave)}[\s:,-]*", texto, flags=re.IGNORECASE, maxsplit=1)
            if len(partes) > 1:
                candidato = partes[1].strip()
                if not candidato:
                    return ""
                candidato_lower = candidato.lower()
                cortes = []
                for k in todas_claves:
                    if k == clave:
                        continue
                    idx = candidato_lower.find(k)
                    if idx != -1:
                        cortes.append(idx)
                if cortes:
                    candidato = candidato[: min(cortes)].strip()
                return candidato
    return ""

def _rellenar_campos_desde_texto(texto: str, tipo: str, campos: Dict[str, Any]) -> Dict[str, Any]:
    resultado = dict(campos or {})
    if tipo == "personales":
        todas = [
            "nombre", "paciente", "me llamo", "se llama",
            "edad", "tipo de documento", "tipo documento", "documento", "cedula", "cÃ©dula",
            "numero de documento", "nÃºmero de documento",
            "sexo",
            "fecha de nacimiento", "dia de nacimiento", "dÃ­a de nacimiento", "mes de nacimiento", "aÃ±o de nacimiento", "anio de nacimiento",
            "estado civil", "lugar de nacimiento", "nacido en", "nacida en",
            "aseguradora", "eps",
            "correo", "correo electrÃ³nico", "email", "mail",
            "telefono", "telÃ©fono", "celular", "movil", "mÃ³vil",
            "municipio", "ciudad"
        ]
        if not resultado.get("nombre"):
            resultado["nombre"] = _capturar_por_clave(texto, ["nombre", "paciente", "me llamo", "se llama"], todas)
        if not resultado.get("edad"):
            resultado["edad"] = _capturar_por_clave(texto, ["edad"], todas)
        if not resultado.get("tipo_documento"):
            resultado["tipo_documento"] = _capturar_por_clave(texto, ["tipo de documento", "tipo documento"], todas)
        if not resultado.get("numero_documento"):
            resultado["numero_documento"] = _capturar_por_clave(
                texto,
                ["numero de documento", "nÃºmero de documento", "documento", "cedula", "cÃ©dula"],
                todas
            )
        if not resultado.get("numero_documento"):
            resultado["numero_documento"] = _extraer_numero_documento_flexible(texto)
        if not resultado.get("sexo"):
            resultado["sexo"] = _capturar_por_clave(texto, ["sexo"], todas)
        if not resultado.get("dia_nacimiento") or not resultado.get("mes_nacimiento") or not resultado.get("anio_nacimiento"):
            fecha_raw = _capturar_por_clave(texto, ["fecha de nacimiento"], todas)
            if fecha_raw:
                digitos = _solo_digitos(fecha_raw)
                if len(digitos) >= 8:
                    resultado["dia_nacimiento"] = digitos[0:2]
                    resultado["mes_nacimiento"] = digitos[2:4]
                    resultado["anio_nacimiento"] = digitos[4:8]
        if not resultado.get("dia_nacimiento"):
            resultado["dia_nacimiento"] = _capturar_por_clave(texto, ["dia de nacimiento", "dÃ­a de nacimiento", "dia"], todas)
        if not resultado.get("mes_nacimiento"):
            resultado["mes_nacimiento"] = _capturar_por_clave(texto, ["mes de nacimiento", "mes"], todas)
        if not resultado.get("anio_nacimiento"):
            resultado["anio_nacimiento"] = _capturar_por_clave(texto, ["aÃ±o de nacimiento", "anio de nacimiento", "aÃ±o", "anio"], todas)
        if (not resultado.get("dia_nacimiento")) or (not resultado.get("mes_nacimiento")) or (not resultado.get("anio_nacimiento")):
            d2, m2, a2 = _extraer_fecha_nacimiento_global(texto)
            if d2 and not resultado.get("dia_nacimiento"):
                resultado["dia_nacimiento"] = d2
            if m2 and not resultado.get("mes_nacimiento"):
                resultado["mes_nacimiento"] = m2
            if a2 and not resultado.get("anio_nacimiento"):
                resultado["anio_nacimiento"] = a2
        if not resultado.get("estado_civil"):
            resultado["estado_civil"] = _capturar_por_clave(texto, ["estado civil"], todas)
        if not resultado.get("lugar_nacimiento"):
            resultado["lugar_nacimiento"] = _capturar_por_clave(texto, ["lugar de nacimiento", "nacido en", "nacida en"], todas)
        if not resultado.get("aseguradora"):
            resultado["aseguradora"] = _capturar_por_clave(texto, ["aseguradora", "eps"], todas)
        if not resultado.get("correo"):
            resultado["correo"] = _capturar_por_clave(texto, ["correo", "correo electrÃ³nico", "email", "mail"], todas)
        if not resultado.get("correo"):
            resultado["correo"] = _normalizar_email_hablado(texto)
        if not resultado.get("telefono"):
            resultado["telefono"] = _capturar_por_clave(texto, ["telefono", "telÃ©fono", "celular", "movil", "mÃ³vil"], todas)
        if not resultado.get("municipio"):
            resultado["municipio"] = _capturar_por_clave(texto, ["municipio", "ciudad"], todas)
    else:
        todas = [
            "nombre", "acompaÃ±ante", "representante", "se llama",
            "tipo de documento", "tipo documento", "documento", "cedula", "cÃ©dula",
            "numero de documento", "nÃºmero de documento",
            "telefono", "telÃ©fono", "celular", "movil", "mÃ³vil"
        ]
        if not resultado.get("nombre"):
            resultado["nombre"] = _capturar_por_clave(texto, ["nombre", "acompaÃ±ante", "representante", "se llama"], todas)
        if not resultado.get("tipo_documento"):
            resultado["tipo_documento"] = _capturar_por_clave(texto, ["tipo de documento", "tipo documento"], todas)
        if not resultado.get("numero_documento"):
            resultado["numero_documento"] = _capturar_por_clave(
                texto,
                ["numero de documento", "nÃºmero de documento", "documento", "cedula", "cÃ©dula"],
                todas
            )
        if not resultado.get("numero_documento"):
            resultado["numero_documento"] = _extraer_numero_documento_flexible(texto)
        if not resultado.get("telefono"):
            resultado["telefono"] = _capturar_por_clave(texto, ["telefono", "telÃ©fono", "celular", "movil", "mÃ³vil"], todas)
    return resultado

def _normalizar_campos(tipo: str, campos: Dict[str, Any]) -> Dict[str, Any]:
    resultado = dict(campos or {})
    if tipo == "personales":
        if "nombre" in resultado:
            resultado["nombre"] = _solo_letras(_limpiar_muletillas_nombre(str(resultado["nombre"])))
        if "tipo_documento" in resultado:
            resultado["tipo_documento"] = _normalizar_tipo_doc(str(resultado["tipo_documento"]))
        if "numero_documento" in resultado:
            resultado["numero_documento"] = _solo_digitos(str(resultado["numero_documento"]))
        if "edad" in resultado:
            edad_txt = str(resultado["edad"]).lower()
            if "mes" in edad_txt:
                numero = _solo_digitos(edad_txt)
                if not numero:
                    numero = _solo_letras(edad_txt)
                resultado["edad"] = f"{numero} meses".strip()
            elif ("aÃ±" in edad_txt) or ("ano" in edad_txt):
                numero = _solo_digitos(edad_txt)
                if not numero:
                    numero = _solo_letras(edad_txt)
                resultado["edad"] = f"{numero} aÃ±os".strip()
            else:
                numero = _solo_digitos(edad_txt)
                if not numero:
                    numero = _solo_letras(edad_txt)
                resultado["edad"] = numero
        for k in ["dia_nacimiento", "mes_nacimiento", "anio_nacimiento", "telefono"]:
            if k in resultado:
                valor = _solo_digitos(str(resultado[k]))
                if not valor:
                    valor = _solo_letras(str(resultado[k]))
                resultado[k] = valor
        for k in ["lugar_nacimiento", "aseguradora", "municipio"]:
            if k in resultado:
                limpio = _recortar_contenido_contaminado(str(resultado[k]))
                resultado[k] = _capitalizar_nombre(_solo_letras(limpio))
        if "correo" in resultado:
            resultado["correo"] = _email_valido(str(resultado["correo"]))
        if "sexo" in resultado:
            s = str(resultado["sexo"]).upper()
            resultado["sexo"] = "M" if s.startswith("M") else "F" if s.startswith("F") else ""
        if "estado_civil" in resultado:
            ec = str(resultado["estado_civil"]).upper().strip()
            if ec not in {"S", "C", "V", "TV", "UL"}:
                ec = ""
            resultado["estado_civil"] = ec
    else:
        if "nombre" in resultado:
            resultado["nombre"] = _capitalizar_nombre(_solo_letras(_limpiar_muletillas_nombre(str(resultado["nombre"]))))
        if "tipo_documento" in resultado:
            resultado["tipo_documento"] = _normalizar_tipo_doc(str(resultado["tipo_documento"]))
        if "numero_documento" in resultado:
            valor = _solo_digitos(str(resultado["numero_documento"]))
            if not valor:
                valor = _solo_letras(str(resultado["numero_documento"]))
            resultado["numero_documento"] = valor
        if "telefono" in resultado:
            valor = _solo_digitos(str(resultado["telefono"]))
            if not valor:
                valor = _solo_letras(str(resultado["telefono"]))
            resultado["telefono"] = valor
    return resultado

def analizar_extraccion(texto: str, tipo: str) -> dict:
    prompt = construir_prompt_extraccion(texto, tipo)

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
                    "temperature": 0.1,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
            )
            salida = respuesta.text.strip()
            datos = _extraer_json_salida(salida)
            if not datos:
                continue
            campos = datos.get("campos") if isinstance(datos, dict) else None
            if not isinstance(campos, dict):
                campos = datos if isinstance(datos, dict) else {}
            campos = _rellenar_campos_desde_texto(texto, tipo, campos)
            campos_norm = _normalizar_campos(tipo, campos)
            for k, v in list(campos_norm.items()):
                if v is None or v == "":
                    campos_norm[k] = "No especificado"
            return {
                "campos": campos_norm,
                "modelo_usado": modelo_id,
                "confianza": 0.9,
            }
        except Exception as e:
            print(f"Error con {modelo_id}: {str(e)}")
            continue

    heur = _heuristica_extraccion(texto, tipo)
    heur["campos"] = _normalizar_campos(tipo, _rellenar_campos_desde_texto(texto, tipo, heur.get("campos", {})))
    for k, v in list(heur["campos"].items()):
        if v is None or v == "":
            heur["campos"][k] = "No especificado"
    return heur

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz(datos_usuario: dict = Depends(verificar_token)):
    return respuesta_ok({"servicio": "Project Parallel - Servicio de IA", "version": "1.0.0", "estado": "funcionando"})

@app.get("/salud", tags=["General"])
async def verificar_salud():
    try:
        await bd.command("ping")
        gemini_ok = bool(CLAVE_API_GEMINI)
        return respuesta_ok({"estado": "saludable", "mongodb": "ok", "gemini_configurado": gemini_ok})
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
    
    inicio = datetime.now(timezone.utc)
    
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
            tiempo_ms = int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
            
            # Guardar en caché
            await guardar_en_cache(hash_texto, resultado, solicitud.texto)
    else:
        # Forzar análisis sin caché
        resultado = analizar_con_gemini(solicitud.texto)
        tiempo_ms = int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
    
    # Registrar uso
    await registrar_log_ia(
        id_usuario=int(datos_usuario.get("sub")),
        texto_entrada=solicitud.texto,
        resultado=resultado,
        tiempo_ms=tiempo_ms,
        desde_cache=desde_cache,
        modelo=resultado.get("modelo_usado", "desconocido")
    )
    
    return respuesta_ok({"texto_corregido": resultado["texto_corregido"], "campos_extraidos": {"paciente": resultado["paciente"], "edad": resultado["edad"], "motivo": resultado["motivo"], "diagnostico": resultado["diagnostico"], "tratamiento": resultado["tratamiento"]}, "confianza": resultado.get("confianza", 0.85), "modelo_usado": resultado.get("modelo_usado", "desconocido"), "tiempo_procesamiento_ms": tiempo_ms, "desde_cache": desde_cache})

@app.post("/api/v1/ia/extraer", tags=["Analisis IA"])
async def extraer_campos(
    solicitud: SolicitudExtraccion,
    datos_usuario: dict = Depends(verificar_token)
):
    inicio = datetime.now(timezone.utc)
    tipo = (solicitud.tipo or "").strip().lower()
    if tipo not in {"personales", "acompanante", "representante"}:
        raise HTTPException(status_code=400, detail="Tipo no soportado")

    hash_texto = generar_hash_cache(f"{tipo}:{solicitud.texto}")
    desde_cache = False

    if solicitud.usar_cache:
        resultado_cache = await obtener_desde_cache(hash_texto)
        if resultado_cache:
            desde_cache = True
            resultado = resultado_cache
            tiempo_ms = 10
        else:
            resultado = analizar_extraccion(solicitud.texto, tipo)
            tiempo_ms = int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
            await guardar_en_cache(hash_texto, resultado, solicitud.texto)
    else:
        resultado = analizar_extraccion(solicitud.texto, tipo)
        tiempo_ms = int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)

    await registrar_log_ia(
        id_usuario=int(datos_usuario.get("sub")),
        texto_entrada=solicitud.texto,
        resultado=resultado,
        tiempo_ms=tiempo_ms,
        desde_cache=desde_cache,
        modelo=resultado.get("modelo_usado", "desconocido")
    )

    return respuesta_ok({"campos": resultado.get("campos", {}), "confianza": resultado.get("confianza", 0.85), "modelo_usado": resultado.get("modelo_usado", "desconocido"), "tiempo_procesamiento_ms": tiempo_ms, "desde_cache": desde_cache})

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
    tiempo_promedio = int(resultado[0].get("tiempo_promedio", 0)) if resultado else 0
    
    return respuesta_ok({"total_analisis": total, "desde_cache": desde_cache, "nuevos_analisis": total - desde_cache, "tiempo_promedio_ms": tiempo_promedio, "porcentaje_cache": round((desde_cache / total * 100), 2) if total > 0 else 0})

@app.delete("/api/v1/ia/cache/limpiar", tags=["Cache"])
async def limpiar_cache(
    datos_usuario: dict = Depends(verificar_token)
):
    """Limpiar caché antiguo (más de 7 días)"""
    
    fecha_limite = datetime.now(timezone.utc)
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
