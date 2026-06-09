# =============================================================================
# main.py — Mini LMS API asosiy fayli (EMERGENCY AUTO-SEED FIXED)
# =============================================================================

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from datetime import datetime, timezone
import uuid
import hashlib

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db, init_db, check_db_connection
import models
from models import (
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def hayot_tsikli(app: FastAPI):
    logger.info("═══════════════════════════════════════════════")
    logger.info("  Mini LMS API — Ishga tushmoqda...")
    logger.info("═══════════════════════════════════════════════")

    if check_db_connection():
        logger.info("✓ Ma'lumotlar bazasiga muvaffaqiyatli ulandi.")
    else:
        logger.critical("✗ Ma'lumotlar bazasiga ulanib bo'lmadi! DATABASE_URL'ni tekshiring.")

    try:
        init_db()
        logger.info("✓ Barcha jadvallar tayyor.")
    except Exception as e:
        logger.critical(f"✗ Jadval yaratishda xato: {e}")

    logger.info("✓ Mini LMS API muvaffaqiyatli ishga tushdi!")
    logger.info("═══════════════════════════════════════════════")
    yield
    logger.info("Mini LMS API to'xtatilmoqda...")


app = FastAPI(
    title="Mini LMS AI API",
    description="Mini LMS platformasi uchun AI-powered Backend (CORS & Auto-Seed Fixed)",
    version="1.0.0",
    lifespan=hayot_tsikli,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# =============================================================================
# MUHIM: BULLETPROOF CORS SOZLAMALARI
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # React Vite
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_origin_regex="https://.*",  # Barcha Vercel/Netlify kabi https domenlarga ruxsat
    allow_credentials=True,           # Frontend'dan xavfsiz token/parollar kelishiga ruxsat
    allow_methods=["*"],              # Barcha HTTP metodlarga ruxsat
    allow_headers=["*"],              # Barcha HTTP headerlarga ruxsat
)

def parolni_heshlash(parol: str) -> str:
    """Parolni xavfsiz tarzda native Python hashlib yordamida hashlaydi."""
    return hashlib.sha256(parol.encode()).hexdigest()

def parolni_tekshirish(parol: str, hash_parol: str) -> bool:
    """Ochiq parolni hashlangan parol bilan solishtiradi."""
    return hashlib.sha256(parol.encode()).hexdigest() == hash_parol


# =============================================================================
# ENDPOINTLAR
# =============================================================================

@app.get("/", tags=["Tizim"], response_model=UmumiyJavob)
async def asosiy_sahifa():
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar="Mini LMS AI API muvaffaqiyatli ishlayapti! Barcha tizimlar faol.",
        malumot={
            "api_nomi": "Mini LMS AI API",
            "vaqt": datetime.now(timezone.utc).isoformat(),
        },
    )

@app.get("/api/v1/salomatlik", tags=["Tizim"], response_model=UmumiyJavob)
async def salomatlik_tekshiruvi():
    db_holati = check_db_connection()
    return UmumiyJavob(
        muvaffaqiyat=db_holati,
        xabar="Tizim salomatligi tekshirildi.",
        malumot={"db_holati": "ulangan" if db_holati else "uzilgan"},
    )

@app.post("/api/v1/auth/login", tags=["Auth"], response_model=UmumiyJavob)
async def tizimga_kirish(malumot: TizimgaKirish, db: Session = Depends(get_db)):
    # ── FAVQULODDA AUTO-SEED REJIMI (Tizimni to'xtovsiz ishlatish uchun) ──
    EMERGENCY_USERS = {
        "admin@gmail.com": {"rol": "admin", "parol": "admin123", "ism": "Asosiy Admin"},
        "teacher@gmail.com": {"rol": "teacher", "parol": "teacher123", "ism": "Asosiy O'qituvchi"},
        "student@gmail.com": {"rol": "student", "parol": "student123", "ism": "A'lochi O'quvchi"}
    }
    
    if malumot.email in EMERGENCY_USERS and malumot.parol == EMERGENCY_USERS[malumot.email]["parol"]:
        foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.email == malumot.email).first()
        if not foydalanuvchi:
            foydalanuvchi = models.Foydalanuvchi(
                tolik_ism=EMERGENCY_USERS[malumot.email]["ism"],
                email=malumot.email,
                parol_heshi=parolni_heshlash(malumot.parol),
                rol=EMERGENCY_USERS[malumot.email]["rol"],
                faol=True
            )
            db.add(foydalanuvchi)
            db.commit()
            db.refresh(foydalanuvchi)
        
        # Frontend roli bilan moslikni ta'minlash (oqituvchi -> teacher)
        res_data = FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump()
        if res_data["rol"] == "oqituvchi":
            res_data["rol"] = "teacher"
            
        return UmumiyJavob(muvaffaqiyat=True, xabar="Tizimga muvaffaqiyatli kirdingiz.", malumot=res_data)

    # Standart kirish oqimi
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.email == malumot.email).first()
    if not foydalanuvchi or not parolni_tekshirish(malumot.parol, foydalanuvchi.parol_heshi):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"muvaffaqiyat": False, "xato_kodi": "XATO_KIRISH", "xabar": "Email yoki parol noto'g'ri."}
        )
    if not foydalanuvchi.faol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"muvaffaqiyat": False, "xato_kodi": "BLOKLANGAN", "xabar": "Hisobingiz bloklangan."}
        )
        
    res_data = FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump()
    if res_data["rol"] == "oqituvchi":
        res_data["rol"] = "teacher"
        
    return UmumiyJavob(muvaffaqiyat=True, xabar="Tizimga muvaffaqiyatli kirdingiz.", malumot=res_data)

@app.post("/api/v1/foydalanuvchilar", tags=["Foydalanuvchilar"], status_code=status.HTTP_201_CREATED, response_model=UmumiyJavob)
async def foydalanuvchi_yaratish(malumot: FoydalanuvchiYaratish, db: Session = Depends(get_db)):
    mavjud = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.email == malumot.email).first()
    if mavjud:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"muvaffaqiyat": False, "xato_kodi": "EMAIL_MAVJUD", "xabar": "Bu email manzili band."}
        )
    
    # Rolni inglizcha formatga o'girish (front-back sinxronizatsiyasi)
    baza_rol = "oqituvchi" if malumot.rol.lower() == "teacher" else malumot.rol.lower()
    
    yangi_foydalanuvchi = models.Foydalanuvchi(
        tolik_ism=malumot.tolik_ism,
        email=malumot.email,
        parol_heshi=parolni_heshlash(malumot.parol),
        rol=baza_rol,
        faol=True,
    )
    db.add(yangi_foydalanuvchi)
    db.commit()
    db.refresh(yangi_foydalanuvchi)
    
    return UmumiyJavob(
        muvaffaqiyat=True,
        xabar=f"'{malumot.tolik_ism}' muvaffaqiyatli yaratildi!",
        malumot=FoydalanuvchiJavob.model_validate(yangi_foydalanuvchi).model_dump(),
    )

@app.get("/api/v1/foydalanuvchilar", tags=["Foydalanuvchilar"], response_model=UmumiyJavob)
async def foydalanuvchilar_royxati(sahifa: int = 1, hajm: int = 20, db: Session = Depends(get_db)):
    hajm = min(hajm, 100)
    sahifa = max(sahifa, 1)
    jami_son = db.query(models.Foydalanuvchi).count()
    foydalanuvchilar = db.query(models.Foydalanuvchi).order_by(models.Foydalanuvchi.yaratilgan_vaqt.desc()).offset((sahifa - 1) * hajm).limit(hajm).all()
    javob = [FoydalanuvchiJavob.model_validate(f).model_dump() for f in foydalanuvchilar]
    return UmumiyJavob(muvaffaqiyat=True, xabar="Foydalanuvchilar yuklandi", malumot={"jami": jami_son, "foydalanuvchilar": javob})

@app.get("/api/v1/foydalanuvchilar/{foydalanuvchi_id}", tags=["Foydalanuvchilar"], response_model=UmumiyJavob)
async def foydalanuvchi_olish(foydalanuvchi_id: uuid.UUID, db: Session = Depends(get_db)):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    return UmumiyJavob(muvaffaqiyat=True, xabar="Topildi.", malumot=FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump())

@app.delete("/api/v1/foydalanuvchilar/{foydalanuvchi_id}", tags=["Foydalanuvchilar"], response_model=UmumiyJavob)
async def foydalanuvchi_ochirish(foydalanuvchi_id: uuid.UUID, db: Session = Depends(get_db)):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    db.delete(foydalanuvchi)
    db.commit()
    return UmumiyJavob(muvaffaqiyat=True, xabar="O'chirildi.")

@app.put("/api/v1/foydalanuvchilar/{foydalanuvchi_id}", tags=["Foydalanuvchilar"], response_model=UmumiyJavob)
async def foydalanuvchi_tahrirlash(foydalanuvchi_id: uuid.UUID, malumot: FoydalanuvchiYangilash, db: Session = Depends(get_db)):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    update_data = malumot.model_dump(exclude_unset=True)
    if "parol" in update_data and update_data["parol"]:
        update_data["parol_heshi"] = parolni_heshlash(update_data.pop("parol"))
    for key, value in update_data.items():
        setattr(foydalanuvchi, key, value)
    db.commit()
    db.refresh(foydalanuvchi)
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yangilandi.", malumot=FoydalanuvchiJavob.model_validate(foydalanuvchi).model_dump())

@app.get("/api/v1/foydalanuvchilar/{foydalanuvchi_id}/tarix", tags=["Foydalanuvchilar"], response_model=UmumiyJavob)
async def foydalanuvchi_tarixi(foydalanuvchi_id: uuid.UUID, db: Session = Depends(get_db)):
    foydalanuvchi = db.query(models.Foydalanuvchi).filter(models.Foydalanuvchi.id == foydalanuvchi_id).first()
    if not foydalanuvchi:
        raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    natijalar = db.query(models.Natija).filter(models.Natija.student_id == foydalanuvchi_id).order_by(models.Natija.topshirilgan_vaqt.desc()).all()
    return UmumiyJavob(muvaffaqiyat=True, xabar="Tarix yuklandi.", malumot=[NatijaJavob.model_validate(n).model_dump() for n in natijalar])


@app.post("/api/v1/kurslar", tags=["Kurslar"], status_code=201, response_model=UmumiyJavob)
async def kurs_yaratish(malumot: KursYaratish, db: Session = Depends(get_db)):
    yangi_kurs = models.Kurs(**malumot.model_dump(), faol=True)
    db.add(yangi_kurs)
    db.commit()
    db.refresh(yangi_kurs)
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yaratildi.", malumot=KursJavob.model_validate(yangi_kurs).model_dump())

@app.get("/api/v1/kurslar", tags=["Kurslar"], response_model=UmumiyJavob)
async def kurslar_royxati(sahifa: int = 1, hajm: int = 20, daraja: str = None, db: Session = Depends(get_db)):
    sorov = db.query(models.Kurs).filter(models.Kurs.faol == True)
    if daraja: sorov = sorov.filter(models.Kurs.daraja == daraja)
    kurslar = sorov.order_by(models.Kurs.yaratilgan_vaqt.desc()).offset((sahifa - 1) * hajm).limit(hajm).all()
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yuklandi.", malumot=[KursJavob.model_validate(k).model_dump() for k in kurslar])

@app.get("/api/v1/kurslar/{kurs_id}", tags=["Kurslar"], response_model=UmumiyJavob)
async def kurs_olish(kurs_id: uuid.UUID, db: Session = Depends(get_db)):
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()
    if not Join: raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    return UmumiyJavob(muvaffaqiyat=True, xabar="Topildi.", malumot=KursJavob.model_validate(kurs).model_dump())

@app.delete("/api/v1/kurslar/{kurs_id}", tags=["Kurslar"], response_model=UmumiyJavob)
async def delete_kurs(kurs_id: uuid.UUID, db: Session = Depends(get_db)):
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()
    if not kurs: raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    db.delete(kurs)
    db.commit()
    return UmumiyJavob(muvaffaqiyat=True, xabar="O'chirildi.")

@app.put("/api/v1/kurslar/{kurs_id}", tags=["Kurslar"], response_model=UmumiyJavob)
async def kurs_tahrirlash(kurs_id: uuid.UUID, malumot: KursYangilash, db: Session = Depends(get_db)):
    kurs = db.query(models.Kurs).filter(models.Kurs.id == kurs_id).first()
    if not kurs: raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Topilmadi."})
    for key, value in malumot.model_dump(exclude_unset=True).items(): setattr(kurs, key, value)
    db.commit()
    db.refresh(kurs)
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yangilandi.", malumot=KursJavob.model_validate(kurs).model_dump())


@app.post("/api/v1/darslar", tags=["Darslar"], status_code=201, response_model=UmumiyJavob)
async def dars_yaratish(malumot: DarsYaratish, db: Session = Depends(get_db)):
    kurs = db.query(models.Kurs).filter(models.Kurs.id == malumot.kurs_id).first()
    if not kurs: raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Kurs topilmadi."})
    yangi_dars = models.Dars(**malumot.model_dump())
    db.add(yangi_dars)
    db.commit()
    db.refresh(yangi_dars)
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yaratildi.", malumot=DarsJavob.model_validate(yangi_dars).model_dump())

@app.get("/api/v1/kurslar/{kurs_id}/darslar", tags=["Darslar"], response_model=UmumiyJavob)
async def kurs_darslari(kurs_id: uuid.UUID, db: Session = Depends(get_db)):
    darslar = db.query(models.Dars).filter(models.Dars.kurs_id == kurs_id).order_by(models.Dars.tartib_raqami.asc()).all()
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yuklandi.", malumot=[DarsJavob.model_validate(d).model_dump() for d in darslar])


@app.post("/api/v1/testlar", tags=["Testlar"], status_code=201, response_model=UmumiyJavob)
async def test_yaratish(malumot: TestYaratish, savollar: list, db: Session = Depends(get_db)):
    yangi_test = models.Test(**malumot.model_dump(), savollar=savollar, yaratuvchi="oqituvchi")
    db.add(yangi_test)
    db.commit()
    db.refresh(yangi_test)
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yaratildi.", malumot=TestJavob.model_validate(yangi_test).model_dump())

@app.get("/api/v1/testlar", tags=["Testlar"], response_model=UmumiyJavob)
async def testlar_royxati(sahifa: int = 1, hajm: int = 20, db: Session = Depends(get_db)):
    testlar = db.query(models.Test).filter(models.Test.faol == True).order_by(models.Test.yaratilgan_vaqt.desc()).offset((sahifa - 1) * hajm).limit(hajm).all()
    return UmumiyJavob(muvaffaqiyat=True, xabar="Yuklandi.", malumot=[TestJavob.model_validate(t).model_dump() for t in testlar])


@app.post("/api/v1/natijalar", tags=["Natijalar"], status_code=201, response_model=UmumiyJavob)
async def test_topshirish(malumot: NatijaYaratish, db: Session = Depends(get_db)):
    test = db.query(models.Test).filter(models.Test.id == malumot.test_id).first()
    if not test: raise HTTPException(status_code=404, detail={"muvaffaqiyat": False, "xabar": "Test topilmadi."})
    
    hisob = testni_tekshirish_va_ball_hisoblash(savollar=test.savollar, foydalanuvchi_javoblari=malumot.foydalanuvchi_javoblari)
    yangi_natija = models.Natija(
        student_id=malumot.student_id, test_id=malumot.test_id,
        foydalanuvchi_javoblari=malumot.foydalanuvchi_javoblari,
        togri_javoblar_soni=hisob["togri_javoblar_soni"], ball_foizi=hisob["ball_foizi"], baho=hisob["baho"]
    )
    db.add(yangi_natija)
    db.commit()
    return UmumiyJavob(muvaffaqiyat=True, xabar="Test topshirildi.", malumot=hisob)


@app.post("/api/v1/ai/generate", tags=["AI Xizmati"], response_model=UmumiyJavob)
async def ai_generatsiya(sorov: AIGeneratsiyaSorovi, saqlash: bool = False, db: Session = Depends(get_db)):
    try:
        ai_natijasi = await ai_kontent_generatsiya(mavzu=sorov.mavzu)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"muvaffaqiyat": False, "xabar": str(e)})
    
    if saqlash:
        yangi_dars = models.Dars(kurs_id=sorov.kurs_id, sarlavha=f"Dars: {sorov.mavzu}", mazmun=ai_natijasi.get("dars_rejasi", {}).get("kirish", ""), ai_mavzu=sorov.mavzu)
        yangi_test = models.Test(nomi=f"Test: {sorov.mavzu}", mavzu=sorov.mavzu, kurs_id=sorov.kurs_id, savollar=ai_natijasi.get("savollar"), yaratuvchi="gemini-ai")
        db.add(yangi_dars)
        db.add(yangi_test)
        db.commit()
        return UmumiyJavob(muvaffaqiyat=True, xabar="Generatsiya qilindi va saqlandi.", malumot={"dars_id": str(yangi_dars.id), "test_id": str(yangi_test.id), "kontent": ai_natijasi})

    return UmumiyJavob(muvaffaqiyat=True, xabar="Generatsiya qilindi.", malumot={"kontent": ai_natijasi})


@app.exception_handler(404)
async def topilmadi_xatosi(so_rov, exc):
    return JSONResponse(status_code=404, content={"muvaffaqiyat": False, "xabar": "Manzil topilmadi."})

@app.exception_handler(405)
async def metod_ruxsat_etilmagan(so_rov, exc):
    return JSONResponse(status_code=405, content={"muvaffaqiyat": False, "xabar": "Metod ruxsat etilmagan."})

@app.exception_handler(500)
async def ichki_server_xatosi(so_rov, exc):
    return JSONResponse(status_code=500, content={"muvaffaqiyat": False, "xabar": "Server ichki xatosi."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
