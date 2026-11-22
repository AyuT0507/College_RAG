import os
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.database import Base, SessionLocal, engine
from app.models import User
from app.auth.local_auth import hash_password

def seed_admin(email: str = "24bcs252@iiitdmj.ac.in", password: str = "Admin@iiitdmj2026"):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        hashed = hash_password(password)
        if user:
            user.role = "admin"
            user.password_hash = hashed
            user.display_name = "Ayush (Admin)"
            print(f"Updated existing user '{email}' to role 'admin'.")
        else:
            admin_user = User(
                email=email.lower().strip(),
                role="admin",
                display_name="Ayush (Admin)",
                password_hash=hashed,
            )
            db.add(admin_user)
            print(f"Created new admin user '{email}'.")
        db.commit()
    print(f"Successfully configured '{email}' as admin!")
    print(f"Default password: {password}")

if __name__ == "__main__":
    pwd = sys.argv[1] if len(sys.argv) > 1 else "Admin@iiitdmj2026"
    seed_admin(password=pwd)
