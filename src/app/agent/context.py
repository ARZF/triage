import sqlite3

from app.agent.dictionaries import match


def build_context(connection: sqlite3.Connection, session_id: str) -> dict:
    current = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if current is None:
        raise KeyError(session_id)

    def intake(row):
        fields = {
            name: row[name][:500] if isinstance(row[name], str) else row[name]
            for name in ("age", "symptoms", "duration", "severity", "medications", "allergies")
        }
        fields["matched"] = {
            "symptoms": [entry["name_fa"][:500] for entry in match("symptoms", row["symptoms"] or "")],
            "medicines": [entry["name_fa"][:500] for entry in match("medicines", row["medications"] or "")],
        }
        return fields

    previous = connection.execute(
        """SELECT s.*, t.specialty_code AS triage_specialty
           FROM sessions s LEFT JOIN triage_results t ON t.session_id=s.id
           WHERE s.patient_id=? AND s.id<>? AND s.created_at<=? AND s.done=1 AND s.emergency=0
           ORDER BY s.created_at DESC, s.rowid DESC LIMIT 3""",
        (current["patient_id"], session_id, current["created_at"]),
    ).fetchall()
    return {
        "current": intake(current),
        "previous_visits": [
            {**intake(row), "date": row["created_at"][:10], "triage_specialty": row["triage_specialty"]}
            for row in previous
        ],
    }
