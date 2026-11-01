# -*- coding: utf-8 -*-
"""Mesure honnete des idees POC, sans rien modifier.

1) FILTRE : dans icebergs.csv, le resultat des trades « entree sur reaction » (stop ou 2R en premier) change-t-il
   selon la distance au POC et selon le cote (iceberg acheteur/vendeur, prix au-dessus/en dessous du POC) ?
2) SIMULATION : bilan par logique de poc_resultats.csv (retour, rebond, cassure).

Chaque ligne donne le nombre de cas, le taux d'objectif, l'esperance en R (objectif = +R, stop = -1) et une marge
d'erreur (intervalle de Wilson a 95 %). Sous 30 cas la ligne est marquee « trop peu » : ne decide rien dessus.

Usage (dossier gimaly) :  .\\.venv\\Scripts\\python.exe analyse_poc.py [dossier_des_csv]
Par defaut : %USERPROFILE%\\GIMALY\\trading
"""
import csv
import math
import sys
from pathlib import Path

MIN_CAS = 30


def lire(chemin):
    if not chemin.exists():
        return []
    with open(chemin, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def nombre(x):
    try:
        v = float(str(x).replace(",", "."))
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m), min(1.0, c + m)


def ligne(nom, gagnes, perdus, r_objectif=2.0):
    n = gagnes + perdus
    if n == 0:
        return f"  {nom:<34} aucun cas"
    p = gagnes / n
    lo, hi = wilson(gagnes, n)
    esp = p * r_objectif - (1 - p)
    seuil = 1 / (1 + r_objectif)
    flag = "  <- trop peu" if n < MIN_CAS else ("  <- IC95 au-dessus du seuil" if lo > seuil else
                                                  ("  <- IC95 sous le seuil" if hi < seuil else ""))
    return (f"  {nom:<34} n={n:<4} objectif {p*100:5.1f} % [{lo*100:4.1f}-{hi*100:4.1f}]  "
            f"esperance {esp:+.2f} R (seuil {seuil*100:.0f} %){flag}")


def filtre(dossier):
    lignes = lire(dossier / "icebergs.csv")
    print(f"\n=== 1) FILTRE POC sur icebergs.csv ({len(lignes)} lignes) ===")
    cas = []
    for l in lignes:
        d = nombre(l.get("dist_poc"))
        e = (l.get("premier_evenement") or "").strip()
        if d is None or e not in ("stop", "2R"):
            continue
        cas.append((d, l.get("cote", ""), e == "2R"))
    if not cas:
        print("  Pas encore de cas exploitables (dist_poc + stop/2R).")
        return
    g = sum(1 for c in cas if c[2])
    print(ligne("ensemble", g, len(cas) - g))
    tranches = [(0, 2), (2, 5), (5, 10), (10, 1e9)]
    print(" par distance au POC (en $, valeur absolue) :")
    for a, b in tranches:
        s = [c for c in cas if a <= abs(c[0]) < b]
        gg = sum(1 for c in s if c[2])
        print(ligne(f"{a} a {'+' if b > 1e8 else b} $", gg, len(s) - gg))
    print(" par cote de l'iceberg et position du prix :")
    for cote in ("acheteur", "vendeur"):
        for nom, test in (("sous le POC", lambda d: d < 0), ("au-dessus du POC", lambda d: d >= 0)):
            s = [c for c in cas if c[1] == cote and test(c[0])]
            gg = sum(1 for c in s if c[2])
            print(ligne(f"iceberg {cote}, prix {nom}", gg, len(s) - gg))
    print(" Lecture : « dans le sens du POC » = acheteur sous le POC ou vendeur au-dessus (retour vers le POC).")
    pour = [c for c in cas if (c[1] == "acheteur" and c[0] < 0) or (c[1] == "vendeur" and c[0] >= 0)]
    contre = [c for c in cas if c not in pour]
    for nom, s in (("vers le POC", pour), ("loin du POC", contre)):
        gg = sum(1 for c in s if c[2])
        print(ligne(f"trades {nom}", gg, len(s) - gg))


def simulation(dossier):
    lignes = lire(dossier / "poc_resultats.csv")
    print(f"\n=== 2) SIMULATION POC ({len(lignes)} fantomes termines) ===")
    if not lignes:
        print("  Rien encore : active  trading_poc_simulation: true  et laisse tourner plusieurs semaines.")
        return
    for logique in sorted({l["logique"] for l in lignes}):
        s = [l for l in lignes if l["logique"] == logique]
        r = [nombre(l["R"]) for l in s if nombre(l["R"]) is not None]
        obj = sum(1 for l in s if l["issue"] == "objectif")
        stp = sum(1 for l in s if l["issue"] == "stop")
        dur = len(s) - obj - stp
        total = sum(r)
        n = len(r)
        print(f"  {logique:<12} n={n:<4} objectif {obj}  stop {stp}  duree max {dur}  "
              f"R total {total:+.1f}  R moyen {total / n:+.2f}" + ("  <- trop peu" if n < MIN_CAS else ""))
        for sens in ("achat", "vente"):
            t = [nombre(l["R"]) for l in s if l["sens"] == sens and nombre(l["R"]) is not None]
            if t:
                print(f"      {sens:<6} n={len(t):<4} R moyen {sum(t) / len(t):+.2f}")
    print("\n  Attention : les signaux d'une meme logique se suivent dans le temps (cas non independants) et le spread n'est"
          "\n  pas retire des sorties : un R moyen faible mais positif ne prouve rien. Exige au moins 30 cas par logique,"
          "\n  un R moyen positif sur deux periodes differentes, et seulement alors un essai en reel au plus petit lot.")


if __name__ == "__main__":
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "GIMALY" / "trading"
    filtre(dossier)
    simulation(dossier)
