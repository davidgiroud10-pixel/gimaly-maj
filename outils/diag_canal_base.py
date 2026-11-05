# -*- coding: utf-8 -*-
r"""Que contient la base locale (trades.db) pour un canal ? LECTURE SEULE, Telegram n'est pas ouvert.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe diag_canal_base.py "coin trader" """
import json
import sqlite3
import sys
from pathlib import Path

canal = (sys.argv[1] if len(sys.argv) > 1 else "coin trader").strip().lower()
d = Path.home() / "GIMALY"
b = sqlite3.connect(f"file:{d / 'trades.db'}?mode=ro", uri=True)
print("Canaux de la base (signaux lus) :")
for c, n, a, z in b.execute("select canal, count(*), min(date), max(date) from trades group by canal order by 2 desc limit 10"):
    print(f"  {c:<16}{n:>5} signaux   du {a[:10]} au {z[:10]}")
print(f"\n{canal} : statuts")
for s, n in b.execute("select statut, count(*) from trades where canal=? group by statut order by 2 desc", (canal,)):
    print(f"  {s:<20}{n}")
print(f"\n{canal} : signaux par mois")
for m, n, r in b.execute("select substr(date,1,7), count(*), round(sum(coalesce(r,0)),1) from trades where canal=? and annule=0 group by 1 order by 1", (canal,)):
    print(f"  {m}  {n:>4} signaux  R brut {r:+}")
print("\ncorrections manuelles :", b.execute("select count(*) from corrections where canal=?", (canal,)).fetchone()[0])
print("messages en cache     :", b.execute("select count(*), min(date) from messages where canal=?", (canal,)).fetchone())
try:
    m = [l for l in json.loads((d / "trades_manuels.json").read_text(encoding="utf-8")) if (l.get("canal") or "").lower() == canal]
except (OSError, ValueError):
    m = []
print("trades manuels        :", m if m else "aucun")
print("\nUn exemple de signal :")
for l in b.execute("select date, sens, symbole, entree, stop, objectifs, statut, r, pips, pourcentage from trades where canal=? order by date desc limit 2", (canal,)):
    print(" ", l)
