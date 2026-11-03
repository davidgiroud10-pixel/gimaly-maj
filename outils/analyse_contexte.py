# -*- coding: utf-8 -*-
r"""Les trades marchent-ils mieux quand le marche est DIRECTIONNEL ? Lecture seule de trades_bot.csv : pour chaque trade
termine, le bot a note le contexte au moment du signal. On regarde le resultat selon :
  - tendance_h1_accord : le trade va AVEC ou CONTRE la tendance de fond H1
  - delta 5 min : le flux d'ordres des 5 dernieres minutes va dans le sens du trade (AVEC) ou a l'inverse (CONTRE)
  - tape_vitesse : vitesse des echanges (lente / normale / rapide)
  - gros ordres : plus de gros ordres POUR que CONTRE le trade, ou l'inverse
Par defaut sur scalp_keltner_large. Lecture seule, rien n'est modifie.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_contexte.py
  .\.venv\Scripts\python.exe analyse_contexte.py 20/10/2026 --genre scalp_keltner_large      (ou --genre tous)"""
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def delta5(flux):
    m = re.search(r"delta 5 min (-?\d+(?:[.,]\d+)?)", flux or "")
    return nombre(m.group(1)) if m else None


def gros(flux):
    m = re.search(r"gros ordres (\d+) pour / (\d+) contre", flux or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def ligne_stats(nom, t):
    n = len(t)
    g = sum(1 for x in t if x[0] > 0)
    r = sum(x[0] for x in t)
    d = sum(x[1] for x in t)
    fiable = "" if n >= 30 else "  (peu de trades)"
    return f"  {nom:<22} {n:>5} {100 * g / n:>6.0f}% {r:>+8.2f} {r / n:>+6.2f} {d:>+8.0f}{fiable}"


def main(argv):
    argv = list(argv)
    genre = "scalp_keltner_large"
    if "--genre" in argv:
        i = argv.index("--genre")
        genre = argv[i + 1] if i + 1 < len(argv) else genre
        del argv[i:i + 2]
    depuis = None
    if argv:
        try:
            depuis = datetime.strptime(argv[0], "%d/%m/%Y")
        except ValueError:
            print("Date attendue : jj/mm/aaaa")
            return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    trades = []
    for l in lignes:
        if (l.get("resultat") or "").strip() in ("", "ouvert"):
            continue
        r, g = nombre(l.get("R")), nombre(l.get("gain_devise"))
        if r is None or g is None:
            continue
        try:
            d = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
        except ValueError:
            continue
        if depuis and d < depuis:
            continue
        if genre != "tous" and (l.get("genre") or "") != genre:
            continue
        sens = (l.get("sens") or "").strip()
        flux = l.get("flux_valeurs") or ""
        dl = delta5(flux)
        if dl is None or dl == 0 or sens not in ("achat", "vente"):
            flux_sens = "inconnu"
        else:
            flux_sens = "avec le flux" if (dl > 0) == (sens == "achat") else "contre le flux"
        go = gros(flux)
        if go is None or go[0] == go[1]:
            gros_sens = "inconnu / egal"
        else:
            gros_sens = "plus de gros ordres POUR" if go[0] > go[1] else "plus de gros ordres CONTRE"
        h1 = (l.get("tendance_h1_accord") or "").strip() or "inconnu"
        tape = (l.get("tape_vitesse") or "").strip() or "inconnu"
        trades.append((r, g, h1, flux_sens, tape, gros_sens))
    if not trades:
        print("Aucun trade termine exploitable.")
        return 0
    print(f"{len(trades)} trades termines | signal : {genre}{' | depuis ' + argv[0] if depuis else ''} | "
          f"R {sum(t[0] for t in trades):+.2f} | devise {sum(t[1] for t in trades):+.0f}\n")
    for titre, idx in (("Tendance de fond H1 (avec / contre le trade)", 2), ("Flux d'ordres des 5 dernieres minutes", 3),
                       ("Vitesse des echanges", 4), ("Gros ordres", 5)):
        print(titre)
        print(f"  {'':<22} {'trades':>5} {'gagn.':>7} {'R cumul':>8} {'R moy':>6} {'devise':>8}")
        for v in sorted({t[idx] for t in trades}):
            print(ligne_stats(v, [(t[0], t[1]) for t in trades if t[idx] == v]))
        print()
    print("Lecture : un contexte qui fait vraiment mieux a un R moyen nettement meilleur ET assez de trades (30 ou plus).")
    print("Ce sont des observations, pas des causes : a confirmer sur plusieurs semaines avant de changer le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
