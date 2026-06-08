# =============================================================================
# ai_service.py — OpenRouter AI Xizmati (OpenAI SDK orqali)
# =============================================================================
# Bu fayl OpenRouter platformasi orqali "openai/gpt-oss-120b:free" modeliga
# murojaat qiladi. OpenRouter — turli AI modellarini bir xil OpenAI-mos
# API interfeysi orqali ishlatish imkonini beruvchi platforma.
#
# ISHLASH PRINSIPI:
#   Oddiy OpenAI SDK → lekin `base_url` OpenRouter manziliga o'zgartiriladi.
#   OpenRouter o'z navbatida so'rovni kerakli modelga yo'naltiradi.
#
#   Mijoz (bu fayl)
#       │
#       ▼  POST https://openrouter.ai/api/v1/chat/completions
#   OpenRouter API
#       │
#       ▼  ichki yo'naltirish
#   openai/gpt-oss-120b:free modeli
#       │
#       ▼  JSON javob
#   Bu faylga qaytadi
#
# MUHIM ARXITEKTURA QARORI:
#   `AsyncOpenAI` — to'liq asinxron mijoz.
#   Bu FastAPI asinxron endpoint'lari bilan mukammal mos keladi va
#   event loop'ni blokllamaydi. Avvalgi Gemini versiyadan farqli o'laroq,
#   `run_in_executor()` endi kerak emas — barcha so'rovlar natively async.
#
# KONTENT TILI: Barcha generatsiya qilingan kontent O'ZBEK tilida bo'ladi.
# =============================================================================

import os          # Muhit o'zgaruvchilarini o'qish uchun
import json        # JSON parse qilish va tekshirish uchun
import re          # Regex — JSON'ni xom matndan ajratib olish uchun
import asyncio     # Asinxron operatsiyalar va retry uchun
import logging     # Loglash uchun
from typing import Any, Dict  # Tip izohlar uchun
from datetime import datetime, timezone  # Vaqt-sana uchun

from openai import AsyncOpenAI  # OpenAI rasmiy async mijozi
                                 # OpenRouter bilan ishlatilganda faqat
                                 # base_url va api_key o'zgartiriladi —
                                 # qolgan barcha API bir xil.
from dotenv import load_dotenv  # .env fayldan o'zgaruvchilarni yuklash

# ---------------------------------------------------------------------------
# Muhit o'zgaruvchilari va Loglashni sozlash
# ---------------------------------------------------------------------------
load_dotenv()  # .env fayldan OPENROUTER_API_KEY va boshqalarni yuklash

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenRouter API Kalitini Olish
# ---------------------------------------------------------------------------
# .env faylidagi OPENROUTER_API_KEY o'zgaruvchisini o'qish.
# OpenRouter kalitleri odatda "sk-or-v1-..." bilan boshlanadi.
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

if not OPENROUTER_API_KEY:
    # API kaliti bo'lmasa — AI xizmati umuman ishlamaydi.
    # Dastur ishga tushganda bu xatoni darhol ko'rsatish kerak.
    logger.critical(
        "KRITIK: OPENROUTER_API_KEY muhit o'zgaruvchisi topilmadi! "
        "https://openrouter.ai/keys saytidan API kalit olib, "
        ".env faylga yoki Vercel Dashboard'ga qo'shing."
    )
    raise EnvironmentError(
        "OPENROUTER_API_KEY muhit o'zgaruvchisi sozlanmagan. "
        "OpenRouter.ai saytidan kalit oling va .env faylga qo'shing."
    )

# ---------------------------------------------------------------------------
# AsyncOpenAI Mijozini Yaratish (OpenRouter uchun)
# ---------------------------------------------------------------------------
# Bu eng muhim bosqich — standart OpenAI mijoziga ikki parametr beriladi:
#
#   1. api_key   → OpenRouter kaliti (OpenAI kaliti emas!)
#   2. base_url  → OpenRouter API manzili (OpenAI manzili emas!)
#
# Natijada SDK barcha so'rovlarni OpenAI o'rniga OpenRouter'ga yuboradi.
# OpenRouter esa kerakli modelga yo'naltiradi va javobni qaytaradi.
# Javob formati to'liq OpenAI-mos — kod o'zgarmaydi!

openrouter_mijoz = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,           # OpenRouter API kaliti
    base_url="https://openrouter.ai/api/v1",  # OpenRouter bazaviy manzil
                                              # Bu parametr standart OpenAI'dan farq qiladi!
)
logger.info(
    "OpenRouter AsyncOpenAI mijozi muvaffaqiyatli yaratildi. "
    "Model: openai/gpt-oss-120b:free"
)

# ---------------------------------------------------------------------------
# Model Nomi — O'ZGARTIRILMASIN!
# ---------------------------------------------------------------------------
# OpenRouter har bir modelni "provayder/model-nomi" formatida ifodalaydi.
# "openai/gpt-oss-120b:free" — OpenAI'ning GPT-o seriyasidan katta model.
# ":free" — bepul qatlamda ishlaydi (rate limit bor, lekin narxi yo'q).
OPENROUTER_MODELI = "openai/gpt-oss-120b:free"

# ---------------------------------------------------------------------------
# OpenRouter Sarlavhalari (HTTP Headers)
# ---------------------------------------------------------------------------
# OpenRouter qo'shimcha sarlavhalarni tavsiya qiladi:
#   HTTP-Referer  — So'rov qayerdan kelgani (OpenRouter statistikasi uchun)
#   X-Title       — Loyiha nomi (OpenRouter dashboard'da ko'rinadi)
# Bu sarlavhalar ixtiyoriy lekin yaxshi amaliyot hisoblanadi.
QOSHIMCHA_SARLAVHALAR = {
    "HTTP-Referer": "https://mini-lms.uz",
    "X-Title": "Mini LMS AI API",
}


# =============================================================================
# YORDAMCHI FUNKSIYALAR
# =============================================================================

def json_ni_ajratib_olish(matn: str) -> Dict[str, Any]:
    """
    AI javobidan valid JSON'ni topib parse qiluvchi ko'p bosqichli funksiya.

    Muammo: Ba'zan GPT modeli JSON atrofiga tushuntirish matni,
    markdown ``` bloki yoki boshqa belgilar qo'shadi. Bu funksiya
    ularni olib tashlab sof JSON'ni ajratib oladi.

    3 BOSQICHLI STRATEGIYA:
      1-bosqich → Bevosita json.loads() — eng tez yo'l
      2-bosqich → Markdown ```json...``` blokidan ajratish (regex)
      3-bosqich → Matndan birinchi { dan oxirgi } gacha kesib olish

    Parametrlar:
        matn (str): AI qaytargan xom javob matni

    Qaytaradi:
        Dict[str, Any] — Parse qilingan JSON ob'ekti

    Istisno:
        ValueError — Barcha 3 bosqich muvaffaqiyatsiz bo'lsa
    """
    # ── 1-BOSQICH: Bevosita parse ──────────────────────────────────────────
    # Model to'g'ridan-to'g'ri toza JSON qaytargan bo'lsa — bu eng yaxshi holat.
    try:
        return json.loads(matn.strip())
    except json.JSONDecodeError:
        logger.debug(
            "1-bosqich (bevosita parse) muvaffaqiyatsiz. "
            "2-bosqich (regex) boshlanmoqda..."
        )

    # ── 2-BOSQICH: Markdown kod bloki ──────────────────────────────────────
    # GPT modeli ba'zan quyidagi formatda javob beradi:
    #   ```json
    #   { "savollar": [...], ... }
    #   ```
    # Regex yordamida ``` ichidagi qismni ajratib olamiz.
    markdown_naqsh = r"```(?:json)?\s*([\s\S]*?)\s*```"
    regex_natija = re.search(markdown_naqsh, matn, re.DOTALL)
    if regex_natija:
        try:
            return json.loads(regex_natija.group(1).strip())
        except json.JSONDecodeError:
            logger.debug(
                "2-bosqich (markdown regex) muvaffaqiyatsiz. "
                "3-bosqich (qavs izlash) boshlanmoqda..."
            )

    # ── 3-BOSQICH: { } qavslari orqali JSON'ni izlash ────────────────────
    # Matnda JSON ob'ekt biror joyida yashiringan bo'lsa,
    # eng birinchi { va eng oxirgi } orasini kesib olamiz.
    birinchi_qavs = matn.find("{")
    oxirgi_qavs = matn.rfind("}")
    if birinchi_qavs != -1 and oxirgi_qavs > birinchi_qavs:
        mumkin_json = matn[birinchi_qavs: oxirgi_qavs + 1]
        try:
            return json.loads(mumkin_json)
        except json.JSONDecodeError:
            logger.warning(
                "3-bosqich (qavs izlash) ham muvaffaqiyatsiz. "
                f"Xom matn (dastlabki 300 belgi): {matn[:300]}"
            )

    # Barcha 3 bosqich muvaffaqiyatsiz — xato qaytarish
    raise ValueError(
        "AI javobi valid JSON formatida emas. "
        "Barcha 3 ta parse urinishi muvaffaqiyatsiz bo'ldi. "
        "Qayta urinib ko'ring yoki mavzuni o'zgartiring."
    )


def javobni_tekshirish(javob: Dict[str, Any]) -> bool:
    """
    AI javobining to'liq va to'g'ri strukturada ekanligini tekshiradi.

    Kutilgan JSON strukturasi (OpenRouter/GPT javobi):
    {
        "savollar": [         ← aynan 5 ta element bo'lishi shart
            {
                "savol": "...",
                "variantlar": {"A":"...", "B":"...", "C":"...", "D":"..."},
                "togri_javob": "A"|"B"|"C"|"D",
                "izoh": "..."
            },
            ...
        ],
        "dars_rejasi": { ... },   ← dict bo'lishi shart
        "uy_vazifasi": "...",      ← string bo'lishi shart
        "baholash_mezoni": { ... } ← dict bo'lishi shart
    }

    Parametrlar:
        javob (Dict): Parse qilingan JSON ob'ekti

    Qaytaradi:
        True  — Javob to'g'ri va to'liq
        False — Javob noto'g'ri yoki yetishmovchilik bor
    """
    # Majburiy yuqori darajadagi maydonlar
    majburiy = ["savollar", "dars_rejasi", "uy_vazifasi", "baholash_mezoni"]
    for maydon in majburiy:
        if maydon not in javob:
            logger.warning(f"Tekshiruv muvaffaqiyatsiz: '{maydon}' maydoni yo'q.")
            return False

    # Savollar ro'yxat bo'lishi va aynan 5 ta bo'lishi shart
    if not isinstance(javob["savollar"], list):
        logger.warning("'savollar' ro'yxat (list) bo'lishi kerak.")
        return False
    if len(javob["savollar"]) != 5:
        logger.warning(
            f"Savollar soni noto'g'ri: {len(javob['savollar'])} ta (5 ta bo'lishi kerak)."
        )
        return False

    # Har bir savol ichki strukturasini tekshirish
    savol_maydonlari = ["savol", "variantlar", "togri_javob", "izoh"]
    for i, savol in enumerate(javob["savollar"]):
        for maydon in savol_maydonlari:
            if maydon not in savol:
                logger.warning(f"{i + 1}-savol: '{maydon}' maydoni yo'q.")
                return False
        # A, B, C, D variantlarining barchasi bo'lishi kerak
        variantlar = savol.get("variantlar", {})
        if not all(k in variantlar for k in ["A", "B", "C", "D"]):
            logger.warning(f"{i + 1}-savol: A/B/C/D variantlari to'liq emas.")
            return False

    # Qolgan maydonlar turini tekshirish
    if not isinstance(javob["dars_rejasi"], dict):
        logger.warning("'dars_rejasi' dict bo'lishi kerak.")
        return False
    if not isinstance(javob["baholash_mezoni"], dict):
        logger.warning("'baholash_mezoni' dict bo'lishi kerak.")
        return False

    logger.info("Javob tekshiruvi muvaffaqiyatli o'tdi — struktura to'g'ri.")
    return True


# =============================================================================
# TIZIM VA FOYDALANUVCHI PROMPTLARI
# =============================================================================

TIZIM_PROMPTI = """\
Sen Mini LMS (Learning Management System) platformasi uchun ishlayotgan
ekspert ta'lim muharririssan. Sening YAGONA vazifang — berilgan mavzu
bo'yicha O'ZBEK tilida ta'lim materialini yaratib, UNI FAQAT VA FAQAT
VALID JSON FORMATIDA qaytarishdir.

QATIY QOIDALAR:
1. Faqat sof JSON qaytar — hech qanday tushuntirish, muqaddima, so'ngso'z
   yoki markdown belgilari (``` kabi) bo'lmasin.
2. Barcha matnlar O'ZBEK tilida bo'lsin — hech qanday boshqa til ishlatilmasin.
3. JSON strukturasidan og'ishma — aynan ko'rsatilgan kalitlar ishlatilsin.
4. Savollar soni AYNAN 5 (besh) ta bo'lsin — na ko'proq, na kamroq.
5. Har bir savolda variantlar: {"A":"...","B":"...","C":"...","D":"..."} bo'lsin.
6. togri_javob qiymati faqat "A", "B", "C" yoki "D" bo'lsin.
"""


def foydalanuvchi_promptini_yaratish(mavzu: str) -> str:
    """
    Foydalanuvchi (user role) uchun batafsil prompt yaratadi.

    OpenAI chat completions API ikki xil xabar rolini qo'llab-quvvatlaydi:
      - "system" → Modelga umumiy ko'rsatmalar (kim bo'lish kerak, qanday javob berish)
      - "user"   → Aniq so'rov (nima qilish kerak bu safar)

    Bu funksiya "user" xabarini yaratadi — mavzuga xos so'rov.

    Parametrlar:
        mavzu (str): Kontent generatsiya qilinadigan mavzu

    Qaytaradi:
        str — To'liq foydalanuvchi prompti
    """
    return f"""Quyidagi mavzu bo'yicha to'liq ta'lim paketi yaratib, FAQAT JSON qaytaring.

MAVZU: "{mavzu}"

Quyidagi aniq JSON strukturasini to'ldirib qaytaring
(barcha qiymatlar o'zbek tilida bo'lsin):

{{
  "savollar": [
    {{
      "savol": "Birinchi savol matni (o'zbekcha)?",
      "variantlar": {{
        "A": "Birinchi variant",
        "B": "Ikkinchi variant",
        "C": "Uchinchi variant",
        "D": "To'rtinchi variant"
      }},
      "togri_javob": "A",
      "izoh": "Nima uchun A to'g'ri — batafsil o'zbekcha tushuntirish"
    }},
    {{
      "savol": "Ikkinchi savol matni?",
      "variantlar": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "togri_javob": "B",
      "izoh": "Izoh..."
    }},
    {{
      "savol": "Uchinchi savol matni?",
      "variantlar": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "togri_javob": "C",
      "izoh": "Izoh..."
    }},
    {{
      "savol": "To'rtinchi savol matni?",
      "variantlar": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "togri_javob": "D",
      "izoh": "Izoh..."
    }},
    {{
      "savol": "Beshinchi savol matni?",
      "variantlar": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "togri_javob": "A",
      "izoh": "Izoh..."
    }}
  ],
  "dars_rejasi": {{
    "sarlavha": "Dars sarlavhasi (o'zbekcha)",
    "maqsadlar": [
      "Birinchi o'quv maqsadi",
      "Ikkinchi o'quv maqsadi",
      "Uchinchi o'quv maqsadi"
    ],
    "kirish": "Darsning kirish qismi — mavzuni tanishtirish (2-3 paragraf)",
    "asosiy_qism": [
      {{
        "qism_sarlavhasi": "Birinchi asosiy mavzu",
        "qism_mazmuni": "Batafsil tushuntirish",
        "misol": "Amaliy misol"
      }},
      {{
        "qism_sarlavhasi": "Ikkinchi asosiy mavzu",
        "qism_mazmuni": "Batafsil tushuntirish",
        "misol": "Amaliy misol"
      }},
      {{
        "qism_sarlavhasi": "Uchinchi asosiy mavzu",
        "qism_mazmuni": "Batafsil tushuntirish",
        "misol": "Amaliy misol"
      }}
    ],
    "xulosa": "Darsning xulosa qismi — asosiy fikrlar",
    "tavsiya_etilgan_manbalar": [
      "Birinchi tavsiya etilgan manba",
      "Ikkinchi tavsiya etilgan manba"
    ]
  }},
  "uy_vazifasi": "Uy vazifasi matni — aniq ko'rsatmalar bilan (kamida 3-4 paragraf, o'zbekcha). Vazifa amaliy bo'lishi va mavzu bilan bog'liq bo'lishi shart.",
  "baholash_mezoni": {{
    "umumiy_ball": 100,
    "qismlar": [
      {{
        "nomi": "Nazariy bilim",
        "ball": 30,
        "tavsif": "Mavzu bo'yicha nazariy bilim darajasi"
      }},
      {{
        "nomi": "Amaliy topshiriq",
        "ball": 50,
        "tavsif": "Uy vazifasi va amaliy topshiriqni to'g'ri bajarish"
      }},
      {{
        "nomi": "Ijodkorlik va mustaqillik",
        "ball": 20,
        "tavsif": "O'z fikrini qo'sha olish, mustaqil yechim topish"
      }}
    ],
    "baholar": {{
      "A": {{"oraliq": "90-100 ball", "tavsif": "A'lo — mukammal o'zlashtirish"}},
      "B": {{"oraliq": "75-89 ball",  "tavsif": "Yaxshi — yaxshi o'zlashtirish"}},
      "C": {{"oraliq": "60-74 ball",  "tavsif": "Qoniqarli — o'rtacha o'zlashtirish"}},
      "D": {{"oraliq": "45-59 ball",  "tavsif": "Qoniqarsiz — qayta ishlash kerak"}},
      "F": {{"oraliq": "0-44 ball",   "tavsif": "O'tmadi — qaytadan o'qish shart"}}
    }},
    "qoshimcha_talablar": [
      "Barcha topshiriqlar belgilangan muddatda topshirilishi shart",
      "Plagiat aniqlanganida ball berilmaydi",
      "Har bir topshiriq o'zbek tilida yozilishi shart"
    ]
  }}
}}

ESLATMA: Yuqoridagi JSON shablonini TO'LDIRIB qaytaring.
Mavzu "{mavzu}" bo'yicha HAQIQIY va BATAFSIL ma'lumotlar kiriting.
FAQAT SOF JSON — hech qanday boshqa matn, muqaddima yoki markdown bo'lmasin!"""


# =============================================================================
# ASOSIY AI GENERATSIYA FUNKSIYASI
# =============================================================================

async def ai_kontent_generatsiya(mavzu: str) -> Dict[str, Any]:
    """
    Berilgan mavzu bo'yicha to'liq ta'lim kontentini asinxron generatsiya qiladi.

    BU FUNKSIYA QANDAY ISHLAYDI:
      1. Tizim va foydalanuvchi promptlarini tayyorlash
      2. OpenRouter API'ga async so'rov yuborish
         (openrouter_mijoz.chat.completions.create)
      3. Javobni 3 bosqichli JSON parsing orqali o'qish
      4. Strukturani tekshirish (5 savol, barcha maydonlar)
      5. Xato bo'lsa — eksponensial backoff bilan qayta urinish
      6. Tozalangan natijani qaytarish

    RETRY STRATEGIYASI:
      - Maksimal 3 marta urinish
      - Har urinish orasida kutish: 2s → 4s → (tugaydi)
      - Rate limit xatosida (429) — 10 soniya kutish

    Parametrlar:
        mavzu (str): Kontent generatsiya qilinadigan mavzu (o'zbekcha)

    Qaytaradi:
        Dict[str, Any] — {
            "savollar": [...],       5 ta MCQ savol
            "dars_rejasi": {...},    Strukturalangan dars rejasi
            "uy_vazifasi": "...",    Uy vazifasi matni
            "baholash_mezoni": {...} Baholash mezonlari
            "mavzu": "...",          Generatsiya mavzusi (meta)
            "yaratilgan_vaqt": "...",Yaratilgan vaqt (ISO, meta)
            "model": "..."           Ishlatilgan model nomi (meta)
        }

    Istisno:
        ValueError  — Xavfsizlik filtri yoki kirish xatosi
        RuntimeError — 3 urinishdan keyin ham muvaffaqiyatsiz
    """
    logger.info(f"OpenRouter AI generatsiyasi boshlanmoqda. Mavzu: '{mavzu}'")

    # Chat xabarlari ro'yxati — OpenAI chat format
    # "system" → modelga umumiy ko'rsatma (kim bo'lish, qanday javob berish)
    # "user"   → aniq so'rov (bu safar nima qilish kerak)
    xabarlar = [
        {
            "role": "system",   # Tizim roli — model xulq-atvorini belgilaydi
            "content": TIZIM_PROMPTI,
        },
        {
            "role": "user",     # Foydalanuvchi roli — aniq so'rov
            "content": foydalanuvchi_promptini_yaratish(mavzu),
        },
    ]

    # Retry parametrlari — serverless muhitda vaqtinchalik xatolar bo'lishi mumkin
    maksimal_urinishlar = 3
    baza_kutish_vaqti = 2  # Soniyada

    for urinish in range(1, maksimal_urinishlar + 1):
        try:
            logger.info(
                f"OpenRouter so'rovi yuborilmoqda... "
                f"({urinish}/{maksimal_urinishlar}-urinish) | "
                f"Model: {OPENROUTER_MODELI}"
            )

            # ── OpenRouter API so'rovi ─────────────────────────────────────
            # `await` — bu asinxron chaqiruv.
            # Event loop bloklanmaydi — boshqa so'rovlar parallel ishlaydi.
            # Bu FastAPI'ning asosiy kuchi: bir vaqtda ko'p so'rovga xizmat qilish.
            javob = await openrouter_mijoz.chat.completions.create(
                model=OPENROUTER_MODELI,      # openai/gpt-oss-120b:free
                messages=xabarlar,            # system + user xabarlari
                temperature=0.3,              # Past temperatura = aniq, tartibli javob
                                              # Yuqori temperatura = ijodkor lekin beqaror
                max_tokens=4096,              # Maksimal token soni (katta JSON uchun yetarli)
                response_format={"type": "json_object"},  # JSON rejimi — GPT-4 va o1 modellari
                                                           # uchun. Bu parametr modelni FAQAT
                                                           # JSON qaytarishga majburlaydi.
                extra_headers=QOSHIMCHA_SARLAVHALAR,       # OpenRouter meta sarlavhalari
            )

            # ── Javobni o'qish ────────────────────────────────────────────
            # OpenAI javob strukturasi:
            #   javob.choices[0].message.content → matn (string)
            # choices[0] — birinchi (va odatda yagona) javob varianti
            if not javob.choices:
                logger.warning(f"{urinish}-urinish: Bo'sh choices ro'yxati.")
                if urinish < maksimal_urinishlar:
                    await asyncio.sleep(baza_kutish_vaqti * urinish)
                continue

            xom_matn: str = javob.choices[0].message.content or ""
            if not xom_matn.strip():
                logger.warning(f"{urinish}-urinish: Bo'sh javob matni.")
                if urinish < maksimal_urinishlar:
                    await asyncio.sleep(baza_kutish_vaqti * urinish)
                continue

            logger.debug(
                f"OpenRouter xom javobi (dastlabki 200 belgi): {xom_matn[:200]}..."
            )

            # ── JSON Parsing — 3 bosqichli ────────────────────────────────
            # json.loads() muvaffaqiyatsiz bo'lsa — ValueError qaytaradi
            # Biz buni ushlayb, qayta urinish qilamiz.
            try:
                parse_qilingan = json_ni_ajratib_olish(xom_matn)
            except ValueError as parse_xato:
                logger.warning(
                    f"{urinish}-urinish: JSON parse muvaffaqiyatsiz: {parse_xato}"
                )
                if urinish < maksimal_urinishlar:
                    await asyncio.sleep(baza_kutish_vaqti * urinish)
                continue

            # ── Struktura Tekshiruvi ───────────────────────────────────────
            # 5 savol, barcha maydonlar, A/B/C/D variantlari tekshiriladi
            if not javobni_tekshirish(parse_qilingan):
                logger.warning(
                    f"{urinish}-urinish: Javob struktura tekshiruvidan o'tmadi. "
                    "Qayta urinilmoqda..."
                )
                if urinish < maksimal_urinishlar:
                    await asyncio.sleep(baza_kutish_vaqti * urinish)
                continue

            # ── Muvaffaqiyat! ─────────────────────────────────────────────
            logger.info(
                f"AI generatsiyasi muvaffaqiyatli! "
                f"Mavzu: '{mavzu}' | Urinish: {urinish}/{maksimal_urinishlar}"
            )

            # Meta ma'lumotlar qo'shish (endpoint javobida ko'rinadi)
            parse_qilingan["mavzu"] = mavzu
            parse_qilingan["yaratilgan_vaqt"] = datetime.now(timezone.utc).isoformat()
            parse_qilingan["model"] = OPENROUTER_MODELI

            # Token sarfi loglanadi (monitoring uchun foydali)
            if hasattr(javob, "usage") and javob.usage:
                logger.info(
                    f"Token sarfi — Kirish: {javob.usage.prompt_tokens}, "
                    f"Chiqish: {javob.usage.completion_tokens}, "
                    f"Jami: {javob.usage.total_tokens}"
                )

            return parse_qilingan

        except Exception as xato:
            # ── Xatolarni Tasniflash va Boshqarish ───────────────────────
            xato_turi = type(xato).__name__
            xato_xabari = str(xato)

            # Rate limit xatosi — ko'proq kutish kerak
            if "429" in xato_xabari or "rate_limit" in xato_xabari.lower():
                kutish = 10  # Rate limit uchun 10 soniya kutish
                logger.warning(
                    f"{urinish}-urinish: Rate limit (429). "
                    f"{kutish} soniya kutilmoqda..."
                )
                if urinish < maksimal_urinishlar:
                    await asyncio.sleep(kutish)
                continue

            # Autentifikatsiya xatosi — API kalit noto'g'ri
            if "401" in xato_xabari or "authentication" in xato_xabari.lower():
                logger.critical(
                    f"Autentifikatsiya xatosi: OPENROUTER_API_KEY noto'g'ri! "
                    f"Tafsilot: {xato_xabari}"
                )
                raise ValueError(
                    "OpenRouter API kaliti noto'g'ri. "
                    ".env faylidagi OPENROUTER_API_KEY ni tekshiring."
                ) from xato

            # Model mavjud emas xatosi
            if "model_not_found" in xato_xabari.lower() or "404" in xato_xabari:
                logger.error(f"Model topilmadi: {OPENROUTER_MODELI}")
                raise ValueError(
                    f"'{OPENROUTER_MODELI}' modeli topilmadi. "
                    "OpenRouter modellar ro'yxatini tekshiring."
                ) from xato

            # Boshqa xatolar — loglash va qayta urinish
            logger.error(
                f"{urinish}-urinish: {xato_turi} xatosi: {xato_xabari}"
            )
            if urinish < maksimal_urinishlar:
                kutish_vaqti = baza_kutish_vaqti * urinish  # Eksponensial: 2s, 4s
                logger.info(f"{kutish_vaqti} soniya kutilmoqda...")
                await asyncio.sleep(kutish_vaqti)
            else:
                # Oxirgi urinish ham muvaffaqiyatsiz — xato qaytarish
                raise RuntimeError(
                    f"AI generatsiyasi {maksimal_urinishlar} ta urinishdan keyin "
                    f"muvaffaqiyatsiz bo'ldi. Oxirgi xato: {xato_xabari}"
                ) from xato

    # Barcha urinishlar bitdi — bu nuqtaga yetishilmasligi kerak
    raise RuntimeError(
        f"'{mavzu}' mavzusi uchun AI generatsiyasi to'liq muvaffaqiyatsiz bo'ldi. "
        "OpenRouter xizmat holati: https://status.openrouter.ai"
    )


# =============================================================================
# BALL HISOBLASH FUNKSIYASI — O'ZGARISHSIZ QOLDI
# =============================================================================

def testni_tekshirish_va_ball_hisoblash(
    savollar: list,
    foydalanuvchi_javoblari: dict,
) -> dict:
    """
    Foydalanuvchi javoblarini test to'g'ri javoblari bilan solishtiradi
    va batafsil natijani hisoblaydi.

    BU FUNKSIYA AI DVIGATELIDAN MUSTAQIL — OpenRouter'ga o'tish bu
    funksiyaga hech qanday ta'sir qilmaydi. Mantiq bir xil qoladi.

    Parametrlar:
        savollar (list): Test savollari ro'yxati (har biri 'togri_javob' bilan)
        foydalanuvchi_javoblari (dict): {"0":"A", "1":"C", "2":"B", ...}

    Qaytaradi:
        dict — {
            "togri_javoblar_soni": int,
            "jami_savollar": int,
            "ball_foizi": float,
            "baho": str,
            "baho_tavsif": str,
            "batafsil": list
        }
    """
    togri_soni = 0
    batafsil = []  # Har bir savol bo'yicha natija

    for indeks, savol in enumerate(savollar):
        # Foydalanuvchi javobi — string indeks bo'yicha olish, yuqori harfga o'tkazish
        foydalanuvchi_javobi = (
            foydalanuvchi_javoblari.get(str(indeks), "").upper().strip()
        )
        # To'g'ri javob — savoldan olish
        togri_javob = savol.get("togri_javob", "").upper().strip()

        togrimi = foydalanuvchi_javobi == togri_javob
        if togrimi:
            togri_soni += 1

        batafsil.append({
            "savol_raqami": indeks + 1,
            "savol": savol.get("savol", ""),
            "foydalanuvchi_javobi": foydalanuvchi_javobi,
            "togri_javob": togri_javob,
            "togrimi": togrimi,
            "izoh": (
                savol.get("izoh", "")
                if not togrimi
                else "To'g'ri javob berdingiz!"
            ),
        })

    # Ball foizini hisoblash: har savol 20 ball (5 × 20 = 100)
    jami = len(savollar)
    ball_foizi = round((togri_soni / jami * 100) if jami > 0 else 0.0, 2)

    # Harfli baho tizimi
    if ball_foizi >= 90:
        baho, tavsif = "A", "A'lo"
    elif ball_foizi >= 75:
        baho, tavsif = "B", "Yaxshi"
    elif ball_foizi >= 60:
        baho, tavsif = "C", "Qoniqarli"
    elif ball_foizi >= 45:
        baho, tavsif = "D", "Qoniqarsiz"
    else:
        baho, tavsif = "F", "O'tmadi"

    logger.info(
        f"Test natijasi: {togri_soni}/{jami} ({ball_foizi}%) — Baho: {baho} ({tavsif})"
    )

    return {
        "togri_javoblar_soni": togri_soni,
        "jami_savollar": jami,
        "ball_foizi": ball_foizi,
        "baho": baho,
        "baho_tavsif": tavsif,
        "batafsil": batafsil,
    }
