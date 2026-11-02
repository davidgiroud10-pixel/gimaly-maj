# -*- coding: utf-8 -*-
r"""Corrige les « R » faux de trades_bot.csv (stop a -10 R au lieu de -1 R) : la valeur d'un lot etait 10 fois trop faible au
moment du calcul. Pour chaque trade du jour choisi, R est recalcule : gain_devise / (volume x |entree - stop| x 100)
(100 $ par lot pour 1 $ d'or). Seules les lignes dont le R enregistre est 8 a 12 fois trop grand sont touchees ; les autres
ne changent pas. Par defaut : APERCU seulement (rien n'est ecrit). Avec --appliquer : copie de sauvegarde
trades_bot.csv.avant_corr_r puis ecriture.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe corriger_r.py                      apercu pour aujourd'hui
  .\.venv\Scripts\python.exe corriger_r.py 02/11/2026           apercu pour une date
  .\.venv\Scripts\python.exe corriger_r.py 02/11/2026 --appliquer
Fichier : %USERPROFILE%\GIMALY\trading\trades_bot.csv"""
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
VALEUR_LOT = 100.0


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def main(argv):
    appliquer = "--appliquer" in argv
    dates = [a for a in argv if not a.startswith("--")]
    jour = dates[0] if dates else datetime.now().strftime("%d/%m/%Y")
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    brut = FICHIER.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lecteur = csv.DictReader(f, delimiter=";")
        colonnes = lecteur.fieldnames
        lignes = list(lecteur)
    if not colonnes or "R" not in colonnes or "gain_devise" not in colonnes:
        print("Colonnes R / gain_devise absentes : rien a corriger.")
        return 1
    touches = 0
    for l in lignes:
        if (l.get("date") or "").strip() != jour:
            continue
        r, gain, vol = nombre(l.get("R")), nombre(l.get("gain_devise")), nombre(l.get("volume"))
        pe, sl = nombre(l.get("pe")), nombre(l.get("sl"))
        if None in (r, gain, vol, pe, sl) or not vol or pe == sl or not r:
            continue
        juste = gain / (vol * abs(pe - sl) * VALEUR_LOT)
        rapport = r / juste if juste else 0
        if 8 <= rapport <= 12:
            print(f"  {l['date']} {l['heure']} {l.get('sens', '')} {l.get('resultat', '')} : R {r:+.2f} -> {juste:+.2f}")
            if appliquer:
                l["R"] = f"{juste:.2f}"
            touches += 1
    if not touches:
        print(f"Aucune ligne a corriger le {jour}.")
        return 0
    if not appliquer:
        print(f"{touches} ligne(s) seraient corrigees. Ajoute --appliquer pour ecrire (sauvegarde automatique).")
        return 0
    shutil.copy2(FICHIER, FICHIER.with_name(FICHIER.name + ".avant_corr_r"))
    with open(FICHIER, "w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colonnes, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    print(f"{touches} ligne(s) corrigee(s). Sauvegarde : {FICHIER.name}.avant_corr_r")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
