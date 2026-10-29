# Vertretungsplan-App – 62. Oberschule „Friedrich Schiller“ Dresden

Lehrkräfte geben ihr Kürzel ein und sehen sofort, was sie heute und morgen tun müssen: Aufsichten, Vertretungen, Betreuung, Aufgaben stellen. Der ganze Plan ist als PDF direkt in der App. Sobald etwas Neues für ein Kürzel im Plan steht, kommt eine Push-Nachricht aufs Handy.

Alles läuft kostenlos und ohne Server: **GitHub** prüft den Plan alle 5 Minuten und hostet die Web-App, **ntfy** verschickt die Push-Nachrichten.

## So funktioniert es

1. Ein GitHub-Workflow lädt Mo–Fr alle 5 Minuten die Vertretungsplan-Seite der Schule und alle aktuellen PDFs.
2. `scraper/check.py` liest jedes PDF aus und ordnet jede Zeile den Kürzeln zu.
3. Wer etwas tun muss, bekommt eine Push-Nachricht über ntfy (Thema `os62-b7eb68-<kürzel>`, z. B. `os62-b7eb68-kun`). Ändert sich der Plan später noch, gibt es eine Nachricht mit „Aktualisiert“. Dieselbe Nachricht kommt nie zweimal.
4. Die Ergebnisse und die PDFs landen in `docs/`. GitHub Pages zeigt daraus die Web-App.

„Muss was machen“ heißt: Aufsicht übernehmen, Betreuung oder Unterricht in einer geänderten Stunde, Aufgaben bereitstellen, in einem Hinweis namentlich genannt. Reine Infos (eigene Stunde fällt aus, eigene Aufsicht entfällt, abwesend) stehen in der App, lösen aber keinen Push aus.

## Einrichten (ca. 10 Minuten, einmalig)

1. Auf github.com ein kostenloses Konto anlegen und ein **neues Repository** erstellen, z. B. `vertretungsplan` (öffentlich, sonst kostet Pages Geld).
2. Den Inhalt dieses Ordners hochladen: im Repository auf **Add file → Upload files**, alle Dateien und Ordner hineinziehen (auch `.github`, ggf. „versteckte Dateien anzeigen“ aktivieren), **Commit changes**.
   Tipp: Falls der Ordner `.github` beim Hochladen fehlt, über **Add file → Create new file** eine Datei mit dem Namen `.github/workflows/check.yml` anlegen und den Inhalt hineinkopieren.
3. **Settings → Pages**: Source „Deploy from a branch“, Branch `main`, Ordner `/docs`, **Save**. Nach 1–2 Minuten ist die App unter `https://<dein-name>.github.io/vertretungsplan/` erreichbar.
4. **Settings → Actions → General** → ganz unten „Workflow permissions“ auf **Read and write permissions** stellen, **Save**.
5. **Actions → Vertretungsplan prüfen → Run workflow** einmal von Hand starten. Danach läuft es automatisch.

Fertig. Den Link zur App an die Kolleginnen und Kollegen schicken.

## Für die Lehrkräfte

1. App-Link öffnen, Kürzel eingeben, **Speichern**. Das Kürzel bleibt auf dem Gerät gespeichert.
2. iPhone: unten auf **Teilen → „Zum Home-Bildschirm“**, dann die App vom Home-Bildschirm öffnen (nötig für Push auf dem iPhone). Android: Menü → „Zum Startbildschirm hinzufügen“ bzw. „App installieren“.
3. In der App auf **„Push-Benachrichtigungen aktivieren“** tippen und erlauben. Fertig.

Tippt man auf eine Push-Nachricht, öffnet sich die App direkt beim richtigen Tag. Wer lieber eine eigene Push-App nutzt, findet in der App unter „Alternative: über die ntfy-App“ den Weg über ntfy.

## Push direkt in der App (Web Push) – einmalige Einrichtung

Die App meldet ihr Push-Abo über das ntfy-Thema `<topic_prefix>-anmeldung` an. Der Workflow holt die Anmeldungen ab und speichert sie verschlüsselt in `subs.enc`. Dafür braucht das Repository ein Secret:

**Settings → Secrets and variables → Actions → New repository secret**, Name `WEBPUSH_KEY`, Wert: der private Schlüssel (PEM, beginnt mit `-----BEGIN PRIVATE KEY-----`). Der passende öffentliche Schlüssel steht als `vapid_public` in `config.json`. Neues Schlüsselpaar = alle Geräte müssen Push neu aktivieren.

## Anpassen

Alles Wichtige steht in `config.json`:

| Feld | Bedeutung |
|---|---|
| `plan_page_url` | Seite der Schule mit den PDF-Links |
| `topic_prefix` | Anfang der ntfy-Themen. Zufällig gewählt, damit Fremde die Themen nicht erraten. Wird er geändert, müssen alle neu abonnieren. |
| `ntfy_server` | Standard `https://ntfy.sh`. Kann auf einen eigenen ntfy-Server zeigen. |
| `site_url` | Leer lassen. Wird automatisch aus dem Repository-Namen gebildet. Nur nötig bei eigener Domain. |

Die Prüfzeiten stehen in `.github/workflows/check.yml` (in UTC). Pläne für den laufenden Tag werden nach 16 Uhr nicht mehr gepusht.

## Gut zu wissen

- **Grenzen der Auswertung:** Die PDFs werden als Text gelesen. Bei ungewöhnlichen Einträgen kann eine Zuordnung danebenliegen. Steht ein Kürzel unter „Lehrer mit Änderung“ und das Skript findet keine passende Zeile, kommt sicherheitshalber „Bitte im PDF nachsehen“. Im Zweifel gilt der Aushang.
- **Datenschutz:** Ausgewertet wird nur, was die Schule ohnehin öffentlich auf ihrer Website zeigt. Push-Nachrichten verschickt nur der Workflow mit dem geheimen Schlüssel; die Liste der angemeldeten Geräte liegt verschlüsselt in `subs.enc`. Vor dem Verteilen an das Kollegium am besten kurz mit der Schulleitung abstimmen.
- **Pausen:** GitHub pausiert geplante Workflows, wenn 60 Tage lang nichts im Repository passiert ist. Während der Schulzeit passiert das nicht, weil jede Planänderung ein Commit ist. Nach langen Ferien ggf. unter **Actions** wieder aktivieren.
- **Testen:** `python scraper/tests/test_parser.py` prüft den Parser an zwei echten Plänen. `python scraper/check.py --dry-run` läuft komplett durch, ohne Push zu senden. `python scraper/check.py --dump datei.pdf` zeigt, was aus einem PDF gelesen wird.
- Die PDFs in `docs/pdf` und `docs/data.json` sind Beispieldaten. Sie werden beim ersten Lauf ersetzt.
