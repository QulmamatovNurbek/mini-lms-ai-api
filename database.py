# =============================================================================
# database.py — Ma'lumotlar Bazasi Konfiguratsiyasi (PostgreSQL / Supabase)
# =============================================================================
# Bu fayl SQLAlchemy orqali Supabase PostgreSQL bazasiga ulanishni sozlaydi.
# Vercel serverless muhitida SQLite ishlamaydi, chunki har bir serverless
# funksiya chaqiruvi yangi, izolyatsiyalangan konteynerda ishlaydi va
# diskka yozilgan ma'lumotlar saqlanmaydi. Shuning uchun biz
# tashqi (remote) PostgreSQL bazasidan foydalanamiz.
# =============================================================================

import os                          # Muhit o'zgaruvchilarini o'qish uchun
from sqlalchemy import create_engine, text  # SQLAlchemy dvigatel va SQL so'rovlari uchun
from sqlalchemy.ext.declarative import declarative_base  # Model bazaviy klassini yaratish uchun
from sqlalchemy.orm import sessionmaker   # Sessiya fabrikasi uchun
from dotenv import load_dotenv     # .env fayldan o'zgaruvchilarni yuklash uchun
import logging                     # Loglash uchun

# ---------------------------------------------------------------------------
# Loglashni sozlash
# ---------------------------------------------------------------------------
# Barcha xatolar va ma'lumotlar konsolda ko'rinishi uchun loglashni yoqamiz.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# .env fayldan muhit o'zgaruvchilarini yuklash
# ---------------------------------------------------------------------------
# Mahalliy ishlab chiqishda .env faylidagi DATABASE_URL o'qiladi.
# Vercel'da esa muhit o'zgaruvchilari dashboard orqali sozlanadi.
load_dotenv()

# ---------------------------------------------------------------------------
# Ma'lumotlar bazasi URL manzilini olish
# ---------------------------------------------------------------------------
# DATABASE_URL Supabase PostgreSQL ulanish qatorini o'z ichiga oladi.
# Misol: postgresql://user:password@host:5432/dbname
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    # Agar DATABASE_URL bo'sh bo'lsa, dastur ishlamaydi —
    # bu ataylab qilingan xavfsizlik chorasi.
    logger.critical(
        "KRITIK XATO: DATABASE_URL muhit o'zgaruvchisi topilmadi! "
        "Iltimos, .env yoki Vercel dashboard'da sozlang."
    )
    raise EnvironmentError(
        "DATABASE_URL muhit o'zgaruvchisi sozlanmagan. "
        "Supabase PostgreSQL URL'ini kiriting."
    )

# ---------------------------------------------------------------------------
# SQLAlchemy Dvigatelini Yaratish (Engine)
# ---------------------------------------------------------------------------
# create_engine() — SQLAlchemy'ning asosiy komponentlaridan biri.
# Ushbu dvigatel orqali barcha SQL so'rovlar bazaga yuboriladi.
#
# Parametrlar:
#   pool_pre_ping=True   — Har bir ulanish ishlatilishidan oldin
#                          "PING" so'rovi yuboriladi. Ulanish uzilgan bo'lsa,
#                          avtomatik qayta ulanish amalga oshiriladi.
#   pool_size=5          — Connection pool'da saqlanadigan ulanishlar soni.
#   max_overflow=10      — Pool to'lganda qo'shimcha yaratilishi mumkin
#                          bo'lgan ulanishlar soni.
#   pool_timeout=30      — Ulanish olish uchun kutish vaqti (soniyada).
#   pool_recycle=1800    — 30 daqiqadan eski ulanishlar yangisiga almashtiriladi.
#                          Bu PostgreSQL'ning "idle timeout" muammosini hal qiladi.
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,    # Ulanishni tekshirish — serverless muhit uchun muhim
        pool_size=5,           # Bir vaqtning o'zida 5 ta ulanish
        max_overflow=10,       # Qo'shimcha 10 ta ulanishga ruxsat
        pool_timeout=30,       # 30 soniyadan so'ng timeout
        pool_recycle=1800,     # 30 daqiqada bir ulanishni yangilash
        echo=False,            # SQL so'rovlarini konsolda ko'rsatmaslik (ishlab chiqishda True)
    )
    logger.info("SQLAlchemy dvigatel muvaffaqiyatli yaratildi.")
except Exception as e:
    logger.critical(f"SQLAlchemy dvigatel yaratishda xato: {e}")
    raise

# ---------------------------------------------------------------------------
# Sessiya Fabrikasini Yaratish (Session Factory)
# ---------------------------------------------------------------------------
# SessionLocal — har bir HTTP so'rovda yangi ma'lumotlar bazasi sessiyasini
# yaratish uchun ishlatiladigan fabrika.
#
# autocommit=False — Har bir operatsiyani qo'lda commit qilish talab etiladi.
#                    Bu tranzaksiya xavfsizligini ta'minlaydi.
# autoflush=False  — SQLAlchemy ob'ektlarni avtomatik flush qilmaydi,
#                    bu bizga ko'proq nazorat beradi.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
logger.info("SQLAlchemy sessiya fabrikasi muvaffaqiyatli sozlandi.")

# ---------------------------------------------------------------------------
# Asosiy Model Klassi (Declarative Base)
# ---------------------------------------------------------------------------
# Barcha SQLAlchemy modellari (User, Course, Lesson, va h.k.) shu
# Base klassidan meros oladi. Bu SQLAlchemy'ga jadval strukturasini
# avtomatik aniqlash imkonini beradi.
Base = declarative_base()

# ---------------------------------------------------------------------------
# Ma'lumotlar Bazasi Sessiya Generatori (Dependency Injection)
# ---------------------------------------------------------------------------
# get_db() — FastAPI'ning dependency injection tizimi orqali har bir
# endpoint funksiyasiga ma'lumotlar bazasi sessiyasini beruvchi generator.
#
# Ishlash tartibi:
#   1. Sessiya yaratiladi
#   2. So'rov bajariladi (yield orqali sessiya endpointga beriladi)
#   3. So'rov tugagandan so'ng sessiya yopiladi (finally bloki)
#
# Bu "context manager" pattern bo'lib, ulanishlar doimo to'g'ri
# yopilishini kafolatlaydi — xato bo'lsa ham.
def get_db():
    """
    Ma'lumotlar bazasi sessiyasini yaratib, so'rov davomida ishlatish uchun beradi.
    So'rov tugagandan so'ng sessiyani avtomatik yopadi.
    
    Foydalanish:
        @app.get("/misol")
        def misol_endpoint(db: Session = Depends(get_db)):
            # db orqali bazaga murojaat qilish
            pass
    """
    db = SessionLocal()  # Yangi sessiya ochish
    try:
        logger.debug("Ma'lumotlar bazasi sessiyasi ochildi.")
        yield db  # Sessiyani endpoint funksiyasiga berish
    except Exception as e:
        # Xato yuz berganda sessiyani rollback qilish
        # Bu bazadagi yarim tugallangan operatsiyalarni bekor qiladi
        logger.error(f"Sessiya davomida xato yuz berdi: {e}")
        db.rollback()
        raise
    finally:
        # Sessiyani har doim yopish — xato bo'lsa ham bo'lmasa ham
        db.close()
        logger.debug("Ma'lumotlar bazasi sessiyasi yopildi.")


# ---------------------------------------------------------------------------
# Barcha Jadvallarni Yaratish (Table Initialization)
# ---------------------------------------------------------------------------
# Bu funksiya dastur ishga tushganda barcha SQLAlchemy modellariga
# mos jadvallarni PostgreSQL bazasida yaratadi (agar mavjud bo'lmasa).
def init_db() -> None:
    """
    Barcha ma'lumotlar bazasi jadvallarini yaratadi.
    Bu funksiya faqat bir marta — ilova ishga tushganda chaqiriladi.
    Mavjud jadvallar qayta yaratilmaydi (checkfirst=True analogu).
    """
    try:
        # models.py'dan barcha modellarni import qilish kerak,
        # chunki Base ularni ro'yxatga olgan bo'lishi kerak.
        # Bu import davri muammosini oldini olish uchun shu yerda amalga oshiriladi.
        import models  # noqa: F401 — Modellarni ro'yxatga olish uchun import

        # create_all() — Base'ga bog'liq barcha jadvallarni yaratadi
        Base.metadata.create_all(bind=engine)
        logger.info("Barcha ma'lumotlar bazasi jadvallari muvaffaqiyatli yaratildi.")
    except Exception as e:
        logger.critical(f"Jadval yaratishda kritik xato: {e}")
        raise


# ---------------------------------------------------------------------------
# Ulanishni Tekshirish Funksiyasi
# ---------------------------------------------------------------------------
def check_db_connection() -> bool:
    """
    Ma'lumotlar bazasiga ulanish mavjudligini tekshiradi.
    
    Qaytaradi:
        True  — Ulanish muvaffaqiyatli
        False — Ulanish muvaffaqiyatsiz
    """
    try:
        with engine.connect() as conn:
            # Oddiy SQL so'rovi yuborib, ulanishni tekshirish
            conn.execute(text("SELECT 1"))
        logger.info("Ma'lumotlar bazasiga ulanish tekshirildi — MUVAFFAQIYATLI.")
        return True
    except Exception as e:
        logger.error(f"Ma'lumotlar bazasiga ulanishda xato: {e}")
        return False
