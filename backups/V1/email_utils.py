# email_utils.py
import base64, mimetypes, os, re, requests
from settings import HTML_TEMPLATE_PATH, ASSETS_DIR, REPLY_TO

GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"

def _inline_attachments_for_template(html: str):
    """
    Wandelt lokale Bilder 'vorlage_anfrage-Dateien/<name>' in Inline-CIDs um.
    Lässt https://… Bilder unangetastet.
    """
    attachments = []

    def repl(m):
        rel = m.group(1)
        file_path = os.path.join(ASSETS_DIR, rel)
        if not os.path.isfile(file_path):
            return f'src="vorlage_anfrage-Dateien/{rel}"'  # Datei fehlt -> Link belassen

        content_id = rel  # Dateiname = CID
        ctype, _ = mimetypes.guess_type(file_path)
        if not ctype:
            ctype = "application/octet-stream"
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": rel,
            "contentId": content_id,
            "isInline": True,
            "contentType": ctype,
            "contentBytes": b64,
        })
        return f'src="cid:{content_id}"'

    pattern = r'src="vorlage_anfrage-Dateien/([^"]+)"'
    new_html = re.sub(pattern, repl, html)
    return new_html, attachments

def _render_template(anrede: str, nachname: str) -> tuple[str, list]:
    """Liest HTML, ersetzt {{ANREDE}} (z.B. 'Herr Müller'), baut Inline-Anhänge."""
    with open(HTML_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    # {{ANREDE}} ersetzen – inkl. Nachname
    anrede_full = (anrede or "").strip()
    if nachname:
        anrede_full = (anrede_full + " " + nachname.strip()).strip()
    html = html.replace("{{ANREDE}}", anrede_full)

    html, attachments = _inline_attachments_for_template(html)
    return html, attachments

def send_email_via_graph(
    access_token: str,
    to_email: str,
    subject: str,
    anrede: str,
    nachname: str,
    reply_to: str | None = None,
):
    html_body, attachments = _render_template(anrede, nachname)
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
            "attachments": attachments,
        },
        "saveToSentItems": True,
    }
    if reply_to or REPLY_TO:
        payload["message"]["replyTo"] = [{"emailAddress": {"address": reply_to or REPLY_TO}}]

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(GRAPH_SENDMAIL_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code not in (202, 200):
        raise RuntimeError(f"Graph sendMail fehlgeschlagen: {resp.status_code} {resp.text}")
