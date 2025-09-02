# extractor.py – Fix Anrede-Erkennung & robustes Abschneiden
from __future__ import annotations
import os, re
from typing import Dict, Optional, Any, List

try:
    from pypdf import PdfReader as PYPDF_Reader
except ImportError:
    PYPDF_Reader = None
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    from pdfminer.layout import LAParams
except ImportError:
    pdfminer_extract_text = None
    LAParams = None

# --------- PDF-Text lesen ---------
def _read_text_pypdf(path: str) -> str:
    if not PYPDF_Reader: return ""
    try:
        r = PYPDF_Reader(path)
        return "\n".join((p.extract_text() or "") for p in r.pages).strip()
    except Exception:
        return ""

def _read_text_pdfminer(path: str) -> str:
    if not pdfminer_extract_text: return ""
    try:
        return (pdfminer_extract_text(path, laparams=LAParams(all_texts=True)) or "").strip()
    except Exception:
        return ""

def extract_text_all(path: str, warnings: List[str]) -> str:
    for name, fn in (("pypdf", _read_text_pypdf), ("pdfminer", _read_text_pdfminer)):
        t = fn(path)
        if t and re.search(r"[A-Za-zÄÖÜäöü]{3,}", t):
            warnings.append(f"Text extrahiert mit: {name}")
            return re.sub(r"\s+", " ", t)
    warnings.append("Keine der PDF-Bibliotheken konnte Text extrahieren.")
    return ""

# --------- Regex-Hilfen ---------
RE_MAIL   = re.compile(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}")
RE_PHONE  = re.compile(r"(\+?\d[\d\s()/\-]{5,})")
RE_DATE   = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
RE_STRASSE= re.compile(r"(?i)^\s*(?P<str>.+?)\s*$")

def _clean(s: Optional[str]) -> str:
    return (s or "").strip(" \t,;:-")

def _normalize_phone_de(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0049"): national = digits[4:]
    elif digits.startswith("49"): national = digits[2:]
    elif digits.startswith("0"): national = digits[1:]
    else: national = digits
    return "+49" + national if national else ""

# --------- Stopwort-/Label-Handling ---------
_NEXT_TERMS = [
    "anrede","vorname","nachname","name",
    "geburtsdatum","geburtstag",
    "telefon","handy","mobil",
    "e-mail","email",
    "straße","strasse","str\\.","adresse",
    "plz","postleitzahl","stadt","ort",
    "status","berufsstatus","sparte","beihilfe",
    "netto","nettopreis","preis",
    # NEU: trennt „anklebende“ Verwaltungslabels zuverlässig
    "interne\\s+lead\\s+id","lead\\s+id","kundennr","kundennummer","sachbearbeiter"
]

def _make_union(terms):
    parts=[]
    for t in terms:
        t = t.replace(".", r"\.")
        t = re.sub(r"\s+", r"\\s*", t)
        parts.append(t)
    return "|".join(parts)

_NEXT_KEYS_RE = re.compile(r"(?si)(" + _make_union(_NEXT_TERMS) + r")\b")

def _get_line_value(text: str, labels: List[str]) -> Optional[str]:
    def _u(vs: List[str]) -> str:
        return "|".join(re.sub(r"\s+", r"\\s*", x.replace(".", r"\.")) for x in vs)
    lab_re = re.compile(rf"(?si)\b(?:{_u(labels)})\b\s*:\s*")
    m = lab_re.search(text)
    if not m: return None
    rest = text[m.end():]
    next_m = _NEXT_KEYS_RE.search(rest)
    cut_next = next_m.start() if next_m else None
    cut_nl = rest.find("\n")
    candidates = [c for c in (cut_next, cut_nl) if c is not None and c >= 0]
    end = min(candidates) if candidates else len(rest)
    return _clean(rest[:end])

# --------- Parser (strict + flexibel) ---------
def parse_lead_strict(text: str) -> Dict[str, Optional[str]]:
    lead = {
        "anrede": None, "vorname": None, "nachname": None,
        "geburtstag": None, "telefon": None, "email": None,
        "strasse": None, "plz": None, "stadt": None,
        "status": "neu", "notes": None
    }
    if not text: return lead

    lead["anrede"]   = _get_line_value(text, ["Anrede"])
    lead["vorname"]  = _get_line_value(text, ["Vorname"])
    lead["nachname"] = _get_line_value(text, ["Nachname"])

    gb_line = _get_line_value(text, ["Geburtstag","Geburtsdatum"])
    if gb_line:
        m = RE_DATE.search(gb_line)
        if m: lead["geburtstag"] = m.group(0)

    street = _get_line_value(text, ["Strasse","Straße","Adresse"])
    if street:
        m = RE_STRASSE.search(street); lead["strasse"] = _clean(m.group("str") if m else street)

    plz_val = _get_line_value(text, ["PLZ","Postleitzahl"])
    if plz_val:
        m = re.search(r"\b\d{5}\b", plz_val)
        if m: lead["plz"] = m.group(0)

    stadt_val = _get_line_value(text, ["Stadt","Ort"])
    if stadt_val:
        lead["stadt"] = _clean(stadt_val)

    tel_line = _get_line_value(text, ["Handy","Telefon","Mobil"])
    if tel_line:
        m = RE_PHONE.search(tel_line)
        if m: lead["telefon"] = _normalize_phone_de(m.group(1))

    mail_line = _get_line_value(text, ["E-Mail","E Mail","Email"])
    if mail_line:
        m = RE_MAIL.search(mail_line)
        if m: lead["email"] = m.group(0)
    if not lead["email"]:
        m = RE_MAIL.search(text)
        if m: lead["email"] = m.group(0)

    # --- Anrede normalisieren + Fallback ---
    if lead.get("anrede"):
        a = _clean(lead["anrede"]).lower()
        if a in ("-", "keine", "k.a.", "k. a.", "n/a", "na"): lead["anrede"] = "-"
        elif "frau" in a: lead["anrede"] = "Frau"
        elif "herr" in a: lead["anrede"] = "Herr"
    else:
        m = re.search(r"(?i)sehr\s+geehrte(?:r)?\s+(frau|herrn?)", text)
        if m:
            lead["anrede"] = "Frau" if m.group(1).lower().startswith("frau") else "Herr"

    return lead

# flexibel: greift noch Werte aus frei formatiertem Text ab
KV_RE = re.compile(
    r"(?i)\b(?P<key>anrede|vorname|nachname|name|geburtsdatum|geburtstag|telefon|handy|mobil|e[-\s]?mail|email|straße|strasse|str\.|adresse|plz|postleitzahl|stadt|ort)\s*[:：\-]?\s*(?P<val>[^:\n\r]+)"
)

def _capture_after(label_regex: str, text: str) -> Optional[str]:
    label_re = re.compile(rf"(?si)\b(?:{label_regex})\b\s*[:：\-]?\s*")
    m = label_re.search(text)
    if not m: return None
    rest = text[m.end():]
    n = _NEXT_KEYS_RE.search(rest)
    segment = rest[:n.start()] if n else rest
    return _clean(segment)

def parse_lead_flexible(text: str) -> Dict[str, Optional[str]]:
    lead = {
        "anrede": None, "vorname": None, "nachname": None,
        "geburtstag": None, "telefon": None, "email": None,
        "strasse": None, "plz": None, "stadt": None,
        "status": "neu", "notes": None
    }
    if not text: return lead
    text = text.replace("\x00", " ")

    for m in KV_RE.finditer(text):
        key = m.group("key").lower()
        val = _clean(m.group("val"))

        if key in ("e-mail","email","e mail"):
            em = RE_MAIL.search(val)
            if em and not lead["email"]:
                lead["email"] = em.group(0)
            continue

        if key in ("telefon","handy","mobil"):
            ph = RE_PHONE.search(val)
            if ph and not lead["telefon"]:
                lead["telefon"] = _normalize_phone_de(ph.group(1))
            continue

        if key in ("plz","postleitzahl"):
            z = re.search(r"\b\d{5}\b", val)
            if z: lead["plz"] = z.group(0); continue

        if key in ("straße","strasse","str.","adresse"):
            lead["strasse"] = val; continue

        if key in ("stadt","ort"):
            lead["stadt"] = val; continue

        if key == "anrede":
            a = val.lower()
            if a in ("-", "keine", "k.a.", "k. a.", "n/a", "na"): lead["anrede"] = "-"
            elif "frau" in a: lead["anrede"] = "Frau"
            elif "herr" in a: lead["anrede"] = "Herr"
            continue

        if key == "vorname" and not lead["vorname"]: lead["vorname"] = val
        if key == "nachname" and not lead["nachname"]: lead["nachname"] = val
        if key in ("geburtsdatum","geburtstag"):
            d = RE_DATE.search(val)
            if d: lead["geburtstag"] = d.group(0)

    if not lead.get("anrede"):
        m = re.search(r"(?i)sehr\s+geehrte(?:r)?\s+(frau|herrn?)", text)
        if m: lead["anrede"] = "Frau" if m.group(1).lower().startswith("frau") else "Herr"

    return lead

# --------- Öffentliche API ---------
def extract_leads_ex(pdf_path: str) -> Dict[str, Any]:
    warnings: List[str] = []
    if not os.path.exists(pdf_path):
        return {"leads": [], "warnings": [f"Datei nicht gefunden: {pdf_path}"]}

    raw_text = extract_text_all(pdf_path, warnings)
    if not raw_text.strip():
        warnings.append("Der extrahierte Text ist leer.")
        return {"leads": [], "warnings": warnings}

    # Ein oder mehrere Leads aus dem Dokument holen:
    # Für deine Exporte reicht i. d. R. 1 Block – wir parsen einfach den Gesamttest.
    lead = parse_lead_strict(raw_text)
    # Falls „strikt“ nichts findet, flexibel nachziehen
    if not any(lead.get(k) for k in ("vorname","nachname","email","telefon","strasse","plz","stadt")):
        lead = parse_lead_flexible(raw_text)

    return {"leads": [lead], "warnings": warnings}
