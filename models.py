# =============================================================================
# models.py — SQLAlchemy Jadvallari va Pydantic Sxemalari (FULL FIXED)
# =============================================================================

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

# =============================================================================
#  QISM 1: SQLAlchemy ORM MODELLARI (Ma'lumotlar Bazasi Jadvallari)
# =============================================================================

class Foydalanuvchi(Base):
    __tablename__ = "foydalanuvchilar"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    tolik_ism = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    parol_heshi = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False, default="student")
    faol = Column(Boolean, nullable=False, default=True)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    yangilangan_vaqt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    natijalar = relationship("Natija", back_populates="foydalanuvchi", cascade="all, delete-orphan")

class Kurs(Base):
    __tablename__ = "kurslar"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    nomi = Column(String(500), nullable=False)
    tavsif = Column(Text, nullable=True)
    mavzu = Column(String(255), nullable=False)
    daraja = Column(String(100), nullable=False, default="boshlovchi")
    oqituvchi_id = Column(UUID(as_uuid=True), ForeignKey("foydalanuvchilar.id", ondelete="SET NULL"), nullable=True)
    faol = Column(Boolean, default=True, nullable=False)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    yangilangan_vaqt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    darslar = relationship("Dars", back_populates="kurs", cascade="all, delete-orphan")
    testlar = relationship("Test", back_populates="kurs", cascade="all, delete-orphan")

class Dars(Base):
    __tablename__ = "darslar"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    kurs_id = Column(UUID(as_uuid=True), ForeignKey("kurslar.id", ondelete="CASCADE"), nullable=False, index=True)
    sarlavha = Column(String(500), nullable=False)
    mazmun = Column(Text, nullable=True)
    dars_rejasi = Column(JSON, nullable=True)
    uy_vazifasi = Column(Text, nullable=True)
    baholash_mezoni = Column(Text, nullable=True)
    tartib_raqami = Column(Integer, nullable=False, default=1)
    ai_mavzu = Column(String(500), nullable=True)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    yangilangan_vaqt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    kurs = relationship("Kurs", back_populates="darslar")

class Test(Base):
    __tablename__ = "testlar"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    kurs_id = Column(UUID(as_uuid=True), ForeignKey("kurslar.id", ondelete="CASCADE"), nullable=True, index=True)
    nomi = Column(String(500), nullable=False)
    mavzu = Column(String(500), nullable=False)
    savollar = Column(JSON, nullable=False)
    umumiy_ball = Column(Integer, nullable=False, default=100)
    yaratuvchi = Column(String(50), nullable=False, default="gemini-ai")
    faol = Column(Boolean, default=True, nullable=False)
    yaratilgan_vaqt = Column(DateTime, default=datetime.utcnow, nullable=False)
    yangilangan_vaqt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

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


# =============================================================================
#  QISM 2: PYDANTIC SXEMALARI (HTTP So'rov/Javob Validatsiyasi)
# =============================================================================

class FoydalanuvchiYaratish(BaseModel):
    tolik_ism: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    parol: str = Field(..., min_length=4, max_length=128)
    rol: Optional[str] = Field(default="student")

    @field_validator("rol")
    def rolni_tekshirish(cls, v: str) -> str:
        ruxsat_etilgan = {"student", "teacher", "oqituvchi", "admin"}
        if v.lower() not in ruxsat_etilgan:
            raise ValueError(f"Rol '{v}' noto'g'ri. Faqat: student, teacher, oqituvchi, admin bo'lishi mumkin.")
        return v.lower()

    model_config = ConfigDict(from_attributes=True)


class FoydalanuvchiJavob(BaseModel):
    id: uuid.UUID
    tolik_ism: str
    email: str
    rol: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


class KursYaratish(BaseModel):
    nomi: str = Field(..., min_length=3, max_length=500)
    tavsif: Optional[str] = None
    mavzu: str = Field(..., min_length=2, max_length=255)
    daraja: Optional[str] = Field(default="boshlovchi")

    @field_validator("daraja")
    def darajani_tekshirish(cls, v: str) -> str:
        ruxsat = {"boshlovchi", "o'rta", "yuqori"}
        if v not in ruxsat:
            raise ValueError(f"Daraja '{v}' noto'g'ri. Faqat: boshlovchi, o'rta, yuqori.")
        return v

    model_config = ConfigDict(from_attributes=True)


class KursJavob(BaseModel):
    id: uuid.UUID
    nomi: str
    tavsif: Optional[str]
    mavzu: str
    daraja: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


class DarsYaratish(BaseModel):
    kurs_id: uuid.UUID
    sarlavha: str = Field(..., min_length=3, max_length=500)
    mazmun: Optional[str] = None
    tartib_raqami: Optional[int] = Field(default=1, ge=1)

    model_config = ConfigDict(from_attributes=True)


class DarsJavob(BaseModel):
    id: uuid.UUID
    kurs_id: uuid.UUID
    sarlavha: str
    mazmun: Optional[str]
    dars_rejasi: Optional[Any] = None
    uy_vazifasi: Optional[str] = None
    baholash_mezoni: Optional[str] = None
    tartib_raqami: int
    ai_mavzu: Optional[str] = None
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


class MCQSavol(BaseModel):
    savol: str
    variantlar: dict
    togri_javob: str
    izoh: str

    @field_validator("togri_javob")
    def togri_javobni_tekshirish(cls, v: str) -> str:
        if v.upper() not in {"A", "B", "C", "D"}:
            raise ValueError("To'g'ri javob faqat A, B, C yoki D bo'lishi mumkin.")
        return v.upper()


class TestYaratish(BaseModel):
    nomi: str = Field(..., min_length=3, max_length=500)
    mavzu: str = Field(..., min_length=2, max_length=500)
    kurs_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class TestJavob(BaseModel):
    id: uuid.UUID
    kurs_id: Optional[uuid.UUID]
    nomi: str
    mavzu: str
    savollar: Any
    umumiy_ball: int
    yaratuvchi: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


class NatijaYaratish(BaseModel):
    student_id: uuid.UUID
    test_id: uuid.UUID
    foydalanuvchi_javoblari: dict

    model_config = ConfigDict(from_attributes=True)


class NatijaJavob(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    test_id: uuid.UUID
    foydalanuvchi_javoblari: Any
    togri_javoblar_soni: int
    ball_foizi: float
    baho: str
    topshirilgan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


class AIGeneratsiyaSorovi(BaseModel):
    mavzu: str = Field(..., min_length=3, max_length=500)
    kurs_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class AIGeneratsiyaJavobi(BaseModel):
    mavzu: str
    savollar: List[MCQSavol]
    dars_rejasi: dict
    uy_vazifasi: str
    baholash_mezoni: dict
    yaratilgan_vaqt: str


class UmumiyJavob(BaseModel):
    muvaffaqiyat: bool
    xabar: str
    malumot: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class XatoJavob(BaseModel):
    muvaffaqiyat: bool = False
    xato_kodi: str
    xabar: str
    tafsilot: Optional[str] = None


class TizimgaKirish(BaseModel):
    email: EmailStr
    parol: str


class FoydalanuvchiYangilash(BaseModel):
    tolik_ism: Optional[str] = None
    email: Optional[EmailStr] = None
    parol: Optional[str] = None
    rol: Optional[str] = None
    faol: Optional[bool] = None

    @field_validator("rol")
    def rolni_tekshirish(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            ruxsat_etilgan = {"student", "teacher", "oqituvchi", "admin"}
            if v.lower() not in ruxsat_etilgan:
                raise ValueError(f"Rol '{v}' noto'g'ri. Faqat: student, teacher, oqituvchi, admin.")
            return v.lower()
        return v


class KursYangilash(BaseModel):
    nomi: Optional[str] = None
    tavsif: Optional[str] = None
    mavzu: Optional[str] = None
    daraja: Optional[str] = None
    faol: Optional[bool] = None


class DarsYangilash(BaseModel):
    sarlavha: Optional[str] = None
    mazmun: Optional[str] = None
    tartib_raqami: Optional[int] = None


class TestYangilash(BaseModel):
    nomi: Optional[str] = None
    mavzu: Optional[str] = None
    faol: Optional[bool] = None
    umumiy_ball: Optional[int] = None
