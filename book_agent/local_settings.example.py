"""Optional local defaults for the web server.

Copy this file to `book_agent/local_settings.py` if you want defaults outside
the database-backed web settings. Never commit the copied file.
"""

DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_REASONING_EFFORT = "high"
DEEPSEEK_THINKING_TYPE = "enabled"
