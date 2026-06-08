# =============================================================================
# main.py — Mini LMS API asosiy fayli
# =============================================================================
# Bu fayl butun FastAPI ilovasining markaziy nuqtasi hisoblanadi.
#
# Tuzilma:
#   - FastAPI ilovasini sozlash va CORS'ni yoqish
#   - Barcha routerlarni ulash (foydalanuvchilar, kurslar, darslar, testlar,
#     natijalar, va AI xizmati)
#   - Dastur ishga tushganda ma'lumotlar bazasi jadvallarini yaratish
#   - Health check endpoint'i
#
# Muhit:
#   - Vercel Serverless Functions (handler = app)
#   - Python 3.11+
#   - FastAPI + SQLAlchemy + Pydantic + Gemini AI
# =============================================================================

import logging                          # Loglash uchun
from contextlib import asynccontextmanager  # Dastur hayot tsikli uchun
from typing import Any, Dict            # Tip izohlar uchun
from datetime import datetime, timezone # Vaqt uchun
import uuid                             # UUID uchun

from fastapi import FastAPI, HTTPException, Depends, status  # FastAPI asosi
from fastapi.middleware.cors import CORSMiddleware           # CORS middleware
from fastapi.responses import JSONResponse                   # JSON javoblar
from sqlalchemy.orm import Session                           # DB sessiya

# Ichki modullarni import qilish
from database import get_db, init_db, check_db_connection   # DB yordamchilari
import models                                                # SQLAlchemy modellari
from models import (                                         # Pydantic sxemalari
    FoydalanuvchiYaratish, FoydalanuvchiJavob,
    KursYaratish, KursJavob,
    DarsYaratish, DarsJavob,
    TestYaratish, TestJavob,
    NatijaYaratish, NatijaJavob,
    AIGeneratsiyaSorovi, AIGeneratsiyaJavobi,
    UmumiyJavob, XatoJavob,
    MCQSavol,
    TizimgaKirish, FoydalanuvchiYangilash,
    KursYangilash, DarsYangilash, TestYangilash,
)
from ai_service import ai_kontent_generatsiya, testni_tekshirish_va_ball_hisoblash

# Parol xeshlash uchun (foydalanuvchi ro'yxatdan o'tishi)
# passlib kutubxonasi bcrypt algoritmini ishlatadi
try:
    from passlib.context import CryptContext
    parol_konteksti = CryptContext(schemes=["bcrypt"], deprecated="auto")
    PASSLIB_MAVJUD = True
except ImportError:
    # Agar passlib o'rnatilmagan bo'lsa, oddiy hash ishlatamiz (faqat test uchun!)
    import hashlib
    PASSLIB_MAVJUD = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(
        "passlib o'rnatilmagan! Ishlab chiqish muhitida SHA-256 ishlatilmoqda. "
        "Ishlab chiqarishda 'pip install passlib[bcrypt]' buyrug'ini bajaring!"
    )

# ---------------------------------------------------------------------------
# Loglashni sozlash
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# DASTUR HAYOT TSIKLI (Application Lifespan)
# =============================================================================

@asynccontextmanager
async def hayot_tsikli(app: FastAPI):
    """
    Dastur ishga tushish va to'xtash paytida bajariladigan operatsiyalar.
    
    ISHGA TUSHISH:
      1. Ma'lumotlar bazasiga ulanishni tekshirish
      2. Barcha jadvallarni yaratish (mavjud bo'lmasa)
    
    TO'XTASH:
      - Hozirda hech narsa — SQLAlchemy connection pool avtomatik yopiladi
    """
    # ── Ishga tushish bosqichi ──────────────────────────────────────────────
    logger.info("═══════════════════════════════════════════════")
    logger.info("  Mini LMS API — Ishga tushmoqda...")
    logger.info("═══════════════════════════════════════════════")

    # Ma'lumotlar bazasiga ulanishni tekshirish
    logger.info("Ma'lumotlar bazasiga ulanish tekshirilmoqda...")
    if check_db_connection():
        logger.info("✓ Ma'lumotlar bazasiga muvaffaqiyatli ulandi.")
    else:
        logger.critical("✗ Ma'lumotlar bazasiga ulanib bo'lmadi! DATABASE_URL'ni tekshiring.")

    # Jadvallarni yaratish
    logger.info("Ma'lumotlar bazasi jadvallari yaratilmoqda...")
    try:
        init_db()
        logger.info("✓ Barcha jadvallar tayyor.")
    except Exception as e:
        logger.critical(f"✗ Jadval yaratishda xato: {e}")

    logger.info("✓ Mini LMS API muvaffaqiyatli ishga tushdi!")
    logger.info("═══════════════════════════════════════════════")

    yield  # Dastur ishlaydi — bu yerda API so'rovlarni qabul qiladi

    # ── To'xtash bosqichi ─────────────────────────────────────────────────
    logger.info("Mini LMS API to'xtatilmoqda...")


# =============================================================================
# FASTAPI ILOVASINI YARATISH
# =============================================================================

# Vercel'da ilova "app" nomli o'zgaruvchi sifatida eksport qilinishi kerak.
# vercel.json'da "handler" sifatida "main.app" ko'rsatiladi.
app = FastAPI(
    title="Mini LMS AI API",
    description="""
    ## O'zbekistondagi Mini LMS (Learning Management System) uchun AI-powered Backend API
    
    Bu API quyidagi komponentlarga xizmat qiladi:
    - **Veb Ilova** — React/Vue/HTML frontend
    - **Telegram Bot** — Python-telegram-bot yoki Aiogram
    - **Desktop Ilova** — Electron yoki PyQt
    
    ### Asosiy imkoniyatlar:
    - 🤖 **AI Kontent Generatsiyasi** — Gemini 1.5 Flash yordamida avtomatik dars va test yaratish
    - 👥 **Foydalanuvchilar Boshqaruvi** — Ro'yxatdan o'tish, kirish, rol tizimi
    - 📚 **Kurslar va Darslar** — To'liq CRUD operatsiyalar
    - 📝 **Testlar va Natijalar** — AI yaratgan MCQ testlar va natijalarni saqlash
    
    ### Barcha ma'lumotlar O'zbek tilida!
    """,
    version="1.0.0",
    lifespan=hayot_tsikli,
    docs_url="/docs",          # Swagger UI manzili
    redoc_url="/redoc",        # ReDoc manzili
    openapi_url="/openapi.json",  # OpenAPI sxemasi
)


# =============================================================================
# CORS MIDDLEWARE SOZLASH
# =============================================================================
# CORS (Cross-Origin Resource Sharing) — turli domenlardan API'ga murojaat
# qilishga ruxsat berish mexanizmi.
#
# allow_origins=["*"] — BARCHA domenlardan murojaat qabul qilinadi.
# Bu Veb Ilova, Telegram Bot va Desktop Ilovaning bir xil API'dan
# foydalanishini ta'minlaydi.
#
# MUHIM XAVFSIZLIK ESLATMASI:
# Ishlab chiqarishda allow_origins'ni aniq domenlar ro'yxati bilan
# almashtirishni tavsiya etamiz. Masalan:
# allow_origins=["https://sizning-domain.uz", "https://bot.sizning-domain.uz"]
# Hozirda ["*"] ishlab chiqish va prototiplash uchun qo'llanilmoqda.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Barcha domenlardan murojaat — wildcard
    allow_credentials=False,       # credentials bilan wildcard birga ishlamaydi
    allow_methods=["*"],           # GET, POST, PUT, DELETE, PATCH, OPTIONS — hammasi
    allow_headers=["*"],           # Barcha HTTP headerlar ruxsat etiladi
)
logger.info("CORS middleware muvaffaqiyatli ulandi (wildcard: *).")


# =============================================================================
# YORDAMCHI FUNKSIYALAR
# =============================================================================

def parolni_heshlash(parol: str) -> str:
    """
    Parolni xavfsiz tarzda hashlaydi.
    
    Bcrypt ishlatilsa — eng xavfsiz usul.
    Bcrypt mavjud bo'lmasa — SHA-256 (FAQAT TEST UCHUN, ishlab chiqarishda ISHLATMA!)
    
    Parametrlar:
        parol: Ochiq matn parol
        
    Qaytaradi:
        str — Hashlangan parol (saqlanishi xavfsiz)
    """
    if PASSLIB_MAVJUD:
        return parol_konteksti.hash(parol)
    else:
        import hashlib
        return hashlib.sha256(parol.encode()).hexdigest()


def parolni_tekshirish(parol: str, hash_parol: str) -> bool:
    """
    Ochiq parolni hashlangan parol bilan solishtiradi.
    
    Parametrlar:
        parol: Foydalanuvchi kiritgan ochiq parol
        hash_parol: Bazada saqlangan hashlangan parol
        
    Qaytaradi:
        True — Parol to'g'ri
        False — Parol noto'g'ri
    """
    if PASSLIB_MAVJUD:
        return parol_konteksti.verify(parol, hash_parol)
    else:
        import hashlib
        return hashlib.sha256(parol.encode()).hexdigest() == hash_parol


# =============================================================================
# ASOSIY ENDPOINT'LAR
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# SOG'LIQ TEKSHIRUVI (Health Check)
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/",
    tags=["Tizim"],
    summary="Asosiy sahifa — API ishlayotganligini tekshirish",
    response_model=UmumiyJavob,
)
async def asosiy_sahifa():
    """
    API asosiy sahifasi — server ishlayotganligini tekshirish uchun.
    
    Vercel deployment'dan keyin ushbu endpoint'ga murojaat qilib,
    API'ning to'g'ri ishga tushganini tasdiqlang.
    
    Qaytaradi:
        - API nomi va versiyasi
        - Joriy vaqt
        - Muvaffaqiyat holati
    """
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Mini LMS AI API muvaffaqiyatli ishlayapti! Barcha tizimlar faol.",
        malumot={
            "api_nomi": "Mini LMS AI API",
            "versiya": "1.0.0",
            "til": "O'zbek",
            "vaqt": datetime.now(timezone.utc).isoformat(),
            "muhit": "Vercel Serverless",
            "tavsif": "O'zbekistondagi Mini LMS platformasi uchun AI-powered Backend",
        },
    )


@app.get(
    "/api/v1/salomatlik",
    tags=["Tizim"],
    summary="Tizim salomatligi va ma'lumotlar bazasi holati",
    response_model=UmumiyJavob,
)
async def salomatlik_tekshiruvi():
    """
    Tizimning to'liq salomatligini tekshiradi:
      - API holati
      - Ma'lumotlar bazasi ulanishi
      - Joriy vaqt
    
    Monitoring tizimlari (Uptime Robot, Ping va h.k.) uchun ishlatiladi.
    """
    # Ma'lumotlar bazasi ulanishini tekshirish
    db_holati = check_db_connection()

    return UmumiyJavob(
        muvaffaqiyat=db_holati,
        xabar="Tizim salomatligi tekshirildi." if db_holati else "Ma'lumotlar bazasi bilan muammo!",
        malumot={
            "api_holati": "faol",
            "db_holati": "ulangan" if db_holati else "uzilgan",
            "vaqt": datetime.now(timezone.utc).isoformat(),
        },
    )


# =============================================================================
# AUTHENTIKATSIYA ENDPOINT'LARI (/api/v1/auth)
# =============================================================================

@app.post(
    "/api/v1/auth/login",
    tags=["Auth"],
    summary="Tizimga kirish (Login)",
    response_model=UmumiyJavob,
)
async def tizimga_kirish(
    malumot: TizimgaKirish,
    db: Session = Depends(get_db),
):
    """
    Foydalanuvchini email va parol orqali tizimga kiritish.
    
    Qaytaradi:
      - Foydalanuvchi ma'lumotlari (shu jumladan roli)
    """
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.email == malumot.email).first()
    
    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"muvaffaqiyat": False, "xato_kodi": "XATO_KIRISH", "xabar": "Email yoki parol noto'g'ri."}
        )
        
    if not parolni_tekshirish(malumot.parol, foydalanuvchi.parol_heshi):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"muvaffaqiyat": False, "xato_kodi": "XATO_KIRISH", "xabar": "Email yoki parol noto'g'ri."}
        )
        
    if not foydalanuvchi.faol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"muvaffaqiyat": False, "xato_kodi": "BLOKLANGAN", "xabar": "Hisobingiz bloklangan."}
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Tizimga muvaffaqiyatli kirdingiz.",
        malumot=FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump(),
    )


# =============================================================================
# FOYDALANUVCHILAR ENDPOINT'LARI (/api/v1/foydalanuvchilar)
# =============================================================================

@app.post(
    "/api/v1/foydalanuvchilar",
    tags=["Foydalanuvchilar"],
    summary="Yangi foydalanuvchi ro'yxatdan o'tkazish",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def foydalanuvchi_yaratish(
    malumot: FoydalanuvchiYaratish,
    db: Session = Depends(get_db),
):
    """
    Yangi foydalanuvchini platforma'ga ro'yxatdan o'tkazadi.
    
    Jarayon:
      1. Email manzilining mavjudligini tekshirish
      2. Parolni bcrypt bilan hashlash
      3. Yangi foydalanuvchini bazaga saqlash
      4. Muvaffaqiyat xabarini qaytarish
    
    Xatolar:
      - 400: Email allaqachon ro'yxatdan o'tgan
      - 500: Server xatosi
    """
    logger.info(f"Yangi foydalanuvchi ro'yxatdan o'tkazilmoqda: {malumot.email}")

    # 1. Email takrorlanishini tekshirish
    # Bazada shu email bilan foydalanuvchi bormi?
    mavjud_foydalanuvchi = (
        db.query(models.Foydalanuvchi)
        .filter(models.Foydalanuvchi.email == malumot.email)
        .first()
    )
    if mavjud_foydalanuvchi:
        logger.warning(f"Ro'yxatdan o'tishda takrorlangan email: {malumot.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "EMAIL_MAVJUD",
                "xabar": f"'{malumot.email}' email manzili allaqachon ro'yxatdan o'tgan.",
                "tafsilot": "Boshqa email kiriting yoki tizimga kiring.",
            },
        )

    # 2. Parolni xavfsiz tarzda hashlash
    # Hech qachon ochiq parolni bazaga saqlama!
    hashlangan_parol = parolni_heshlash(malumot.parol)

    # 3. Yangi foydalanuvchi ob'ektini yaratish
    yangi_foydalanuvchi = models.Foydalanuvchi(
        tolik_ism=malumot.tolik_ism,
        email=malumot.email,
        parol_heshi=hashlangan_parol,
        rol=malumot.rol,
        faol=True,
    )

    # 4. Bazaga saqlash
    try:
        db.add(yangi_foydalanuvchi)  # Ob'ektni sessiyaga qo'shish
        db.commit()                  # Tranzaksiyani yakunlash
        db.refresh(yangi_foydalanuvchi)  # Bazadan yangilangan ma'lumotlarni o'qish
        logger.info(
            f"Yangi foydalanuvchi muvaffaqiyatli yaratildi: "
            f"ID={yangi_foydalanuvchi.id}, Email={yangi_foydalanuvchi.email}"
        )
    except Exception as db_xatosi:
        db.rollback()  # Xato bo'lsa — barcha o'zgarishlarni bekor qilish
        logger.error(f"Foydalanuvchi yaratishda baza xatosi: {db_xatosi}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "BAZA_XATOSI",
                "xabar": "Foydalanuvchi ma'lumotlarini saqlashda xato yuz berdi.",
                "tafsilot": str(db_xatosi),
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{malumot.tolik_ism}' muvaffaqiyatli ro'yxatdan o'tdi!",
        malumot=FoydalanuvchiJavob.model_validate(yangi_foydalanuvchi).model_dump(),
    )


@app.get(
    "/api/v1/foydalanuvchilar",
    tags=["Foydalanuvchilar"],
    summary="Barcha foydalanuvchilarni ro'yxatini olish",
    response_model=UmumiyJavob,
)
async def foydalanuvchilar_royxati(
    sahifa: int = 1,           # Sahifa raqami (pagination)
    hajm: int = 20,            # Har sahifadagi elementlar soni
    db: Session = Depends(get_db),
):
    """
    Barcha foydalanuvchilar ro'yxatini sahifalash bilan qaytaradi.
    
    Parametrlar:
      - sahifa: Nechchi sahifani ko'rsatish (1 dan boshlab)
      - hajm: Bir sahifada nechta foydalanuvchi (maksimal 100)
    """
    # Hajmni cheklash — 100 dan ko'p bo'lmasin (server yukini kamaytirish)
    hajm = min(hajm, 100)
    # Sahifani manfiy bo'lmasin
    sahifa = max(sahifa, 1)

    # Jami foydalanuvchilar sonini hisoblash
    jami_son = db.query(models.Foydalanuvchi).count()

    # Sahifalangan foydalanuvchilar ro'yxatini olish
    # offset — qancha yozuvni o'tkazib yuborish
    # limit — nechta yozuv olish
    foydalanuvchilar = (
        db.query(models.Foydalanuvchi)
        .order_by(models.Foydalanuvchi.yaratilgan_vaqt.desc())  # Eng yangilari birinchi
        .offset((sahifa - 1) * hajm)
        .limit(hajm)
        .all()
    )

    # SQLAlchemy modellarini Pydantic sxemasiga aylantirish
    javob_ro_yxati = [
        FoydalanuvchiJavob.model_validate(f).model_dump() for f in foydalanuvchilar
    ]

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"Jami {jami_son} ta foydalanuvchidan {len(javob_ro_yxati)} tasi ko'rsatilmoqda.",
        malumot={
            "jami": jami_son,
            "sahifa": sahifa,
            "hajm": hajm,
            "foydalanuvchilar": javob_ro_yxati,
        },
    )


@app.get(
    "/api/v1/foydalanuvchilar/{foydalanuvchi_id}",
    tags=["Foydalanuvchilar"],
    summary="Bitta foydalanuvchini ID bo'yicha olish",
    response_model=UmumiyJavob,
)
async def foydalanuvchi_olish(
    foydalanuvchi_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Berilgan ID bo'yicha bitta foydalanuvchi ma'lumotlarini qaytaradi.
    
    Xatolar:
      - 404: Foydalanuvchi topilmadi
    """
    foydalanuvchi = (
        db.query(models.Foydalanuvchi)
        .filter(models.Foydalanuvchi.id == foydalanuvchi_id)
        .first()
    )

    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{foydalanuvchi_id}' bo'lgan foydalanuvchi topilmadi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Foydalanuvchi muvaffaqiyatli topildi.",
        malumot=FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump(),
    )


@app.delete(
    "/api/v1/foydalanuvchilar/{foydalanuvchi_id}",
    tags=["Foydalanuvchilar"],
    summary="Foydalanuvchini o'chirish",
    response_model=UmumiyJavob,
)
async def foydalanuvchi_ochirish(
    foydalanuvchi_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Berilgan ID bo'lgan foydalanuvchini bazadan o'chiradi.
    Bu operatsiya qaytarib bo'lmaydi!
    
    Cascade Delete: Foydalanuvchi o'chganda uning barcha natijalari ham o'chadi.
    """
    foydalanuvchi = (
        db.query(models.Foydalanuvchi)
        .filter(models.Foydalanuvchi.id == foydalanuvchi_id)
        .first()
    )

    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{foydalanuvchi_id}' bo'lgan foydalanuvchi topilmadi.",
            },
        )

    ism = foydalanuvchi.tolik_ism  # O'chirishdan oldin ismni saqlash
    db.delete(foydalanuvchi)       # O'chirish uchun belgilash
    db.commit()                    # Tranzaksiyani yakunlash

    logger.info(f"Foydalanuvchi o'chirildi: {ism} (ID: {foydalanuvchi_id})")

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{ism}' foydalanuvchisi muvaffaqiyatli o'chirildi.",
    )

@app.put(
    "/api/v1/foydalanuvchilar/{foydalanuvchi_id}",
    tags=["Foydalanuvchilar"],
    summary="Foydalanuvchi ma'lumotlarini tahrirlash",
    response_model=UmumiyJavob,
)
async def foydalanuvchi_tahrirlash(
    foydalanuvchi_id: uuid.UUID,
    malumot: FoydalanuvchiYangilash,
    db: Session = Depends(get_db),
):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"muvaffaqiyat": False, "xato_kodi": "TOPILMADI", "xabar": "Foydalanuvchi topilmadi."}
        )
    
    update_data = malumot.model_dump(exclude_unset=True)
    if "parol" in update_data and update_data["parol"]:
        update_data["parol_heshi"] = parolni_heshlash(update_data.pop("parol"))
        
    for key, value in update_data.items():
        setattr(foydalanuvchi, key, value)
        
    db.commit()
    db.refresh(foydalanuvchi)
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Foydalanuvchi ma'lumotlari yangilandi.",
        malumot=FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump(),
    )

@app.get(
    "/api/v1/foydalanuvchilar/{foydalanuvchi_id}/tarix",
    tags=["Foydalanuvchilar"],
    summary="Foydalanuvchining test natijalari tarixi",
    response_model=UmumiyJavob,
)
async def foydalanuvchi_tarixi(
    foydalanuvchi_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"muvaffaqiyat": False, "xato_kodi": "TOPILMADI", "xabar": "Foydalanuvchi topilmadi."}
        )
        
    natijalar = db.query(models.Natija).filter(models.Natija.student_id == foydalanuvchi_id).order_by(models.Natija.topshirilgan_vaqt.desc()).all()
    javob_ro_yxati = [NatijaJavob.model_validate(n).model_dump() for n in natijalar]
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"Topilgan natijalar soni: {len(javob_ro_yxati)}",
        malumot=javob_ro_yxati,
    )


# =============================================================================
# KURSLAR ENDPOINT'LARI (/api/v1/kurslar)
# =============================================================================

@app.post(
    "/api/v1/kurslar",
    tags=["Kurslar"],
    summary="Yangi kurs yaratish",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def kurs_yaratish(
    malumot: KursYaratish,
    db: Session = Depends(get_db),
):
    """
    Yangi o'quv kursini yaratadi va bazaga saqlaydi.
    
    So'rov tanasi (JSON):
      - nomi: Kurs nomi (majburiy)
      - mavzu: Kurs fani (majburiy)
      - tavsif: Kurs tavsifi (ixtiyoriy)
      - daraja: boshlovchi | o'rta | yuqori (ixtiyoriy)
    """
    logger.info(f"Yangi kurs yaratilmoqda: '{malumot.nomi}'")

    yangi_kurs = models.Kurs(
        nomi=malumot.nomi,
        tavsif=malumot.tavsif,
        mavzu=malumot.mavzu,
        daraja=malumot.daraja,
        faol=True,
    )

    try:
        db.add(yangi_kurs)
        db.commit()
        db.refresh(yangi_kurs)
        logger.info(f"Kurs yaratildi: ID={yangi_kurs.id}, Nomi='{yangi_kurs.nomi}'")
    except Exception as e:
        db.rollback()
        logger.error(f"Kurs yaratishda xato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "BAZA_XATOSI",
                "xabar": "Kursni saqlashda xato yuz berdi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{malumot.nomi}' kursi muvaffaqiyatli yaratildi!",
        malumot=KursJavob.model_validate(yangi_kurs).model_dump(),
    )


@app.get(
    "/api/v1/kurslar",
    tags=["Kurslar"],
    summary="Barcha kurslar ro'yxatini olish",
    response_model=UmumiyJavob,
)
async def kurslar_royxati(
    sahifa: int = 1,
    hajm: int = 20,
    daraja: str = None,  # Daraja bo'yicha filtrlash (ixtiyoriy)
    db: Session = Depends(get_db),
):
    """
    Barcha kurslar ro'yxatini sahifalash va filtrlash bilan qaytaradi.
    
    Parametrlar:
      - sahifa: Sahifa raqami
      - hajm: Bir sahifadagi kurslar soni (max 100)
      - daraja: Daraja bo'yicha filtrlash (boshlovchi, o'rta, yuqori)
    """
    hajm = min(hajm, 100)
    sahifa = max(sahifa, 1)

    # Asosiy so'rov — faqat faol kurslar
    sorov = db.query(models.Kurs).filter(models.Kurs.faol == True)

    # Daraja bo'yicha filtrlash (agar berilgan bo'lsa)
    if daraja:
        sorov = sorov.filter(models.Kurs.daraja == daraja)

    # Jami son va sahifalash
    jami_son = sorov.count()
    kurslar = (
        sorov
        .order_by(models.Kurs.yaratilgan_vaqt.desc())
        .offset((sahifa - 1) * hajm)
        .limit(hajm)
        .all()
    )

    javob_ro_yxati = [KursJavob.model_validate(k).model_dump() for k in kurslar]

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"Jami {jami_son} ta kursdan {len(javob_ro_yxati)} tasi ko'rsatilmoqda.",
        malumot={
            "jami": jami_son,
            "sahifa": sahifa,
            "hajm": hajm,
            "kurslar": javob_ro_yxati,
        },
    )


@app.get(
    "/api/v1/kurslar/{kurs_id}",
    tags=["Kurslar"],
    summary="Bitta kursni ID bo'yicha olish",
    response_model=UmumiyJavob,
)
async def kurs_olish(
    kurs_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Berilgan ID bo'lgan kursni barcha ma'lumotlari bilan qaytaradi."""
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()

    if not kurs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{kurs_id}' bo'lgan kurs topilmadi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Kurs muvaffaqiyatli topildi.",
        malumot=KursJavob.model_validate(kurs).model_dump(),
    )


@app.delete(
    "/api/v1/kurslar/{kurs_id}",
    tags=["Kurslar"],
    summary="Kursni o'chirish",
    response_model=UmumiyJavob,
)
async def kurs_ochirish(
    kurs_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Berilgan ID bo'lgan kursni o'chiradi.
    DIQQAT: Kurs o'chganda uning barcha darslari va testlari ham o'chadi (CASCADE)!
    """
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()

    if not kurs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{kurs_id}' bo'lgan kurs topilmadi.",
            },
        )

    nomi = kurs.nomi
    db.delete(kurs)
    db.commit()
    logger.info(f"Kurs o'chirildi: '{nomi}' (ID: {kurs_id})")

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{nomi}' kursi muvaffaqiyatli o'chirildi.",
    )

@app.put(
    "/api/v1/kurslar/{kurs_id}",
    tags=["Kurslar"],
    summary="Kurs ma'lumotlarini tahrirlash",
    response_model=UmumiyJavob,
)
async def kurs_tahrirlash(
    kurs_id: uuid.UUID,
    malumot: KursYangilash,
    db: Session = Depends(get_db),
):
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()
    if not kurs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"muvaffaqiyat": False, "xato_kodi": "TOPILMADI", "xabar": "Kurs topilmadi."}
        )
        
    update_data = malumot.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(kurs, key, value)
        
    db.commit()
    db.refresh(kurs)
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Kurs ma'lumotlari yangilandi.",
        malumot=KursJavob.model_validate(kurs).model_dump(),
    )


# =============================================================================
# DARSLAR ENDPOINT'LARI (/api/v1/darslar)
# =============================================================================

@app.post(
    "/api/v1/darslar",
    tags=["Darslar"],
    summary="Yangi dars yaratish",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def dars_yaratish(
    malumot: DarsYaratish,
    db: Session = Depends(get_db),
):
    """
    Yangi darsni yaratadi va berilgan kursga bog'laydi.
    
    Kurs mavjudligi tekshiriladi — mavjud bo'lmasa 404 xatosi qaytariladi.
    """
    logger.info(f"Yangi dars yaratilmoqda: '{malumot.sarlavha}'")

    # Kursning mavjudligini tekshirish
    kurs = db.query(models.Kurs).filter(models.Kurs.id == malumot.kurs_id).first()
    if not kurs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "KURS_TOPILMADI",
                "xabar": f"ID '{malumot.kurs_id}' bo'lgan kurs topilmadi.",
            },
        )

    yangi_dars = models.Dars(
        kurs_id=malumot.kurs_id,
        sarlavha=malumot.sarlavha,
        mazmun=malumot.mazmun,
        tartib_raqami=malumot.tartib_raqami,
    )

    try:
        db.add(yangi_dars)
        db.commit()
        db.refresh(yangi_dars)
        logger.info(f"Dars yaratildi: ID={yangi_dars.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Dars yaratishda xato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "BAZA_XATOSI",
                "xabar": "Darsni saqlashda xato yuz berdi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{malumot.sarlavha}' darsi muvaffaqiyatli yaratildi!",
        malumot=DarsJavob.model_validate(yangi_dars).model_dump(),
    )


@app.get(
    "/api/v1/kurslar/{kurs_id}/darslar",
    tags=["Darslar"],
    summary="Kursga tegishli barcha darslarni olish",
    response_model=UmumiyJavob,
)
async def kurs_darslari(
    kurs_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Berilgan kursga tegishli barcha darslarni tartib raqami bo'yicha qaytaradi.
    """
    # Kursni tekshirish
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()
    if not kurs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "KURS_TOPILMADI",
                "xabar": f"ID '{kurs_id}' bo'lgan kurs topilmadi.",
            },
        )

    # Kurs darslarini tartib raqami bo'yicha tartiblash
    darslar = (
        db.query(models.Dars)
        .filter(models.Dars.kurs_id == kurs_id)
        .order_by(models.Dars.tartib_raqami.asc())  # Birinchi dars birinchi
        .all()
    )

    javob_ro_yxati = [DarsJavob.model_validate(d).model_dump() for d in darslar]

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{kurs.nomi}' kursi uchun {len(darslar)} ta dars topildi.",
        malumot={
            "kurs_nomi": kurs.nomi,
            "jami_darslar": len(darslar),
            "darslar": javob_ro_yxati,
        },
    )


@app.get(
    "/api/v1/darslar/{dars_id}",
    tags=["Darslar"],
    summary="Bitta darsni ID bo'yicha olish",
    response_model=UmumiyJavob,
)
async def dars_olish(
    dars_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Berilgan ID bo'lgan darsni to'liq ma'lumotlari bilan qaytaradi."""
    dars = db.query(models.Dars).filter(models.Dars.id == dars_id).first()

    if not dars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{dars_id}' bo'lgan dars topilmadi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Dars muvaffaqiyatli topildi.",
        malumot=DarsJavob.model_validate(dars).model_dump(),
    )

@app.put(
    "/api/v1/darslar/{dars_id}",
    tags=["Darslar"],
    summary="Dars ma'lumotlarini tahrirlash",
    response_model=UmumiyJavob,
)
async def dars_tahrirlash(
    dars_id: uuid.UUID,
    malumot: DarsYangilash,
    db: Session = Depends(get_db),
):
    dars = db.query(models.Dars).filter(models.Dars.id == dars_id).first()
    if not dars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"muvaffaqiyat": False, "xato_kodi": "TOPILMADI", "xabar": "Dars topilmadi."}
        )
        
    update_data = malumot.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(dars, key, value)
        
    db.commit()
    db.refresh(dars)
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Dars ma'lumotlari yangilandi.",
        malumot=DarsJavob.model_validate(dars).model_dump(),
    )


# =============================================================================
# TESTLAR ENDPOINT'LARI (/api/v1/testlar)
# =============================================================================

@app.post(
    "/api/v1/testlar",
    tags=["Testlar"],
    summary="Yangi test yaratish (qo'lda)",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def test_yaratish(
    malumot: TestYaratish,
    savollar: list,        # Test savollari — MCQSavol formatida ro'yxat
    db: Session = Depends(get_db),
):
    """
    Qo'lda test yaratish endpoint'i.
    AI orqali test yaratish uchun /api/v1/ai/generate dan foydalaning.
    """
    yangi_test = models.Test(
        nomi=malumot.nomi,
        mavzu=malumot.mavzu,
        kurs_id=malumot.kurs_id,
        savollar=savollar,
        yaratuvchi="oqituvchi",
    )

    try:
        db.add(yangi_test)
        db.commit()
        db.refresh(yangi_test)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"xabar": f"Testni saqlashda xato: {str(e)}"},
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{malumot.nomi}' testi muvaffaqiyatli yaratildi!",
        malumot=TestJavob.model_validate(yangi_test).model_dump(),
    )


@app.get(
    "/api/v1/testlar",
    tags=["Testlar"],
    summary="Barcha testlar ro'yxatini olish",
    response_model=UmumiyJavob,
)
async def testlar_royxati(
    sahifa: int = 1,
    hajm: int = 20,
    db: Session = Depends(get_db),
):
    """Barcha faol testlar ro'yxatini sahifalash bilan qaytaradi."""
    hajm = min(hajm, 100)
    sahifa = max(sahifa, 1)

    jami_son = db.query(models.Test).filter(models.Test.faol == True).count()
    testlar = (
        db.query(models.Test)
        .filter(models.Test.faol == True)
        .order_by(models.Test.yaratilgan_vaqt.desc())
        .offset((sahifa - 1) * hajm)
        .limit(hajm)
        .all()
    )

    javob_ro_yxati = [TestJavob.model_validate(t).model_dump() for t in testlar]

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"Jami {jami_son} ta testdan {len(javob_ro_yxati)} tasi ko'rsatilmoqda.",
        malumot={
            "jami": jami_son,
            "sahifa": sahifa,
            "hajm": hajm,
            "testlar": javob_ro_yxati,
        },
    )


@app.get(
    "/api/v1/testlar/{test_id}",
    tags=["Testlar"],
    summary="Bitta testni ID bo'yicha olish",
    response_model=UmumiyJavob,
)
async def test_olish(
    test_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Berilgan ID bo'lgan testni barcha savollari bilan qaytaradi."""
    test = db.query(models.Test).filter(models.Test.id == test_id).first()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TOPILMADI",
                "xabar": f"ID '{test_id}' bo'lgan test topilmadi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Test muvaffaqiyatli topildi.",
        malumot=TestJavob.model_validate(test).model_dump(),
    )

@app.put(
    "/api/v1/testlar/{test_id}",
    tags=["Testlar"],
    summary="Test ma'lumotlarini tahrirlash",
    response_model=UmumiyJavob,
)
async def test_tahrirlash(
    test_id: uuid.UUID,
    malumot: TestYangilash,
    db: Session = Depends(get_db),
):
    test = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"muvaffaqiyat": False, "xato_kodi": "TOPILMADI", "xabar": "Test topilmadi."}
        )
        
    update_data = malumot.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(test, key, value)
        
    db.commit()
    db.refresh(test)
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Test ma'lumotlari yangilandi.",
        malumot=TestJavob.model_validate(test).model_dump(),
    )


# =============================================================================
# NATIJALAR ENDPOINT'LARI (/api/v1/natijalar)
# =============================================================================

@app.post(
    "/api/v1/natijalar",
    tags=["Natijalar"],
    summary="Test topshirish va natijani hisoblash",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def test_topshirish(
    malumot: NatijaYaratish,
    db: Session = Depends(get_db),
):
    """
    Foydalanuvchi test javoblarini qabul qiladi, ball hisoblaydi va natijani saqlaydi.
    
    Jarayon:
      1. Foydalanuvchi va test mavjudligini tekshirish
      2. Foydalanuvchi javoblarini to'g'ri javoblar bilan solishtirish
      3. Ball va baho hisoblash
      4. Natijani bazaga saqlash
      5. Batafsil natijani qaytarish
    
    So'rov tanasi:
      - student_id: UUID
      - test_id: UUID
      - foydalanuvchi_javoblari: {"0": "A", "1": "B", "2": "C", "3": "D", "4": "A"}
    """
    logger.info(
        f"Test topshirilmoqda: Foydalanuvchi={malumot.student_id}, "
        f"Test={malumot.test_id}"
    )

    # 1. Foydalanuvchini tekshirish
    foydalanuvchi = (
        db.query(models.Foydalanuvchi)
        .filter(models.Foydalanuvchi.id == malumot.student_id)
        .first()
    )
    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "FOYDALANUVCHI_TOPILMADI",
                "xabar": "Berilgan ID bo'lgan foydalanuvchi topilmadi.",
            },
        )

    # 2. Testni tekshirish
    test = db.query(models.Test).filter(models.Test.id == malumot.test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "TEST_TOPILMADI",
                "xabar": "Berilgan ID bo'lgan test topilmadi.",
            },
        )

    # 3. Natijani hisoblash
    # ai_service.py'dan hisoblash funksiyasini chaqirish
    hisoblash_natijasi = testni_tekshirish_va_ball_hisoblash(
        savollar=test.savollar,
        foydalanuvchi_javoblari=malumot.foydalanuvchi_javoblari,
    )

    # 4. Natijani bazaga saqlash
    yangi_natija = models.Natija(
        student_id=malumot.student_id,
        test_id=malumot.test_id,
        foydalanuvchi_javoblari=malumot.foydalanuvchi_javoblari,
        togri_javoblar_soni=hisoblash_natijasi["togri_javoblar_soni"],
        ball_foizi=hisoblash_natijasi["ball_foizi"],
        baho=hisoblash_natijasi["baho"],
    )

    try:
        db.add(yangi_natija)
        db.commit()
        db.refresh(yangi_natija)
        logger.info(
            f"Natija saqlandi: {foydalanuvchi.tolik_ism} — "
            f"{hisoblash_natijasi['ball_foizi']}% ({hisoblash_natijasi['baho']})"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Natijani saqlashda xato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "BAZA_XATOSI",
                "xabar": "Natijani saqlashda xato yuz berdi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=(
            f"Test muvaffaqiyatli topshirildi! "
            f"Natija: {hisoblash_natijasi['ball_foizi']}% — "
            f"Baho: {hisoblash_natijasi['baho']} ({hisoblash_natijasi['baho_tavsif']})"
        ),
        malumot={
            "natija_id": str(yangi_natija.id),
            "togri_javoblar_soni": hisoblash_natijasi["togri_javoblar_soni"],
            "jami_savollar": hisoblash_natijasi["jami_savollar"],
            "ball_foizi": hisoblash_natijasi["ball_foizi"],
            "baho": hisoblash_natijasi["baho"],
            "baho_tavsif": hisoblash_natijasi["baho_tavsif"],
            "batafsil": hisoblash_natijasi["batafsil"],  # Har bir savol bo'yicha natija
        },
    )


@app.get(
    "/api/v1/foydalanuvchilar/{foydalanuvchi_id}/natijalar",
    tags=["Natijalar"],
    summary="Foydalanuvchining barcha test natijalarini olish",
    response_model=UmumiyJavob,
)
async def foydalanuvchi_natijalari(
    foydalanuvchi_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Berilgan foydalanuvchining barcha test topshirish tarixini qaytaradi.
    Eng yangi natija birinchi ko'rsatiladi.
    """
    # Foydalanuvchini tekshirish
    foydalanuvchi = (
        db.query(models.Foydalanuvchi)
        .filter(models.Foydalanuvchi.id == foydalanuvchi_id)
        .first()
    )
    if not foydalanuvchi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "FOYDALANUVCHI_TOPILMADI",
                "xabar": "Foydalanuvchi topilmadi.",
            },
        )

    natijalar = (
        db.query(models.Natija)
        .filter(models.Natija.foydalanuvchi_id == foydalanuvchi_id)
        .order_by(models.Natija.topshirilgan_vaqt.desc())
        .all()
    )

    javob_ro_yxati = [NatijaJavob.model_validate(n).model_dump() for n in natijalar]

    # Statistikani hisoblash
    if natijalar:
        ortacha_ball = sum(n.ball_foizi for n in natijalar) / len(natijalar)
        eng_yaxshi_ball = max(n.ball_foizi for n in natijalar)
    else:
        ortacha_ball = 0.0
        eng_yaxshi_ball = 0.0

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{foydalanuvchi.tolik_ism}' ning {len(natijalar)} ta natijasi topildi.",
        malumot={
            "foydalanuvchi": foydalanuvchi.tolik_ism,
            "jami_testlar": len(natijalar),
            "ortacha_ball": round(ortacha_ball, 2),
            "eng_yaxshi_ball": eng_yaxshi_ball,
            "natijalar": javob_ro_yxati,
        },
    )


# =============================================================================
# AI XIZMATI ENDPOINT'LARI (/api/v1/ai)
# =============================================================================

@app.post(
    "/api/v1/ai/generate",
    tags=["AI Xizmati"],
    summary="Gemini AI orqali to'liq ta'lim kontenti generatsiya qilish",
    response_model=UmumiyJavob,
    status_code=status.HTTP_200_OK,
)
async def ai_generatsiya(
    sorov: AIGeneratsiyaSorovi,
    saqlash: bool = False,   # Natijani bazaga saqlash kerakmi?
    db: Session = Depends(get_db),
):
    """
    Bu endpoint butun sistemaning "miyasi" — Gemini 1.5 Flash AI modeli yordamida
    berilgan mavzu bo'yicha to'liq ta'lim paketi generatsiya qiladi:
    
    ✅ **5 ta MCQ savol** — har biri 4 ta variant va to'g'ri javob bilan
    ✅ **Strukturalangan dars rejasi** — kirish, asosiy qism, xulosa
    ✅ **Uy vazifasi** — aniq ko'rsatmalar bilan
    ✅ **Baholash mezonlari** — A, B, C, D, F baholash tizimi
    
    **Muhim:**
    - Barcha kontent O'ZBEK tilida generatsiya qilinadi
    - Gemini FAQAT valid JSON qaytarishga majburlanadi
    - Xato bo'lsa 3 marta qayta uriniladi
    - `saqlash=true` parametri bilan kontent bazaga saqlanadi
    
    **So'rov tanasi:**
    ```json
    {
        "mavzu": "Pythonda ro'yxatlar va ularning metodlari",
        "kurs_id": null
    }
    ```
    
    **Misollar:**
    - `mavzu`: "Matematikada integral hisobi"
    - `mavzu`: "Ingliz tilida Present Perfect zamoni"
    - `mavzu`: "Biologiyada fotosintez jarayoni"
    """
    logger.info(
        f"AI generatsiya so'rovi qabul qilindi. "
        f"Mavzu: '{sorov.mavzu}', Saqlash: {saqlash}"
    )

    # Gemini AI'dan kontent olish
    # Bu asinxron funksiya — event loop'ni blokllamaydi
    try:
        ai_natijasi = await ai_kontent_generatsiya(mavzu=sorov.mavzu)
    except ValueError as val_xato:
        # Xavfsizlik filtri yoki kirish xatosi
        logger.warning(f"AI generatsiyada kirish xatosi: {val_xato}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "AI_KIRISH_XATOSI",
                "xabar": str(val_xato),
                "tafsilot": "Mavzuni o'zgartirib qayta urinib ko'ring.",
            },
        )
    except RuntimeError as runtime_xato:
        # Qayta urinishdan keyin ham muvaffaqiyatsiz
        logger.error(f"AI generatsiyada runtime xato: {runtime_xato}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "AI_XIZMAT_XATOSI",
                "xabar": "AI xizmati hozirda mavjud emas. Keyinroq urinib ko'ring.",
                "tafsilot": str(runtime_xato),
            },
        )
    except Exception as kutilmagan_xato:
        # Kutilmagan xato
        logger.critical(f"AI generatsiyada kutilmagan xato: {kutilmagan_xato}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "ICHKI_SERVER_XATOSI",
                "xabar": "Server ichida xato yuz berdi.",
                "tafsilot": str(kutilmagan_xato),
            },
        )

    # Agar `saqlash=true` bo'lsa — dars va testni bazaga saqlash
    saqlangan_ma_lumotlar = {}
    if saqlash:
        logger.info("AI natijasi bazaga saqlanmoqda...")
        try:
            # Kursni aniqlash yoki yangi yaratish
            kurs_id = sorov.kurs_id

            # Darsni bazaga saqlash
            yangi_dars = models.Dars(
                kurs_id=kurs_id,
                sarlavha=ai_natijasi.get("dars_rejasi", {}).get(
                    "sarlavha", f"Dars: {sorov.mavzu}"
                ),
                mazmun=ai_natijasi.get("dars_rejasi", {}).get("kirish", ""),
                dars_rejasi=ai_natijasi.get("dars_rejasi"),
                uy_vazifasi=ai_natijasi.get("uy_vazifasi"),
                baholash_mezoni=str(ai_natijasi.get("baholash_mezoni", "")),
                ai_mavzu=sorov.mavzu,
            )
            db.add(yangi_dars)

            # Testni bazaga saqlash (5 ta MCQ savol bilan)
            yangi_test = models.Test(
                nomi=f"Test: {sorov.mavzu}",
                mavzu=sorov.mavzu,
                kurs_id=kurs_id,
                savollar=ai_natijasi.get("savollar"),
                yaratuvchi="gemini-ai",
            )
            db.add(yangi_test)

            db.commit()
            db.refresh(yangi_dars)
            db.refresh(yangi_test)

            saqlangan_ma_lumotlar = {
                "dars_id": str(yangi_dars.id),
                "test_id": str(yangi_test.id),
                "xabar": "Dars va test bazaga muvaffaqiyatli saqlandi.",
            }
            logger.info(
                f"AI natijasi saqlandi: Dars ID={yangi_dars.id}, Test ID={yangi_test.id}"
            )

        except Exception as saqla_xato:
            db.rollback()
            logger.error(f"AI natijasini saqlashda xato: {saqla_xato}")
            # Saqlash muvaffaqiyatsiz bo'lsa ham AI natijasini qaytaramiz
            saqlangan_ma_lumotlar = {
                "xato": "Saqlashda xato yuz berdi, lekin kontent generatsiya qilindi.",
                "tafsilot": str(saqla_xato),
            }

    # Muvaffaqiyatli javob qaytarish
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=(
            f"'{sorov.mavzu}' mavzusi bo'yicha ta'lim kontenti muvaffaqiyatli generatsiya qilindi! "
            f"5 ta MCQ savol, dars rejasi, uy vazifasi va baholash mezonlari tayyor."
        ),
        malumot={
            "generatsiya_qilingan_kontent": ai_natijasi,
            "saqlash_natijasi": saqlangan_ma_lumotlar if saqlash else None,
        },
    )


@app.post(
    "/api/v1/ai/test-generatsiya",
    tags=["AI Xizmati"],
    summary="Faqat 5 ta MCQ test generatsiya qilib, bazaga saqlash",
    response_model=UmumiyJavob,
    status_code=status.HTTP_201_CREATED,
)
async def ai_test_generatsiya_va_saqlash(
    sorov: AIGeneratsiyaSorovi,
    db: Session = Depends(get_db),
):
    """
    Berilgan mavzu bo'yicha AI yordamida 5 ta MCQ savol generatsiya qiladi
    va ularni bazaga test sifatida avtomatik saqlaydi.
    
    Bu endpoint `/api/v1/ai/generate` endpoint'idan farqli ravishda
    faqat testni generatsiya qiladi va darhol bazaga saqlaydi.
    Telegram Bot va Desktop App uchun qulay!
    """
    # AI'dan to'liq kontent olish
    try:
        ai_natijasi = await ai_kontent_generatsiya(mavzu=sorov.mavzu)
    except (ValueError, RuntimeError) as xato:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "AI_XIZMAT_XATOSI",
                "xabar": f"AI test generatsiya qila olmadi: {str(xato)}",
            },
        )

    # Testni bazaga saqlash
    yangi_test = models.Test(
        nomi=f"AI Test: {sorov.mavzu}",
        mavzu=sorov.mavzu,
        kurs_id=sorov.kurs_id,
        savollar=ai_natijasi.get("savollar"),
        yaratuvchi="gemini-ai",
        umumiy_ball=100,
    )

    try:
        db.add(yangi_test)
        db.commit()
        db.refresh(yangi_test)
        logger.info(f"AI testi yaratildi va saqlandi: ID={yangi_test.id}, Mavzu='{sorov.mavzu}'")
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "muvaffaqiyat": False,
                "xato_kodi": "BAZA_XATOSI",
                "xabar": "Testni bazaga saqlashda xato yuz berdi.",
            },
        )

    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{sorov.mavzu}' mavzusi bo'yicha 5 ta savoldan iborat test yaratildi va saqlandi!",
        malumot={
            "test_id": str(yangi_test.id),
            "mavzu": sorov.mavzu,
            "savollar_soni": len(ai_natijasi.get("savollar", [])),
            "savollar": ai_natijasi.get("savollar"),
        },
    )


# =============================================================================
# XATO ISHLOVCHILARI (Global Exception Handlers)
# =============================================================================

@app.exception_handler(404)
async def topilmadi_xatosi(so_rov, exc):
    """
    404 xato — manzil topilmadi.
    FastAPI'ning standart xato javobini o'zbekchalashtiradi.
    """
    return JSONResponse(
        status_code=404,
        content={
            "muvaffaqiyat": False,
            "xato_kodi": "MANZIL_TOPILMADI",
            "xabar": "So'ralgan manzil (URL) topilmadi. API hujjatini /docs da ko'ring.",
        },
    )


@app.exception_handler(405)
async def metod_ruxsat_etilmagan(so_rov, exc):
    """
    405 xato — HTTP metodi ruxsat etilmagan.
    Masalan, GET kerak joyda POST yuborsa.
    """
    return JSONResponse(
        status_code=405,
        content={
            "muvaffaqiyat": False,
            "xato_kodi": "METOD_RUXSAT_ETILMAGAN",
            "xabar": "Bu manzil uchun bunday HTTP metodi ruxsat etilmagan.",
        },
    )


@app.exception_handler(500)
async def ichki_server_xatosi(so_rov, exc):
    """
    500 xato — ichki server xatosi.
    Foydalanuvchiga texnik tafsilotlarni ko'rsatmasdan xabar beradi.
    """
    logger.critical(f"500 ichki server xatosi: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "muvaffaqiyat": False,
            "xato_kodi": "ICHKI_SERVER_XATOSI",
            "xabar": "Server ichida xato yuz berdi. Iltimos, keyinroq urinib ko'ring.",
        },
    )


# =============================================================================
# VERCEL UCHUN HANDLER (MUHIM!)
# =============================================================================
# Vercel serverless funksiyalarda FastAPI ilovasi "app" nomli
# o'zgaruvchi sifatida eksport qilinishi kerak.
# vercel.json'da bu quyidagicha ko'rsatiladi:
#   "builds": [{"src": "main.py", "use": "@vercel/python"}]
#   "routes": [{"src": "/(.*)", "dest": "main.py"}]
#
# Vercel avtomatik ravishda "app" o'zgaruvchisini ASGI ilovasi sifatida
# aniqlaydi va HTTP so'rovlarni unga yo'naltiradi.
#
# Mahalliy test uchun:
#   uvicorn main:app --reload --port 8000
# Yoki:
#   python -m uvicorn main:app --reload

# "app" o'zgaruvchisi yuqorida allaqachon yaratilgan.
# Bu faylni to'g'ridan-to'g'ri ishga tushirish uchun (ixtiyoriy):
if __name__ == "__main__":
    import uvicorn
    # Mahalliy ishlab chiqish serveri
    # Ishlab chiqarishda Vercel bu qismni ishlatmaydi
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,        # Kod o'zgarganda avtomatik qayta yuklash
        log_level="info",
        access_log=True,    # Har bir so'rovni loglash
    )
