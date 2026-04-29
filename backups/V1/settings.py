# settings.py
# === Azure AD / Graph ===
TENANT_ID     = "8872d607-5eb2-42a1-8008-3a4604d31891"
CLIENT_ID     = "06c27266-6bd2-4809-8d9e-ce340761d871"
CLIENT_SECRET = "tBE8Q~apqzZdYmXrbYhZNT5RzRjOpc~0UivEicpN"

REDIRECT_URI  = "http://localhost:8000/auth/callback"
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"

# Für Benutzer-Login MUSS ein Graph-Scope dabei sein:
AUTH_SCOPES_LOGIN = ["User.Read", "Mail.Send"]

# Für App-Aufrufe (Client-Credentials):
GRAPH_SCOPE_APP_DEFAULT = ["https://graph.microsoft.com/.default"]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Pfade für die E-Mail-Vorlage
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMAIL_TEMPLATES_DIR = os.path.join(BASE_DIR, "email_templates")
HTML_TEMPLATE_PATH  = os.path.join(EMAIL_TEMPLATES_DIR, "vorlage_anfrage.html")
ASSETS_DIR          = os.path.join(EMAIL_TEMPLATES_DIR, "vorlage_anfrage-Dateien")
