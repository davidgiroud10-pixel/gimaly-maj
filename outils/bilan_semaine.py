# -*- coding: utf-8 -*-
r"""Bilan des trades REELS du bot depuis une date, par jour, par moteur (signal), par sens et par heure (lecture seule, rien n'est modifie).
Source : trades_bot.csv (lignes terminees). Le R vient du bot (gain / risque reel). Pour chaque groupe : trades, part de gagnants, R cumule,
R moyen, argent, et (si au moins 8 trades) un intervalle a 95 % du R moyen (bootstrap) : « avantage probable », « perdant probable » ou
« indistinguable du hasard ». Peu de trades = aucune conclusion ; plusieurs trades au meme moment ne sont pas independants.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe bilan_semaine.py                    depuis le 02/11/2026
  .\.venv\Scripts\python.exe bilan_semaine.py 27/10/2026"""
import csv
import random
import statistics
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def lire(lignes, depuis):
    res = []
    for l in lignes:
        if (l.get("resultat") or "").strip() in ("", "ouvert"):
            continue
        try:
            jour = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
        except ValueError:
            continue
        if jour < depuis:
            continue
        r, gain = nombre(l.get("R")), nombre(l.get("gain_devise"))
        if r is None:
            continue
        h = (l.get("heure") or "").strip()[:2]
        res.append({"jour": jour, "genre": (l.get("genre") or "?").strip() or "?", "sens": (l.get("sens") or "?").strip().lower(),
                    "h": int(h) if h.isdigit() else None, "r": r, "gain": gain or 0.0, "t": (l.get("heure") or "").strip()})
    return res


def verdict(rs):
    if len(rs) < 8:
        return "trop peu de trades"
    rnd = random.Random(7)
    m = sorted(statistics.fmean(rnd.choices(rs, k=len(rs))) for _ in range(2000))
    bas, haut = m[50], m[1949]
    return (f"[{bas:+.2f} ; {haut:+.2f}] " + ("avantage probable" if bas > 0 else "perdant probable" if haut < 0 else "indistinguable du hasard"))


def ligne(nom, lot):
    rs = [x["r"] for x in lot]
    gagn = sum(1 for r in rs if r > 0.05)
    return (f"  {nom:<30} {len(lot):>4} {100 * gagn / len(lot):>5.0f} % {sum(rs):>+8.2f} {statistics.fmean(rs):>+7.2f} "
            f"{sum(x['gain'] for x in lot):>+10,.0f}   {verdict(rs)}")


def groupes(titre, trades, cle, ordre=None):
    d = OrderedDict()
    for x in trades:
        d.setdefault(cle(x), []).append(x)
    print(f"\n{titre}")
    print(f"  {'':<30} {'n':>4} {'gagn.':>7} {'R cumul':>8} {'R moy':>7} {'argent':>10}   intervalle 95 % du R moyen")
    for k in (sorted(d, key=ordre) if ordre else sorted(d, key=lambda k: sum(x['r'] for x in d[k]))):
        print(ligne(str(k), d[k]))


def serie_max(trades):
    pire = cour = 0
    for x in sorted(trades, key=lambda x: (x["jour"], x["t"])):
        cour = cour + 1 if x["r"] < -0.5 else 0
        pire = max(pire, cour)
    return pire


def main(argv):
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 11, 2)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        trades = lire(list(csv.DictReader(f, delimiter=";")), depuis)
    if not trades:
        print("Aucun trade termine depuis cette date.")
        return 0
    rs = [x["r"] for x in trades]
    print(f"BILAN DES TRADES REELS depuis le {depuis:%d/%m/%Y} : {len(trades)} trades, R cumule {sum(rs):+.2f}, "
          f"argent {sum(x['gain'] for x in trades):+,.0f}, plus longue serie de stops : {serie_max(trades)}")
    groupes("PAR JOUR", trades, lambda x: f"{x['jour']:%d/%m}", ordre=lambda k: k[3:] + k[:2])
    groupes("PAR MOTEUR (signal)", trades, lambda x: x["genre"])
    groupes("PAR MOTEUR ET SENS", trades, lambda x: f"{x['genre']} {x['sens']}")
    groupes("PAR SENS", trades, lambda x: x["sens"])
    groupes("PAR HEURE (colonne « heure » du fichier)", trades, lambda x: "?" if x["h"] is None else f"{x['h']:02d}h-{x['h'] + 1:02d}h",
            ordre=lambda k: k)
    print("\nLecture : un groupe n'est jamais une preuve s'il a moins d'une trentaine de trades. Compare les moteurs entre eux, pas a zero. "
          "Rien n'est modifie.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
