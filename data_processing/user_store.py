import sqlite3
import time
from typing import Optional, Dict, Any, List


class UserStore:
    """
    One table for both:
      - ADMIN: email + password_hash (+ role)
      - USER (quick): username-only, no password required

    Table columns are kept backward-compatible with your existing admin auth.
    """

    def __init__(self, db_path: str = "session_store.sqlite3"):
        self.db_path = db_path
        self._init()

    def _conn(self):
        # Using row_factory makes result mapping easier and safer
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        """
        Auto-migrate:
        - Ensure table exists
        - Rebuild if legacy email NOT NULL
        - Add missing columns
        - Create indexes
        """
        with self._conn() as con:
            # 1) Ensure base table exists
            con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                username TEXT,
                password_hash TEXT,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                last_login_at INTEGER
            )
            """)
            con.commit()

            # Helper to read schema
            def read_colmap():
                cols = con.execute("PRAGMA table_info(users)").fetchall()
                return {row["name"]: row for row in cols}

            colmap = read_colmap()

            def has_col(name: str) -> bool:
                return name in colmap

            def is_not_null(name: str) -> bool:
                return has_col(name) and int(colmap[name]["notnull"]) == 1

            # 2) Rebuild if legacy schema has email NOT NULL
            if is_not_null("email"):
                existing = set(colmap.keys())

                con.execute("BEGIN")
                con.execute("""
                CREATE TABLE IF NOT EXISTS users_new (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    username TEXT,
                    password_hash TEXT,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    last_login_at INTEGER
                )
                """)

                select_username = "username" if "username" in existing else "NULL AS username"
                select_is_active = "is_active" if "is_active" in existing else "1 AS is_active"
                select_last_login = "last_login_at" if "last_login_at" in existing else "NULL AS last_login_at"

                con.execute(f"""
                INSERT INTO users_new (id, email, username, password_hash, role, is_active, created_at, last_login_at)
                SELECT
                    id,
                    email,
                    {select_username},
                    password_hash,
                    role,
                    {select_is_active},
                    created_at,
                    {select_last_login}
                FROM users
                """)

                con.execute("DROP TABLE users")
                con.execute("ALTER TABLE users_new RENAME TO users")
                con.execute("COMMIT")

                colmap = read_colmap()

            # 3) Add missing columns
            def add_col(sql: str):
                con.execute(sql)
                con.commit()

            if "username" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN username TEXT")
                colmap = read_colmap()

            if "is_active" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
                colmap = read_colmap()

            if "last_login_at" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN last_login_at INTEGER")
                colmap = read_colmap()

            if "password_hash" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN password_hash TEXT")
                colmap = read_colmap()

            if "role" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'USER'")
                colmap = read_colmap()

            if "email" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN email TEXT")
                colmap = read_colmap()

            if "created_at" not in colmap:
                add_col("ALTER TABLE users ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
                colmap = read_colmap()

            # 4) Indexes
            try:
                con.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
                con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username) WHERE username IS NOT NULL")
                con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users(email) WHERE email IS NOT NULL")
                con.commit()
            except Exception:
                # keep silent to avoid breaking app on old SQLite
                pass

    # -------------------------
    # Common getters
    # -------------------------
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").strip()
        if not email:
            return None
        with self._conn() as con:
            row = con.execute(
                "SELECT id,email,username,password_hash,role,is_active,created_at,last_login_at "
                "FROM users WHERE email=?",
                (email,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        username = (username or "").strip()
        if not username:
            return None
        with self._conn() as con:
            row = con.execute(
                "SELECT id,email,username,password_hash,role,is_active,created_at,last_login_at "
                "FROM users WHERE username=?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        user_id = (user_id or "").strip()
        if not user_id:
            return None
        with self._conn() as con:
            row = con.execute(
                "SELECT id,email,username,password_hash,role,is_active,created_at,last_login_at "
                "FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    # -------------------------
    # Create users
    # -------------------------
    def create_admin(self, user_id: str, email: str, password_hash: str, role: str = "ADMIN") -> None:
        role_u = (role or "ADMIN").upper().strip()
        if role_u != "ADMIN":
            raise ValueError("create_admin_role_must_be_ADMIN")

        email = (email or "").strip()
        if not email:
            raise ValueError("admin_email_required")

        password_hash = (password_hash or "").strip()
        if not password_hash:
            raise ValueError("admin_password_required")

        now = int(time.time())
        with self._conn() as con:
            con.execute(
                "INSERT INTO users(id,email,password_hash,role,is_active,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, email, password_hash, "ADMIN", 1, now),
            )
            con.commit()

    # Backward compatible alias (your existing code calls create())
    def create(self, user_id: str, email: str, password_hash: str, role: str) -> None:
        self.create_admin(user_id=user_id, email=email, password_hash=password_hash, role=role)

    def create_user_username_only(self, user_id: str, username: str, role: str = "USER", is_active: int = 1) -> None:
        role_u = (role or "USER").upper().strip()
        if role_u != "USER":
            # Không cho tạo ADMIN kiểu username-only
            raise ValueError("admin_requires_password")

        username = (username or "").strip()
        if not username:
            raise ValueError("username_required")

        now = int(time.time())
        with self._conn() as con:
            con.execute(
                "INSERT INTO users(id, username, role, is_active, created_at) VALUES(?,?,?,?,?)",
                (user_id, username, "USER", int(is_active), now),
            )
            con.commit()

    # -------------------------
    # List + update for Admin UI
    # -------------------------
    def list_users(self, q: str = "", role: str = "ALL", active: str = "ALL") -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []

        q = (q or "").strip()
        if q:
            where.append("(username LIKE ? OR email LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])

        role = (role or "ALL").upper()
        if role != "ALL":
            where.append("role = ?")
            params.append(role)

        active = (active or "ALL").upper()
        if active == "ACTIVE":
            where.append("is_active = 1")
        elif active == "INACTIVE":
            where.append("is_active = 0")

        sql = (
            "SELECT id,email,username,role,is_active,created_at,last_login_at "
            "FROM users"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"

        with self._conn() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_user(
        self,
        user_id: str,
        *,
        role: Optional[str] = None,
        is_active: Optional[int] = None,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        user_id = (user_id or "").strip()
        if not user_id:
            raise ValueError("user_id_required")

        # Lấy user hiện tại để enforce rule khi đổi role
        current = self.get_by_id(user_id)
        if not current:
            raise ValueError("user_not_found")

        # Chuẩn hoá input
        new_role = (role or "").upper().strip() if role is not None else None
        new_email = (email.strip() if isinstance(email, str) else email)  # giữ None nếu None
        new_username = (username.strip() if isinstance(username, str) else username)

        # =========================
        # Enforce: ADMIN phải có email + password_hash
        # - update_user KHÔNG nhận password_hash, nên chỉ cho phép lên ADMIN nếu password_hash đã tồn tại
        # =========================
        if new_role == "ADMIN":
            # email hiệu lực = email mới (nếu truyền) hoặc email hiện tại
            effective_email = (new_email if new_email is not None else (current.get("email") or "")).strip()
            if not effective_email:
                raise ValueError("admin_email_required")

            # password_hash phải tồn tại sẵn trong DB
            if not (current.get("password_hash") or "").strip():
                raise ValueError("admin_password_required")

        # (Tuỳ chọn) Nếu bạn muốn cứng hơn: ADMIN không được xoá email
        if (current.get("role") or "").upper() == "ADMIN" and email is not None:
            if not (new_email or "").strip():
                raise ValueError("admin_email_required")

        sets = []
        params: List[Any] = []

        if new_role is not None:
            sets.append("role = ?")
            params.append(new_role)

        if is_active is not None:
            sets.append("is_active = ?")
            params.append(int(is_active))

        if email is not None:
            sets.append("email = ?")
            params.append(new_email if new_email else None)

        if username is not None:
            sets.append("username = ?")
            params.append(new_username if new_username else None)

        if not sets:
            return

        params.append(user_id)

        with self._conn() as con:
            con.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
            con.commit()

    def touch_login(self, user_id: str) -> None:
        user_id = (user_id or "").strip()
        if not user_id:
            return
        now = int(time.time())
        with self._conn() as con:
            con.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
            con.commit()

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        user_id = (user_id or "").strip()
        if not user_id:
            raise ValueError("user_id_required")
        password_hash = (password_hash or "").strip()
        if not password_hash:
            raise ValueError("password_required")

        with self._conn() as con:
            con.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            con.commit()
