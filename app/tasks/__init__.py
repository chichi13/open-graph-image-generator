# app/tasks/__init__.py
# Make tasks defined in modules within this directory importable via the package.

from .screenshot import generate_screenshot_task

# If you add more tasks in other files (e.g., cleanup.py), import them here too:
# from .cleanup import cleanup_old_records
