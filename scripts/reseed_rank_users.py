#!/usr/bin/env python3
"""Reseed organizational rank accounts and purge legacy demo users."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

os.environ.setdefault("ENTERPRISE_AUTH", "true")
os.environ.setdefault("SEED_DEMO_USERS", "true")

from services.enterprise.db import init_enterprise_db
from services.enterprise.rbac import clear_rbac_cache
from services.enterprise.users import migrate_legacy_user_roles, purge_legacy_demo_users, seed_admin_user, seed_demo_users

if __name__ == "__main__":
    clear_rbac_cache()
    init_enterprise_db()
    seed_admin_user()
    migrated = migrate_legacy_user_roles()
    removed = purge_legacy_demo_users()
    created = seed_demo_users()
    print(f"Migrated legacy roles: {migrated}")
    print(f"Removed legacy users: {removed}")
    print(f"Created rank users: {created}")
    print("Done. Demo rank passwords: Socmint@CID2026!Admin")
    print("Admin password from ADMIN_PASSWORD env (default Socmint@CID2026!Admin)")
