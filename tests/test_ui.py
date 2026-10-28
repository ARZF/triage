from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


STATIC = Path(__file__).parents[1] / "src/app/static"


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.hidden_text = 0
        self.visible_copy = []
        self.local_styles = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if "id" in values: self.ids.append(values["id"])
        if tag in ("script", "style"): self.hidden_text += 1
        if tag == "link" and values.get("rel") == "stylesheet": self.local_styles.append(values.get("href"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.hidden_text -= 1

    def handle_data(self, data):
        if not self.hidden_text: self.visible_copy.append(data)


class InterfaceChecks(unittest.TestCase):
    def test_pages_have_unique_ids_local_shared_styles_and_honest_copy(self):
        for path in STATIC.glob("*.html"):
            with self.subTest(page=path.name):
                source = path.read_text(encoding="utf-8")
                document = Document(); document.feed(source)
                self.assertEqual(len(document.ids), len(set(document.ids)))
                self.assertEqual(document.local_styles, ["/assets/shell.css"])
                copy = " ".join(document.visible_copy)
                for removed in ("نسخهٔ نمایشی", "دموی", "دمو ", "آزمایشی", "Demo Mode"):
                    self.assertNotIn(removed, copy)
                self.assertIn("اطلاعات واقعی", copy)
                self.assertIn('lang="fa" dir="rtl"', source)

    def test_all_used_style_tokens_are_defined(self):
        css = (STATIC / "shell.css").read_text(encoding="utf-8")
        for path in STATIC.glob("*.html"):
            css += "\n".join(re.findall(r"<style>(.*?)</style>", path.read_text(encoding="utf-8"), re.S))
        defined = set(re.findall(r"(--[\w-]+)\s*:", css))
        used = set(re.findall(r"var\((--[\w-]+)", css))
        self.assertFalse(used - defined, str(used - defined))
        self.assertIn("overflow-x:clip", css)

    def test_keyboard_and_loading_feedback_stay_wired(self):
        shell = (STATIC / "shell.js").read_text(encoding="utf-8")
        login = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertIn('skip.className="skip-link"', shell)
        self.assertIn('event.key==="Escape"', shell)
        self.assertIn('event.key==="Tab"', shell)
        self.assertIn('form.setAttribute("aria-busy","true")', login)
        self.assertIn('autocomplete="username"', login)
        self.assertIn('autocomplete="current-password"', login)
