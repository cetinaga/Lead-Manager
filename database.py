# database.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Dict, Any, List
import json
from datetime import datetime, date
import re

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "leads.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATUSES = ["neu", "nicht erreicht", "Termin", "RiVo", "in Bearbeitung", "Abgelegt"]

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def init_db() -> None:
    con = connect()
    # Basistabelle (mit neuen Adressfeldern)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          anrede        TEXT,
          vorname       TEXT,
          nachname      TEXT,
          geburtstag    TEXT,
          telefon       TEXT,
          email         TEXT,
          strasse       TEXT,
          plz           TEXT,
          stadt         TEXT,
          notes         TEXT DEFAULT '',
          status        TEXT DEFAULT 'neu',
          -- Analyse-Felder (optional, werden bei Migration ergänzt)
          start_date    TEXT,
          profession    TEXT,
          civil_servant_status TEXT,
          employer      TEXT,
          subsidy_entitlement TEXT,
          previous_insurance TEXT,
          previous_insurance_name TEXT,
          gkv_type      TEXT,
          pkv_since     TEXT,
          marital_status TEXT,
          children      INTEGER,
          spouse_is_civil_servant INTEGER,
          children_co_insured INTEGER,
          consultant_assessment TEXT,
          email_sent_at TEXT,
          created_at    TEXT NOT NULL,
          updated_at    TEXT NOT NULL
        )
        """
    )
    # Migration: falls alte DB ohne Adressspalten vorhanden ist -> hinzufügen
    cols = {r["name"] for r in con.execute("PRAGMA table_info(leads)").fetchall()}
    for col, ddl in [
        ("strasse", "ALTER TABLE leads ADD COLUMN strasse TEXT"),
        ("plz",     "ALTER TABLE leads ADD COLUMN plz TEXT"),
        ("stadt",   "ALTER TABLE leads ADD COLUMN stadt TEXT"),
        ("start_date", "ALTER TABLE leads ADD COLUMN start_date TEXT"),
        ("profession", "ALTER TABLE leads ADD COLUMN profession TEXT"),
        ("civil_servant_status", "ALTER TABLE leads ADD COLUMN civil_servant_status TEXT"),
        ("employer", "ALTER TABLE leads ADD COLUMN employer TEXT"),
        ("subsidy_entitlement", "ALTER TABLE leads ADD COLUMN subsidy_entitlement TEXT"),
        ("previous_insurance", "ALTER TABLE leads ADD COLUMN previous_insurance TEXT"),
        ("previous_insurance_name", "ALTER TABLE leads ADD COLUMN previous_insurance_name TEXT"),
        ("gkv_type", "ALTER TABLE leads ADD COLUMN gkv_type TEXT"),
        ("pkv_since", "ALTER TABLE leads ADD COLUMN pkv_since TEXT"),
        ("marital_status", "ALTER TABLE leads ADD COLUMN marital_status TEXT"),
        ("children", "ALTER TABLE leads ADD COLUMN children INTEGER"),
        ("spouse_is_civil_servant", "ALTER TABLE leads ADD COLUMN spouse_is_civil_servant INTEGER"),
        ("children_co_insured", "ALTER TABLE leads ADD COLUMN children_co_insured INTEGER"),
        ("consultant_assessment", "ALTER TABLE leads ADD COLUMN consultant_assessment TEXT"),
    ]:
        if col not in cols:
            con.execute(ddl)
    con.commit()
    # Versioning table
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_versions (
          lead_id     INTEGER NOT NULL,
          version     INTEGER NOT NULL,
          data        TEXT NOT NULL,
          changed_at  TEXT NOT NULL,
          PRIMARY KEY (lead_id, version),
          FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        )
        """
    )
    con.commit()
    # Initialize base versions for existing leads if none present
    try:
        row = con.execute("SELECT COUNT(*) AS c FROM lead_versions").fetchone()
        if not row or int(row["c"]) == 0:
            ids = [r["id"] for r in con.execute("SELECT id FROM leads").fetchall()]
            con.close()
            for lead_id in ids:
                save_version(lead_id)
            con = connect()
    except Exception:
        pass
    con.close()

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _parse_age(geburtstag: Optional[str]) -> Optional[int]:
    if not geburtstag:
        return None
    s = geburtstag.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt).date()
            today = date.today()
            age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
            return age
        except ValueError:
            pass
    return None

def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["age"] = _parse_age(d.get("geburtstag"))
    return d

# ---------- Telefon-Normalisierung ----------

def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """
    Immer '+49' + Nummer (ohne führende '0' oder doppelte '49'), soweit erkennbar.
    Beispiele:
      '0176 6099 6924'   -> '+4917660996924'
      '04917660996924'   -> '+4917660996924'
      '0049 176...'      -> '+4917660996924'
      '+49 0176 ...'     -> '+4917660996924'
      '49 176 ...'       -> '+4917660996924'
      '+43 660 ...'      -> '+43660...' (andere Länder werden nur bereinigt)
    """
    if not raw:
        return None

    s = str(raw).strip()
    s = re.sub(r"[()\s/,-]+", "", s)  # Leerzeichen, Klammern, /, - entfernen

    if s.startswith("00"):
        s = "+" + s[2:]

    if s.startswith("+"):
        if s.startswith("+49"):
            rest = re.sub(r"\D", "", s[3:])
            rest = re.sub(r"^0+", "", rest)
            if rest.startswith("49"):
                rest = rest[2:]
            return "+49" + rest if rest else "+49"
        else:
            return "+" + re.sub(r"\D", "", s[1:])

    digits = re.sub(r"\D", "", s)

    if digits.startswith("49"):
        rest = re.sub(r"^49", "", digits)
        rest = re.sub(r"^0+", "", rest)
        return "+49" + rest if rest else "+49"

    if digits.startswith("0"):
        rest = re.sub(r"^0+", "", digits)
        if rest.startswith("49"):
            rest = rest[2:]
        return "+49" + rest if rest else "+49"

    return "+49" + digits if digits else None

def normalize_all_phones() -> int:
    con = connect()
    rows = con.execute("SELECT id, telefon FROM leads").fetchall()
    changed = 0
    for r in rows:
        old = r["telefon"] or ""
        new = normalize_phone(old) or ""
        if old != new:
            con.execute("UPDATE leads SET telefon = ?, updated_at = ? WHERE id = ?", (new, _now(), r["id"]))
            changed += 1
    con.commit()
    con.close()
    return changed

# ---------- CRUD ----------

def list_leads(status: Optional[str] = None, q: Optional[str] = None) -> List[Dict[str, Any]]:
    con = connect()
    sql = "SELECT * FROM leads"
    params: List[Any] = []
    where = []
    if status:
        where.append("status = ?")
        params.append(status)
    if q:
        like = f"%{q}%"
        where.append("("
                     "vorname LIKE ? OR nachname LIKE ? OR email LIKE ? OR telefon LIKE ? OR "
                     "strasse LIKE ? OR plz LIKE ? OR stadt LIKE ? OR notes LIKE ?)"
        )
        params += [like, like, like, like, like, like, like, like]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [row_to_dict(r) for r in rows]

def get_lead(lead_id: int) -> Optional[Dict[str, Any]]:
    con = connect()
    row = con.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    con.close()
    return row_to_dict(row) if row else None

def create_lead(data: Dict[str, Any]) -> int:
    con = connect()
    now = _now()
    phone = normalize_phone(data.get("telefon"))
    cur = con.execute(
        """
        INSERT INTO leads (anrede, vorname, nachname, geburtstag, telefon, email, strasse, plz, stadt, notes, status, profession, employer, created_at, updated_at)
        VALUES (:anrede, :vorname, :nachname, :geburtstag, :telefon, :email, :strasse, :plz, :stadt, :notes, :status, :profession, :employer, :created_at, :updated_at)
        """,
        {
            "anrede": data.get("anrede"),
            "vorname": data.get("vorname"),
            "nachname": data.get("nachname"),
            "geburtstag": data.get("geburtstag"),
            "telefon": phone,
            "email": data.get("email"),
            "strasse": data.get("strasse"),
            "plz": data.get("plz"),
            "stadt": data.get("stadt"),
            "notes": data.get("notes") or "",
            "status": data.get("status") or "neu",
            "profession": data.get("profession"),
            "employer": data.get("employer"),
            "created_at": now,
            "updated_at": now,
        },
    )
    lead_id = cur.lastrowid
    con.commit()
    con.close()
    # Save initial version
    save_version(lead_id)
    return lead_id

def update_lead(lead_id: int, **fields) -> Optional[Dict[str, Any]]:
    if not fields:
        return get_lead(lead_id)
    allowed = {"anrede","vorname","nachname","geburtstag","telefon","email","strasse","plz","stadt","notes","status","email_sent_at",
               "start_date","profession","civil_servant_status","employer","subsidy_entitlement",
               "previous_insurance","previous_insurance_name","gkv_type","pkv_since",
               "marital_status","children","spouse_is_civil_servant","children_co_insured","consultant_assessment"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "telefon" in fields:
        fields["telefon"] = normalize_phone(fields.get("telefon"))
    if not fields:
        return get_lead(lead_id)
    fields["updated_at"] = _now()
    con = connect()
    cols = ", ".join([f"{k} = :{k}" for k in fields.keys()])
    fields["id"] = lead_id
    con.execute(f"UPDATE leads SET {cols} WHERE id = :id", fields)
    con.commit()
    con.close()
    # Save new version after update
    save_version(lead_id)
    return get_lead(lead_id)

def append_note(lead_id: int, line: str) -> None:
    con = connect()
    row = con.execute("SELECT notes FROM leads WHERE id = ?", (lead_id,)).fetchone()
    now_notes = (row["notes"] if row and row["notes"] else "").rstrip()
    new_notes = (now_notes + ("\n" if now_notes else "") + line).strip()
    con.execute("UPDATE leads SET notes = ?, updated_at = ? WHERE id = ?", (new_notes, _now(), lead_id))
    con.commit()
    con.close()
    save_version(lead_id)

def mark_email_sent(lead_id: int) -> None:
    con = connect()
    con.execute("UPDATE leads SET email_sent_at = ?, updated_at = ? WHERE id = ?", (_now(), _now(), lead_id))
    con.commit()
    con.close()
    save_version(lead_id)

def bulk_delete(ids: Iterable[int]) -> int:
    ids = list(ids)
    if not ids:
        return 0
    con = connect()
    q = f"DELETE FROM leads WHERE id IN ({','.join(['?']*len(ids))})"
    cur = con.execute(q, ids)
    con.commit()
    con.close()
    return cur.rowcount

def find_by_email(email: str) -> Optional[Dict[str, Any]]:
    con = connect()
    row = con.execute("SELECT * FROM leads WHERE email = ?", (email,)).fetchone()
    con.close()
    return row_to_dict(row) if row else None

def find_by_phone(telefon: str) -> Optional[Dict[str, Any]]:
    norm = normalize_phone(telefon)
    con = connect()
    row = con.execute("SELECT * FROM leads WHERE telefon = ?", (norm,)).fetchone()
    con.close()
    return row_to_dict(row) if row else None

def upsert_import(lead: Dict[str, Any]) -> int:
    # Telefon direkt normalisieren
    tel_norm = normalize_phone(lead.get("telefon"))
    lead = {**lead, "telefon": tel_norm}

    email = (lead.get("email") or "").strip()
    existing = None
    if email:
        existing = find_by_email(email)
    if not existing and tel_norm:
        existing = find_by_phone(tel_norm)

    if existing:
        # Nur dann Anrede überschreiben, wenn eine sinnvolle (nicht-leere, nicht "-") Anrede aus dem Import kommt.
        update_fields = {
            "vorname": lead.get("vorname"),
            "nachname": lead.get("nachname"),
            "geburtstag": lead.get("geburtstag"),
            "telefon": lead.get("telefon"),
            "email": lead.get("email"),
            "strasse": lead.get("strasse"),
            "plz": lead.get("plz"),
            "stadt": lead.get("stadt"),
            "notes": (lead.get("notes") or existing.get("notes") or ""),
            "status": lead.get("status") or existing.get("status") or "neu",
            "profession": lead.get("profession") or existing.get("profession"),
            "employer": lead.get("employer") or existing.get("employer"),
        }
        new_anrede = (lead.get("anrede") or "").strip()
        if new_anrede and new_anrede != "-":
            update_fields["anrede"] = new_anrede
        # Felder mit None herausfiltern, damit wir bestehende Werte nicht versehentlich nullen
        update_fields = {k: v for k, v in update_fields.items() if v is not None}
        update_lead(existing["id"], **update_fields)
        return existing["id"]
    else:
        return create_lead(lead)

def counts_by_status() -> Dict[str, int]:
    con = connect()
    rows = con.execute("SELECT status, COUNT(*) c FROM leads GROUP BY status").fetchall()
    con.close()
    out = {r["status"]: r["c"] for r in rows}
    out["total"] = sum(out.values())
    for s in STATUSES:
        out.setdefault(s, 0)
    return out

# ---------- Versioning helpers ----------

def _max_version(con: sqlite3.Connection, lead_id: int) -> int:
    row = con.execute("SELECT MAX(version) AS v FROM lead_versions WHERE lead_id = ?", (lead_id,)).fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0

def save_version(lead_id: int) -> None:
    """Store the full current record as a new version."""
    lead = get_lead(lead_id)
    if not lead:
        return
    # Drop non-persistent fields
    lead = {k: v for k, v in lead.items() if k != "age"}
    con = connect()
    v = _max_version(con, lead_id) + 1
    con.execute(
        "INSERT OR REPLACE INTO lead_versions (lead_id, version, data, changed_at) VALUES (?, ?, ?, ?)",
        (lead_id, v, json.dumps(lead, ensure_ascii=False), _now()),
    )
    con.commit()
    con.close()

def get_versions(lead_id: int) -> List[Dict[str, Any]]:
    con = connect()
    rows = con.execute("SELECT version, changed_at FROM lead_versions WHERE lead_id = ? ORDER BY version DESC", (lead_id,)).fetchall()
    con.close()
    return [{"version": r["version"], "changed_at": r["changed_at"]} for r in rows]

def get_version_data(lead_id: int, version: int) -> Optional[Dict[str, Any]]:
    con = connect()
    row = con.execute("SELECT data FROM lead_versions WHERE lead_id = ? AND version = ?", (lead_id, version)).fetchone()
    con.close()
    if not row:
        return None
    try:
        return json.loads(row["data"])
    except Exception:
        return None

def rollback_to_version(lead_id: int, version: int) -> Optional[Dict[str, Any]]:
    """Revert record to the given version and save a new version."""
    data = get_version_data(lead_id, version)
    if not data:
        return get_lead(lead_id)
    allowed = {"anrede","vorname","nachname","geburtstag","telefon","email","strasse","plz","stadt","notes","status","email_sent_at",
               "start_date","profession","civil_servant_status","employer","subsidy_entitlement",
               "previous_insurance","previous_insurance_name","gkv_type","pkv_since",
               "marital_status","children","spouse_is_civil_servant","children_co_insured","consultant_assessment"}
    fields = {k: v for k, v in data.items() if k in allowed}
    update_lead(lead_id, **fields)
    return get_lead(lead_id)

# init/migrate
init_db()
