# auth.py
import msal
import settings

def _cca() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        settings.CLIENT_ID,
        authority=settings.AUTHORITY,
        client_credential=settings.CLIENT_SECRET,
    )

def get_signin_url(state: str) -> str:
    cca = _cca()
    return cca.get_authorization_request_url(
        scopes=settings.AUTH_SCOPES_LOGIN,     # <- WICHTIG: z.B. User.Read
        redirect_uri=settings.REDIRECT_URI,
        state=state,
        prompt="select_account",
    )

def exchange_code_for_token(code: str) -> dict:
    cca = _cca()
    result = cca.acquire_token_by_authorization_code(
        code,
        scopes=settings.AUTH_SCOPES_LOGIN,     # <- WICHTIG: z.B. User.Read
        redirect_uri=settings.REDIRECT_URI,
    )
    return result
