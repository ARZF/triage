from uuid import uuid4

from app.agent.intake import IntakeState, advance

MAX_SESSIONS = 1000
# ponytail: single process/event loop, lost on restart, max 1000 sessions; use a database in the EHR slice.
SESSIONS: dict[str, IntakeState] = {}


def create_session() -> tuple[str, IntakeState]:
    session_id = uuid4().hex
    state = IntakeState()
    if len(SESSIONS) >= MAX_SESSIONS:
        del SESSIONS[next(iter(SESSIONS))]
    SESSIONS[session_id] = state
    return session_id, state


def send_message(session_id: str, message: str) -> IntakeState:
    state, _ = advance(SESSIONS[session_id], message)
    SESSIONS[session_id] = state
    return state
