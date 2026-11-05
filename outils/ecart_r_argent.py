# -*- coding: utf-8 -*-
r"""Pourquoi le R cumule et l'argent cumule ne racontent pas la meme histoire ? (LECTURE SEULE)

Lit ~\GIMALY\trading\trades_bot.csv (trades REELS termines). Pour chaque trade, la valeur d'1 R en euros est deduite
(gain_devise / R) : elle depend du lot. Le script compare ensuite le R et l'argent.
Usage : python ecart_r_argent.py [debut dd/mm/yyyy] [--genre NOM|tous]
Rien n'est modifie. Petits echantillons : lire les chiffres avec prudence."""
import csv
import statistics as st
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


def main(argv):
    debut, genre = None, "tous"
    i = 0
    while i < len(argv):
        if argv[i] == "--genre" and i + 1 < len(argv):
            genre = argv[i + 1]
            i += 2
            continue
        try:
            debut = datetime.strptime(argv[i], "%d/%m/%Y")
        except ValueError:
            print("Date attendue au format dd/mm/yyyy")
            return 1
        i += 1
    tr = []
    with open(F, newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            if (l.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            try:
                j = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
            except ValueError:
                continue
            r, g = nb(l.get("R")), nb(l.get("gain_devise"))
            if r is None or g is None or (debut and j < debut):
                continue
            gn = (l.get("genre") or "?").strip()
            if genre != "tous" and gn != genre:
                continue
            tr.append({"j": j, "h": (l.get("heure") or "")[:2], "genre": gn, "r": r, "g": g,
                       "u": g / r if abs(r) >= 0.2 else None})
    if not tr:
        print("Aucun trade.")
        return 0
    R, G = sum(t["r"] for t in tr), sum(t["g"] for t in tr)
    print(f"{len(tr)} trades · R cumule {R:+.2f} · argent cumule {G:+.0f} EUR\n")

    gag = [t for t in tr if t["r"] > 0]
    per = [t for t in tr if t["r"] < 0]
    print("1) GAINS ET PERTES")
    for nom, ens in (("gagnants", gag), ("perdants", per)):
        if ens:
            print(f"   {nom:9s}: {len(ens):4d} · R moyen {st.mean(t['r'] for t in ens):+.2f} · "
                  f"argent moyen {st.mean(t['g'] for t in ens):+.0f} EUR · total {sum(t['g'] for t in ens):+.0f} EUR")
    ug = [t["u"] for t in gag if t["u"]]
    up = [t["u"] for t in per if t["u"]]
    print("\n2) VALEUR D'1 R EN EUROS (depend du lot ; trades avec |R| >= 0,2)")
    for nom, u in (("sur gagnants", ug), ("sur perdants", up)):
        if u:
            print(f"   {nom:13s}: mediane {st.median(u):.0f} EUR/R · moyenne {st.mean(u):.0f} · min {min(u):.0f} · max {max(u):.0f}")
    if ug and up:
        print(f"   -> si les pertes ont une valeur de R plus haute que les gains, l'argent est plus bas que le R"
              f" (ici {st.median(up) / st.median(ug):.2f}x en mediane).")
    tous_u = [t["u"] for t in tr if t["u"]]
    if len(tous_u) >= 20:
        q = sorted(tous_u)
        n4 = len(q) // 4
        print("\n3) PAR TAILLE DE LOT (quartiles de la valeur de R)")
        bornes = [q[0] - 1, q[n4], q[2 * n4], q[3 * n4], q[-1] + 1]
        for k in range(4):
            ens = [t for t in tr if t["u"] and bornes[k] < t["u"] <= bornes[k + 1]]
            if ens:
                print(f"   {q[0] if k == 0 else bornes[k]:6.0f}-{bornes[k + 1]:6.0f} EUR/R : {len(ens):3d} trades · "
                      f"R {sum(t['r'] for t in ens):+6.1f} · argent {sum(t['g'] for t in ens):+6.0f} EUR · "
                      f"gagnants {100 * sum(1 for t in ens if t['r'] > 0) / len(ens):.0f} %")
    petits = [t for t in tr if abs(t["r"]) < 0.2]
    if petits:
        print(f"\n4) TRADES QUASI NULS (|R| < 0,2) : {len(petits)} trades · argent moyen {st.mean(t['g'] for t in petits):+.1f} EUR "
              f"(= couts / ecarts, le R ne les voit pas)")
    print("\n5) PAR JOUR")
    pj = defaultdict(lambda: [0, 0.0, 0.0])
    for t in tr:
        d = pj[t["j"]]
        d[0] += 1
        d[1] += t["r"]
        d[2] += t["g"]
    print("   jour         trades      R    argent   EUR/R")
    for j in sorted(pj):
        n, r, g = pj[j]
        print(f"   {j:%d/%m/%Y}  {n:6d}  {r:+6.1f}  {g:+7.0f}  {(g / r if abs(r) >= 0.5 else float('nan')):6.0f}")
    print("\nLecture : un ecart R / argent vient (a) du lot, qui varie d'un trade a l'autre (plafond lots_max, risque en %),"
          " (b) des couts. Il ne dit rien sur la qualite des signaux.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
