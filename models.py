# models.py
import uuid
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import (
    Column, String, Text, Float, Integer,
    ForeignKey, DateTime, Boolean, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from database import Base

# --- SQLAlchemy Modellari ---
class Foydalanuvchi(Base):
    __tablename__ = "foydalanuvchilar"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tolik_ism = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    parol_heshi = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False, default="student")
    faol = Column(Boolean, nullable=False, default=True)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    natijalar = relationship("Natija", back_populates="foydalanuvchi", cascade="all, delete-orphan")

class Kurs(Base):
    __tablename__ = "kurslar"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    nomi = Column(String(500), nullable=False)
    tavsif = Column(Text, nullable=True)
    mavzu = Column(String(255), nullable=False)
    daraja = Column(String(100), nullable=False, default="boshlovchi")
    faol = Column(Boolean, default=True, nullable=False)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    darslar = relationship("Dars", back_populates="kurs", cascade="all, delete-orphan")
    testlar = relationship("Test", back_populates="kurs", cascade="all, delete-orphan")

class Dars(Base):
    __tablename__ = "darslar"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    kurs_id = Column(UUID(as_uuid=True), ForeignKey("kurslar.id", ondelete="CASCADE"), nullable=False, index=True)
    sarlavha = Column(String(500), nullable=False)
    mazmun = Column(Text, nullable=True)
    tartib_raqami = Column(Integer, nullable=False, default=1)
    kurs = relationship("Kurs", back_populates="darslar")

class Test(Base):
    __tablename__ = "testlar"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    kurs_id = Column(UUID(as_uuid=True), ForeignKey("kurslar.id", ondelete="CASCADE"), nullable=True, index=True)
    nomi = Column(String(500), nullable=False)
    mavzu = Column(String(500), nullable=False)
    savollar = Column(JSON, nullable=False)
    yaratuvchi = Column(String(50), nullable=False, default="gemini-ai")
    faol = Column(Boolean, default=True, nullable=False)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    kurs = relationship("Kurs", back_populates="testlar")
    natijalar = relationship("Natija", back_populates="test", cascade="all, delete-orphan")

class Natija(Base):
    __tablename__ = "natijalar"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("foydalanuvchilar.id", ondelete="CASCADE"), nullable=False, index=True)
    test_id = Column(UUID(as_uuid=True), ForeignKey("testlar.id", ondelete="CASCADE"), nullable=False, index=True)
    foydalanuvchi_javoblari = Column(JSON, nullable=False)
    togri_javoblar_soni = Column(Integer, nullable=False, default=0)
    ball_foizi = Column(Float, nullable=False, default=0.0)
    baho = Column(String(10), nullable=False, default="F")
    topshirilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    foydalanuvchi = relationship("Foydalanuvchi", back_populates="natijalar")
    test = relationship("Test", back_populates="natijalar")

# --- Pydantic Sxemalari ---
class FoydalanuvchiYaratish(BaseModel):
    tolik_ism: str
    email: EmailStr
    parol: str
    rol: Optional[str] = "student"
    model_config = ConfigDict(from_attributes=True)

class FoydalanuvchiJavob(BaseModel):
    id: uuid.UUID
    tolik_ism: str
    email: str
    rol: str
    model_config = ConfigDict(from_attributes=True)

class KursYaratish(BaseModel):
    nomi: str
    tavsif: Optional[str] = None
    mavzu: str
    daraja: Optional[str] = "boshlovchi"
    model_config = ConfigDict(from_attributes=True)

class KursJavob(BaseModel):
    id: uuid.UUID
    nomi: str
    model_config = ConfigDict(from_attributes=True)

class DarsYaratish(BaseModel):
    kurs_id: uuid.UUID
    sarlavha: str
    model_config = ConfigDict(from_attributes=True)

class DarsJavob(BaseModel):
    id: uuid.UUID
    sarlavha: str
    model_config = ConfigDict(from_attributes=True)

class TestYaratish(BaseModel):
    nomi: str
    mavzu: str
    kurs_id: Optional[uuid.UUID] = None
    model_config = ConfigDict(from_attributes=True)

class TestJavob(BaseModel):
    id: uuid.UUID
    nomi: str
    model_config = ConfigDict(from_attributes=True)

class NatijaYaratish(BaseModel):
    student_id: uuid.UUID
    test_id: uuid.UUID
    foydalanuvchi_javoblari: dict
    model_config = ConfigDict(from_attributes=True)

class NatijaJavob(BaseModel):
    id: uuid.UUID
    togri_javoblar_soni: int
    ball_foizi: float
    baho: str
    model_config = ConfigDict(from_attributes=True)

class AIGeneratsiyaSorovi(BaseModel):
    mavzu: str
    kurs_id: Optional[uuid.UUID] = None

class UmumiyJavob(BaseModel):
    muvaffaqiyat: bool
    xabar: str
    malumot: Optional[Any] = None

# MANA SHU YERDA EDI XATO: XatoJavob qayta qo'shildi
class XatoJavob(BaseModel):
    muvaffaqiyat: bool = False
    xato_kodi: str
    xabar: str

class TizimgaKirish(BaseModel):
    email: EmailStr
    parol: str

class FoydalanuvchiYangilash(BaseModel):
    tolik_ism: Optional[str] = None
    email: Optional[EmailStr] = None
    parol: Optional[str] = None
    rol: Optional[str] = None

class KursYangilash(BaseModel):
    nomi: Optional[str] = None
    tavsif: Optional[str] = None

class DarsYangilash(BaseModel):
    sarlavha: Optional[str] = None
class TestYangilash(BaseModel):
    nomi: Optional[str] = None
