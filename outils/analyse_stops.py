# -*- coding: utf-8 -*-
r"""Resultats par LARGEUR DE STOP (|entree - stop| en $ d'or), sur tout l'historique de trades_bot.csv.
Montre pour chaque tranche : nombre de trades, % gagnants, R cumule, R moyen, devise, et ce que donnerait
l'historique SANS les trades de cette tranche. Lecture seule : rien n'est modifie.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_stops.py                 tout l'historique
  .\.venv\Scripts\python.exe analyse_stops.py 01/10/2026      a partir d'une date (jj/mm/aaaa)"""
import csv
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
TRANCHES = [(0, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 1e9)]


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def jour(s):
    try:
        return datetime.strptime((s or "").strip(), "%d/%m/%Y")
    except ValueError:
        return None


def main(argv):
    depuis = jour(argv[0]) if argv else None
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    res = []
    for l in lignes:
        if (l.get("resultat") or "").strip() in ("", "ouvert"):
            continue
        d = jour(l.get("date"))
        if depuis and (not d or d < depuis):
            continue
        r, g = nombre(l.get("R")), nombre(l.get("gain_devise"))
        pe, sl = nombre(l.get("pe")), nombre(l.get("sl"))
        if None in (r, g, pe, sl) or pe == sl:
            continue
        res.append((abs(pe - sl), r, g, (l.get("genre") or l.get("signal") or "?"), d))
    if not res:
        print("Aucun trade termine exploitable.")
        return 0
    tot_r = sum(x[1] for x in res)
    tot_g = sum(x[2] for x in res)
    print(f"{len(res)} trades termines{' depuis ' + argv[0] if depuis else ''} : R {tot_r:+.2f} | devise {tot_g:+.0f}\n")
    print(f"{'stop ($)':>10} {'trades':>7} {'gagn.%':>7} {'R cumul':>8} {'R moy':>6} {'devise':>8}   sans cette tranche : R / devise")
    for lo, hi in TRANCHES:
        t = [x for x in res if lo <= x[0] < hi]
        if not t:
            continue
        g = sum(1 for x in t if x[1] > 0)
        rr = sum(x[1] for x in t)
        gg = sum(x[2] for x in t)
        nom = f"{lo:g}-{hi:g}" if hi < 1e8 else f">={lo:g}"
        print(f"{nom:>10} {len(t):>7} {100 * g / len(t):>6.0f}% {rr:>+8.2f} {rr / len(t):>+6.2f} {gg:>+8.0f}   {tot_r - rr:+.2f} / {tot_g - gg:+.0f}")
    print("\nPar genre de signal :")
    for nom in sorted({x[3] for x in res}):
        t = [x for x in res if x[3] == nom]
        print(f"  {nom:<28} {len(t):>4} trades | R {sum(x[1] for x in t):+.2f} | devise {sum(x[2] for x in t):+.0f}")
    print("\nLecture : si 'sans cette tranche' est meilleur que le total, la tranche fait perdre. Prudence : moins de ~50 trades")
    print("par tranche = chiffres peu fiables ; a confirmer sur plusieurs semaines avant de changer le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
