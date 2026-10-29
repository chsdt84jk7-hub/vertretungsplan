"""Liest den Text eines Untis-Vertretungsplans (62. OS Dresden) und wertet ihn pro Lehrerkürzel aus."""
import re

MONATE = {"Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6, "Juli": 7,
          "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12}

NAME = r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]{1,5}"            # Kürzel wie Kun, Hin, MülB
SUBJ = r"[A-ZÄÖÜ]{2,4}(?::[a-zäöü]+)?"             # Fach wie MA, BIO, SPO:w
KLASSE_STD = re.compile(r"(?<![\w.])(\d{1,2}[a-z](?:,\s?\d{1,2}[a-z])*)\s+(\d{1,2}(?:-\d{1,2})?)\s+(?=\S)")
AUFSICHT = re.compile(r"(\d{1,2}:\d{2}):\s*\d{1,2}:\d{2}\s*-\s*(.+?)\s*-->\s*(\S+)\s*\(für\s*([^)]+)\)")
HEADER_SKIP = re.compile(r"^(62\. Oberschule|\d{2}\.\d{2}\.\d{4}$|Vertretungsplan für|Klassenplan$|Klasse/Kurs)")


def _list_after(text, label, stop_labels):
    """Holt eine Kürzel-Liste wie 'Abwesende Lehrer: Fis (5-9), Hei' – auch wenn sie umbricht."""
    m = re.search(re.escape(label) + r"\s*(.*?)(?=" + "|".join(map(re.escape, stop_labels)) + r"|$)", text, re.S)
    if not m:
        return []
    out = []
    for name, std in re.findall(r"(" + NAME + r")(?:\s*\(([^)]*)\))?", m.group(1).replace("\n", " ")):
        out.append({"k": name, "std": std or ""})
    return out


STOPS = ["Abwesende Lehrer:", "Abwesende Klassen:", "Lehrer mit Änderung:", "Klassen mit Änderung:",
         "Geänderte Aufsichten:", "Klasse/Kurs", "Geänderte Unterrichtsstunden:"]


def rows_from_tables(tables):
    """Zeilen aus pdfplumber-Tabellen (Klasse, St., Fach, Lehrer, Raum, Info) – genauer als der Fließtext."""
    out = []
    for t in tables:
        for r in t:
            cells = [re.sub(r"\s+", " ", c or "").strip() for c in r]
            if not cells or cells[0].startswith("Klasse"):
                continue
            if re.fullmatch(r"\d{1,2}[a-z](?:,\s?\d{1,2}[a-z])*", cells[0]) and len(cells) >= 2:
                out.append(" ".join(c for c in cells if c))
            elif out and any(cells):  # Fortsetzung einer Zeile über den Seitenumbruch
                out[-1] += " " + " ".join(c for c in cells if c)
    return out


def parse(text, table_rows=None):
    plan = {"titel": "", "datum": None, "woche": "", "erstellt": "",
            "abwesend": [], "geaendert": [], "aufsichten": [], "zeilen": [], "hinweise": []}
    m = re.search(r"Vertretungsplan für\s+(\w+),\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})(?:\s*\(([^)]*)\))?", text)
    if m:
        wt, d, mon, y, woche = m.groups()
        plan["titel"] = f"{wt}, {d}. {mon} {y}"
        if mon in MONATE:
            plan["datum"] = f"{y}-{MONATE[mon]:02d}-{int(d):02d}"
        plan["woche"] = woche or ""
    m = re.search(r"^(\d{2}\.\d{2}\.\d{4})\s*$", text, re.M)
    if m:
        plan["erstellt"] = m.group(1)

    plan["abwesend"] = _list_after(text, "Abwesende Lehrer:", [s for s in STOPS if s != "Abwesende Lehrer:"])
    plan["geaendert"] = [x["k"] for x in _list_after(text, "Lehrer mit Änderung:", [s for s in STOPS if s != "Lehrer mit Änderung:"])]

    for zeit, ort, wer, fuer in AUFSICHT.findall(text):
        plan["aufsichten"].append({"zeit": zeit, "ort": ort.strip(), "wer": wer.strip(), "fuer": fuer.strip()})

    # Unterrichtsänderungen: Zeilen zwischen "Geänderte Unterrichtsstunden" und "Zusätzliche Informationen"
    teil = text.split("Geänderte Unterrichtsstunden:", 1)
    rest = teil[1] if len(teil) > 1 else ""
    rest, _, hinweise = rest.partition("Zusätzliche Informationen:")
    offen = []
    for line in rest.splitlines():
        line = line.strip()
        if not line or HEADER_SKIP.match(line) or line.startswith(("Seite", "Abwesende", "Lehrer mit", "Klassen mit", "Geänderte")):
            continue
        offen.append(line)
        if KLASSE_STD.search(line):
            plan["zeilen"].append(_zeile(" ".join(offen)))
            offen = []
    if offen and plan["zeilen"]:
        plan["zeilen"][-1] = _zeile(plan["zeilen"][-1]["roh"] + " " + " ".join(offen))
    if table_rows:  # Tabellen aus dem PDF haben Vorrang; Zeilen, die die Tabellenerkennung verpasst, kommen aus dem Text
        tab = [_zeile(r) for r in table_rows]
        keys = {(z["klasse"], z["std"]) for z in tab}
        extra = [z for z in plan["zeilen"] if (z["klasse"], z["std"]) not in keys]
        reihenfolge = {(z["klasse"], z["std"]): i for i, z in enumerate(plan["zeilen"])}
        plan["zeilen"] = sorted(tab + extra, key=lambda z: reihenfolge.get((z["klasse"], z["std"]), 10**6))
    plan["hinweise"] = [h.strip() for h in hinweise.splitlines() if h.strip() and not HEADER_SKIP.match(h.strip())]
    return plan


def _zeile(roh):
    roh = re.sub(r"\s+", " ", roh).strip()
    m = KLASSE_STD.search(roh)
    klasse, std = (m.group(1), m.group(2)) if m else ("", "")
    if m:
        vorne = roh[:m.start()].strip(" ,")
        hinten = roh[m.end():].strip()
        text = (hinten + (" · " + vorne if vorne else "")).strip()
    else:
        text = roh
    return {"klasse": klasse, "std": std, "text": text, "roh": roh}


def _klass(roh, k):
    """Ordnet eine Planzeile für Kürzel k ein. Gibt (art, handeln) oder None zurück."""
    e = re.escape(k)
    pers = rf"(?:Fr\.|Hr\.)\s*{e}(?![\wäöüß])"
    if re.search(rf"(?:Betreuung|Unterricht|Betr\.)\s+{pers}", roh):
        return "betreuung", True
    if re.search(rf"Aufgaben\s+{pers}", roh):
        return "aufgaben", True
    if re.search(rf"\(\s*{e}\s*\)", roh) or re.search(rf"für\s+{SUBJ}\s+{e}(?![\wäöüß])", roh):
        return "vertreten", False
    if re.search(rf"(?:^|[\s(-]){SUBJ}\s+{e}(?![\wäöüß])", roh):
        if re.search(rf"{e}\s+(fällt aus|gehalten am)", roh):
            return "faellt_aus", False
        andere = [n for n in re.findall(rf"(?:Betreuung|Unterricht|Betr\.)\s+(?:Fr\.|Hr\.)\s*({NAME})", roh) if n != k]
        if andere:
            return "vertreten", False
        return "unterricht", True
    if re.search(pers, roh):
        return "erwaehnt", True
    return None


ART_TEXT = {"betreuung": "Betreuung/Unterricht", "aufgaben": "Aufgaben bereitstellen",
            "vertreten": "Deine Stunde wird vertreten", "faellt_aus": "Deine Stunde entfällt",
            "unterricht": "Geänderter Unterricht", "erwaehnt": "Du bist erwähnt"}


def kuerzel_im_plan(plan):
    ks = {a["k"] for a in plan["abwesend"]} | set(plan["geaendert"])
    for a in plan["aufsichten"]:
        ks |= {a["wer"], *re.findall(NAME, a["fuer"])}
    for z in plan["zeilen"]:
        ks |= set(re.findall(rf"(?:Fr\.|Hr\.)\s*({NAME})", z["roh"]))
        ks |= set(re.findall(rf"(?:^|[\s(-]){SUBJ}\s+\(?({NAME})\)?(?![\wäöüß])", z["roh"]))
    for h in plan["hinweise"]:
        ks |= set(re.findall(rf"(?:Fr\.|Hr\.)\s*({NAME})", h))
    ks.discard("entfällt")
    return sorted(k for k in ks if 2 <= len(k) <= 6)


def fuer_kuerzel(plan, k):
    items = []
    for a in plan["abwesend"]:
        if a["k"] == k:
            items.append({"art": "abwesend", "handeln": False,
                          "text": "Du bist als abwesend eingetragen" + (f" (Std. {a['std']})" if a["std"] else "")})
    for a in plan["aufsichten"]:
        if a["wer"] == k:
            items.append({"art": "aufsicht", "handeln": True,
                          "text": f"{a['zeit']} Uhr Aufsicht {a['ort']} (für {a['fuer']})"})
        elif re.search(rf"(?<![\w]){re.escape(k)}(?![\wäöüß])", a["fuer"]):
            if a["wer"] == "entfällt":
                items.append({"art": "aufsicht_frei", "handeln": False, "text": f"Deine Aufsicht {a['zeit']} Uhr ({a['ort']}) entfällt"})
            else:
                items.append({"art": "aufsicht_frei", "handeln": False, "text": f"Deine Aufsicht {a['zeit']} Uhr ({a['ort']}) übernimmt {a['wer']}"})
    ganztags_weg = any(a["k"] == k and not a["std"] for a in plan["abwesend"])
    for z in plan["zeilen"]:
        r = _klass(z["roh"], k)
        if r:
            art, handeln = r
            if ganztags_weg and art == "unterricht":
                art, handeln = "vertreten", False
            items.append({"art": art, "handeln": handeln, "label": ART_TEXT[art],
                          "text": f"{z['klasse']}, {z['std']}. Std.: {z['text']}"})
    for h in plan["hinweise"]:
        if re.search(rf"(?:Fr\.|Hr\.)\s*{re.escape(k)}(?![\wäöüß])", h):
            items.append({"art": "hinweis", "handeln": True, "label": "Hinweis", "text": h})
    if k in plan["geaendert"] and not any(i["handeln"] or i["art"] not in ("abwesend",) for i in items):
        items.append({"art": "unklar", "handeln": True,
                      "text": "Du stehst unter „Lehrer mit Änderung“ – bitte im PDF nachsehen"})
    return items


def topic_slug(k):
    t = k.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", t)
