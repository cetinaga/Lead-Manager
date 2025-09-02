# main.py (Final - Korrigierter Login-Redirect)
from __future__ import annotations

import os
import datetime as dt
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

import extractor
import database as db

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from auth import get_signin_url, exchange_code_for_token
from notifications import send_email_via_graph

app = FastAPI()
templates = Jinja2Templates(directory="templates")
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

SESSION: dict = {}
STATUSES = getattr(db, "STATUSES", ["neu","nicht erreicht","Termin","RiVo","in Bearbeitung","Abgelegt"])

def _ctx(request: Request, **extra):
    return {"request": request, **extra}

def normalize_anrede(value: Optional[str]) -> str:
    if value is None: return "-"
    v = str(value).strip().lower()
    if v in {"-", "–", "—", ""}: return "-"
    if v.startswith("frau") or v.startswith("fr"): return "Frau"
    if v.startswith("herr") or v.startswith("hr"): return "Herr"
    return "-"

def _format_call_note(now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now()
    return f"({now.strftime('%d.%m.')} - {now.strftime('%H:%M')})"

def _format_email_note(now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now()
    return f"(E-Mail versendet {now.strftime('%d.%m')})"

@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    import traceback
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return HTMLResponse(f"<h1>Fehler</h1><pre>{tb}</pre>", status_code=500)

@app.get("/")
def home(request: Request, status: Optional[str] = None, q: Optional[str] = None):
    leads = db.list_leads(status=status, q=q)
    counts = db.counts_by_status()
    return templates.TemplateResponse(
        "index.html",
        _ctx(request, leads=leads, counts=counts, current_status=status, search_term=q or ""),
    )

@app.get("/login")
def login(request: Request):
    if not get_signin_url:
        return PlainTextResponse("Login nicht konfiguriert.", status_code=501)
    if 'redirect_after_login' not in SESSION and request.headers.get("referer"):
        SESSION['redirect_after_login'] = request.headers.get("referer")
    return RedirectResponse(get_signin_url(state="local"), status_code=302)

@app.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, error: str | None = None, state: str | None = None):
    if error:
        return templates.TemplateResponse("error.html", _ctx(request, error=f"Login-Fehler: {error}"), status_code=400)
    if not exchange_code_for_token:
        return templates.TemplateResponse("error.html", _ctx(request, error="Auth nicht konfiguriert"), status_code=500)
    result = exchange_code_for_token(code=code)
    if "access_token" not in result:
        return templates.TemplateResponse("error.html", _ctx(request, error=str(result)), status_code=400)
    SESSION["access_token"] = result["access_token"]
    redirect_url = SESSION.pop('redirect_after_login', '/')
    return RedirectResponse(redirect_url, status_code=302)

@app.post("/leads/{lead_id}/update_anrede")
def update_anrede(lead_id: int, request: Request, anrede: str = Form("-"), redirect_url: str = Form("/")):
    db.update_lead(lead_id, anrede=normalize_anrede(anrede))
    return RedirectResponse(redirect_url or "/", status_code=303)

@app.post("/leads/{lead_id}/update_note")
def update_note(lead_id: int, request: Request, notes: str = Form(""), redirect_url: str = Form("/")):
    db.update_lead(lead_id, notes=notes)
    return RedirectResponse(redirect_url or "/", status_code=303)

@app.post("/leads/{lead_id}/update_status")
def update_status(lead_id: int, request: Request, status: str = Form("neu"), redirect_url: str = Form("/")):
    db.update_lead(lead_id, status=status)
    return RedirectResponse(redirect_url or "/", status_code=303)

@app.post("/leads/{lead_id}/notify/email")
def notify_email(lead_id: int, request: Request, redirect_url: str = Form("/")):
    token = SESSION.get("access_token")
    # KORREKTUR: Leitet zum Login um, falls kein Token vorhanden ist.
    if not token:
        # Merken, dass wir nach dem Login hierher zurückwollen.
        SESSION['redirect_after_login'] = redirect_url
        # Umleiten mit Status 303, was den Browser zu einer GET-Anfrage zwingt.
        return RedirectResponse(url="/login", status_code=303)

    lead = db.get_lead(lead_id)
    if not lead or not lead.get("email"):
        db.append_note(lead_id, "(E-Mail NICHT gesendet – keine Adresse)")
        return RedirectResponse(redirect_url or "/", status_code=303)

    try:
        send_email_via_graph(
            access_token=token,
            to_email=lead["email"],
            subject=os.getenv("MAIL_SUBJECT", "Ihre Anfrage bei WbV Onlinemakler GmbH"),
            anrede=lead.get("anrede", ""),
            nachname=lead.get("nachname", ""),
            reply_to=os.getenv("MAIL_REPLY_TO")
        )
    except Exception as e:
        db.append_note(lead_id, f"(E-Mail FEHLGESCHLAGEN: {e})")
    else:
        db.mark_email_sent(lead_id)
        db.append_note(lead_id, _format_email_note())

    return RedirectResponse(redirect_url or "/", status_code=303)

@app.post("/leads/{lead_id}/log_call")
def log_call(lead_id: int):
    note = _format_call_note()
    db.append_note(lead_id, note)
    return JSONResponse({"ok": True, "note": note})

@app.post("/leads/bulk_delete")
async def bulk_delete(request: Request):
    form = await request.form()
    ids = [int(v) for k, v in form.multi_items() if k == "selected"]
    db.bulk_delete(ids)
    redirect_url = form.get("redirect_url") or "/"
    return RedirectResponse(redirect_url, status_code=303)

@app.get("/leads/{lead_id}/edit")
def edit_lead(lead_id: int, request: Request):
    lead = db.get_lead(lead_id)
    if not lead: return HTMLResponse("<p>Lead nicht gefunden.</p>", status_code=404)
    def esc(v: Optional[str]) -> str:
        s = (v or ""); return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    html = f"""
    <form id="edit-form" action="/leads/{lead_id}/save" method="post">
      <div class="list">
        <div class="row">
          <input class="input" name="anrede"  value="{esc(lead.get('anrede'))}" placeholder="Anrede" style="max-width:120px">
          <input class="input" name="vorname" value="{esc(lead.get('vorname'))}" placeholder="Vorname">
          <input class="input" name="nachname"value="{esc(lead.get('nachname'))}" placeholder="Nachname">
        </div>
        <div class="row">
          <input class="input" name="geburtstag" value="{esc(lead.get('geburtstag'))}" placeholder="TT.MM.JJJJ" style="max-width:160px">
          <input class="input" name="telefon"    value="{esc(lead.get('telefon'))}" placeholder="Telefon">
          <input class="input" name="email"      value="{esc(lead.get('email'))}"   placeholder="E-Mail">
        </div>
        <div class="row">
          <input class="input" name="strasse" value="{esc(lead.get('strasse'))}" placeholder="Straße + Nr.">
          <input class="input" name="plz"      value="{esc(lead.get('plz'))}"    placeholder="PLZ" style="max-width:150px">
          <input class="input" name="stadt"    value="{esc(lead.get('stadt'))}"   placeholder="Ort">
        </div>
        <div class="row">
          <textarea class="input grow" name="notes" placeholder="Notizen…">{esc(lead.get('notes'))}</textarea>
        </div>
        <div class="row">
          <select class="input" name="status" style="max-width:220px">
            {''.join(f'<option value="{s}" {"selected" if s==lead.get("status") else ""}>{s}</option>' for s in STATUSES)}
          </select>
          <button class="btn" type="submit">Speichern</button>
        </div>
      </div>
    </form>
    """
    return HTMLResponse(html)

@app.post("/leads/{lead_id}/save")
async def save_lead(lead_id: int, request: Request):
    form = await request.form()
    db.update_lead(
        lead_id, anrede=normalize_anrede(form.get("anrede")), vorname=form.get("vorname"),
        nachname=form.get("nachname"), geburtstag=form.get("geburtstag"), telefon=form.get("telefon"),
        email=form.get("email"), strasse=form.get("strasse"), plz=form.get("plz"),
        stadt=form.get("stadt"), notes=form.get("notes"), status=form.get("status"),
    )
    return JSONResponse({"ok": True})

@app.post("/upload")
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    Path("data").mkdir(parents=True, exist_ok=True)
    created, updated_or_existing, errors = 0, 0, []
    for f in files:
        tmp_path: Optional[Path] = None
        try:
            tmp_path = Path("data") / f"upload_{dt.datetime.now().timestamp()}_{f.filename}"
            with open(tmp_path, "wb") as out: out.write(await f.read())
            result = extractor.extract_leads_ex(str(tmp_path))
            leads = result.get("leads", []); warns = result.get("warnings", [])
            if not leads:
                errors.append(f"{f.filename}: " + (warns[0] if warns else "Keine Leads erkannt"))
                continue
            for raw in leads:
                lead = {
                    "anrede": normalize_anrede(raw.get("anrede")), "vorname": raw.get("vorname"),
                    "nachname": raw.get("nachname"), "geburtstag": raw.get("geburtstag"),
                    "telefon": raw.get("telefon"), "email": raw.get("email"),
                    "strasse": raw.get("strasse") or raw.get("straße"), "plz": raw.get("plz"),
                    "stadt": raw.get("stadt"), "notes": raw.get("notes") or "", "status": raw.get("status") or "neu",
                }
                existed = (db.find_by_email(lead["email"]) if lead.get("email") else None) \
                       or (db.find_by_phone(lead["telefon"]) if lead.get("telefon") else None)
                db.upsert_import(lead)
                if existed: updated_or_existing += 1
                else: created += 1
        except Exception as e: errors.append(f"{f.filename}: {e}")
        finally:
            if tmp_path and tmp_path.exists():
                try: os.remove(tmp_path)
                except Exception: pass
    return JSONResponse({"created": created, "updated_or_existing": updated_or_existing, "errors": errors})

@app.get("/admin/normalize_phones")
def admin_normalize_phones():
    changed = db.normalize_all_phones()
    return {"ok": True, "changed": changed}

@app.get("/health")
def health():
    return {"ok": True}