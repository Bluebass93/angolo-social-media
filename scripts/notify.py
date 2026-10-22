"""Notifiche Telegram (facoltative). Mai bloccanti: ogni errore viene inghiottito.
Usa TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (GitHub Secrets). Se mancano, non fa nulla.
Con DRY_RUN=1 stampa il messaggio senza inviarlo. Il token non viene mai stampato."""
import json
import os
import urllib.request


def _scrub(text):
    text = str(text)
    for var in ("TELEGRAM_BOT_TOKEN", "PAGE_ACCESS_TOKEN", "META_APP_SECRET"):
        secret = os.environ.get(var)
        if secret:
            text = text.replace(secret, "***")
    return text


def one_line(text, limit=200):
    return _scrub(" ".join(str(text).split()))[:limit]


def notify(text):
    try:
        text = _scrub(text)
        if os.environ.get("DRY_RUN") == "1":
            print("[DRY-RUN] Telegram (non inviato):\n" + text)
            return False
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat:
            return False  # non configurato: silenzio
        body = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:  # mai far fallire la pubblicazione
        print(f"Notifica Telegram non inviata ({type(e).__name__})")
        return False
