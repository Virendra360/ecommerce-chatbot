from pathlib import Path
import sqlite3
from typing import TypedDict


class UserRecord(TypedDict):
    email: str
    full_name: str
    role: str


def authenticate_user(email, password, role=None):
    root = Path(__file__).resolve().parents[2]
    db_path = root / "ecommerce.db"

    query = """
        SELECT email, full_name, role
        FROM users
        WHERE email = ? AND password = ?
    """
    params = [email, password]

    if role:
        query += " AND role = ?"
        params.append(role)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(query, params).fetchone()

    if row is None:
        return None

    return dict(row)