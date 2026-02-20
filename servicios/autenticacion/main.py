# servicios/autenticacion/main.py
"""
Microservicio de Autenticación - Project Parallel
Sistema de autenticación con JWT, PostgreSQL y Redis
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Any, Mapping, Dict, cast
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from redis import Redis
from sqlalchemy import create_engine, Integer, String, Boolean, DateTime, text
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.orm import sessionmaker, Session
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

# ==================== CONFIGURACIÓN ====================
URL_BASE_DATOS = os.getenv(
    "URL_BASE_DATOS",
    os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/project_parallel"),
)
URL_REDIS = os.getenv("URL_REDIS", os.getenv("REDIS_URL", "redis://localhost:6379"))
SECRETO_JWT = os.getenv("SECRETO_JWT", os.getenv("JWT_SECRET", ""))
ALGORITMO_JWT = os.getenv("JWT_ALGORITHM", "HS256")
MINUTOS_EXPIRACION_TOKEN_ACCESO = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
DIAS_EXPIRACION_TOKEN_REFRESCO = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

if not SECRETO_JWT:
    raise RuntimeError("SECRETO_JWT/JWT_SECRET es obligatorio")

# ==================== CONFIGURACIÓN BASE DE DATOS ====================
if "connect_timeout=" not in URL_BASE_DATOS:
    sep = "&" if "?" in URL_BASE_DATOS else "?"
    URL_BASE_DATOS = f"{URL_BASE_DATOS}{sep}connect_timeout=5"
motor = create_engine(URL_BASE_DATOS, pool_pre_ping=True)
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)
Base = declarative_base()

# Cliente Redis para lista negra de tokens
if "socket_connect_timeout=" not in URL_REDIS:
    sep = "&" if "?" in URL_REDIS else "?"
    URL_REDIS = f"{URL_REDIS}{sep}socket_connect_timeout=5"
cliente_redis: Redis = Redis.from_url(  # type: ignore[reportUnknownMemberType,reportAssignmentType]
    URL_REDIS,
    decode_responses=True
)

# ==================== MODELOS DE BASE DE DATOS ====================
class Usuario(Base):
    __tablename__ = "usuarios"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usuario: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    contrasena_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(50), default="paramedico")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

# Crear tablas
print("Inicializando base de datos...")
Base.metadata.create_all(bind=motor)
print("Base de datos lista.")

# ==================== ESQUEMAS PYDANTIC ====================
class RegistroUsuario(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=100, description="Nombre de usuario único")
    contrasena: str = Field(..., min_length=6, description="Contraseña (mínimo 6 caracteres)")
    email: Optional[EmailStr] = Field(None, description="Correo electrónico (opcional)")
    rol: str = Field(default="paramedico", description="Rol del usuario")

class LoginUsuario(BaseModel):
    usuario: str = Field(..., description="Nombre de usuario")
    contrasena: str = Field(..., description="Contraseña")

class RespuestaToken(BaseModel):
    token_acceso: str = Field(..., description="Token JWT de acceso")
    token_refresco: str = Field(..., description="Token JWT de refresco")
    tipo_token: str = Field(default="bearer", description="Tipo de token")
    expira_en: int = Field(..., description="Tiempo de expiración en segundos")

class RespuestaUsuario(BaseModel):
    id: int
    usuario: str
    email: Optional[str]
    rol: str
    activo: bool
    fecha_creacion: datetime

    class Config:
        from_attributes = True

class CambioContrasena(BaseModel):
    contrasena_actual: str = Field(..., description="Contraseña actual")
    contrasena_nueva: str = Field(..., min_length=6, description="Nueva contraseña")

# ==================== APLICACIÓN FASTAPI ====================
app = FastAPI(
    title="Project Parallel - Servicio de Autenticación",
    version="1.0.0",
    description="Microservicio de autenticación para sistema de historias clínicas de ambulancia"
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

seguridad = HTTPBearer()

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

# ==================== FUNCIONES AUXILIARES ====================
def hashear_contrasena(contrasena: str) -> str:
    """Crear hash seguro de contraseña usando bcrypt"""
    sal = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(contrasena.encode("utf-8"), sal).decode("utf-8")

def verificar_contrasena(contrasena_plana: str, contrasena_hash: str) -> bool:
    """Verificar contraseña contra el hash almacenado"""
    return bcrypt.checkpw(
        contrasena_plana.encode("utf-8"),
        contrasena_hash.encode("utf-8")
    )

def crear_token(datos: Mapping[str, Any], delta_expiracion: timedelta) -> str:
    """Crear token JWT"""
    a_codificar: Dict[str, Any] = dict(datos)
    expiracion = datetime.now(timezone.utc) + delta_expiracion
    a_codificar.update({"exp": expiracion})
    token = jwt.encode(a_codificar, SECRETO_JWT, algorithm=ALGORITMO_JWT)  # type: ignore[reportUnknownMemberType]
    return token

def decodificar_token(token: str) -> Dict[str, Any]:
    """Decodificar y validar token JWT"""
    try:
        payload = jwt.decode(token, SECRETO_JWT, algorithms=[ALGORITMO_JWT])  # type: ignore[reportUnknownMemberType]
        return cast(Dict[str, Any], dict(payload))
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )

def extraer_id_usuario(payload: Mapping[str, Any]) -> int:
    """Extraer y validar el ID de usuario desde el payload JWT."""
    id_usuario = payload.get("sub")
    if id_usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload de token invÃ¡lido"
        )
    try:
        return int(id_usuario)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload de token invÃ¡lido"
        )

def agregar_a_lista_negra(token: str, expira_en: int):
    """Agregar token a lista negra en Redis"""
    cliente_redis.setex(f"lista_negra:{token}", expira_en, "1")  # type: ignore[reportUnknownMemberType]

def esta_en_lista_negra(token: str) -> bool:
    """Verificar si token está en lista negra"""
    return int(cliente_redis.exists(f"lista_negra:{token}")) > 0  # type: ignore[reportUnknownMemberType]

async def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(seguridad),
    bd: Session = Depends(obtener_bd)
) -> Usuario:
    """Dependency para obtener usuario autenticado actual"""
    token = credenciales.credentials
    
    # Verificar lista negra
    if esta_en_lista_negra(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado"
        )
    
    # Decodificar token
    payload = decodificar_token(token)
    id_usuario = extraer_id_usuario(payload)
    
    # Obtener usuario de BD
    usuario = bd.query(Usuario).filter(Usuario.id == id_usuario).first()
    if not usuario or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo"
        )
    
    return usuario

# ==================== ENDPOINTS ====================

@app.get("/", tags=["General"])
async def raiz(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> Dict[str, Any]:
    """Endpoint raíz del servicio"""
    return {
        "servicio": "Project Parallel - Servicio de Autenticación",
        "version": "1.0.0",
        "estado": "funcionando"
    }

@app.get("/salud", tags=["General"])
async def verificar_salud() -> Dict[str, Any]:
    """Verificación de salud del servicio"""
    try:
        # Verificar BD
        bd = SesionLocal()
        bd.execute(text("SELECT 1"))
        bd.close()
        
        # Verificar Redis
        cliente_redis.ping()  # type: ignore[reportUnknownMemberType]
        
        return respuesta_ok({"estado": "saludable", "base_datos": "ok", "redis": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Servicio no saludable: {str(e)}"
        )

@app.post("/api/v1/auth/registro", response_model=RespuestaUsuario, status_code=status.HTTP_201_CREATED, tags=["Autenticación"])
async def registrar_usuario(datos_usuario: RegistroUsuario, bd: Session = Depends(obtener_bd)):
    """Registrar nuevo usuario en el sistema"""
    
    # Verificar si el usuario ya existe
    usuario_existente = bd.query(Usuario).filter(
        Usuario.usuario == datos_usuario.usuario.lower()
    ).first()
    
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya existe"
        )
    
    # Verificar si el email ya existe
    if datos_usuario.email:
        email_existente = bd.query(Usuario).filter(
            Usuario.email == datos_usuario.email
        ).first()
        if email_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya está registrado"
            )
    
    # Crear nuevo usuario
    nuevo_usuario = Usuario(
        usuario=datos_usuario.usuario.lower(),
        email=datos_usuario.email,
        contrasena_hash=hashear_contrasena(datos_usuario.contrasena),
        rol=datos_usuario.rol
    )
    
    bd.add(nuevo_usuario)
    bd.commit()
    bd.refresh(nuevo_usuario)
    
    return respuesta_ok(RespuestaUsuario.model_validate(nuevo_usuario).model_dump(), "Usuario registrado")

@app.post("/api/v1/auth/login", response_model=RespuestaToken, tags=["Autenticación"])
async def iniciar_sesion(credenciales: LoginUsuario, bd: Session = Depends(obtener_bd)) -> Dict[str, Any]:
    """Iniciar sesión y obtener tokens JWT"""
    
    # Buscar usuario
    usuario = bd.query(Usuario).filter(
        Usuario.usuario == credenciales.usuario.lower()
    ).first()
    
    if not usuario or not verificar_contrasena(credenciales.contrasena, usuario.contrasena_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )
    
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario está inactiva"
        )
    
    # Crear tokens
    token_acceso = crear_token(
        datos={"sub": str(usuario.id), "usuario": usuario.usuario, "rol": usuario.rol},
        delta_expiracion=timedelta(minutes=MINUTOS_EXPIRACION_TOKEN_ACCESO)
    )
    
    token_refresco = crear_token(
        datos={"sub": str(usuario.id), "tipo": "refresco"},
        delta_expiracion=timedelta(days=DIAS_EXPIRACION_TOKEN_REFRESCO)
    )
    
    return respuesta_ok({"token_acceso": token_acceso, "token_refresco": token_refresco, "tipo_token": "bearer", "expira_en": MINUTOS_EXPIRACION_TOKEN_ACCESO * 60}, "Login exitoso")

@app.post("/api/v1/auth/refrescar", response_model=RespuestaToken, tags=["Autenticación"])
async def refrescar_token(
    credenciales: HTTPAuthorizationCredentials = Depends(seguridad),
    bd: Session = Depends(obtener_bd)
) -> Dict[str, Any]:
    """Refrescar token de acceso usando token de refresco"""
    
    token = credenciales.credentials
    
    # Verificar lista negra
    if esta_en_lista_negra(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresco revocado"
        )
    
    # Decodificar token de refresco
    payload = decodificar_token(token)
    
    if payload.get("tipo") != "refresco":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido"
        )
    
    id_usuario = extraer_id_usuario(payload)
    usuario = bd.query(Usuario).filter(Usuario.id == id_usuario).first()
    
    if not usuario or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo"
        )
    
    # Crear nuevo token de acceso
    nuevo_token_acceso = crear_token(
        datos={"sub": str(usuario.id), "usuario": usuario.usuario, "rol": usuario.rol},
        delta_expiracion=timedelta(minutes=MINUTOS_EXPIRACION_TOKEN_ACCESO)
    )
    
    return respuesta_ok({"token_acceso": nuevo_token_acceso, "token_refresco": token, "tipo_token": "bearer", "expira_en": MINUTOS_EXPIRACION_TOKEN_ACCESO * 60}, "Token refrescado")

@app.post("/api/v1/auth/cerrar-sesion", tags=["Autenticación"])
async def cerrar_sesion(
    credenciales: HTTPAuthorizationCredentials = Depends(seguridad),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
) -> Dict[str, Any]:
    """Cerrar sesión agregando token a lista negra"""
    
    token = credenciales.credentials
    payload = decodificar_token(token)
    
    # Calcular TTL restante
    exp_value = payload.get("exp")
    if not isinstance(exp_value, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invÃ¡lido"
        )
    exp = float(exp_value)
    ahora = datetime.now(timezone.utc).timestamp()
    ttl = int(exp - ahora)
    
    if ttl > 0:
        agregar_a_lista_negra(token, ttl)
    
    return {"mensaje": "Sesión cerrada exitosamente"}

@app.get("/api/v1/auth/yo", tags=["Usuarios"])
async def obtener_info_usuario_actual(usuario_actual: Usuario = Depends(obtener_usuario_actual)) -> RespuestaUsuario:
    """Obtener información del usuario autenticado actual"""
    return respuesta_ok(RespuestaUsuario.model_validate(usuario_actual).model_dump())

@app.put("/api/v1/auth/cambiar-contrasena", tags=["Usuarios"])
async def cambiar_contrasena(
    datos_cambio: CambioContrasena,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    bd: Session = Depends(obtener_bd)
) -> Dict[str, Any]:
    """Cambiar contraseña del usuario actual"""
    
    if not verificar_contrasena(datos_cambio.contrasena_actual, usuario_actual.contrasena_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta"
        )
    
    usuario_actual.contrasena_hash = hashear_contrasena(datos_cambio.contrasena_nueva)
    bd.commit()
    
    return {"mensaje": "Contraseña actualizada exitosamente"}

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

