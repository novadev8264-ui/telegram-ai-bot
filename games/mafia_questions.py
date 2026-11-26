
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Lock

logger = logging.getLogger("PULSE.MAFIA.QUESTIONS")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("MAFIA_AI_MODEL", "openrouter/free")
API_KEY = os.getenv("API_KEY")

DEFAULT_HISTORY_FILE = Path(__file__).with_name(
    "mafia_questions_used.json"
)
HISTORY_FILE = Path(
    os.getenv("MAFIA_QUESTIONS_FILE", str(DEFAULT_HISTORY_FILE))
)

_file_lock = Lock()
_generation_lock = asyncio.Lock()

QUESTION_BANK = [
    ("اگر قرار باشد یک سفر کوتاه بروی، ترجیح می‌دهی کجا بروی؟", "برای یک سفر کوتاه، چه وسیله‌ای را انتخاب می‌کنی؟"),
    ("به نظرت بهترین ویژگی یک دوست خوب چیست؟", "به نظرت مهم‌ترین رفتار یک دوست قابل اعتماد چیست؟"),
    ("اگر یک روز کاملاً آزاد داشته باشی، چطور می‌گذرانی؟", "اگر یک عصر آزاد داشته باشی، چه کاری انجام می‌دهی؟"),
    ("کدام فصل سال را بیشتر دوست داری و چرا؟", "کدام نوع آب‌وهوا را بیشتر می‌پسندی؟"),
    ("برای تماشای فیلم چه ژانری را انتخاب می‌کنی؟", "برای دیدن یک سریال، چه سبکی را ترجیح می‌دهی؟"),
    ("اگر بتوانی یک مهارت تازه یاد بگیری، چه چیزی انتخاب می‌کنی؟", "اگر فرصت یادگیری یک هنر را داشته باشی، سراغ چه چیزی می‌روی؟"),
    ("به نظرت یک شهر خوب چه ویژگی‌ای باید داشته باشد؟", "برای زندگی در یک شهر، کدام امکانات مهم‌ترند؟"),
    ("غذای خانگی مورد علاقه‌ات چیست؟", "اگر بخواهی یک غذای ساده انتخاب کنی، چه می‌خوری؟"),
    ("برای استراحت بیشتر سکوت را دوست داری یا موسیقی؟", "هنگام استراحت ترجیح می‌دهی تنها باشی یا در جمع؟"),
    ("اگر یک حیوان خانگی انتخاب کنی، کدام را انتخاب می‌کنی؟", "کدام حیوان را برای نگهداری در خانه مناسب‌تر می‌دانی؟"),
    ("به نظرت مهم‌ترین وسیله برای یک سفر چیست؟", "در سفر کدام وسیله را حتماً همراهت می‌بری؟"),
    ("کدام ورزش را برای تماشا جذاب‌تر می‌دانی؟", "کدام فعالیت ورزشی را برای انجام دادن بیشتر می‌پسندی؟"),
    ("اگر بخواهی یک کتاب بخوانی، چه موضوعی را انتخاب می‌کنی؟", "کدام سبک داستانی بیشتر توجهت را جلب می‌کند؟"),
    ("به نظرت صبح زود زمان بهتری برای کار است یا شب؟", "بیشتر در چه ساعتی از روز انرژی داری؟"),
    ("برای یک دورهمی خوب چه چیزی از همه مهم‌تر است؟", "چه چیزی باعث می‌شود یک مهمانی به‌یادماندنی شود؟"),
    ("اگر بتوانی به یک مکان تاریخی بروی، کجا را انتخاب می‌کنی؟", "بازدید از چه نوع مکان تاریخی برایت جذاب‌تر است؟"),
    ("کدام نوشیدنی را بیشتر دوست داری؟", "برای یک روز گرم چه نوشیدنی‌ای انتخاب می‌کنی؟"),
    ("اگر قرار باشد یک وسیله جدید بخری، چه چیزی را در اولویت می‌گذاری؟", "هنگام خرید یک وسیله، کیفیت مهم‌تر است یا ظاهر؟"),
    ("به نظرت بهترین راه گذراندن تعطیلات چیست؟", "برای آخر هفته بیشتر بیرون رفتن را دوست داری یا خانه ماندن؟"),
    ("اگر بتوانی در یک کنسرت شرکت کنی، چه نوع موسیقی‌ای را انتخاب می‌کنی؟", "برای گوش دادن روزانه چه سبک موسیقی‌ای را ترجیح می‌دهی؟"),
    ("کدام ویژگی طبیعت برایت آرامش‌بخش‌تر است؟", "برای تفریح در طبیعت، جنگل را ترجیح می‌دهی یا ساحل؟"),
    ("اگر یک روز بدون اینترنت داشته باشی، چه کار می‌کنی؟", "در زمان دوری از گوشی، چه سرگرمی‌ای انتخاب می‌کنی؟"),
    ("به نظرت یک هدیه خوب باید کاربردی باشد یا خاطره‌انگیز؟", "برای خوشحال کردن یک دوست چه نوع هدیه‌ای می‌دهی؟"),
    ("اگر بتوانی یک غذای تازه امتحان کنی، چه نوع غذایی را انتخاب می‌کنی؟", "در امتحان کردن غذاهای جدید، بیشتر به چه چیزی توجه می‌کنی؟"),
    ("کدام وسیله نقلیه برای سفرهای طولانی راحت‌تر است؟", "برای رفت‌وآمد روزانه چه وسیله‌ای را ترجیح می‌دهی؟"),
    ("اگر یک روز در طبیعت بمانی، چه چیزی همراهت می‌بری؟", "برای یک گردش بیرون شهر، چه وسیله‌ای ضروری است؟"),
    ("کدام سرگرمی گروهی را بیشتر می‌پسندی؟", "برای دورهمی دوستانه چه بازی‌ای پیشنهاد می‌کنی؟"),
    ("به نظرت یادگیری زبان جدید چه فایده‌ای دارد؟", "اگر زبان تازه‌ای یاد بگیری، دوست داری از آن کجا استفاده کنی؟"),
    ("چه چیزی باعث می‌شود به یک مکان دوباره سر بزنی؟", "برای انتخاب یک مقصد تفریحی، چه چیزی برایت مهم‌تر است؟"),
    ("اگر بخواهی یک روز را به یادگیری اختصاص بدهی، چه موضوعی را انتخاب می‌کنی؟", "کدام موضوع آموزشی را دوست داری بیشتر بشناسی؟"),
]


def _fingerprint(citizen_question, mafia_question):
    normalized = "|".join(
        re.sub(r"\s+", " ", value.strip().lower())
        for value in (citizen_question, mafia_question)
    )
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _read_history():
    try:
        with _file_lock:
            if not HISTORY_FILE.exists():
                return {"used": [], "history": []}

            with HISTORY_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)

        if not isinstance(data, dict):
            return {"used": [], "history": []}

        used = data.get("used", [])
        history = data.get("history", [])

        return {
            "used": used if isinstance(used, list) else [],
            "history": history if isinstance(history, list) else [],
        }

    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read mafia question history")
        return {"used": [], "history": []}


def _write_history(data):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        with _file_lock:
            fd, temporary_path = tempfile.mkstemp(
                prefix="mafia_questions_",
                suffix=".tmp",
                dir=str(HISTORY_FILE.parent),
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync(file.fileno())

                os.replace(temporary_path, HISTORY_FILE)

            finally:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)

    except OSError:
        logger.exception("Could not save mafia question history")


def _extract_json(content):
    if not isinstance(content, str):
        raise ValueError("AI response content is not text")

    content = content.strip()
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"\s*```$", "", content)

    start = content.find("{")
    end = content.rfind("}")

    if start < 0 or end <= start:
        raise ValueError("AI response does not contain JSON")

    return json.loads(content[start:end + 1])


def _validate_pair(data):
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")

    citizen = data.get("citizen")
    mafia = data.get("mafia")

    if not isinstance(citizen, str) or not isinstance(mafia, str):
        raise ValueError("AI questions are missing")

    citizen = re.sub(r"\s+", " ", citizen).strip()
    mafia = re.sub(r"\s+", " ", mafia).strip()

    if not (10 <= len(citizen) <= 220 and 10 <= len(mafia) <= 220):
        raise ValueError("AI questions have invalid length")

    normalized_citizen = re.sub(r"\W+", "", citizen.casefold())
    normalized_mafia = re.sub(r"\W+", "", mafia.casefold())

    if normalized_citizen == normalized_mafia:
        raise ValueError("AI questions are identical")

    return citizen, mafia


def _generate_ai_pair():
    if not API_KEY:
        raise RuntimeError("API_KEY is not configured")

    prompt = (
        "برای بازی گروهی مافیا دقیقاً یک جفت سؤال فارسی تولید کن. "
        "سؤال شهروند باید درباره یک موضوع مشخص باشد. "
        "سؤال مافیا باید متفاوت، اما درباره همان موضوع و به‌اندازه کافی "
        "نزدیک باشد تا بازی منصفانه بماند. "
        "سؤال‌ها باید کوتاه، طبیعی، مناسب همه سنین و بدون موضوعات حساس باشند. "
        "هیچ توضیح اضافه‌ای ننویس و فقط JSON معتبر با این ساختار برگردان: "
        '{"citizen":"سؤال شهروند","mafia":"سؤال مافیا"}. '
        "از سؤال‌های کلیشه‌ای و تکراری پرهیز کن."
    )

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "تو طراح سؤال فارسی برای بازی دوستانه مافیا هستی. "
                    "فقط خروجی JSON معتبر بده."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.9,
        "max_tokens": 180,
    }

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://railway.app",
            "X-Title": "PULSE Mafia Questions",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result["choices"][0]["message"]["content"]
        return _validate_pair(_extract_json(content))

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        logger.exception(
            "AI question generation failed; local bank will be used"
        )
        raise


def _choose_bank_pair(history):
    used = set(history["used"])

    available = [
        pair for pair in QUESTION_BANK
        if _fingerprint(pair[0], pair[1]) not in used
    ]

    if not available:
        logger.info(
            "Mafia question bank exhausted; starting a new cycle"
        )
        history["used"] = []
        available = list(QUESTION_BANK)

    return random.choice(available)


def _save_used_pair(history, citizen, mafia, source):
    fingerprint = _fingerprint(citizen, mafia)

    history["used"].append(fingerprint)

    history["history"].append({
        "citizen": citizen,
        "mafia": mafia,
        "source": source,
        "used_at": int(time.time()),
    })

    history["history"] = history["history"][-1000:]
    history["used"] = history["used"][-2000:]

    _write_history(history)


async def get_mafia_questions():
    """انتخاب سؤال با اولویت هوش مصنوعی و پشتیبان بانک محلی."""

    async with _generation_lock:
        history = _read_history()
        source = "ai"

        try:
            citizen, mafia = await asyncio.to_thread(
                _generate_ai_pair
            )

            fingerprint = _fingerprint(citizen, mafia)

            if fingerprint in set(history["used"]):
                raise ValueError(
                    "AI generated a previously used question pair"
                )

        except Exception:
            source = "bank"
            citizen, mafia = _choose_bank_pair(history)

        _save_used_pair(
            history,
            citizen,
            mafia,
            source,
        )

        logger.info(
            "Mafia questions selected: source=%s",
            source,
        )

        return {
            "citizen": citizen,
            "mafia": mafia,
  }
              
