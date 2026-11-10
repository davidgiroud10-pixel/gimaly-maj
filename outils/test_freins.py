# -*- coding: utf-8 -*-
r"""Deux freins contre les series de stops, testes sur TOUT l'historique M1 (lecture seule, rien n'est modifie, aucun ordre).
Regles FIXEES A L'AVANCE (pas ajustees apres coup) :
  A  frein de serie : apres 2 stops du MEME cote en moins de 90 min, on bloque ce cote pendant 60 min.
  B  stop minimum : on ne prend pas un trade dont la distance au stop est inferieure a 0,5 x ATR(14) des bougies M5.
Methode : meme rejeu que rejeu_keltner.py (tous les signaux scalp_keltner_large, stop large, objectif 1,5 R, 60 min max), spread deduit
(--spread, 0,20 $). Chaque signal a son R propre ; un frein ne fait qu'ECARTER des signaux. ATTENTION : si le R moyen est negatif, ecarter N'IMPORTE QUELS trades
« ameliore » le total ; le gain VRAI est donc mesure contre l'ecart de N trades tires au hasard (R des ecartes - R moyen). On compare
le R par trade avec / sans frein, l'IC 95 % de la difference (regroupe par jour, corrige Bonferroni pour 2 variantes), le nombre de gagnants perdus, et les deux moities.
Limites : le rejeu ignore les filtres du bot (sessions, positions, news) ; un frein qui n'est pas distinguable du hasard ne doit PAS etre
installe ; meme positif, il faut le confirmer en suivi avant de toucher au bot.
Usage (dossier gimaly, MetaTrader 5 ouvert, historique M1 charge, a cote de rejeu_keltner.py) :
  .\.venv\Scripts\python.exe test_freins.py                      depuis le 01/01/2026
  .\.venv\Scripts\python.exe test_freins.py 01/06/2026 --spread 0.25"""
import math
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import rejeu_keltner as rk
except ImportError:
    print("Place ce script a cote de rejeu_keltner.py (dossier gimaly).")
    raise SystemExit(1)

SERIE_N, SERIE_FEN, SERIE_BLOC = 2, 90 * 60, 60 * 60
SEUIL_ATR = 0.5
Z_BONF = 2.24            # IC 97,5 % : 2 variantes


def jouer(barres, i, sens, entree, sl):
    """(R avant spread, indice de la bougie de sortie, est_stop)."""
    achat = sens == "achat"
    dist = abs(entree - sl)
    tp = entree + rk.TP_R * dist if achat else entree - rk.TP_R * dist
    t0 = barres[i][0]
    dern, jd = entree, i
    for j in range(i + 1, len(barres)):
        t, o, h, b, c = barres[j]
        if t - t0 > rk.DUREE_S:
            break
        if (b <= sl) if achat else (h >= sl):
            return -1.0, j, True
        if (h >= tp) if achat else (b <= tp):
            return rk.TP_R, j, False
        dern, jd = c, j
    return ((dern - entree) if achat else (entree - dern)) / dist, jd, False


def atr_m5(barres, n=14):
    """ATR(14) M5 connu a chaque bougie M1 (derniere bougie M5 TERMINEE)."""
    m5 = {}
    for t, o, h, b, c in barres:
        k = t - t % 300
        if k not in m5:
            m5[k] = [h, b, c]
        else:
            m5[k][0] = max(m5[k][0], h)
            m5[k][1] = min(m5[k][1], b)
            m5[k][2] = c
    cles = sorted(m5)
    atr, prec, tr, val = None, None, [], {}
    for k in cles:
        h, b, c = m5[k]
        v = h - b if prec is None else max(h - b, abs(h - prec), abs(b - prec))
        prec = c
        tr.append(v)
        if len(tr) == n:
            atr = sum(tr) / n
        elif len(tr) > n:
            atr = (atr * (n - 1) + v) / n
        val[k] = atr                      # ATR incluant la bougie k (terminee quand k+300 est atteint)
    return val


def ic_jours(par_jour, n, z):
    """Moyenne par trade de base (somme des differences / n) et IC regroupe par jour."""
    tot = sum(sum(v) for v in par_jour.values())
    m = tot / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par_jour.values())) / n if n else 0.0
    return m, m - z * se, m + z * se


def frein_serie(lignes):
    """lignes : triees par temps, dict(t, sens, r, tsortie, stop). Renvoie l'ensemble des indices BLOQUES."""
    bloque, stops, ferme_jusqua = set(), {"achat": [], "vente": []}, {"achat": -1, "vente": -1}
    ev = []
    for idx, l in enumerate(lignes):
        ev.append((l["t"], 0, idx))
    # sorties evaluees au fil du temps : on avance signal par signal, en integrant les stops deja terminees
    sorties = sorted(((l["tsortie"], idx) for idx, l in enumerate(lignes) if l["stop"]))
    p = 0
    pris = set()
    for idx, l in enumerate(lignes):
        while p < len(sorties) and sorties[p][0] <= l["t"]:
            ts, j = sorties[p]
            p += 1
            if j not in pris:
                continue                  # un signal bloque n'a jamais ete pris : son stop n'existe pas
            s = lignes[j]["sens"]
            stops[s] = [x for x in stops[s] if ts - x <= SERIE_FEN] + [ts]
            if len(stops[s]) >= SERIE_N:
                ferme_jusqua[s] = max(ferme_jusqua[s], ts + SERIE_BLOC)
        if l["t"] < ferme_jusqua[l["sens"]]:
            bloque.add(idx)
        else:
            pris.add(idx)
    return bloque


def resume(nom, lignes, bloque, n_jours, z):
    n = len(lignes)
    gard = [l["r"] for i, l in enumerate(lignes) if i not in bloque]
    perdus = [l["r"] for i, l in enumerate(lignes) if i in bloque]
    par_jour = {}
    base_moy = sum(l["r"] for l in lignes) / n
    for i in bloque:                                     # gain PAR RAPPORT a ecarter le meme nombre de trades au hasard
        par_jour.setdefault(lignes[i]["jour"], []).append(-(lignes[i]["r"] - base_moy))
    for l in lignes:
        par_jour.setdefault(l["jour"], par_jour.get(l["jour"], []))
    m = n // 2
    d1 = -sum(lignes[i]["r"] - base_moy for i in bloque if i < m)
    d2 = -sum(lignes[i]["r"] - base_moy for i in bloque if i >= m)
    moy_g = statistics.fmean(gard) if gard else float("nan")
    print(f"\n{nom}")
    print(f"  signaux ecartes : {len(bloque)} sur {n} ({100 * len(bloque) / n:.0f} %) | dont gagnants perdus : {sum(1 for x in perdus if x > 0)}"
          f" | R des ecartes : {sum(perdus):+.1f} (moyenne {statistics.fmean(perdus) if perdus else 0:+.3f})")
    print(f"  R par trade : sans frein {base_moy:+.3f} | avec frein {moy_g:+.3f} | total sans {sum(l['r'] for l in lignes):+.1f} R, avec {sum(gard):+.1f} R")
    dm, lo, hi = ic_jours(par_jour, n, z)
    print(f"  gain VRAI du frein (en R par trade de base, au-dela d'ecarter autant de trades au hasard) : {dm:+.4f}   IC (par jour, Bonferroni 97,5 %) [{lo:+.4f} ; {hi:+.4f}]")
    print(f"  deux moities (gain vrai en R total) : {d1:+.1f} puis {d2:+.1f}")
    verdict = "NON distinguable du hasard" if lo <= 0 <= hi else ("AIDE (a confirmer)" if lo > 0 else "NUIT")
    print(f"  => {verdict}")


def main(argv):
    argv = list(argv)
    spread = 0.20
    if "--spread" in argv:
        i = argv.index("--spread")
        spread = float(argv[i + 1].replace(",", "."))
        del argv[i:i + 2]
    depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 1, 1)
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}).")
        return 1
    try:
        mt5.symbol_select(rk.SYMBOLE, True)
        barres = rk.charger(mt5, depuis - timedelta(days=3))
    finally:
        mt5.shutdown()
    if len(barres) < 2000:
        print("Historique M1 insuffisant : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche.")
        return 0
    atr = atr_m5(barres)
    lignes = []
    for i, sens, entree, sl in rk.signaux(barres):
        t = barres[i][0]
        if datetime.utcfromtimestamp(t) < depuis:
            continue
        dist = abs(entree - sl)
        r0, j, stop = jouer(barres, i, sens, entree, sl)
        k = (t - t % 300) - 300                    # derniere bougie M5 terminee avant l'entree
        a = atr.get(k)
        lignes.append({"t": t, "sens": sens, "r": r0 - spread / dist, "tsortie": barres[j][0], "stop": stop, "dist": dist,
                       "ratio": (dist / a) if a else None, "jour": datetime.utcfromtimestamp(t).date()})
    if len(lignes) < 100:
        print("Trop peu de signaux.")
        return 0
    lignes.sort(key=lambda x: x["t"])
    n_j = len({l["jour"] for l in lignes})
    d0, d1 = lignes[0]["jour"], lignes[-1]["jour"]
    print(f"{len(lignes)} signaux rejoues du {d0:%d/%m/%Y} au {d1:%d/%m/%Y} ({n_j} jours), spread {spread:.2f} $, R moyen de reference {statistics.fmean(l['r'] for l in lignes):+.3f}")
    print(f"part de stops (avant spread) : {100 * sum(1 for l in lignes if l['stop']) / len(lignes):.0f} %")
    resume("A  frein de serie (2 stops meme cote en 90 min -> cote bloque 60 min)", lignes, frein_serie(lignes), n_j, Z_BONF)
    bloq_b = {i for i, l in enumerate(lignes) if l["ratio"] is not None and l["ratio"] < SEUIL_ATR}
    resume(f"B  stop minimum ({SEUIL_ATR} x ATR M5)", lignes, bloq_b, n_j, Z_BONF)
    print("\nDescriptif (EXPLORATOIRE, ne sert pas a choisir un seuil) : R par trade selon distance stop / ATR M5")
    for lo, hi in ((0, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 99)):
        v = [l["r"] for l in lignes if l["ratio"] is not None and lo <= l["ratio"] < hi]
        if v:
            print(f"  {lo:>3.1f} - {hi:>4.1f} : {len(v):>5} trades  R/trade {statistics.fmean(v):>+7.3f}  stops {100 * sum(1 for x in v if x < -0.5) / len(v):>3.0f} %")
    print("\nLecture : on n'installe un frein que si son IC (apres Bonferroni) exclut 0 ET que les deux moities vont dans le meme sens ET qu'il tient en suivi.")
    print("Sinon c'est du bruit : une journee a 10 stops sur 14 n'est pas, a elle seule, une preuve que la strategie est cassee.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
