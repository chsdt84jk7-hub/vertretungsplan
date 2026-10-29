#!/usr/bin/env python3
"""Prüft den Vertretungsplan, spiegelt die PDFs in docs/pdf, schreibt docs/data.json
und schickt per Web Push (direkt in die App) und ntfy eine Push-Nachricht an jedes Kürzel, das etwas tun muss.

Lokal testen:  python scraper/check.py --dry-run     (schickt keine Push-Nachrichten)
Einzelnes PDF: python scraper/check.py --dump plan.pdf
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

import pdfplumber
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import plan_parser as pp  # noqa: E402
from webpush_store import WebPush  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS, STATE = ROOT / "docs", ROOT / "state.json"
PDFDIR = DOCS / "pdf"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PAGE_URL = os.environ.get("PLAN_PAGE_URL") or CFG["plan_page_url"]
NTFY = (os.environ.get("NTFY_SERVER") or CFG.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
PREFIX = os.environ.get("NTFY_PREFIX") or CFG.get("topic_prefix", "")
TZ = ZoneInfo("Europe/Berlin")
UA = {"User-Agent": "Mozilla/5.0 (Vertretungsplan-Benachrichtigung)"}


def site_url():
    if CFG.get("site_url"):
        return CFG["site_url"].rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def pdf_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text(x_tolerance=1.5) or "") for p in pdf.pages)


def pdf_rows(path):
    with pdfplumber.open(path) as pdf:
        tables = [t for p in pdf.pages for t in p.extract_tables()]
    return pp.rows_from_tables(tables)


def read_plan(path):
    return pp.parse(pdf_text(path), pdf_rows(path))


def find_pdfs(html):
    links = []
    for href in re.findall(r'href="([^"]+\.pdf)"', html, re.I):
        url = urllib.parse.urljoin(PAGE_URL, href.replace("&amp;", "&"))
        name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        m = re.search(r"Vertretungsplan.*?(\d{4}-\d{2}-\d{2})([a-z]?)", name)
        if m and url not in [l["url"] for l in links]:
            links.append({"url": url, "datum": m.group(1), "suffix": m.group(2)})
    return links


def notify(k, plan, items, url, update, wp):
    lines = [("• " + (i.get("label") + ": " if i.get("label") else "") + i["text"]) for i in items if i["handeln"]]
    title = ("Aktualisiert: " if update else "") + f"Vertretungsplan {plan['titel'].rsplit(' ', 1)[0]}"
    message = "\n".join(lines)[:3800]
    click = f"{url}?k={urllib.parse.quote(k)}&d={plan['datum']}" if url else ""
    ok = False
    # 1) direkt in der Web-App (Web Push)
    try:
        ok |= wp.send(k, title, message[:1500], click or "./") > 0
    except Exception as e:
        print(f"Web Push an {k} fehlgeschlagen: {e}")
    # 2) zusätzlich über die ntfy-App
    body = {"topic": f"{PREFIX}-{pp.topic_slug(k)}", "title": title, "message": message, "tags": ["school"], "priority": 4}
    if click:
        body["click"] = click
    try:
        r = requests.post(NTFY, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, timeout=20)
        r.raise_for_status()
        ok = True
    except Exception as e:
        print(f"ntfy an {k} fehlgeschlagen: {e}")
    return ok


def main():
    dry = "--dry-run" in sys.argv
    if "--dump" in sys.argv:
        f = sys.argv[sys.argv.index("--dump") + 1]
        t = pdf_text(f)
        print(t)
        print(json.dumps(read_plan(f), ensure_ascii=False, indent=1))
        return

    now = dt.datetime.now(TZ)
    heute = now.date().isoformat()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"gesendet": {}}
    wp = WebPush(NTFY, PREFIX)
    wp.sync(state)
    test_k = (os.environ.get("TEST_KUERZEL") or "").strip()
    if test_k:  # einmalige Nachricht von Hand (Actions → Run workflow)
        text = (os.environ.get("TEST_NACHRICHT") or "").strip() or f"Für {test_k} gibt es keine Änderungen im Vertretungsplan."
        url = site_url()
        n = wp.send(test_k, "Vertretungsplan", text, f"{url}?k={urllib.parse.quote(test_k)}" if url else "./")
        print(f"Testnachricht an {test_k}: {n} Gerät(e) per Web Push erreicht.")
        try:
            requests.post(NTFY, data=json.dumps({"topic": f"{PREFIX}-{pp.topic_slug(test_k)}", "title": "Vertretungsplan",
                                                  "message": text, "tags": ["school"]}).encode(),
                          headers={"Content-Type": "application/json"}, timeout=20)
        except Exception as e:
            print(f"ntfy-Test fehlgeschlagen: {e}")
    try:
        run(now, heute, state, wp, dry)
    finally:
        wp.save()
        STATE.write_text(json.dumps(state, indent=1))


def run(now, heute, state, wp, dry):
    html = requests.get(PAGE_URL, headers=UA, timeout=30).text
    links = find_pdfs(html)
    # pro Datum nur die neueste Fassung (z. B. ...-23b.pdf schlägt ...-23.pdf)
    neu = {}
    for l in links:
        if l["datum"] >= heute and (l["datum"] not in neu or l["suffix"] > neu[l["datum"]]["suffix"]):
            neu[l["datum"]] = l

    PDFDIR.mkdir(parents=True, exist_ok=True)
    url = site_url()
    plaene = []
    for datum in sorted(neu):
        l = neu[datum]
        raw = requests.get(l["url"], headers=UA, timeout=30).content
        local = PDFDIR / f"plan-{datum}.pdf"
        local.write_bytes(raw)
        plan = read_plan(local)
        plan["datum"] = plan["datum"] or datum
        plan["pdf"] = f"pdf/plan-{datum}.pdf"
        plan["quelle"] = l["url"]
        plan["sha"] = hashlib.sha1(raw).hexdigest()[:12]
        plan["lehrer"] = {}
        for k in pp.kuerzel_im_plan(plan):
            items = pp.fuer_kuerzel(plan, k)
            plan["lehrer"][k] = items
            aktion = [i["text"] for i in items if i["handeln"]]
            if not aktion or not PREFIX:
                continue
            key = f"{datum}|{k}"
            h = hashlib.sha1("\n".join(aktion).encode()).hexdigest()[:12]
            if state["gesendet"].get(key) == h:
                continue
            # Plan für heute nach 16 Uhr nicht mehr pushen
            if datum == heute and now.hour >= 16:
                continue
            if dry:
                print(f"[dry-run] Push an {k}: {aktion}")
            elif not notify(k, plan, items, url, key in state["gesendet"], wp):
                continue
            state["gesendet"][key] = h
        plaene.append(plan)

    # alte PDFs und alte Einträge aufräumen
    grenze = (now.date() - dt.timedelta(days=3)).isoformat()
    for f in PDFDIR.glob("plan-*.pdf"):
        if f.stem[5:] < grenze:
            f.unlink()
    state["gesendet"] = {k: v for k, v in state["gesendet"].items() if k[:10] >= grenze}

    data = {"schule": CFG.get("school_name", ""), "aktualisiert": now.isoformat(timespec="minutes"),
            "ntfy_server": NTFY, "topic_prefix": PREFIX, "vapid_public": CFG.get("vapid_public", ""),
            "quelle": PAGE_URL, "plaene": plaene}
    alt_pfad = DOCS / "data.json"
    alt = json.loads(alt_pfad.read_text(encoding="utf-8")) if alt_pfad.exists() else {}
    unveraendert = all(alt.get(f) == data[f] for f in ("plaene", "topic_prefix", "ntfy_server", "vapid_public", "quelle"))
    if not unveraendert:  # nur bei echten Änderungen schreiben -> keine leeren Commits alle 15 Minuten
        alt_pfad.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(plaene)} Plan/Pläne verarbeitet: {', '.join(neu) or '—'}")


if __name__ == "__main__":
    main()
