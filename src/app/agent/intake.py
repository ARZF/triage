from dataclasses import dataclass, field, replace
import math
import re
from typing import Literal

AnswerField = Literal["age", "height_cm", "weight_kg", "chief_complaint", "symptoms", "duration", "severity", "medical_history", "medications", "medication_history", "food_allergies", "allergies", "additional_context"]
Step = Literal["profile", "confirm", AnswerField]
QUESTIONS = {
    "age": "سن بیمار چند سال است؟ (۰ تا ۱۲۰)",
    "height_cm": "قد بیمار چند سانتی‌متر است؟",
    "weight_kg": "وزن بیمار چند کیلوگرم است؟",
    "chief_complaint": "شکایت اصلی بیمار و دلیل مراجعه چیست؟",
    "symptoms": "بیمار چه علائمی دارد؟",
    "duration": "این علائم از چه زمانی شروع شده‌اند؟",
    "severity": "شدت علائم از ۱ تا ۱۰ چقدر است؟",
    "medical_history": "بیمار چه سابقهٔ بیماری دارد؟ اگر ندارد، بنویسید «ندارد».",
    "medications": "داروهایی که مصرف می‌کنید را برای بیمار وارد کنید. اگر دارویی مصرف نمی‌کند، بنویسید «هیچ».",
    "medication_history": "سابقهٔ مصرف داروی بیمار چیست؟ داروهای قبلی را بنویسید؛ اگر ندارد، بنویسید «ندارد».",
    "food_allergies": "بیمار چه حساسیت غذایی دارد؟ اگر ندارد، بنویسید «ندارد».",
    "allergies": "بیمار چه حساسیت دارویی یا سایر حساسیت‌هایی دارد؟ اگر ندارد، بنویسید «ندارد».",
    "additional_context": "آیا توضیح دیگری دربارهٔ خودتان دارید که پزشک بداند؟ نوشتن این بخش اختیاری است و برای هوش مصنوعی ارسال نمی‌شود. اگر توضیحی ندارید، «رد کردن» را بزنید.",
    "confirm": "اطلاعات ثبت‌شده رو بررسی کردید؟ همه موارد درسته؟",
}
STEPS = tuple(QUESTIONS)
QUESTIONS["profile"] = "آیا سن، قد، وزن، سوابق، داروها و حساسیت‌های قبلی همچنان درست هستند؟ «بله» یا «خیر» بنویسید."
PROFILE_FIELDS = ("age", "height_cm", "weight_kg", "medical_history", "medications", "medication_history", "food_allergies", "allergies")
WELCOME = "به Triage خوش آمدید. برای شروع، چند پرسش را پاسخ دهید. فقط از داده‌های ساختگی استفاده کنید و نام یا اطلاعات شناسایی وارد نکنید."
PROFILE_WELCOME = "خوش آمدید! اطلاعات ثبت‌شدهٔ قبلی شما: "
# Compatibility marker only: recognize existing conversations without rewriting their stored messages.
LEGACY_PROFILE_WELCOME = "خوش آمدید! اطلاعات قبلی شما در این نسخهٔ نمایشی: "
EMERGENCY_REPLY = "لطفاً همین حالا با خدمات اورژانس محل خود تماس بگیرید. این سامانه نمی‌تواند کمک اضطراری ارائه کند."
COMPLETE_REPLY = "اطلاعات ثبت و تأیید شد. پیشنهاد تخصص جایگزین تشخیص یا توصیهٔ درمانی پزشک نیست."
# ponytail: starter substring list needs clinical review; replace with clinically reviewed screening before clinical use.
RED_FLAGS = (
    "chest pain", "trouble breathing", "difficulty breathing", "shortness of breath",
    "unconscious", "severe bleeding", "stroke", "suicidal",
    "درد قفسه سینه", "درد سینه", "مشکل در تنفس", "مشکل تنفسی", "دشواری در تنفس",
    "سختی در تنفس", "تنگی نفس", "بیهوش", "بی هوش", "خونریزی شدید", "خون ریزی شدید",
    "سکته مغزی", "خودکشی",
)
TEXT_NORMALIZATION = str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " "})


@dataclass(frozen=True)
class Collected:
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    chief_complaint: str | None = None
    symptoms: str | None = None
    duration: str | None = None
    severity: int | None = None
    medical_history: str | None = None
    medications: str | None = None
    medication_history: str | None = None
    food_allergies: str | None = None
    allergies: str | None = None
    additional_context: str | None = None


@dataclass(frozen=True)
class IntakeState:
    step: Step = "age"
    returning_profile: bool = False
    done: bool = False
    emergency: bool = False
    collected: Collected = field(default_factory=Collected)
    reply: str = WELCOME + "\n\n" + QUESTIONS["age"]


def profile_state(prefill: Collected) -> IntakeState:
    labels = ("سن", "قد (سانتی‌متر)", "وزن (کیلوگرم)", "سابقه بیماری", "داروهایی که مصرف می‌کنید", "سابقه مصرف دارو", "حساسیت غذایی", "حساسیت دارویی / سایر حساسیت‌ها")
    details = "؛ ".join(f"{label}: {getattr(prefill, name)}" for name, label in zip(PROFILE_FIELDS, labels))
    details = details.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    reply = PROFILE_WELCOME + details + ". " + QUESTIONS["profile"]
    return IntakeState(step="profile", collected=prefill, reply=reply)


def parse_measurement(value: str | int | float) -> float:
    if type(value) in (int, float):
        number = float(str(value))
    elif isinstance(value, str) and re.fullmatch(r"(?:\d+(?:[.٫]\d+)?|[.٫]\d+)", value.strip()):
        number = float(value.strip().replace("٫", "."))
    else:
        raise ValueError("عدد مثبت وارد کنید؛ برای اعشار از نقطه یا «٫» استفاده کنید.")
    if not math.isfinite(number) or number <= 0:
        raise ValueError("عدد مثبت و محدود وارد کنید.")
    return number


def advance(state: IntakeState, message: str) -> tuple[IntakeState, str]:
    if state.done:
        return state, state.reply

    answer = message.strip()
    normalized = answer.casefold().translate(TEXT_NORMALIZATION)
    step = state.step
    hint = ""
    value: str | int | float = answer

    if step in ("age", "severity"):
        lower, upper = (0, 120) if step == "age" else (1, 10)
        if answer.isdecimal() and lower <= int(answer) <= upper:
            value = int(answer)
        else:
            hint = "عدد صحیح بین ۰ تا ۱۲۰ وارد کنید." if step == "age" else "عدد صحیح بین ۱ تا ۱۰ وارد کنید."
    elif step in ("height_cm", "weight_kg"):
        try:
            value = parse_measurement(answer)
        except ValueError as error:
            hint = str(error)
    elif step in ("confirm", "profile"):
        if normalized not in ("yes", "no", "بله", "خیر", "نه"):
            hint = "لطفاً «بله» یا «خیر» بنویسید."
    elif step == "additional_context":
        value = "" if not answer or normalized in ("skip", "رد کردن") else answer
    elif not answer:
        hint = "لطفاً پاسخ را خالی نگذارید."

    if hint:
        updated = replace(state, reply=hint + " " + QUESTIONS[step])
    elif step == "profile":
        updated = (
            replace(state, step="chief_complaint", returning_profile=True, reply=QUESTIONS["chief_complaint"])
            if normalized in ("yes", "بله") else IntakeState()
        )
    elif step in ("chief_complaint", "symptoms") and any(phrase in normalized for phrase in RED_FLAGS):
        updated = replace(state, done=True, emergency=True, reply=EMERGENCY_REPLY)
    elif step == "confirm":
        updated = (
            replace(state, done=True, reply=COMPLETE_REPLY)
            if normalized in ("yes", "بله")
            else IntakeState(reply="دوباره شروع می‌کنیم. " + QUESTIONS["age"])
        )
    else:
        next_step = "additional_context" if state.returning_profile and step == "severity" else STEPS[STEPS.index(step) + 1]
        updated = replace(
            state,
            step=next_step,
            collected=replace(state.collected, **{step: value}),
            reply=QUESTIONS[next_step],
        )
    return updated, updated.reply
