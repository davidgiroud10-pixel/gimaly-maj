# -*- coding: utf-8 -*-
r"""Track record « Le Coin Trader VIP » : CAPTURE d'ecran (PNG) + version MEMBRES en lecture seule (LECTURE SEULE, rien n'est modifie dans GIMALY).

Etapes : 1. regenere la page de track_record_vip.py a partir de la base de GIMALY (signaux du canal tels que lus sur Telegram) ;
         2. en fait une copie « membres » : meme chiffres, plus un avertissement visible en bas (resultats theoriques, passe, pas de garantie) ;
         3. prend une capture PLEINE PAGE en PNG avec Edge ou Chrome (deja installes, aucune installation).
Fichiers (dans ~\GIMALY\trading\) :
    track_record_membres.html     page autonome, lecture seule, a mettre en ligne ou a envoyer (aucun script, aucune donnee privee)
    track_record_membres.png      capture nette (largeur 960 px, double resolution) a poster sur Telegram / reseaux
Les chiffres sont THEORIQUES (hors spread, commission, glissement) ; tous les signaux clos sont comptes, gagnants et perdants ; les ajustements
manuels sont exclus par defaut. Rien n'est envoye nulle part.
Usage (dossier gimaly, a cote de track_record_vip.py) :
  .\.venv\Scripts\python.exe capture_track_vip.py                         tout l'historique du canal
  .\.venv\Scripts\python.exe capture_track_vip.py --depuis 13/04/2026     premiere date a retenir
  .\.venv\Scripts\python.exe capture_track_vip.py --navigateur "C:\chemin\msedge.exe"
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import track_record_vip as tr
except ImportError:
    print("Place ce script a cote de track_record_vip.py (dossier gimaly).")
    raise SystemExit(1)

LARGEUR = 1000
AVERT = ('<section class="avert"><h2>A lire</h2><p class="note">Resultats THEORIQUES calcules a partir des signaux publies sur le canal '
         '(hors spread, commission et glissement), tous les signaux clos etant comptes, gagnants et perdants. Les performances passees ne '
         'garantissent pas les performances futures ; le trading comporte un risque de perte en capital. Ceci n\'est pas un conseil en investissement.'
         '</p></section>')


def navigateur(force):
    if force:
        return force if Path(force).exists() else None
    cand = []
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            cand += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
    cand = [str(c) for c in cand if c.exists()]
    for nom in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(nom)
        if p:
            cand.append(p)
    return cand[0] if cand else None


def lancer(exe, args, timeout=90, mode="--headless=new"):
    base = [exe, mode, "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={tempfile.mkdtemp(prefix='cap_')}"]
    return subprocess.run(base + args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def hauteur(exe, page_html):
    """Hauteur reelle de la page : une copie temporaire inscrit scrollHeight dans le titre, qu'on relit via --dump-dom."""
    mesure = page_html.replace("</body>", '<script>addEventListener("load",function(){setTimeout(function(){document.title="H="+document.documentElement.scrollHeight},300)})</script></body>')
    tmp = Path(tempfile.mkdtemp(prefix="mes_")) / "m.html"
    tmp.write_text(mesure, encoding="utf-8")
    r = lancer(exe, [f"--window-size={LARGEUR},900", "--virtual-time-budget=4000", "--dump-dom", tmp.as_uri()])
    m = re.search(r"<title>H=(\d+)</title>", r.stdout or "")
    return int(m.group(1)) if m else None


def main(argv):
    argv = list(argv)
    force = None
    if "--navigateur" in argv:
        i = argv.index("--navigateur")
        force = argv[i + 1]
        del argv[i:i + 2]
    exe = navigateur(force)
    if not exe:
        print("Ni Edge ni Chrome trouves : indique-le avec --navigateur \"C:\\...\\msedge.exe\". La page HTML sera quand meme creee.")
    code = tr.main(argv)
    if code or not tr.SORTIE.exists():
        return code or 1
    page = tr.SORTIE.read_text(encoding="utf-8")
    page = page.replace("</main>", AVERT + "</main>", 1) if "</main>" in page else page
    page = page.replace("<html lang=\"fr\"><head>", "<html lang=\"fr\"><head><meta name=\"color-scheme\" content=\"light\">", 1)
    # theme clair fixe : meme rendu pour tout le monde (la capture ne depend pas du reglage de ton PC)
    page = re.sub(r"@media \(prefers-color-scheme:dark\)\{:root\{[^}]*\}\}", "", page)
    html_out = tr.SORTIE.with_name("track_record_membres.html")
    html_out.write_text(page, encoding="utf-8")
    print(f"\nPage membres (lecture seule) : {html_out}")
    if not exe:
        return 0
    png = html_out.with_suffix(".png")
    h = None
    try:
        h = hauteur(exe, page)
    except Exception as e:  # noqa: BLE001
        print(f"(mesure de la hauteur impossible : {e!r} ; hauteur par defaut)")
    h = h or 3600
    erreurs = []
    for mode in ("--headless=new", "--headless"):
        if png.exists():
            png.unlink()
        try:
            r = lancer(exe, [f"--window-size={LARGEUR},{h + 40}", "--force-device-scale-factor=2", "--virtual-time-budget=4000",
                             f"--screenshot={png}", html_out.as_uri()], mode=mode)
            erreurs.append(f"{mode} : code {r.returncode} {((r.stderr or '') + (r.stdout or '')).strip()[-300:]}")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"{mode} : {e!r}")
        for _ in range(10):                      # le fichier peut apparaitre juste apres la fin du processus
            if png.exists() and png.stat().st_size > 5000:
                break
            time.sleep(0.5)
        if png.exists() and png.stat().st_size > 5000:
            print(f"Capture : {png}  ({LARGEUR} x {h + 40} px, double resolution)")
            return 0
    print("La capture n'a pas ete creee. Navigateur utilise : " + exe)
    for e in erreurs:
        print("  " + e)
    print("En attendant : ouvre track_record_membres.html dans le navigateur et fais une capture (ou Imprimer > Enregistrer en PDF).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
