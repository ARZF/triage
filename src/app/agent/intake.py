from dataclasses import dataclass, field, replace
from typing import Literal

Step = Literal["profile", "age", "symptoms", "duration", "severity", "medications", "allergies", "confirm"]
QUESTIONS = {
    "age": "سن بیمار فرضی چند سال است؟ (۰ تا ۱۲۰)",
    "symptoms": "بیمار فرضی چه علائمی دارد؟",
    "duration": "این علائم از چه زمانی شروع شده‌اند؟",
    "severity": "شدت علائم از ۱ تا ۱۰ چقدر است؟",
    "medications": "بیمار فرضی چه داروهایی مصرف می‌کند؟ اگر دارویی مصرف نمی‌کند، بنویسید «هیچ».",
    "allergies": "بیمار فرضی چه حساسیت‌هایی دارد؟ اگر حساسیتی ندارد، بنویسید «ندارد».",
    "confirm": "آیا اطلاعات درست است؟ برای پایان «بله» و برای شروع دوباره «خیر» بنویسید.",
}
STEPS = tuple(QUESTIONS)
QUESTIONS["profile"] = "آیا سن، داروها و حساسیت‌های قبلی همچنان درست هستند؟ «بله» یا «خیر» بنویسید."
WELCOME = "خوش آمدید! این یک نسخهٔ نمایشی است؛ فقط از داده‌های ساختگی استفاده کنید. نام یا اطلاعات شناسایی وارد نکنید."
EMERGENCY_REPLY = "لطفاً همین حالا با خدمات اورژانس محل خود تماس بگیرید. این نسخهٔ نمایشی نمی‌تواند کمک اضطراری ارائه کند."
COMPLETE_REPLY = "ثبت اطلاعات ساختگی به پایان رسید. این نسخهٔ نمایشی تشخیص یا توصیهٔ درمانی ارائه نمی‌کند."
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
    symptoms: str | None = None
    duration: str | None = None
    severity: int | None = None
    medications: str | None = None
    allergies: str | None = None


@dataclass(frozen=True)
class IntakeState:
    step: Step = "age"
    returning_profile: bool = False
    done: bool = False
    emergency: bool = False
    collected: Collected = field(default_factory=Collected)
    reply: str = WELCOME + "\n\n" + QUESTIONS["age"]


def profile_state(prefill: Collected) -> IntakeState:
    age = str(prefill.age).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    reply = (
        f"خوش آمدید! اطلاعات قبلی شما در این نسخهٔ نمایشی: سن {age} سال؛ "
        f"داروها: {prefill.medications}؛ حساسیت‌ها: {prefill.allergies}. "
        + QUESTIONS["profile"]
    )
    return IntakeState(step="profile", collected=prefill, reply=reply)


def advance(state: IntakeState, message: str) -> tuple[IntakeState, str]:
    if state.done:
        return state, state.reply

    answer = message.strip()
    normalized = answer.casefold().translate(TEXT_NORMALIZATION)
    step = state.step
    hint = ""
    value: str | int = answer

    if step in ("age", "severity"):
        lower, upper = (0, 120) if step == "age" else (1, 10)
        if answer.isdecimal() and lower <= int(answer) <= upper:
            value = int(answer)
        else:
            hint = "عدد صحیح بین ۰ تا ۱۲۰ وارد کنید." if step == "age" else "عدد صحیح بین ۱ تا ۱۰ وارد کنید."
    elif step in ("confirm", "profile"):
        if normalized not in ("yes", "no", "بله", "خیر", "نه"):
            hint = "لطفاً «بله» یا «خیر» بنویسید."
    elif not answer:
        hint = "لطفاً پاسخ را خالی نگذارید."

    if hint:
        updated = replace(state, reply=hint + " " + QUESTIONS[step])
    elif step == "profile":
        updated = (
            replace(state, step="symptoms", returning_profile=True, reply=QUESTIONS["symptoms"])
            if normalized in ("yes", "بله") else IntakeState()
        )
    elif step == "symptoms" and any(phrase in normalized for phrase in RED_FLAGS):
        updated = replace(state, done=True, emergency=True, reply=EMERGENCY_REPLY)
    elif step == "confirm":
        updated = (
            replace(state, done=True, reply=COMPLETE_REPLY)
            if normalized in ("yes", "بله")
            else IntakeState(reply="دوباره شروع می‌کنیم. " + QUESTIONS["age"])
        )
    else:
        next_step = "confirm" if state.returning_profile and step == "severity" else STEPS[STEPS.index(step) + 1]
        updated = replace(
            state,
            step=next_step,
            collected=replace(state.collected, **{step: value}),
            reply=QUESTIONS[next_step],
        )
    return updated, updated.reply
