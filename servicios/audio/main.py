# servicios/audio/main.py
"""
Microservicio de Procesamiento de Audio - Project Parallel
Maneja grabación, almacenamiento y transcripción de audio con Whisper
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import os
import uuid
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from minio import Minio
from minio.error import S3Error
import whisper
import tempfile
import io
import re
import jwt
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

# ==================== CONFIGURACIÓN ====================
URL_MONGODB = os.getenv("URL_MONGODB", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
ENDPOINT_MINIO = os.getenv("ENDPOINT_MINIO", os.getenv("MINIO_ENDPOINT", "localhost:9000"))
CLAVE_ACCESO_MINIO = os.getenv("CLAVE_ACCESO_MINIO", os.getenv("MINIO_USER", "admin"))
CLAVE_SECRETA_MINIO = os.getenv("CLAVE_SECRETA_MINIO", os.getenv("MINIO_PASSWORD", "password"))
BUCKET_MINIO = "archivos-audio"
MINIO_SEGURO = os.getenv("MINIO_SEGURO", os.getenv("MINIO_SECURE", "False")).lower() == "true"
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", "cambia-esto-en-produccion-abc123xyz"))

# ==================== CLIENTES ====================
app = FastAPI(
    title="Project Parallel - Servicio de Audio",
    version="1.0.0",
    description="Microservicio de procesamiento de audio con transcripción automática"
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

# Cliente MongoDB
cliente_mongo = AsyncIOMotorClient(URL_MONGODB)
bd = cliente_mongo.project_parallel
coleccion_audios = bd.audios

# Cliente MinIO
cliente_minio = Minio(
    ENDPOINT_MINIO,
    access_key=CLAVE_ACCESO_MINIO,
    secret_key=CLAVE_SECRETA_MINIO,
    secure=MINIO_SEGURO
)

# Asegurar que el bucket existe
try:
    if not cliente_minio.bucket_exists(BUCKET_MINIO):
        cliente_minio.make_bucket(BUCKET_MINIO)
        print(f"✅ Bucket '{BUCKET_MINIO}' creado exitosamente")
except S3Error as e:
    print(f"⚠️ Error configurando MinIO: {e}")

# Modelo Whisper (se carga una vez al inicio)
print("🔄 Cargando modelo Whisper...")
modelo_whisper = whisper.load_model("medium")
print("✅ Modelo Whisper cargado")

# ==================== ESQUEMAS ====================
class RespuestaSubidaAudio(BaseModel):
    id_audio: str = Field(..., description="ID único del audio")
    estado: str = Field(..., description="Estado del procesamiento")
    mensaje: str = Field(..., description="Mensaje informativo")

class RespuestaEstadoAudio(BaseModel):
    id_audio: str
    estado: str  # pendiente, procesando, completado, fallido
    transcripcion: Optional[str] = None
    duracion_segundos: Optional[float] = None
    fecha_creacion: datetime
    fecha_procesamiento: Optional[datetime] = None
    error: Optional[str] = None

class SolicitudTranscripcion(BaseModel):
    id_audio: str = Field(..., description="ID del audio a transcribir")

# ==================== FUNCIONES AUXILIARES ====================

def verificar_token(authorization: Optional[str] = Header(None)) -> dict:
    """Verificar token JWT y extraer información del usuario"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
    try:
        # Extraer token del header "Bearer {token}"
        esquema, token = authorization.split()
        if esquema.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Esquema de autorización inválido")
        
        # Decodificar token
        payload = jwt.decode(token, SECRETO_JWT, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    except Exception:
        raise HTTPException(status_code=401, detail="Error de autenticación")

async def guardar_en_minio(
    contenido_archivo: bytes,
    nombre_archivo: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Subir archivo a MinIO y retornar nombre del objeto"""
    nombre_objeto = f"{uuid.uuid4()}_{nombre_archivo}"
    
    try:
        cliente_minio.put_object(
            BUCKET_MINIO,
            nombre_objeto,
            io.BytesIO(contenido_archivo),
            length=len(contenido_archivo),
            content_type=content_type or "application/octet-stream",
        )
        return nombre_objeto
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Error en MinIO: {str(e)}")

async def obtener_de_minio(nombre_objeto: str) -> bytes:
    """Descargar archivo desde MinIO"""
    try:
        respuesta = cliente_minio.get_object(BUCKET_MINIO, nombre_objeto)
        datos = respuesta.read()
        respuesta.close()
        respuesta.release_conn()
        return datos
    except S3Error as e:
        raise HTTPException(status_code=404, detail=f"Audio no encontrado: {str(e)}")

def limpiar_transcripcion(texto: str) -> str:
    """Limpiar transcripción de muletillas y normalizar"""
    if not isinstance(texto, str):
        return ""
    
    # Muletillas a eliminar
    muletillas = [
        r"\beh\b", r"\beste\b", r"\bpues\b", r"\bo sea\b", 
        r"\bmmm\b", r"\bajá\b", r"\bem\b", r"\bah\b", 
        r"\bdigamos\b", r"\bentonces\b"
    ]
    
    for muletilla in muletillas:
        texto = re.sub(muletilla, " ", texto, flags=re.IGNORECASE)
    
    # Normalizar espacios
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s+([.,!?;:])", r"\1", texto)
    texto = texto.strip()
    
    # Capitalizar primera letra
    if texto:
        texto = texto[0].upper() + texto[1:]
    
    return texto

async def transcribir_audio(id_audio: str):
    """Tarea en segundo plano para transcribir audio usando Whisper"""
    try:
        # Actualizar estado a procesando
        await coleccion_audios.update_one(
            {"_id": id_audio},
            {
                "$set": {
                    "estado": "procesando",
                    "fecha_inicio_procesamiento": datetime.utcnow()
                }
            }
        )
        
        # Obtener metadata del audio
        doc_audio = await coleccion_audios.find_one({"_id": id_audio})
        if not doc_audio:
            raise Exception("Documento de audio no encontrado")
        
        # Descargar desde MinIO
        bytes_audio = await obtener_de_minio(doc_audio["nombre_objeto_s3"])
        
        # Guardar en archivo temporal para Whisper
        _, ext = os.path.splitext(doc_audio.get("nombre_archivo_original", ""))
        if not ext:
            ext = ".wav"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(bytes_audio)
            ruta_tmp = tmp.name
        
        try:
            # Transcribir con Whisper
            print(f"🎙️ Transcribiendo audio {id_audio}...")
            resultado = modelo_whisper.transcribe(ruta_tmp, fp16=False, language="es")
            transcripcion_raw = resultado.get("text", "").strip()
            
            # Limpiar transcripción
            transcripcion = limpiar_transcripcion(transcripcion_raw)
            
            print(f"✅ Transcripción completada: {transcripcion[:100]}...")
            
            # Actualizar documento con transcripción
            await coleccion_audios.update_one(
                {"_id": id_audio},
                {
                    "$set": {
                        "estado": "completado",
                        "transcripcion": transcripcion,
                        "transcripcion_raw": transcripcion_raw,
                        "fecha_procesamiento": datetime.utcnow()
                    }
                }
            )
            
        finally:
            # Limpiar archivo temporal
            if os.path.exists(ruta_tmp):
                os.remove(ruta_tmp)
                
    except Exception as e:
        print(f"❌ Error transcribiendo audio {id_audio}: {str(e)}")
        # Actualizar estado a fallido
        await coleccion_audios.update_one(
            {"_id": id_audio},
            {
                "$set": {
                    "estado": "fallido",
                    "error": str(e),
                    "fecha_procesamiento": datetime.utcnow()
                }
            }
        )

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz():
    """Endpoint raíz del servicio"""
    return {
        "servicio": "Project Parallel - Servicio de Audio",
        "version": "1.0.0",
        "estado": "funcionando"
    }

@app.get("/salud", tags=["General"])
async def verificar_salud():
    """Verificación de salud del servicio"""
    try:
        # Verificar MongoDB
        await bd.command("ping")
        
        # Verificar MinIO
        cliente_minio.bucket_exists(BUCKET_MINIO)
        
        return {
            "estado": "saludable",
            "mongodb": "ok",
            "minio": "ok",
            "modelo_whisper": "cargado"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No saludable: {str(e)}")

@app.post("/api/v1/audio/subir", response_model=RespuestaSubidaAudio, tags=["Audio"])
async def subir_audio(
    archivo: UploadFile = File(..., description="Archivo de audio (WAV recomendado)"),
    tareas_fondo: BackgroundTasks = None,
    datos_usuario: dict = Depends(verificar_token)
):
    """Subir archivo de audio y activar transcripción automática"""
    
    # Validar tipo de archivo
    if not archivo.content_type or not archivo.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser de tipo audio"
        )
    
    # Leer contenido del archivo
    contenido = await archivo.read()
    
    if len(contenido) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    
    # Generar ID único
    id_audio = str(uuid.uuid4())
    
    # Subir a MinIO
    nombre_objeto = await guardar_en_minio(contenido, archivo.filename, archivo.content_type or "application/octet-stream")
    
    # Crear documento en MongoDB
    doc_audio = {
        "_id": id_audio,
        "id_usuario": int(datos_usuario.get("sub")),
        "usuario": datos_usuario.get("usuario"),
        "nombre_archivo_original": archivo.filename,
        "nombre_objeto_s3": nombre_objeto,
        "bucket_s3": BUCKET_MINIO,
        "tamano_bytes": len(contenido),
        "tipo_contenido": archivo.content_type,
        "estado": "pendiente",
        "transcripcion": None,
        "fecha_creacion": datetime.utcnow(),
        "fecha_procesamiento": None,
        "error": None
    }
    
    await coleccion_audios.insert_one(doc_audio)
    
    # Activar transcripción en segundo plano
    tareas_fondo.add_task(transcribir_audio, id_audio)
    
    return RespuestaSubidaAudio(
        id_audio=id_audio,
        estado="pendiente",
        mensaje="Audio subido exitosamente. Transcripción en progreso."
    )

@app.get("/api/v1/audio/{id_audio}/estado", response_model=RespuestaEstadoAudio, tags=["Audio"])
async def obtener_estado_audio(
    id_audio: str,
    datos_usuario: dict = Depends(verificar_token)
):
    """Obtener estado de transcripción del audio"""
    
    doc_audio = await coleccion_audios.find_one({"_id": id_audio})
    
    if not doc_audio:
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    
    # Verificar que el usuario sea dueño del audio
    if doc_audio["id_usuario"] != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado para ver este audio")
    
    return RespuestaEstadoAudio(
        id_audio=doc_audio["_id"],
        estado=doc_audio["estado"],
        transcripcion=doc_audio.get("transcripcion"),
        duracion_segundos=doc_audio.get("duracion_segundos"),
        fecha_creacion=doc_audio["fecha_creacion"],
        fecha_procesamiento=doc_audio.get("fecha_procesamiento"),
        error=doc_audio.get("error")
    )

@app.get("/api/v1/audio/{id_audio}/descargar", tags=["Audio"])
async def descargar_audio(
    id_audio: str,
    datos_usuario: dict = Depends(verificar_token)
):
    """Descargar archivo de audio original"""
    
    doc_audio = await coleccion_audios.find_one({"_id": id_audio})
    
    if not doc_audio:
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    
    # Verificar permisos
    if doc_audio["id_usuario"] != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    # Descargar desde MinIO
    bytes_audio = await obtener_de_minio(doc_audio["nombre_objeto_s3"])
    
    return StreamingResponse(
        io.BytesIO(bytes_audio),
        media_type=doc_audio.get("tipo_contenido", "audio/wav"),
        headers={
            "Content-Disposition": f'attachment; filename="{doc_audio["nombre_archivo_original"]}"'
        }
    )

@app.delete("/api/v1/audio/{id_audio}", tags=["Audio"])
async def eliminar_audio(
    id_audio: str,
    datos_usuario: dict = Depends(verificar_token)
):
    """Eliminar archivo de audio y metadata"""
    
    doc_audio = await coleccion_audios.find_one({"_id": id_audio})
    
    if not doc_audio:
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    
    # Verificar permisos
    if doc_audio["id_usuario"] != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    # Eliminar de MinIO
    try:
        cliente_minio.remove_object(BUCKET_MINIO, doc_audio["nombre_objeto_s3"])
    except S3Error:
        pass  # Ya eliminado o no existe
    
    # Eliminar de MongoDB
    await coleccion_audios.delete_one({"_id": id_audio})
    
    return {"mensaje": "Audio eliminado exitosamente"}

@app.get("/api/v1/audio/usuario/listar", tags=["Audio"])
async def listar_audios_usuario(
    limite: int = 50,
    datos_usuario: dict = Depends(verificar_token)
):
    """Listar todos los audios del usuario actual"""
    
    id_usuario = int(datos_usuario.get("sub"))
    
    cursor = coleccion_audios.find(
        {"id_usuario": id_usuario}
    ).sort("fecha_creacion", -1).limit(limite)
    
    audios = await cursor.to_list(length=limite)
    
    return {
        "total": len(audios),
        "audios": [
            {
                "id_audio": a["_id"],
                "nombre_archivo": a["nombre_archivo_original"],
                "estado": a["estado"],
                "fecha_creacion": a["fecha_creacion"],
                "tiene_transcripcion": a.get("transcripcion") is not None
            }
            for a in audios
        ]
    }

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
