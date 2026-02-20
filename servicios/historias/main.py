# servicios/historias/main.py
"""
Microservicio de Historias Clínicas - Project Parallel
CRUD completo de historias clínicas con estados y búsquedas
"""

from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Mapping, cast
from datetime import datetime, timezone
from sqlalchemy import create_engine, Integer, String, Text, DateTime, text
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
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
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", ""))
if not SECRETO_JWT:
    raise RuntimeError("SECRETO_JWT/JWT_SECRET es obligatorio")

# ==================== CONFIGURACIÓN BASE DE DATOS ====================
motor = create_engine(URL_BASE_DATOS, pool_pre_ping=True)
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)
Base = declarative_base()

# ==================== MODELOS DE BASE DE DATOS ====================
class HistoriaClinica(Base):
    __tablename__ = "historias_clinicas"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    consecutivo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    id_usuario: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    usuario: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Datos del paciente
    paciente: Mapped[str] = mapped_column(String(200), nullable=False)
    edad: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Datos clínicos
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostico: Mapped[Optional[str]] = mapped_column(Text)
    tratamiento: Mapped[Optional[str]] = mapped_column(Text)
    
    # Datos de audio (referencia al servicio de audio)
    id_audio: Mapped[Optional[str]] = mapped_column(String(100))
    transcripcion: Mapped[Optional[str]] = mapped_column(Text)
    texto_corregido: Mapped[Optional[str]] = mapped_column(Text)
    
    # Estado y fechas
    estado: Mapped[str] = mapped_column(String(20), default="incompleta", index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    fecha_completado: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Datos adicionales
    ubicacion: Mapped[Optional[str]] = mapped_column(String(200))
    signos_vitales: Mapped[Optional[str]] = mapped_column(Text)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

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
_origenes.add("http://localhost:5174")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_origenes),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def respuesta_ok(datos: Any, mensaje: str = "Operaci?n exitosa") -> Dict[str, Any]:
    return {"estado": "ok", "datos": datos, "mensaje": mensaje}

# ==================== DEPENDENCIAS ====================
def obtener_bd():
    """Dependency para obtener sesión de base de datos"""
    bd = SesionLocal()
    try:
        yield bd
    finally:
        bd.close()

def verificar_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Verificar token JWT y extraer información del usuario"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    
    try:
        esquema, token = authorization.split()
        if esquema.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Esquema de autorización inválido")
        
        payload = jwt.decode(token, SECRETO_JWT, algorithms=["HS256"])  # type: ignore[reportUnknownMemberType]
        return cast(Dict[str, Any], dict(payload))
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
    año_actual = datetime.now(timezone.utc).year
    return f"HC-{año_actual}-{(total + 1):05d}"

def extraer_id_usuario(payload: Mapping[str, Any]) -> int:
    id_usuario = payload.get("sub")
    if id_usuario is None:
        raise HTTPException(status_code=401, detail="Token inválido")
    try:
        return int(id_usuario)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido")

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz(datos_usuario: Dict[str, Any] = Depends(verificar_token)) -> Dict[str, Any]:
    """Endpoint raíz del servicio"""
    return {
        "servicio": "Project Parallel - Servicio de Historias Clínicas",
        "version": "1.0.0",
        "estado": "funcionando"
    }

@app.get("/salud", tags=["General"])
async def verificar_salud() -> Dict[str, Any]:
    """Verificación de salud del servicio"""
    try:
        bd = SesionLocal()
        bd.execute(text("SELECT 1"))
        bd.close()
        return respuesta_ok({"estado": "saludable", "base_datos": "ok"})
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No saludable: {str(e)}")

@app.post("/api/v1/historias", status_code=201, tags=["Historias"])
async def crear_historia(
    datos: CrearHistoria,
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Crear nueva historia clínica"""
    
    consecutivo = generar_consecutivo(bd)
    
    nueva_historia = HistoriaClinica(
        consecutivo=consecutivo,
        id_usuario=extraer_id_usuario(datos_usuario),
        usuario=str(datos_usuario.get("usuario", "")),
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
    
    return respuesta_ok(RespuestaHistoria.model_validate(nueva_historia).model_dump(), "Historia creada")

@app.get("/api/v1/historias", tags=["Historias"])
async def listar_historias(
    estado: Optional[str] = Query(None, pattern="^(incompleta|completa)$"),
    paciente: Optional[str] = Query(None, description="Buscar por nombre de paciente"),
    fecha_desde: Optional[datetime] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    pagina: int = Query(1, ge=1, description="Número de página"),
    por_pagina: int = Query(50, ge=1, le=100, description="Resultados por página"),
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Listar historias clínicas con filtros"""
    
    id_usuario = extraer_id_usuario(datos_usuario)
    
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
    
    return respuesta_ok(ListaHistorias(total=total, pagina=pagina, por_pagina=por_pagina, historias=cast(List[RespuestaHistoria], historias)).model_dump())

@app.get("/api/v1/historias/{consecutivo}", tags=["Historias"])
async def obtener_historia(
    consecutivo: str,
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Obtener historia clínica por consecutivo"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    # Verificar que el usuario sea dueño
    if historia.id_usuario != extraer_id_usuario(datos_usuario):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    return respuesta_ok(RespuestaHistoria.model_validate(historia).model_dump())

@app.put("/api/v1/historias/{consecutivo}", tags=["Historias"])
async def actualizar_historia(
    consecutivo: str,
    datos: ActualizarHistoria,
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Actualizar historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != extraer_id_usuario(datos_usuario):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    # Actualizar campos proporcionados
    datos_actualizacion = datos.model_dump(exclude_unset=True)
    for campo, valor in datos_actualizacion.items():
        setattr(historia, campo, valor)
    
    bd.commit()
    bd.refresh(historia)
    
    return respuesta_ok(RespuestaHistoria.model_validate(historia).model_dump())

@app.put("/api/v1/historias/{consecutivo}/estado", tags=["Historias"])
async def actualizar_estado_historia(
    consecutivo: str,
    datos_estado: ActualizarEstado,
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Actualizar estado de historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != extraer_id_usuario(datos_usuario):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    historia.estado = datos_estado.estado
    
    # Si se marca como completa, guardar fecha
    if datos_estado.estado == "completa" and historia.fecha_completado is None:
        historia.fecha_completado = datetime.now(timezone.utc)
    
    bd.commit()
    bd.refresh(historia)
    
    return respuesta_ok(RespuestaHistoria.model_validate(historia).model_dump())

@app.delete("/api/v1/historias/{consecutivo}", tags=["Historias"])
async def eliminar_historia(
    consecutivo: str,
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
):
    """Eliminar historia clínica"""
    
    historia = bd.query(HistoriaClinica).filter(
        HistoriaClinica.consecutivo == consecutivo
    ).first()
    
    if not historia:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    
    if historia.id_usuario != extraer_id_usuario(datos_usuario):
        raise HTTPException(status_code=403, detail="No autorizado")
    
    bd.delete(historia)
    bd.commit()
    
    return respuesta_ok({}, f"Historia {consecutivo} eliminada exitosamente")

@app.get("/api/v1/historias/estadisticas/resumen", tags=["Estadísticas"])
async def obtener_estadisticas(
    datos_usuario: Dict[str, Any] = Depends(verificar_token),
    bd: Session = Depends(obtener_bd)
) -> Dict[str, Any]:
    """Obtener estadísticas de historias del usuario"""
    
    id_usuario = extraer_id_usuario(datos_usuario)
    
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
    
    return respuesta_ok({"total_historias": total, "incompletas": incompletas, "completas": completas, "ultima_historia": {"consecutivo": ultima.consecutivo, "paciente": ultima.paciente, "fecha": ultima.fecha_creacion.isoformat()} if ultima else None})

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
