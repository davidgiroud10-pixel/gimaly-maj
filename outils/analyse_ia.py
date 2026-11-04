# -*- coding: utf-8 -*-
r"""L'avis de l'IA (observateur, ia_avis.csv) aurait-il eu raison ? (lecture seule, rien n'est modifie)
Rapproche chaque avis du resultat reel du trade (trades_bot.csv : meme jour, meme signal, meme sens, prix d'entree a 5 cents pres, heure a
moins de 5 minutes) puis resume par avis. Un avis n'est utile que s'il DIFFERENCIE : si l'IA dit « eviter » pour presque tout, elle
n'apprend rien ; il faut que les trades « evites » perdent nettement plus que les autres. Moins de ~100 avis : aucune conclusion.
Usage (dossier gimaly) :  $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe analyse_ia.py"""
import csv
import statistics
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
D = Path.home() / "GIMALY" / "trading"


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def instant(date, heure):
    try:
        return datetime.strptime(f"{date.strip()} {heure.strip()}", "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def main():
    fa, ft = D / "ia_avis.csv", D / "trades_bot.csv"
    if not fa.exists() or not ft.exists():
        print("ia_avis.csv ou trades_bot.csv introuvable.")
        return 1
    with open(fa, newline="", encoding="utf-8-sig") as f:
        avis = list(csv.DictReader(f, delimiter=";"))
    with open(ft, newline="", encoding="utf-8-sig") as f:
        trades = list(csv.DictReader(f, delimiter=";"))
    print(f"{len(avis)} avis de l'IA | {len(trades)} lignes de trades\n")
    lignes = []
    for a in avis:
        ta = instant(a.get("date", ""), a.get("heure", ""))
        pe = nombre(a.get("pe"))
        res = None
        for t in trades:
            if (t.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            tt = instant(t.get("date", ""), t.get("heure", ""))
            if ta and tt and abs((tt - ta).total_seconds()) <= 300 and (t.get("genre") or "").strip() == a.get("genre", "").strip() \
                    and (t.get("sens") or "").strip() == a.get("sens", "").strip() and None not in (pe, nombre(t.get("pe"))) \
                    and abs(nombre(t.get("pe")) - pe) <= 0.05:
                res = nombre(t.get("R"))
                break
        lignes.append((a, res))
        r = "en cours / non trouve" if res is None else f"{res:+.2f} R"
        print(f"  {a.get('date', '')} {a.get('heure', '')[:5]} {a.get('genre', ''):<20} {a.get('sens', ''):<7} IA : {a.get('avis', ''):<8} "
              f"({a.get('confiance', '?')} %)  ->  {r}")
    print()
    for v in sorted({a.get("avis", "") for a, _ in lignes}):
        rs = [r for a, r in lignes if a.get("avis", "") == v and r is not None]
        n = sum(1 for a, _ in lignes if a.get("avis", "") == v)
        if rs:
            print(f"  avis « {v} » : {n} avis, {len(rs)} termines, R cumule {sum(rs):+.2f}, R moyen {statistics.fmean(rs):+.2f}, "
                  f"gagnants {sum(1 for r in rs if r > 0)}/{len(rs)}")
        else:
            print(f"  avis « {v} » : {n} avis, aucun trade termine pour l'instant")
    print("\nLecture : trop peu d'avis pour conclure. A refaire a partir de ~100 avis ; l'IA n'influence aucun trade (observation seule).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
