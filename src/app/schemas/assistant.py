from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[AssistantMessage] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def conversation(self):
        if len(self.messages) % 2 == 0 or sum(len(item.content) for item in self.messages) > 40000:
            raise ValueError("Start a new chat")
        for index, item in enumerate(self.messages):
            if item.role != ("assistant" if index % 2 else "user") or item.role == "user" and len(item.content) > 4000:
                raise ValueError("Invalid conversation")
        return self
