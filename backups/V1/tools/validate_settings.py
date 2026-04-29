import os
import importlib.util
import sys

# lade settings.py dynamisch
settings_path = os.path.join(os.path.dirname(__file__), "..", "settings.py")
settings_path = os.path.normpath(settings_path)

spec = importlib.util.spec_from_file_location("app_settings", settings_path)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except Exception as e:
    print("Fehler beim Importieren von settings.py:")
    raise

def exists(p):
    return os.path.exists(p)

print("== Settings-Check ==")
print("TENANT_ID:", getattr(module, "TENANT_ID", None))
print("CLIENT_ID:", getattr(module, "CLIENT_ID", None))
cs = getattr(module, "CLIENT_SECRET", None)
print("CLIENT_SECRET set:", bool(cs))
print("CLIENT_SECRET length:", len(cs) if cs else 0)
print("CLIENT_SECRET_ID:", getattr(module, "CLIENT_SECRET_ID", "(nicht gesetzt)"))
print("REDIRECT_URI:", getattr(module, "REDIRECT_URI", None))
print("AUTHORITY:", getattr(module, "AUTHORITY", None))
print("SCOPES:", getattr(module, "SCOPES", None))
print()
print("HTML_TEMPLATE_PATH:", getattr(module, "HTML_TEMPLATE_PATH", None), "-> exists:", exists(getattr(module, "HTML_TEMPLATE_PATH", "")))
print("ASSETS_DIR:", getattr(module, "ASSETS_DIR", None), "-> exists:", exists(getattr(module, "ASSETS_DIR", "")))
print()
# einfache Prüfungen
if "DEIN" in (module.TENANT_ID or "") or "DEIN" in (module.CLIENT_ID or ""):
    print("WARNUNG: Tenant/Client-ID sehen wie Platzhalter aus.")
if not cs:
    print("FEHLER: CLIENT_SECRET ist leer.")
print("== Ende ==")