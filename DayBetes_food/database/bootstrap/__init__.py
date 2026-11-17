"""Schema bootstrap of db_init.py, split by area (audit H-11). Each module
holds the idempotent `_ensure_*` steps of its tables; init_db runs them in order."""
