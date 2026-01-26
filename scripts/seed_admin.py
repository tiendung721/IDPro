import os
import uuid

from data_processing.user_store import UserStore
import common.security as security
from common.roles import Role
from dotenv import load_dotenv
load_dotenv()

def seed():
    email = os.getenv("ADMIN_EMAIL")
    pwd = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if not email or not pwd:
        print("Missing ADMIN_EMAIL / ADMIN_PASSWORD in env")
        return

    store = UserStore()
    if store.get_by_email(email):
        print("Admin already exists:", email)
        return

    store.create(
        user_id=str(uuid.uuid4()),
        email=email,
        password_hash=security.hash_password(pwd),
        role=Role.ADMIN.value,
    )
    print("Seeded admin:", email)

if __name__ == "__main__":
    seed()
