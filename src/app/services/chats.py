from contextlib import closing

from app.core import db
from app.core.errors import ServiceError

# ponytail: 500 texts per visit and polling suit this demo; add explicit retention and push delivery when needed.
MESSAGE_LIMIT = 500


def _participant(connection, request_id: str, user: dict):
    row = connection.execute(
        """SELECT r.* FROM visit_requests r WHERE r.id=? AND r.status='accepted'
           AND ((?='patient' AND r.patient_id=?) OR (?='doctor' AND EXISTS (
               SELECT 1 FROM doctors d WHERE d.id=r.doctor_id AND d.user_id=? AND d.verified=1)))""",
        (request_id, user["role"], user["patient_id"], user["role"], user["id"]),
    ).fetchone()
    if row is None:
        raise ServiceError(404, "http_404", "Not Found")
    return row


def read_messages(request_id: str, user: dict, after: int = 0, limit: int = 50) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN")
        row = _participant(connection, request_id, user)
        messages = connection.execute(
            """SELECT id, sender_role AS sender, content, created_at FROM visit_messages
               WHERE request_id=? AND id>? ORDER BY id LIMIT ?""", (request_id, after, limit + 1),
        ).fetchall()
        return {"messages": [dict(message) for message in messages[:limit]],
                "ended": row["ended_at"] is not None, "has_more": len(messages) > limit}


def post_message(request_id: str, user: dict, content: str) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _participant(connection, request_id, user)
        if row["ended_at"] is not None:
            raise ServiceError(409, "visit_ended", "Visit has ended")
        count = connection.execute("SELECT COUNT(*) FROM visit_messages WHERE request_id=?", (request_id,)).fetchone()[0]
        if count >= MESSAGE_LIMIT:
            raise ServiceError(409, "chat_full", "Chat message limit reached")
        cursor = connection.execute(
            "INSERT INTO visit_messages(request_id, sender_role, content, created_at) VALUES (?, ?, ?, ?)",
            (request_id, user["role"], content, db.utc_now()),
        )
        return dict(connection.execute(
            "SELECT id, sender_role AS sender, content, created_at FROM visit_messages WHERE id=?", (cursor.lastrowid,),
        ).fetchone())


def end_visit(request_id: str, user: dict) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _participant(connection, request_id, user)
        now = db.utc_now()
        connection.execute(
            """UPDATE visit_requests SET ended_at=?, updated_at=?
               WHERE id=? AND doctor_id=? AND status='accepted' AND ended_at IS NULL""",
            (now, now, request_id, user["doctor_id"]),
        )
        row = _participant(connection, request_id, user)
        return {"ended": row["ended_at"] is not None}
