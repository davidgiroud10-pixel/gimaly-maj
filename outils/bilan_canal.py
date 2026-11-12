# -*- coding: utf-8 -*-
r"""Bilan en R du canal « Le Coin Trader » (LECTURE SEULE, rien n'est modifie, aucun acces a Telegram).
Deux mesures : le R du TP le plus loin atteint (comme les bilans du canal) ET le R REEL encaisse deduit du % du capital (partiels, point mort apres TP1).
Lit la base locale de GIMALY (~\GIMALY\trades.db, comme track_record_vip.py) : les signaux du canal tels que GIMALY les a lus, avec leur R final.
Affiche : nombre de signaux clos, gagnants / perdants / nuls, R total, R moyen par signal (avec intervalle 95 % regroupe par jour), gain moyen, perte moyenne,
RR REEL (gain moyen / perte moyenne), facteur de profit, plus longue serie de pertes, pire creux, resultat par mois, par sens, et sur les 30 / 90 derniers jours.
LIMITES a garder en tete : R theorique tel qu'ecrit dans les messages du canal (hors spread, commission, glissement) ; signaux « non declenches », « en cours » et
« clos sans chiffre » non comptes (leur nombre est affiche) ; ajustements manuels exclus. Peu de signaux = intervalle large = aucune conclusion.
Usage (dossier gimaly, a cote de track_record_vip.py) :
  .\.venv\Scripts\python.exe bilan_canal.py [--canal "coin trader"] [--depuis jj/mm/aaaa]"""
import math
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import track_record_vip as tr
except ImportError:
    print("Place ce script a cote de track_record_vip.py (dossier gimaly).")
    raise SystemExit(1)


def ic_jours(trades, z=1.96, cle="r"):
    par = {}
    for t in trades:
        par.setdefault(t["jour"], []).append(t[cle])
    n = len(trades)
    m = sum(t[cle] for t in trades) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par.values())) / n
    return m, m - z * se, m + z * se


def serie_pertes(trades, cle="r"):
    pire = cur = 0
    for t in trades:
        if t[cle] < -0.05:
            cur += 1
            pire = max(pire, cur)
        elif t[cle] > 0.05:
            cur = 0
    return pire


def ligne(nom, L, cle="r"):
    if not L:
        return f"  {nom:<22} aucun signal"
    r = [t[cle] for t in L]
    g = [x for x in r if x > 0.05]
    p = [x for x in r if x < -0.05]
    pf = sum(g) / -sum(p) if p else float("inf")
    rr = (statistics.fmean(g) / -statistics.fmean(p)) if g and p else float("nan")
    return (f"  {nom:<22}{len(L):>5} sig. | gagn. {100 * len(g) / len(L):>3.0f} % | R total {sum(r):>+8.1f} | R/signal {statistics.fmean(r):>+6.2f}"
            f" | RR reel {rr:>4.2f} | facteur de profit {pf:>4.2f}")


def main(argv):
    argv = list(argv)
    canal, depuis = "coin trader", None
    if "--canal" in argv:
        i = argv.index("--canal")
        canal = argv[i + 1].lower()
        del argv[i:i + 2]
    if "--depuis" in argv:
        i = argv.index("--depuis")
        depuis = datetime.strptime(argv[i + 1], "%d/%m/%Y")
        del argv[i:i + 2]
    clos, ignores, _ = tr.lire(canal, depuis, False)
    if not clos:
        print("Aucun signal clos trouve pour ce canal (verifie --canal et que GIMALY a lu le canal).")
        return 0
    clos.sort(key=lambda t: t["t"])
    n = len(clos)
    print(f"Canal « {canal} » : {n} signaux clos du {clos[0]['t']:%d/%m/%Y} au {clos[-1]['t']:%d/%m/%Y}"
          f" (ignores : {ignores['non déclenché']} non declenches, {ignores['clos sans chiffre']} sans chiffre, {ignores['en cours']} en cours)")
    r = [t["r"] for t in clos]
    g = [x for x in r if x > 0.05]
    p = [x for x in r if x < -0.05]
    m, lo, hi = ic_jours(clos)
    print(f"\nR total {sum(r):+.1f} | R moyen par signal {m:+.3f} [IC 95 % par jour : {lo:+.3f} ; {hi:+.3f}]")
    if g and p:
        print(f"gain moyen {statistics.fmean(g):+.2f} R ({len(g)} gagnants) | perte moyenne {statistics.fmean(p):+.2f} R ({len(p)} perdants)"
              f" | RR REEL {statistics.fmean(g) / -statistics.fmean(p):.2f} | facteur de profit {sum(g) / -sum(p):.2f}")
    print(f"nuls (|R| <= 0,05) : {n - len(g) - len(p)} | plus longue serie de pertes : {serie_pertes(clos)}")
    pire, _ = tr.recul(r)
    print(f"pire creux de la courbe en R : -{pire:.1f} R")
    mois = {}
    for t in clos:
        mois.setdefault(t["t"].strftime("%Y-%m"), []).append(t)
    # --- R REEL : d'apres le % du capital ecrit par le canal (1 % de risque par signal reparti entre les TP, stop remonte au point mort apres TP1) ---
    suspects = [t for t in clos if t.get("suspect")]
    for t in clos:
        t["rr_reel"] = t["pct"] / 1.0            # 1 % de risque = 1 R
    sans_pct = [t for t in clos if abs(t["pct"]) < 1e-9 and abs(t["r"]) > 0.05]
    print("\n" + "=" * 100)
    print("R REEL ENCAISSE (d'apres le % du capital des messages : partiels aux TP, point mort apres TP1 ; 1 % de risque = 1 R)")
    print(f"signaux au % illisible mis a 0 : {len(suspects)} | signaux avec un R mais sans % : {len(sans_pct)} (comptes a 0 dans cette mesure : elle est PRUDENTE si ce sont des gagnants)")
    rg = [x["rr_reel"] for x in clos if x["rr_reel"] > 0.05]
    rp = [x["rr_reel"] for x in clos if x["rr_reel"] < -0.05]
    mr, lor, hir = ic_jours(clos, cle="rr_reel")
    print(f"R reel total {sum(x['rr_reel'] for x in clos):+.1f} (contre {sum(r):+.1f} R mesure sur le TP le plus loin) | R reel moyen par signal {mr:+.3f} [IC 95 % par jour : {lor:+.3f} ; {hir:+.3f}]")
    if rg and rp:
        print(f"gain moyen {statistics.fmean(rg):+.2f} R ({len(rg)}) | perte moyenne {statistics.fmean(rp):+.2f} R ({len(rp)}) | RR REEL {statistics.fmean(rg) / -statistics.fmean(rp):.2f} | facteur de profit {sum(rg) / -sum(rp):.2f}")
    print(f"plus longue serie de pertes : {serie_pertes(clos, 'rr_reel')} | pire creux : -{tr.recul([x['rr_reel'] for x in clos])[0]:.1f} R")
    print("Par mois (R reel) :")
    for k in sorted(mois):
        print(ligne(k, mois[k], "rr_reel"))
    print("Periodes recentes (R reel) :")
    for jours in (30, 90):
        print(ligne(f"{jours} derniers jours", [t for t in clos if t["t"] >= clos[-1]["t"] - timedelta(days=jours)], "rr_reel"))
    print("=" * 100)
    print("\nPar mois (R du TP le plus loin atteint) :")
    for k in sorted(mois):
        print(ligne(k, mois[k]))
    print("\nPar sens :")
    for s in ("ACHAT", "VENTE", "BUY", "SELL", "LONG", "SHORT"):
        L = [t for t in clos if t["sens"] == s]
        if L:
            print(ligne(s, L))
    print("\nPeriodes recentes :")
    fin = clos[-1]["t"]
    for jours in (30, 90):
        print(ligne(f"{jours} derniers jours", [t for t in clos if t["t"] >= fin - timedelta(days=jours)]))
    print("\nLecture : R theorique tel qu'ecrit par le canal (hors spread/glissement). Si l'IC contient 0, on ne peut pas dire que l'esperance est positive ;")
    print("un RR reel eleve avec peu de gagnants et un RR faible avec beaucoup de gagnants peuvent donner la meme esperance : regarde le R moyen par signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
