"""Push direkt in der Web-App (Web Push).

Die App meldet ihr Push-Abo über ein ntfy-Thema an ("<prefix>-anmeldung"). Dieses Skript
holt die Anmeldungen bei jedem Lauf ab und speichert sie verschlüsselt in subs.enc.
Verschlüsselt und signiert wird mit dem geheimen Schlüssel aus dem GitHub-Secret WEBPUSH_KEY.
"""
import base64
import hashlib
import json
import os
import pathlib
import tempfile

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "subs.enc"


class WebPush:
    def __init__(self, ntfy, prefix, contact="mailto:vertretungsplan@users.noreply.github.com"):
        self.pem = (os.environ.get("WEBPUSH_KEY") or "").strip()
        self.ntfy, self.topic, self.contact = ntfy, f"{prefix}-anmeldung", contact
        self.subs, self.changed = {}, False
        self.enabled = bool(self.pem and prefix)
        if not self.enabled:
            print("Web Push aus: Secret WEBPUSH_KEY fehlt.")
            return
        from cryptography.fernet import Fernet
        self.fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(self.pem.encode()).digest()))
        if STORE.exists():
            try:
                self.subs = json.loads(self.fernet.decrypt(STORE.read_bytes()))
            except Exception as e:
                print(f"subs.enc nicht lesbar ({e}) – starte leer.")
        self._keyfile = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        self._keyfile.write(self.pem if self.pem.endswith("\n") else self.pem + "\n")
        self._keyfile.close()

    # --- Anmeldungen abholen -------------------------------------------------
    def sync(self, state):
        if not self.enabled:
            return
        since = state.get("anmeldung_seit") or "24h"
        try:
            r = requests.get(f"{self.ntfy}/{self.topic}/json", params={"poll": "1", "since": since}, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"Anmeldungen nicht abrufbar: {e}")
            return
        n = 0
        for line in r.text.splitlines():
            try:
                ev = json.loads(line)
                if ev.get("event") != "message":
                    continue
                state["anmeldung_seit"] = ev["id"]
                msg = json.loads(ev.get("message", ""))
                sub = msg.get("sub") or {}
                ep = sub.get("endpoint", "")
                if not ep.startswith("https://"):
                    continue
                if msg.get("aktion") == "abmelden" or not msg.get("k"):
                    self.changed |= self.subs.pop(ep, None) is not None
                    continue
                keys = sub.get("keys") or {}
                if not (keys.get("p256dh") and keys.get("auth")):
                    continue
                k = str(msg["k"])[:8]
                neu = {"k": k, "sub": {"endpoint": ep, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}}
                if self.subs.get(ep, {}).get("k") != k or self.subs.get(ep, {}).get("sub") != neu["sub"]:
                    self.subs[ep] = neu
                    self.changed = True
                    n += 1
            except Exception:
                continue
        print(f"Web Push: {len(self.subs)} Geräte angemeldet ({n} neu/geändert).")

    # --- Senden --------------------------------------------------------------
    def send(self, k, title, body, url):
        if not self.enabled:
            return 0
        from pywebpush import WebPushException, webpush
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        sent = 0
        for ep, s in list(self.subs.items()):
            if s["k"].lower() != k.lower():
                continue
            host = ep.split("/")[2]
            try:
                r = webpush(subscription_info=s["sub"], data=payload, vapid_private_key=self._keyfile.name,
                            vapid_claims={"sub": self.contact}, ttl=12 * 3600, headers={"Urgency": "high"})
                print(f"  -> {k} @ {host}: HTTP {getattr(r, 'status_code', '?')} {getattr(r, 'text', '')[:200]}")
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                print(f"  -> {k} @ {host}: Fehler HTTP {code} {getattr(e.response, 'text', '')[:300]}")
                if code in (404, 410):  # Abo abgelaufen oder vom Gerät entfernt
                    del self.subs[ep]
                    self.changed = True
                else:
                    print(f"Web Push an {k} fehlgeschlagen: {e}")
            except Exception as e:
                print(f"Web Push an {k} fehlgeschlagen: {e}")
        return sent

    def save(self):
        if self.enabled and self.changed:
            STORE.write_bytes(self.fernet.encrypt(json.dumps(self.subs).encode()))
