from pydantic import BaseModel

from app.agent.dictionaries import Kind


class MatchedEntry(BaseModel):
    code: str
    name_fa: str


class DictionaryEntry(MatchedEntry):
    name_en: str
    aliases: list[str]


class DictionaryResponse(BaseModel):
    kind: Kind
    entries: list[DictionaryEntry]
