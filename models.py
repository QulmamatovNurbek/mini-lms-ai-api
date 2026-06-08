# =============================================================================
# models.py — SQLAlchemy Jadvallari va Pydantic Sxemalari
# =============================================================================
# Bu fayl ikki xil turdagi modellarni o'z ichiga oladi:
#
#  1. SQLAlchemy ORM Modellari — PostgreSQL jadvallariga mos keladi.
#     Bular "@app.get(...)" kabi endpoint'larda db bilan ishlash uchun.
#
#  2. Pydantic Sxemalari — HTTP so'rov va javoblarini validatsiya qiladi.
#     FastAPI bu sxemalardan avtomatik API dokumentatsiya yaratadi.
#
# Jadvallar:
#   - foydalanuvchilar (User)       — Platforma foydalanuvchilari
#   - kurslar        (Course)       — O'quv kurslari
#   - darslar        (Lesson)       — Kurs darslari
#   - testlar        (Test)         — Kurs testlari (AI tomonidan yaratiladi)
#   - natijalar      (Result)       — Foydalanuvchi test natijalari
# =============================================================================

import uuid                           # Unikal identifikatorlar yaratish uchun
from datetime import datetime         # Vaqt-sana ma'lumotlari uchun
from typing import Optional, List, Any  # Tip izohlar uchun

from sqlalchemy import (
    Column, String, Text, Float, Integer,
    ForeignKey, DateTime, Boolean, JSON,
)
from sqlalchemy.dialects.postgresql import UUID  # PostgreSQL UUID turi
from sqlalchemy.orm import relationship           # Jadvallar orasidagi munosabatlar

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict  # Validatsiya uchun

from database import Base  # Asosiy deklarativ klass

# =============================================================================
#  QISM 1: SQLAlchemy ORM MODELLARI (Ma'lumotlar Bazasi Jadvallari)
# =============================================================================


# -----------------------------------------------------------------------------
# Foydalanuvchi Modeli (users jadvali)
# -----------------------------------------------------------------------------
class Foydalanuvchi(Base):
    """
    Platforma foydalanuvchilarini saqlash uchun jadval.
    
    Har bir foydalanuvchi UUID bilan identifikatsiyalanadi,
    bu xavfsizlikni oshiradi va sequential ID'lardan kelib chiqadigan
    enumeration hujumlarini oldini oladi.
    """
    __tablename__ = "foydalanuvchilar"  # PostgreSQL'dagi jadval nomi (o'zbekcha)

    # Asosiy kalit — UUID formati (PostgreSQL UUID turi)
    # default=uuid.uuid4 — Yangi foydalanuvchi qo'shilganda avtomatik UUID yaratadi
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Foydalanuvchining unikal identifikatori (UUID4)"
    )

    # To'liq ism — majburiy maydon, maksimal 255 belgi
    tolik_ism = Column(
        String(255),
        nullable=False,
        comment="Foydalanuvchining to'liq ismi va familiyasi"
    )

    # Email manzil — unikal, indekslangan
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,  # Tez qidirish uchun indeks
        comment="Foydalanuvchining email manzili (unikal)"
    )

    # Parol xeshi — hech qachon ochiq parol saqlanmaydi!
    # bcrypt yoki argon2 bilan hashlangan qiymat saqlanadi.
    parol_heshi = Column(
        String(255),
        nullable=False,
        comment="Bcrypt bilan hashlangan parol (ochiq parol emas!)"
    )

    # Rol — foydalanuvchi yoki admin
    # "talaba" yoki "oqituvchi" yoki "admin"
    rol = Column(
        String(50),
        nullable=False,
        default="student",
        comment="Foydalanuvchi roli: student | teacher | admin"
    )

    # Faollik holati — bloklangan foydalanuvchilar tizimga kira olmaydi
    faol = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Foydalanuvchi faolmi? (False = bloklangan)"
    )

    # Ro'yxatdan o'tish vaqti
    yaratilgan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Foydalanuvchi ro'yxatdan o'tgan vaqt (UTC)"
    )

    # Oxirgi yangilanish vaqti
    yangilangan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Ma'lumotlar oxirgi yangilangan vaqt (UTC)"
    )

    # ----- Munosabatlar (Relationships) -----
    # Bir foydalanuvchi ko'p natijaga ega bo'lishi mumkin
    natijalar = relationship(
        "Natija",
        back_populates="foydalanuvchi",
        cascade="all, delete-orphan",  # Foydalanuvchi o'chganda natijalari ham o'chadi
    )

    def __repr__(self) -> str:
        return f"<Foydalanuvchi(id={self.id}, email={self.email}, rol={self.rol})>"


# -----------------------------------------------------------------------------
# Kurs Modeli (kurslar jadvali)
# -----------------------------------------------------------------------------
class Kurs(Base):
    """
    O'quv kurslarini saqlash uchun jadval.
    
    Kurslar o'qituvchi tomonidan yaratiladi va ko'p darslardan,
    testlardan iborat bo'ladi.
    """
    __tablename__ = "kurslar"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Kursning unikal identifikatori"
    )

    # Kurs nomi — o'zbekcha bo'lishi majburiy
    nomi = Column(
        String(500),
        nullable=False,
        comment="Kurs nomi (o'zbekcha)"
    )

    # Kurs tavsifi — batafsil izoh
    tavsif = Column(
        Text,
        nullable=True,
        comment="Kurs haqida batafsil tavsif (o'zbekcha)"
    )

    # Qaysi fan/mavzu bo'yicha kurs
    mavzu = Column(
        String(255),
        nullable=False,
        comment="Kurs mavzusi yoki fani (masalan: Matematika, Fizika)"
    )

    # Kurs darajasi — boshlovchi, o'rta, yuqori
    daraja = Column(
        String(100),
        nullable=False,
        default="boshlovchi",
        comment="Kurs darajasi: boshlovchi | o'rta | yuqori"
    )

    # Kurs yaratgan o'qituvchining ID'si
    oqituvchi_id = Column(
        UUID(as_uuid=True),
        ForeignKey("foydalanuvchilar.id", ondelete="SET NULL"),
        nullable=True,
        comment="Kursni yaratgan o'qituvchi ID'si"
    )

    # Kurs faolmi?
    faol = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Kurs hozirda faolmi?"
    )

    yaratilgan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Kurs yaratilgan vaqt (UTC)"
    )

    yangilangan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Kurs oxirgi yangilangan vaqt (UTC)"
    )

    # ----- Munosabatlar -----
    # Bir kursda ko'p dars bo'lishi mumkin
    darslar = relationship(
        "Dars",
        back_populates="kurs",
        cascade="all, delete-orphan",
    )
    # Bir kursda ko'p test bo'lishi mumkin
    testlar = relationship(
        "Test",
        back_populates="kurs",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Kurs(id={self.id}, nomi={self.nomi})>"


# -----------------------------------------------------------------------------
# Dars Modeli (darslar jadvali)
# -----------------------------------------------------------------------------
class Dars(Base):
    """
    Kurs darslarini saqlash uchun jadval.
    
    Har bir dars muayyan kursga tegishli va tartib raqamiga ega.
    AI tomonidan yaratilgan dars reja va topshiriqlar ham shu yerda saqlanadi.
    """
    __tablename__ = "darslar"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Darsning unikal identifikatori"
    )

    # Tegishli kurs
    kurs_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kurslar.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dars tegishli bo'lgan kurs ID'si"
    )

    # Dars sarlavhasi
    sarlavha = Column(
        String(500),
        nullable=False,
        comment="Dars sarlavhasi (o'zbekcha)"
    )

    # Dars mazmuni — to'liq matn
    mazmun = Column(
        Text,
        nullable=True,
        comment="Dars mazmuni va tushuntirishi (o'zbekcha)"
    )

    # AI tomonidan yaratilgan dars rejasi (JSON format)
    # Misol: {"kirish": "...", "asosiy_qism": [...], "xulosa": "..."}
    dars_rejasi = Column(
        JSON,
        nullable=True,
        comment="AI yaratgan dars rejasi (JSON, o'zbekcha)"
    )

    # Uy vazifasi (AI tomonidan yaratilgan, o'zbekcha)
    uy_vazifasi = Column(
        Text,
        nullable=True,
        comment="Dars bo'yicha uy vazifasi (o'zbekcha)"
    )

    # Baholash mezonlari (AI yaratgan)
    baholash_mezoni = Column(
        Text,
        nullable=True,
        comment="Uy vazifasini baholash mezonlari (o'zbekcha)"
    )

    # Dars tartib raqami kurs ichida
    tartib_raqami = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Kurs ichidagi dars tartib raqami"
    )

    # AI mavzusi — bu dars qaysi mavzu bo'yicha AI yaratgan
    ai_mavzu = Column(
        String(500),
        nullable=True,
        comment="AI'ga berilgan mavzu (dars yaratishda ishlatilgan)"
    )

    yaratilgan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Dars yaratilgan vaqt (UTC)"
    )

    yangilangan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Dars oxirgi yangilangan vaqt (UTC)"
    )

    # ----- Munosabatlar -----
    kurs = relationship("Kurs", back_populates="darslar")

    def __repr__(self) -> str:
        return f"<Dars(id={self.id}, sarlavha={self.sarlavha})>"


# -----------------------------------------------------------------------------
# Test Modeli (testlar jadvali)
# -----------------------------------------------------------------------------
class Test(Base):
    """
    AI tomonidan yaratilgan testlarni saqlash uchun jadval.
    
    Har bir test 5 ta ko'p tanlovli savoldan (MCQ) iborat bo'ladi.
    Savollar va javoblar JSON formatida saqlanadi.
    """
    __tablename__ = "testlar"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Testning unikal identifikatori"
    )

    kurs_id = Column(
        UUID(as_uuid=True),
        ForeignKey("kurslar.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Test tegishli bo'lgan kurs ID'si (ixtiyoriy)"
    )

    # Test nomi / sarlavhasi
    nomi = Column(
        String(500),
        nullable=False,
        comment="Test nomi yoki sarlavhasi (o'zbekcha)"
    )

    # Test mavzusi
    mavzu = Column(
        String(500),
        nullable=False,
        comment="Test mavzusi (AI'ga berilgan mavzu)"
    )

    # 5 ta MCQ savol — JSON formatida
    # Misol strukturasi:
    # [
    #   {
    #     "savol": "Savol matni?",
    #     "variantlar": {"A": "...", "B": "...", "C": "...", "D": "..."},
    #     "togri_javob": "A",
    #     "izoh": "Nima uchun A to'g'ri ekanligi..."
    #   },
    #   ... (5 ta)
    # ]
    savollar = Column(
        JSON,
        nullable=False,
        comment="5 ta MCQ savol (JSON formatida, o'zbekcha)"
    )

    # Umumiy ball (odatda 100)
    umumiy_ball = Column(
        Integer,
        nullable=False,
        default=100,
        comment="Testning umumiy balli (har savol 20 ball)"
    )

    # Testni kim yaratdi (AI yoki o'qituvchi)
    yaratuvchi = Column(
        String(50),
        nullable=False,
        default="gemini-ai",
        comment="Testni kim/nima yaratdi: gemini-ai | oqituvchi"
    )

    faol = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Test hozirda faolmi?"
    )

    yaratilgan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Test yaratilgan vaqt (UTC)"
    )

    yangilangan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Test oxirgi yangilangan vaqt (UTC)"
    )

    # ----- Munosabatlar -----
    kurs = relationship("Kurs", back_populates="testlar")
    natijalar = relationship(
        "Natija",
        back_populates="test",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Test(id={self.id}, mavzu={self.mavzu})>"


# -----------------------------------------------------------------------------
# Natija Modeli (natijalar jadvali)
# -----------------------------------------------------------------------------
class Natija(Base):
    """
    Foydalanuvchi test natijalarini saqlash uchun jadval.
    
    Har safar foydalanuvchi test topshirganda yangi natija yozuvi yaratiladi.
    Bu tarixni kuzatish va tahlil qilish imkonini beradi.
    """
    __tablename__ = "natijalar"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Natijaning unikal identifikatori"
    )

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("foydalanuvchilar.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Test topshirgan foydalanuvchi (talaba) ID'si"
    )

    test_id = Column(
        UUID(as_uuid=True),
        ForeignKey("testlar.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Topshirilgan test ID'si"
    )

    # Foydalanuvchi tanlagan javoblar (JSON)
    # Misol: {"0": "A", "1": "C", "2": "B", "3": "D", "4": "A"}
    foydalanuvchi_javoblari = Column(
        JSON,
        nullable=False,
        comment="Foydalanuvchi tanlagan javoblar (JSON, indeks: javob)"
    )

    # Nechta to'g'ri javob berdi
    togri_javoblar_soni = Column(
        Integer,
        nullable=False,
        default=0,
        comment="To'g'ri javoblar soni (0-5)"
    )

    # Foizda ball
    ball_foizi = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Natija foizi (0.0 - 100.0)"
    )

    # Baho — harfli (A, B, C, D, F) yoki raqamli
    baho = Column(
        String(10),
        nullable=False,
        default="F",
        comment="Harfli baho: A (90+) | B (75+) | C (60+) | D (45+) | F (<45)"
    )

    # Test topshirilgan vaqt
    topshirilgan_vaqt = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Test topshirilgan vaqt (UTC)"
    )

    # ----- Munosabatlar -----
    foydalanuvchi = relationship("Foydalanuvchi", back_populates="natijalar")
    test = relationship("Test", back_populates="natijalar")

    def __repr__(self) -> str:
        return f"<Natija(id={self.id}, ball={self.ball_foizi}%)>"


# =============================================================================
#  QISM 2: PYDANTIC SXEMALARI (HTTP So'rov/Javob Validatsiyasi)
# =============================================================================
# Pydantic sxemalari uchta maqsadda ishlatiladi:
#  - "Create" sxemasi: POST so'rovlarda yangi ob'ekt yaratish uchun kirish ma'lumotlari
#  - "Response" sxemasi: Mijozga qaytariladigan ma'lumotlar strukturasi
#  - "Base" sxemasi: Umumiy maydonlarni o'z ichiga oluvchi asosiy klass
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# FOYDALANUVCHI SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class FoydalanuvchiYaratish(BaseModel):
    """
    Yangi foydalanuvchi ro'yxatdan o'tkazish uchun so'rov ma'lumotlari sxemasi.
    POST /api/v1/foydalanuvchilar endpoint'ida ishlatiladi.
    """
    tolik_ism: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Foydalanuvchining to'liq ismi va familiyasi"
    )
    email: EmailStr = Field(
        ...,
        description="Foydalanuvchining email manzili (to'g'ri format bo'lishi shart)"
    )
    parol: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Parol (kamida 8 belgi)"
    )
    rol: Optional[str] = Field(
        default="student",
        description="Foydalanuvchi roli: student | teacher | admin"
    )

    @field_validator("rol")
    def rolni_tekshirish(cls, v: str) -> str:
        """Foydalanuvchi roli faqat ruxsat etilgan qiymatlardan biri bo'lishi kerak."""
        ruxsat_etilgan = {"student", "teacher", "admin"}
        if v not in ruxsat_etilgan:
            raise ValueError(
                f"Rol '{v}' noto'g'ri. Faqat: student, teacher, admin bo'lishi mumkin."
            )
        return v

    class Config:
        # Pydantic V1 uchun ORM modidan foydalanish uchun
        from_attributes = True


class FoydalanuvchiJavob(BaseModel):
    """
    Foydalanuvchi ma'lumotlarini qaytarish uchun javob sxemasi.
    Parol xeshi hech qachon qaytarilmaydi — xavfsizlik maqsadida.
    """
    id: uuid.UUID
    tolik_ism: str
    email: str
    rol: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)  # SQLAlchemy modellaridan avtomatik o'qish


# ─────────────────────────────────────────────────────────────────────────────
# KURS SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class KursYaratish(BaseModel):
    """Yangi kurs yaratish uchun so'rov sxemasi."""
    nomi: str = Field(..., min_length=3, max_length=500, description="Kurs nomi (o'zbekcha)")
    tavsif: Optional[str] = Field(None, description="Kurs tavsifi (o'zbekcha, ixtiyoriy)")
    mavzu: str = Field(..., min_length=2, max_length=255, description="Kurs fani/mavzusi")
    daraja: Optional[str] = Field(
        default="boshlovchi",
        description="Kurs darajasi: boshlovchi | o'rta | yuqori"
    )

    @field_validator("daraja")
    def darajani_tekshirish(cls, v: str) -> str:
        """Kurs darajasi faqat belgilangan qiymatlardan biri bo'lishi kerak."""
        ruxsat = {"boshlovchi", "o'rta", "yuqori"}
        if v not in ruxsat:
            raise ValueError(f"Daraja '{v}' noto'g'ri. Faqat: boshlovchi, o'rta, yuqori.")
        return v

    model_config = ConfigDict(from_attributes=True)


class KursJavob(BaseModel):
    """Kurs ma'lumotlarini qaytarish uchun javob sxemasi."""
    id: uuid.UUID
    nomi: str
    tavsif: Optional[str]
    mavzu: str
    daraja: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# DARS SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class DarsYaratish(BaseModel):
    """Yangi dars yaratish uchun so'rov sxemasi."""
    kurs_id: uuid.UUID = Field(..., description="Dars tegishli bo'lgan kurs ID'si")
    sarlavha: str = Field(..., min_length=3, max_length=500, description="Dars sarlavhasi")
    mazmun: Optional[str] = Field(None, description="Dars mazmuni (ixtiyoriy)")
    tartib_raqami: Optional[int] = Field(default=1, ge=1, description="Tartib raqami (1 dan boshlab)")

    model_config = ConfigDict(from_attributes=True)


class DarsJavob(BaseModel):
    """Dars ma'lumotlarini qaytarish uchun javob sxemasi."""
    id: uuid.UUID
    kurs_id: uuid.UUID
    sarlavha: str
    mazmun: Optional[str]
    dars_rejasi: Optional[Any]      # AI yaratgan dars rejasi (JSON)
    uy_vazifasi: Optional[str]
    baholash_mezoni: Optional[str]
    tartib_raqami: int
    ai_mavzu: Optional[str]
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# TEST SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class MCQSavol(BaseModel):
    """
    Bitta ko'p tanlovli savol (MCQ) strukturasi.
    AI tomonidan yaratilgan har bir savol ushbu formatga mos bo'lishi kerak.
    """
    savol: str = Field(..., description="Savol matni (o'zbekcha)")
    variantlar: dict = Field(
        ...,
        description="Javob variantlari: {'A': '...', 'B': '...', 'C': '...', 'D': '...'}"
    )
    togri_javob: str = Field(
        ...,
        description="To'g'ri javob kaliti: A, B, C yoki D"
    )
    izoh: str = Field(
        ...,
        description="To'g'ri javob izohlanishi (o'zbekcha)"
    )

    @field_validator("togri_javob")
    def togri_javobni_tekshirish(cls, v: str) -> str:
        """To'g'ri javob faqat A, B, C yoki D bo'lishi kerak."""
        if v.upper() not in {"A", "B", "C", "D"}:
            raise ValueError("To'g'ri javob faqat A, B, C yoki D bo'lishi mumkin.")
        return v.upper()


class TestYaratish(BaseModel):
    """Test yaratish uchun so'rov sxemasi."""
    nomi: str = Field(..., min_length=3, max_length=500, description="Test nomi (o'zbekcha)")
    mavzu: str = Field(..., min_length=2, max_length=500, description="Test mavzusi")
    kurs_id: Optional[uuid.UUID] = Field(None, description="Tegishli kurs ID'si (ixtiyoriy)")

    model_config = ConfigDict(from_attributes=True)


class TestJavob(BaseModel):
    """Test ma'lumotlarini qaytarish uchun javob sxemasi."""
    id: uuid.UUID
    nomi: str
    mavzu: str
    kurs_id: Optional[uuid.UUID]
    savollar: Any          # JSON — 5 ta MCQ savol
    umumiy_ball: int
    yaratuvchi: str
    faol: bool
    yaratilgan_vaqt: datetime
    yangilangan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# NATIJA SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class NatijaYaratish(BaseModel):
    """Test topshirish uchun so'rov sxemasi."""
    student_id: uuid.UUID = Field(..., description="Foydalanuvchi (talaba) ID'si")
    test_id: uuid.UUID = Field(..., description="Topshirilayotgan test ID'si")
    foydalanuvchi_javoblari: dict = Field(
        ...,
        description="Foydalanuvchi javoblari: {'0': 'A', '1': 'B', ...}"
    )

    model_config = ConfigDict(from_attributes=True)


class NatijaJavob(BaseModel):
    """Natija ma'lumotlarini qaytarish uchun javob sxemasi."""
    id: uuid.UUID
    student_id: uuid.UUID
    test_id: uuid.UUID
    foydalanuvchi_javoblari: Any
    togri_javoblar_soni: int
    ball_foizi: float
    baho: str
    topshirilgan_vaqt: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# AI XIZMATI SXEMALARI
# ─────────────────────────────────────────────────────────────────────────────

class AIGeneratsiyaSorovi(BaseModel):
    """
    AI kontent generatsiya so'rovi sxemasi.
    POST /api/v1/ai/generate endpoint'ida ishlatiladi.
    """
    mavzu: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="AI generatsiya qilishi kerak bo'lgan mavzu (o'zbekcha bo'lishi kerak)"
    )
    kurs_id: Optional[uuid.UUID] = Field(
        None,
        description="Agar ma'lum bir kursga tegishli bo'lsa, kurs ID'si (ixtiyoriy)"
    )

    model_config = ConfigDict(from_attributes=True)

    # Foydalanish misoli — bu FastAPI docs'da ko'rinadi
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "mavzu": "Pythonda ro'yxatlar (Lists) va ularning metodlari",
                    "kurs_id": None
                }
            ]
        }
    }


class AIGeneratsiyaJavobi(BaseModel):
    """
    AI tomonidan yaratilgan to'liq kontent uchun javob sxemasi.
    Bu sxema API javobida qaytariladigan barcha AI ma'lumotlarini o'z ichiga oladi.
    """
    mavzu: str = Field(..., description="Generatsiya qilingan mavzu")
    savollar: List[MCQSavol] = Field(
        ...,
        description="5 ta ko'p tanlovli savol (MCQ)"
    )
    dars_rejasi: dict = Field(
        ...,
        description="Strukturalangan dars rejasi (o'zbekcha)"
    )
    uy_vazifasi: str = Field(
        ...,
        description="Dars bo'yicha uy vazifasi (o'zbekcha)"
    )
    baholash_mezoni: dict = Field(
        ...,
        description="Qat'iy baholash mezonlari (o'zbekcha)"
    )
    yaratilgan_vaqt: str = Field(
        ...,
        description="Kontent yaratilgan vaqt (ISO format)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# UMUMIY JAVOB SXEMASI
# ─────────────────────────────────────────────────────────────────────────────

class UmumiyJavob(BaseModel):
    """
    Barcha API endpoint'larida ishlatilishi mumkin bo'lgan
    standart javob o'rami (response wrapper).
    
    Misol:
        {
            "muvaffaqiyat": true,
            "xabar": "Foydalanuvchi muvaffaqiyatli yaratildi",
            "malumot": { ... }
        }
    """
    muvaffaqiyat: bool = Field(..., description="Operatsiya muvaffaqiyatli bo'ldimi?")
    xabar: str = Field(..., description="Natija haqida xabar (o'zbekcha)")
    malumot: Optional[Any] = Field(None, description="Asosiy ma'lumot (ixtiyoriy)")

    model_config = ConfigDict(from_attributes=True)


class XatoJavob(BaseModel):
    """
    Xato holatlarda qaytariladigan standart xato javob sxemasi.
    
    Misol:
        {
            "muvaffaqiyat": false,
            "xato_kodi": "TOPILMADI",
            "xabar": "Foydalanuvchi topilmadi",
            "tafsilot": "id=xxx bo'lgan foydalanuvchi bazada mavjud emas"
        }
    """
    muvaffaqiyat: bool = Field(default=False)
    xato_kodi: str = Field(..., description="Xato kodi (masalan: TOPILMADI, XATO_SOROV)")
    xabar: str = Field(..., description="Foydalanuvchiga mo'ljallangan xabar (o'zbekcha)")
    tafsilot: Optional[str] = Field(None, description="Texnik tafsilot (debug uchun)")


# ─────────────────────────────────────────────────────────────────────────────
# YANGI QO'SHILGAN SXEMALAR (Auth & PUT)
# ─────────────────────────────────────────────────────────────────────────────

class TizimgaKirish(BaseModel):
    """Tizimga kirish (Login) uchun sxema."""
    email: EmailStr = Field(..., description="Foydalanuvchining email manzili")
    parol: str = Field(..., description="Parol")

class FoydalanuvchiYangilash(BaseModel):
    """Foydalanuvchi ma'lumotlarini qisman yangilash uchun sxema."""
    tolik_ism: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = Field(None)
    parol: Optional[str] = Field(None, min_length=8, max_length=128)
    rol: Optional[str] = Field(None)
    faol: Optional[bool] = Field(None)

    @field_validator("rol")
    def rolni_tekshirish(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            ruxsat_etilgan = {"student", "teacher", "admin"}
            if v not in ruxsat_etilgan:
                raise ValueError(f"Rol '{v}' noto'g'ri. Faqat: student, teacher, admin.")
        return v

class KursYangilash(BaseModel):
    """Kurs ma'lumotlarini qisman yangilash uchun sxema."""
    nomi: Optional[str] = Field(None, min_length=3, max_length=500)
    tavsif: Optional[str] = Field(None)
    mavzu: Optional[str] = Field(None, min_length=2, max_length=255)
    daraja: Optional[str] = Field(None)
    faol: Optional[bool] = Field(None)

class DarsYangilash(BaseModel):
    """Dars ma'lumotlarini qisman yangilash uchun sxema."""
    sarlavha: Optional[str] = Field(None, min_length=3, max_length=500)
    mazmun: Optional[str] = Field(None)
    tartib_raqami: Optional[int] = Field(None, ge=1)

class TestYangilash(BaseModel):
    """Test ma'lumotlarini qisman yangilash uchun sxema."""
    nomi: Optional[str] = Field(None, min_length=3, max_length=500)
    mavzu: Optional[str] = Field(None, min_length=2, max_length=500)
    faol: Optional[bool] = Field(None)
    umumiy_ball: Optional[int] = Field(None, ge=0)
