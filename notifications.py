# notifications.py
import base64
import mimetypes
import os
import re
import requests
import settings

GRAPH_SENDMAIL_URL = f"{settings.GRAPH_BASE}/me/sendMail"

def _inline_attachments_for_template(html: str):
    """
    Sucht nach lokalen Bildquellen 'vorlage_anfrage-Dateien/<name>' und erzeugt Inline-Attachments (CID).
    Ersetzt gleichzeitig die src-Pfade im HTML.
    """
    attachments = []

    def repl(match):
        rel_path = match.group(1)  # z.B. image001.png
        file_path = os.path.join(settings.ASSETS_DIR, rel_path)
        if not os.path.isfile(file_path):
            return f'src="vorlage_anfrage-Dateien/{rel_path}"'
        content_id = rel_path
        ctype, _ = mimetypes.guess_type(file_path)
        if ctype is None:
            ctype = "application/octet-stream"
        with open(file_path, "rb") as f:
            content_bytes = base64.b64encode(f.read()).decode("utf-8")
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": rel_path,
            "contentId": content_id,
            "isInline": True,
            "contentType": ctype,
            "contentBytes": content_bytes,
        })
        return f'src="cid:{content_id}"'

    pattern = r'src="vorlage_anfrage-Dateien/([^"]+)"'
    new_html = re.sub(pattern, repl, html)
    return new_html, attachments

def _render_template(anrede: str, nachname: str) -> (str, list):
    """Liest das HTML, ersetzt {{ANREDE}} (z. B. 'Herr Müller'), baut Inline-Anhänge."""
    if not os.path.isfile(settings.HTML_TEMPLATE_PATH):
        raise RuntimeError(f"HTML-Vorlage nicht gefunden: {settings.HTML_TEMPLATE_PATH}")

    with open(settings.HTML_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # ANREDE bauen: 'Herr Müller' / 'Frau Schulz' / fallback
    parts = [p for p in [anrede, nachname] if p]
    anrede_full = " ".join(parts).strip()

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
    """
    Versendet die Vorlage als HTML-Mail über Microsoft Graph (sendMail).
    {{ANREDE}} wird als 'Anrede Nachname' ersetzt (z. B. 'Herr Müller').
    """
    html_body, attachments = _render_template(anrede, nachname)

    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
            "attachments": attachments,
        },
        "saveToSentItems": True,
    }
    if reply_to:
        message["message"]["replyTo"] = [{"emailAddress": {"address": reply_to}}]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(GRAPH_SENDMAIL_URL, headers=headers, json=message, timeout=30)
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"Graph sendMail fehlgeschlagen: {resp.status_code} {resp.text}")
