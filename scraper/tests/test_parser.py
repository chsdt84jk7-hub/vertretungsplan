"""Schnelltest gegen echte Pläne: python scraper/tests/test_parser.py"""
import pathlib
import sys

HIER = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import plan_parser as pp  # noqa: E402


def items(datei, k):
    plan = pp.parse((HIER / datei).read_text(encoding="utf-8"))
    return plan, pp.fuer_kuerzel(plan, k)


plan, kun = items("plan_2026-10-30.txt", "Kun")
assert plan["datum"] == "2026-10-30" and plan["woche"] == "A-Woche"
assert len(plan["zeilen"]) == 13 and len(plan["aufsichten"]) == 9
assert [i["art"] for i in kun if i["handeln"]] == ["aufsicht", "betreuung", "betreuung"]

_, nad = items("plan_2026-10-30.txt", "Nad")
assert not any(i["handeln"] for i in nad), "Nad ist abwesend, muss nichts tun"

_, hin = items("plan_2026-10-30.txt", "Hin")
assert not any(i["handeln"] for i in hin), "Hin ist abwesend, wird vertreten"

_, die = items("plan_2026-10-30.txt", "Die")
assert sum(i["art"] == "unterricht" for i in die) == 2   # "Die Moldau" darf nicht zählen

plan29, zim = items("plan_2026-10-29.txt", "Zim")
assert "Zim" in plan29["geaendert"]                       # Liste bricht im PDF um
assert len(plan29["zeilen"]) == 27
assert any(i["art"] == "aufsicht" for i in zim)

_, fra = items("plan_2026-10-29.txt", "Fra")
assert any(i["art"] == "hinweis" for i in fra)            # Nachschreiben-Betreuung

# Schülersicht
plan30 = pp.parse((HIER / "plan_2026-10-30.txt").read_text(encoding="utf-8"))
assert plan30["abwesende_klassen"] == [{"k": "8a", "std": "5-9"}]
k8c = pp.fuer_klasse(plan30, "8c")
assert len([i for i in k8c if i["art"] == "stunde"]) == 3        # Sport (8b,8c) + 2x Mathe
assert any("2. Std." in i["text"] and i["label"] == "Entfällt" for i in k8c)
k8a = pp.fuer_klasse(plan30, "8a")
assert any(i["art"] == "klasse_weg" for i in k8a) and any(i["art"] == "hinweis" for i in k8a)  # Exkursion
assert pp.fuer_klasse(plan30, "8 C") == k8c and pp.klasse_norm("08c") == "8c"
assert "10a" in pp.klassen_im_plan(plan30) and pp.fuer_klasse(plan30, "1a") == []

assert pp.topic_slug("MülB") == "muelb"
print("Alle Tests bestanden.")
