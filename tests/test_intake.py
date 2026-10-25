import unittest
from dataclasses import asdict

from app.agent.intake import (
    COMPLETE_REPLY, EMERGENCY_REPLY, QUESTIONS, RED_FLAGS, Collected, IntakeState, advance,
)

ANSWERS = ("30", "mild cough", "two days", "3", "none", "no")


def before_step(step):
    state = IntakeState()
    for answer in ANSWERS:
        if state.step == step:
            break
        state, _ = advance(state, answer)
    return state


class IntakeTests(unittest.TestCase):
    def test_happy_path_is_pure_and_terminal(self):
        state = IntakeState()
        original = state
        self.assertIn("داده‌های ساختگی", state.reply)
        self.assertIn(QUESTIONS["age"], state.reply)
        for answer, next_step in zip(
            ANSWERS, ("symptoms", "duration", "severity", "medications", "allergies", "confirm")
        ):
            state, reply = advance(state, answer)
            self.assertEqual(state.step, next_step)
            self.assertEqual(reply, QUESTIONS[next_step])
            self.assertFalse(state.done)
        self.assertEqual(original.collected, Collected())
        state, reply = advance(state, " YES ")
        self.assertTrue(state.done)
        self.assertFalse(state.emergency)
        self.assertEqual(reply, COMPLETE_REPLY)
        self.assertEqual(asdict(state.collected), {
            "age": 30, "symptoms": "mild cough", "duration": "two days",
            "severity": 3, "medications": "none", "allergies": "no",
        })
        self.assertEqual(advance(state, "no"), (state, reply))

    def test_every_validation_reasks_without_storing(self):
        invalid = {
            "age": ("", " ", "-1", "121", "abc", "3.5", "1_0"),
            "symptoms": ("", " "),
            "duration": ("", " "),
            "severity": ("", " ", "0", "11", "abc", "3.5"),
            "medications": ("", " "),
            "allergies": ("", " "),
            "confirm": ("", " ", "maybe"),
        }
        for step, messages in invalid.items():
            for message in messages:
                with self.subTest(step=step, message=message):
                    state = before_step(step)
                    updated, reply = advance(state, message)
                    self.assertEqual(updated.step, step)
                    self.assertEqual(updated.collected, state.collected)
                    self.assertFalse(updated.done)
                    self.assertIn(QUESTIONS[step], reply)
                    self.assertNotEqual(reply, QUESTIONS[step])

    def test_numeric_boundaries_and_trimmed_text(self):
        for answer in ("0", "120"):
            with self.subTest(age=answer):
                state, _ = advance(IntakeState(), answer)
                self.assertEqual(state.collected.age, int(answer))
        for answer in ("1", "10"):
            with self.subTest(severity=answer):
                state, _ = advance(before_step("severity"), answer)
                self.assertEqual(state.collected.severity, int(answer))
        state, _ = advance(before_step("symptoms"), "  mild cough  ")
        self.assertEqual(state.collected.symptoms, "mild cough")
        for step in ("medications", "allergies"):
            for answer in ("none", "no"):
                with self.subTest(step=step, answer=answer):
                    state, _ = advance(before_step(step), answer)
                    self.assertEqual(getattr(state.collected, step), answer)

    def test_no_at_confirm_resets_all_data(self):
        state, reply = advance(before_step("confirm"), " NO ")
        self.assertEqual(state.step, "age")
        self.assertEqual(state.collected, Collected())
        self.assertFalse(state.done)
        self.assertFalse(state.emergency)
        self.assertIn(QUESTIONS["age"], reply)

    def test_each_red_flag_stops_without_storing_answer(self):
        for phrase in RED_FLAGS:
            with self.subTest(phrase=phrase):
                initial = before_step("symptoms")
                state, reply = advance(initial, "Synthetic report: " + phrase.upper())
                self.assertTrue(state.done)
                self.assertTrue(state.emergency)
                self.assertEqual(state.collected, initial.collected)
                self.assertIsNone(state.collected.symptoms)
                self.assertEqual(reply, EMERGENCY_REPLY)
                self.assertEqual(advance(state, "anything else"), (state, reply))


    def test_persian_and_arabic_indic_digits(self):
        for answer, expected in (("۰", 0), ("۱۲۰", 120), ("٣٠", 30), ("۳۰", 30)):
            with self.subTest(age=answer):
                state, _ = advance(IntakeState(), answer)
                self.assertEqual(state.collected.age, expected)
        for answer, expected in (("۱", 1), ("۱۰", 10), ("٣", 3)):
            with self.subTest(severity=answer):
                state, _ = advance(before_step("severity"), answer)
                self.assertEqual(state.collected.severity, expected)
        for answer in ("۱۲۱", "۳.۵", "²"):
            with self.subTest(invalid_age=answer):
                state, reply = advance(IntakeState(), answer)
                self.assertEqual(state.step, "age")
                self.assertIsNone(state.collected.age)
                self.assertIn("عدد صحیح", reply)

    def test_persian_confirmation_and_normalized_red_flags(self):
        state, _ = advance(before_step("confirm"), " بله ")
        self.assertTrue(state.done)
        for answer in ("خیر", "نه", "خير"):
            with self.subTest(reset=answer):
                state, _ = advance(before_step("confirm"), answer)
                self.assertEqual(state.step, "age")
                self.assertEqual(state.collected, Collected())
        for answer in ("درد قفسه سينه", "خون‌ریزی شدید", "بيهوش", "فکر خودكشي"):
            with self.subTest(symptoms=answer):
                state, reply = advance(before_step("symptoms"), answer)
                self.assertTrue(state.emergency)
                self.assertTrue(state.done)
                self.assertIsNone(state.collected.symptoms)
                self.assertEqual(reply, EMERGENCY_REPLY)
