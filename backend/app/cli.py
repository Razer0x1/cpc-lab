"""CLI: python -m app.cli seed | create-admin TOKEN etc. Keep idempotent."""
from __future__ import annotations

import sys

from .database import Base, SessionLocal, engine
from .seed import seed_db


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if action == "seed":
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_db(db)
            db.commit()
        print("Database seeded (idempotent).")
        return 0
    if action == "create-tables":
        Base.metadata.create_all(bind=engine)
        print("Tables created.")
        return 0
    print(f"Unknown action: {action}. Available: seed, create-tables")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
