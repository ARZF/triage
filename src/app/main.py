from contextlib import closing
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router
from app.api.chat import router as chat_router
from app.api.demo import router as demo_router
from app.api.dictionaries import router as dictionary_router
from app.agent.dictionaries import load_dictionaries
from app.agent.doctors import load_doctors
from app.core.config import Settings
from app.core.db import connect
from app.core.errors import register_exception_handlers
from app.core.logging_config import configure_logging, disable_access_logging
from app.api.patients import router as patient_router

settings = Settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dictionaries()
    load_doctors()
    disable_access_logging()
    with closing(connect()):
        pass
    yield


app = FastAPI(title="Healthcare Agent", lifespan=lifespan)
app.include_router(router)
app.include_router(chat_router)
app.include_router(demo_router)
app.include_router(dictionary_router)
app.include_router(patient_router)
register_exception_handlers(app)
