# -*- coding: utf-8 -*-
r"""Corrige les « R » gonfles (x ~10) d'un jour dans trades_bot.csv, pour les trades termines AVANT une heure donnee :
ils ont ete calcules par une ancienne version (valeur d'un lot 10 fois trop faible). L'echelle est calibree sur les stops
loss de la meme selection (un stop = -1 R) : chaque R de la selection est divise par la moyenne de |R| des stops (entre 7 et 12 ;
sinon rien n'est touche). Par defaut : APERCU seulement. Avec --appliquer : sauvegarde trades_bot.csv.avant_corr_r10, puis ecriture.

Usage (dossier du programme de l'ami) :
  .\.venv\Scripts\python.exe corriger_r_x10.py 02/11/2026 --avant 14:00             apercu
  .\.venv\Scripts\python.exe corriger_r_x10.py 02/11/2026 --avant 14:00 --appliquer
Fichier : %USERPROFILE%\GIMALY\trading\trades_bot.csv"""
import csv
import shutil
import sys
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def main(argv):
    argv = list(argv)
    appliquer = "--appliquer" in argv
    argv = [a for a in argv if a != "--appliquer"]
    avant = None
    if "--avant" in argv:
        i = argv.index("--avant")
        avant = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if not argv or not avant:
        print("Usage : corriger_r_x10.py JJ/MM/AAAA --avant HH:MM [--appliquer]")
        return 1
    jour = argv[0].strip()
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    brut = FICHIER.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lecteur = csv.DictReader(f, delimiter=";")
        colonnes = lecteur.fieldnames
        lignes = list(lecteur)
    if not colonnes or "R" not in colonnes:
        print("Colonne R absente : rien a corriger.")
        return 1
    sel = [l for l in lignes
           if (l.get("date") or "").strip() == jour and (l.get("heure") or "").strip()[:5] < avant
           and (l.get("resultat") or "").strip() not in ("", "ouvert") and nombre(l.get("R")) is not None]
    stops = [abs(nombre(l["R"])) for l in sel if "stop" in (l.get("resultat") or "").lower()]
    if not sel:
        print(f"Aucun trade termine le {jour} avant {avant}.")
        return 0
    if not stops:
        print("Aucun stop loss dans la selection pour calibrer l'echelle : rien n'est touche. Envoie-moi les lignes.")
        return 2
    k = sum(stops) / len(stops)
    if not 7 <= k <= 12:
        print(f"Echelle des stops ({k:.2f}) hors de 7-12 : ces R ne semblent pas gonfles x10. Rien n'est touche.")
        return 2
    print(f"Echelle calibree sur {len(stops)} stop(s) : /{k:.2f}")
    for l in sel:
        r = nombre(l["R"])
        nouveau = round(r / k, 2)
        print(f"  {l['date']} {l['heure']} {l.get('sens', '')} {l.get('resultat', '')} : R {r:+.2f} -> {nouveau:+.2f}")
        if appliquer:
            l["R"] = f"{nouveau:.2f}"
    if not appliquer:
        print(f"{len(sel)} ligne(s) seraient corrigees. Ajoute --appliquer pour ecrire (sauvegarde automatique).")
        return 0
    shutil.copy2(FICHIER, FICHIER.with_name(FICHIER.name + ".avant_corr_r10"))
    with open(FICHIER, "w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colonnes, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    print(f"{len(sel)} ligne(s) corrigee(s). Sauvegarde : {FICHIER.name}.avant_corr_r10")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
