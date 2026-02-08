# servicios/historias/main.py
"""
Microservicio de Historias Clínicas - Project Parallel
CRUD completo de historias clínicas con estados y búsquedas
"""

from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
import jwt
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

# ==================== CONFIGURACIÓN ====================
URL_BASE_DATOS = os.getenv(
    "URL_BASE_DATOS",
    os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/project_parallel"),
)
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", "cambia-esto-en-produccion-abc123xyz"))

# ==================== CONFIGURACIÓN BASE DE DATOS ====================
motor = create_engine(URL_BASE_DATOS)
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)
Base = declarative_base()

# ==================== MODELOS DE BASE DE DATOS ====================
class HistoriaClinica(Base):
    __tablename__ = "historias_clinicas"
    
    id = Column(Integer, primary_key=True, index=True)
    consecutivo = Column(String(50), unique=True, nullable=False, index=True)
    id_usuario = Column(Integer, nullable=False, index=True)
    usuario = Column(String(100), nullable=False)
    
    # Datos del paciente
    paciente = Column(String(200), nullable=False)
    edad = Column(Integer, nullable=False)
    
    # Datos clínicos
    motivo = Column(Text, nullable=False)
    diagnostico = Column(Text)
    tratamiento = Column(Text)
    
    # Datos de audio (referencia al servicio de audio)
    id_audio = Column(String(100))
    transcripcion = Column(Text)
    texto_corregido = Column(Text)
    
    # Estado y fechas
    estado = Column(String(20), default="incompleta", index=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, index=True)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fecha_completado = Column(DateTime)
    
    # Datos adicionales
    ubicacion = Column(String(200))
    signos_vitales = Column(Text)
    observaciones = Column(Text)

# Crear tablas
Base.metadata.create_all(bind=motor)

# ==================== ESQUEMAS PYDANTIC ====================
class CrearHistoria(BaseModel):
    paciente: str = Field(..., min_length=3, description="Nombre del paciente")
    edad: int = Field(..., ge=0, le=150, description="Edad del paciente")
    motivo: str = Field(..., min_length=10, description="Motivo de atención")
    diagnostico: Optional[str] = Field(None, description="Diagnóstico o impresión diagnóstica")
    tratamiento: Optional[str] = Field(None, description="Tratamiento realizado")
    id_audio: Optional[str] = Field(None, description="ID del audio asociado")
    transcripcion: Optional[str] = Field(None, description="Transcripción del audio")
    texto_corregido: Optional[str] = Field(None, description="Texto corregido por IA")
    ubicacion: Optional[str] = Field(None, description="Ubicación del incidente")
    signos_vitales: Optional[str] = Field(None, description="Signos vitales del paciente")
    observaciones: Optional[str] = Field(None, description="Observaciones adicionales")

class ActualizarHistoria(BaseModel):
    paciente: Optional[str] = None
    edad: Optional[int] = Field(None, ge=0, le=150)
    motivo: Optional[str] = None
    diagnostico: Optional[str] = None
    tratamiento: Optional[str] = None
    id_audio: Optional[str] = None
    transcripcion: Optional[str] = None
    texto_corregido: Optional[str] = None
    ubicacion: Optional[str] = None
    signos_vitales: Optional[str] = None
    observaciones: Optional[str] = None

class ActualizarEstado(BaseModel):
    estado: str = Field(..., pattern="^(incompleta|completa)$", description="Estado de la historia")

class RespuestaHistoria(BaseModel):
    id: int
    consecutivo: str
    usuario: str
    paciente: str
    edad: int
    motivo: str
    diagnostico: Optional[str]
    tratamiento: Optional[str]
    id_audio: Optional[str]
    transcripcion: Optional[str]
    texto_corregido: Optional[str]
    estado: str
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    fecha_completado: Optional[datetime]
    ubicacion: Optional[str]
    signos_vitales: Optional[str]
    observaciones: Optional[str]

    class Config:
        from_attributes = True

class ListaHistorias(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    historias: List[RespuestaHistoria]

# ==================== APLICACIÓN FASTAPI ====================
app = FastAPI(
    title="Project Parallel - Servicio de Historias Clínicas",
    version="1.0.0",
    description="Microservicio CRUD para gestión de historias clínicas de ambulancia"
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

# ==================== DEPENDENCIAS ====================
def obtener_bd():
    """Dependency para obtener sesión de base de datos"""
    bd = SesionLocal()
    try:
        yield bd
    finally:
        bd.close()

def verificar_token(authorization: Optional[str] = Header(None)) -> dict:
    """Verificar token JWT y extraer información del usuario"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
    try:
        esquema, token = authorization.split()
        if esquema.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Esquema de autorización inválido")
        
        payload = jwt.decode(token, SECRETO_JWT, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    except Exception:
        raise HTTPException(status_code=401, detail="Error de autenticación")

def generar_consecutivo(bd: Session) -> str:
    """Generar consecutivo automático para nueva historia"""
    from sqlalchemy import func
    total = bd.query(func.count(HistoriaClinica.id)).scalar()
    año_actual = datetime.now().year
    return f"HC-{año_actual}-{(total + 1):05d}"

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz():
    """Endpoint raíz del servicio"""
    return {
        "servicio": "Project Parallel - Servicio de Historias Clínicas",
        "version": "1.0.0",
        "estado": "funcionando"
    }

@app.get("/salud", tags=["General"])
async def verificar_salud():
    """Verificación de salud del servicio"""
    try:
        bd = SesionLocal()
        bd.execute("SELECT 1")
        bd.close()
        return {"estado": "saludable", "base_datos": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No saludable: {str(e)}")

@app.post("/api/v1/historias", response_model=RespuestaHistoria, status_code=201, tags=["Historias"])
async def crear_historia(
    datos: CrearHistoria,
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Crear nueva historia clínica"""
    
    consecutivo = generar_consecutivo(bd)
    
    nueva_historia = HistoriaClinica(
        consecutivo=consecutivo,
        id_usuario=int(datos_usuario.get("sub")),
        usuario=datos_usuario.get("usuario"),
        paciente=datos.paciente,
        edad=datos.edad,
        motivo=datos.motivo,
        diagnostico=datos.diagnostico,
        tratamiento=datos.tratamiento,
        id_audio=datos.id_audio,
        transcripcion=datos.transcripcion,
        texto_corregido=datos.texto_corregido,
        ubicacion=datos.ubicacion,
        signos_vitales=datos.signos_vitales,
        observaciones=datos.observaciones,
        estado="incompleta"
    )
    
    bd.add(nueva_historia)
    bd.commit()
    bd.refresh(nueva_historia)
    
    return nueva_historia

@app.get("/api/v1/historias", response_model=ListaHistorias, tags=["Historias"])
async def listar_historias(
    estado: Optional[str] = Query(None, pattern="^(incompleta|completa)$"),
    paciente: Optional[str] = Query(None, description="Buscar por nombre de paciente"),
    fecha_desde: Optional[datetime] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    pagina: int = Query(1, ge=1, description="Número de página"),
    por_pagina: int = Query(50, ge=1, le=100, description="Resultados por página"),
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Listar historias clínicas con filtros"""
    
    id_usuario = int(datos_usuario.get("sub"))
    
    # Construir query base
    query = bd.query(HistoriaClinica).filter(HistoriaClinica.id_usuario == id_usuario)
    
    # Aplicar filtros
    if estado:
        query = query.filter(HistoriaClinica.estado == estado)
    
    if paciente:
        query = query.filter(HistoriaClinica.paciente.ilike(f"%{paciente}%"))
    
    if fecha_desde:
        query = query.filter(HistoriaClinica.fecha_creacion >= fecha_desde)
    
    if fecha_hasta:
        query = query.filter(HistoriaClinica.fecha_creacion <= fecha_hasta)
    
    # Contar total
    total = query.count()
    
    # Paginación
    offset = (pagina - 1) * por_pagina
    historias = query.order_by(HistoriaClinica.fecha_creacion.desc()).offset(offset).limit(por_pagina).all()
    
    return ListaHistorias(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        historias=historias
    )

@app.get("/api/v1/historias/{consecutivo}", response_model=RespuestaHistoria, tags=["Historias"])
async def obtener_historia(
    consecutivo: str,
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Obtener historia clínica por consecutivo"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    # Verificar que el usuario sea dueño
    if historia.id_usuario != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    return historia

@app.put("/api/v1/historias/{consecutivo}", response_model=RespuestaHistoria, tags=["Historias"])
async def actualizar_historia(
    consecutivo: str,
    datos: ActualizarHistoria,
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Actualizar historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    # Actualizar campos proporcionados
    datos_actualizacion = datos.dict(exclude_unset=True)
    for campo, valor in datos_actualizacion.items():
        setattr(historia, campo, valor)
    
    bd.commit()
    bd.refresh(historia)
    
    return historia

@app.put("/api/v1/historias/{consecutivo}/estado", response_model=RespuestaHistoria, tags=["Historias"])
async def actualizar_estado_historia(
    consecutivo: str,
    datos_estado: ActualizarEstado,
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Actualizar estado de historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    historia.estado = datos_estado.estado
    
    # Si se marca como completa, guardar fecha
    if datos_estado.estado == "completa" and not historia.fecha_completado:
        historia.fecha_completado = datetime.utcnow()
    
    bd.commit()
    bd.refresh(historia)
    
    return historia

@app.delete("/api/v1/historias/{consecutivo}", tags=["Historias"])
async def eliminar_historia(
    consecutivo: str,
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Eliminar historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != int(datos_usuario.get("sub")):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    bd.delete(historia)
    bd.commit()
    
    return {"mensaje": f"Historia {consecutivo} eliminada exitosamente"}

@app.get("/api/v1/historias/estadisticas/resumen", tags=["Estadísticas"])
async def obtener_estadisticas(
    datos_usuario: dict = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Obtener estadísticas de historias del usuario"""
    
    id_usuario = int(datos_usuario.get("sub"))
    
    from sqlalchemy import func
    
    total = bd.query(func.count(HistoriaClinica.id)).filter(
        HistoriaClinica.id_usuario == id_usuario
    ).scalar()
    
    incompletas = bd.query(func.count(HistoriaClinica.id)).filter(
        HistoriaClinica.id_usuario == id_usuario,
        HistoriaClinica.estado == "incompleta"
    ).scalar()
    
    completas = bd.query(func.count(HistoriaClinica.id)).filter(
        HistoriaClinica.id_usuario == id_usuario,
        HistoriaClinica.estado == "completa"
    ).scalar()
    
    # Última historia creada
    ultima = bd.query(HistoriaClinica).filter(
        HistoriaClinica.id_usuario == id_usuario
    ).order_by(HistoriaClinica.fecha_creacion.desc()).first()
    
    return {
        "total_historias": total,
        "incompletas": incompletas,
        "completas": completas,
        "ultima_historia": {
            "consecutivo": ultima.consecutivo,
            "paciente": ultima.paciente,
            "fecha": ultima.fecha_creacion
        } if ultima else None
    }

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
