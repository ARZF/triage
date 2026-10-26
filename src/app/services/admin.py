import json
import logging
from contextlib import closing
from uuid import uuid4

from app.agent.doctors import load_doctors
from app.core import db, security
from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.doctors import specialty

logger = logging.getLogger(__name__)


def seed_admin() -> None:
    settings = Settings()
    if not settings.admin_username:
        logger.info("admin_disabled")
        return
    if settings.admin_username in {doctor["id"] for doctor in load_doctors()["doctors"]}:
        raise ValueError("APP_ADMIN_USERNAME")
    encoded = security.hash_password(settings.admin_password)
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT role FROM users WHERE username=?", (settings.admin_username,)).fetchone()
        if row and row["role"] != "admin":
            raise ValueError("APP_ADMIN_USERNAME")
        connection.execute(
            """INSERT INTO users(id,role,username,password_hash,created_at) VALUES (?,'admin',?,?,?)
               ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash""",
            (uuid4().hex, settings.admin_username, encoded, db.utc_now()),
        )


def _item(row) -> dict:
    return {"id": row["id"], "name_fa": row["name_fa"], "specialty": specialty(row["specialty_code"]),
            "expertise": json.loads(row["expertise"]), "license_number": row["license_number"],
            "registered_at": row["created_at"], "status": row["review_status"],
            "reviewed_at": row["reviewed_at"], "review_note": row["review_note"]}


def list_doctors(status: str, limit: int, offset: int) -> dict:
    order = "created_at, id" if status == "pending" else "reviewed_at DESC, created_at DESC, id"
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN")
        total = connection.execute("SELECT COUNT(*) FROM doctors WHERE review_status=?", (status,)).fetchone()[0]
        rows = connection.execute(f"SELECT * FROM doctors WHERE review_status=? ORDER BY {order} LIMIT ? OFFSET ?",
                                  (status, limit, offset)).fetchall()
        return {"items": [_item(row) for row in rows], "total": total}


def review(doctor_id: str, admin_id: str, action: str, note: str | None = None) -> dict:
    allowed, target = {"approve": (("pending", "rejected", "suspended"), "approved"),
                       "reject": (("pending",), "rejected"), "suspend": (("approved",), "suspended")}[action]
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
        if row is None:
            raise ServiceError(404, "http_404", "Not Found")
        now = db.utc_now()
        # ponytail: keep verified equal to review_status='approved' in the same UPDATE; drop the redundant column on the next table rebuild.
        changed = connection.execute(
            f"""UPDATE doctors SET review_status=?, verified=?, reviewed_at=?, review_note=?,
                available=CASE WHEN ? THEN available ELSE 0 END,
                last_seen_at=CASE WHEN ? THEN last_seen_at ELSE NULL END
                WHERE id=? AND review_status IN ({','.join('?' for _ in allowed)})""",
            (target, target == "approved", now, None if action == "approve" else note,
             target == "approved", target == "approved", doctor_id, *allowed),
        ).rowcount
        if changed != 1:
            raise ServiceError(409, "invalid_transition", "Doctor review status changed or transition is not allowed")
        if action == "suspend":
            connection.execute("""UPDATE visit_requests SET ended_at=?, updated_at=?
                WHERE doctor_id=? AND status='accepted' AND ended_at IS NULL""", (now, now, doctor_id))
        connection.execute("""INSERT INTO admin_audit(admin_user_id,action,doctor_id,from_status,to_status,note,created_at)
            VALUES (?,?,?,?,?,?,?)""", (admin_id, action, doctor_id, row["review_status"], target,
                                       None if action == "approve" else note, now))
        return _item(connection.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone())


def audit(limit: int) -> dict:
    with closing(db.connect()) as connection:
        rows = connection.execute("""SELECT a.id,a.action,a.doctor_id,d.name_fa AS doctor_name_fa,
            a.from_status,a.to_status,a.note,a.created_at FROM admin_audit a
            LEFT JOIN doctors d ON d.id=a.doctor_id ORDER BY a.created_at DESC,a.id DESC LIMIT ?""", (limit,)).fetchall()
        return {"items": [dict(row) for row in rows]}
