# graph_service.py
import os
import msal
from urllib.parse import urljoin
from dotenv import load_dotenv

load_dotenv()

# --- Azure App Konfig aus .env ---
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")  # z.B. 'organizations' oder deine Tenant-ID
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_PATH = "/auth/callback"  # muss im Azure-Portal exakt hinterlegt sein!
SCOPES = ["openid", "profile", "offline_access", "User.Read", "Mail.Send"]

def _msal_app():
    return msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

def _redirect_uri(request):
    # http(s)://host:port + REDIRECT_PATH
    base = str(request.base_url).rstrip("/")
    return urljoin(base + "/", REDIRECT_PATH.lstrip("/"))

def build_auth_url(request):
    app = _msal_app()
    return app.get_authorization_request_url(SCOPES, redirect_uri=_redirect_uri(request))

def exchange_code_for_token(request, code: str):
    app = _msal_app()
    token = app.acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=_redirect_uri(request))
    if "access_token" not in token:
        # token enthält dann "error" / "error_description"
        raise RuntimeError(f"OAuth Fehler: {token.get('error')}: {token.get('error_description')}")
    return token
