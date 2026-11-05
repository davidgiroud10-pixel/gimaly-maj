# -*- coding: utf-8 -*-
r"""Le bot perd-il plus en fin de journee (a partir de 17 h jusqu'a la cloture) ? (LECTURE SEULE, trades REELS termines)

Lit ~\GIMALY\trading\trades_bot.csv. Compare « avant la coupure » et « a partir de la coupure » (17 h par defaut, colonne « heure »
du fichier) : trades, % de stops (R <= -0,9), % gagnants, R cumule, R moyen avec intervalle a 95 %, et l'ecart avec son intervalle.
Puis : meme comparaison sur la 1re et la 2e moitie de la periode, jour par jour (dans combien de jours la fin de journee est-elle
pire ?), et le detail heure par heure. Rien n'est modifie.

Prudence : la coupure a 17 h vient d'une impression, donc de ces memes donnees : elle ne peut pas servir de preuve. Le vrai test est
de relancer l'outil sur des trades POSTERIEURS (par ex. depuis le 06/11/2026), sans changer la coupure.

Usage : python analyse_fin_journee.py [debut dd/mm/yyyy] [--coupure 17] [--genre NOM|tous]"""
import csv
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

F = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nb(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def ic(vals, n=2000, graine=7):
    if len(vals) < 8:
        return None
    rnd = random.Random(graine)
    m = sorted(statistics.fmean(rnd.choices(vals, k=len(vals))) for _ in range(n))
    return m[int(.025 * n)], m[int(.975 * n) - 1]


def ic_ecart(a, b, n=2000, graine=11):
    if len(a) < 8 or len(b) < 8:
        return None
    rnd = random.Random(graine)
    d = sorted(statistics.fmean(rnd.choices(a, k=len(a))) - statistics.fmean(rnd.choices(b, k=len(b))) for _ in range(n))
    return d[int(.025 * n)], d[int(.975 * n) - 1]


def ligne(nom, rs):
    if not rs:
        return f"  {nom:<26}    0"
    stops = 100 * sum(1 for r in rs if r <= -0.9) / len(rs)
    gag = 100 * sum(1 for r in rs if r > 0.05) / len(rs)
    i = ic(rs)
    return (f"  {nom:<26}{len(rs):>5} {stops:>7.0f} % {gag:>6.0f} % {sum(rs):>+8.1f} {statistics.fmean(rs):>+7.3f}  "
            + (f"[{i[0]:+.2f} ; {i[1]:+.2f}]" if i else "trop peu"))


def comparer(titre, lots, coupure):
    avant = [r for h, r, _ in lots if h < coupure]
    apres = [r for h, r, _ in lots if h >= coupure]
    print(titre)
    print(f"  {'':<26}{'trades':>5} {'stops':>9} {'gagn.':>8} {'R cumul':>8} {'R moy':>7}  IC 95 % du R moyen")
    print(ligne(f"avant {coupure} h", avant))
    print(ligne(f"{coupure} h et apres", apres))
    e = ic_ecart(apres, avant)
    if e:
        print(f"  ecart R moyen (apres - avant) : {statistics.fmean(apres) - statistics.fmean(avant):+.3f}  IC 95 % [{e[0]:+.2f} ; {e[1]:+.2f}]")
    print()


def main(argv):
    argv = list(argv)
    genre, coupure = "tous", 17
    for nom in ("--genre", "--coupure"):
        if nom in argv:
            i = argv.index(nom)
            v = argv[i + 1] if i + 1 < len(argv) else None
            del argv[i:i + 2]
            if nom == "--genre" and v:
                genre = v
            if nom == "--coupure" and v:
                coupure = int(v)
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    lots = []
    with open(F, newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            if (l.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            try:
                j = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
                h = int((l.get("heure") or "")[:2])
            except ValueError:
                continue
            r = nb(l.get("R"))
            if r is None or j < depuis or (genre != "tous" and (l.get("genre") or "").strip() != genre):
                continue
            lots.append((h, r, j))
    if not lots:
        print("Aucun trade.")
        return 0
    lots.sort(key=lambda x: x[2])
    print(f"{len(lots)} trades termines | depuis {depuis:%d/%m/%Y} | moteur : {genre} | coupure : {coupure} h\n")
    comparer("TOUTE LA PERIODE", lots, coupure)
    m = len(lots) // 2
    comparer(f"PREMIERE MOITIE ({m} trades, jusqu'au {lots[m - 1][2]:%d/%m})", lots[:m], coupure)
    comparer(f"DEUXIEME MOITIE ({len(lots) - m} trades, depuis le {lots[m][2]:%d/%m})", lots[m:], coupure)
    jours = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for h, r, j in lots:
        d = jours[j]
        if h >= coupure:
            d[1] += r
            d[3] += 1
        else:
            d[0] += r
            d[2] += 1
    pires = sum(1 for d in jours.values() if d[3] and d[2] and d[1] / d[3] < d[0] / d[2])
    comp = sum(1 for d in jours.values() if d[3] and d[2])
    print(f"JOUR PAR JOUR : la fin de journee a un R moyen PIRE que le reste de la journee dans {pires} jours sur {comp} comparables.")
    print("  (au hasard on attend a peu pres la moitie)\n")
    print("HEURE PAR HEURE (colonne « heure » du fichier)")
    print(f"  {'':<26}{'trades':>5} {'stops':>9} {'gagn.':>8} {'R cumul':>8} {'R moy':>7}")
    for h in sorted({x[0] for x in lots}):
        rs = [r for hh, r, _ in lots if hh == h]
        print(ligne(f"{h:02d} h", rs).split("  [")[0].split("  trop peu")[0])
    print("\nLecture : la coupure vient d'une impression sur ces memes donnees, donc ce n'est PAS une preuve. Credible seulement si l'ecart")
    print("a un intervalle qui n'inclut pas 0, va dans le meme sens dans les deux moities et la majorite des jours, avec ~30 trades par groupe,")
    print("et se CONFIRME sur des trades posterieurs (relancer avec une date de debut apres aujourd'hui).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
