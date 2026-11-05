# -*- coding: utf-8 -*-
r"""Trades « longs » (swing) avec STOP SUIVEUR, sans objectif fixe : est-ce que laisser courir paie ? (lecture seule)

PARTIE A - tes entrees reelles du bot, gerees autrement. Pour chaque trade termine (trades_bot.csv), on rejoue les bougies M1 de
MetaTrader depuis l'entree avec le MEME stop de depart, mais SANS objectif : le stop suit le prix a une distance de 1 / 1,5 / 2 / 3 fois
le stop de depart (il ne recule jamais), et le trade dure au plus 4 h ou 24 h. Resultat en R. Compare au resultat de la gestion actuelle
(stop + objectif tp1) rejouee de la meme facon, et au resultat reel. Deux moities de periode pour voir si ca tient.
PARTIE B - un systeme swing independant sur plusieurs annees (bougies H4) : entree sur cassure du plus haut/plus bas des N dernieres
bougies (N = 20 ou 55), stop de depart et suiveur a k fois l'ATR(14) (k = 2, 3 ou 4), sortie uniquement par le stop suiveur. Achats et
ventes separes, resultat en R apres un spread suppose (0,30 $ par trade), detail PAR ANNEE. Attention : l'or a beaucoup monte ces annees,
donc les achats profitent de la tendance : regarde surtout si les ventes et les annees faibles tiennent.
Honnetete : 6 reglages x 2 sens testes = risque de hasard ; un bon chiffre isole ne prouve rien. Spread et glissement : simplifies.
Necessite MetaTrader 5 ouvert (celui du bot) ; ce script a cote de analyse_stop_ideal.py. Rien n'est modifie, aucun ordre.

Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe analyse_swing_suiveur.py                  parties A et B, depuis le 20/10/2026 pour A
  .\.venv\Scripts\python.exe analyse_swing_suiveur.py 20/10/2026 --genre tous
  .\.venv\Scripts\python.exe analyse_swing_suiveur.py --partie B --spread 0.4"""
import csv
import statistics
import sys
import time
from datetime import datetime

try:
    from analyse_stop_ideal import (DECALAGES_H, FICHIER, SYMBOLE, alignement, trades_complets)
except ImportError:  # pragma: no cover
    print("Place ce script a cote de analyse_stop_ideal.py (dossier gimaly).")
    raise SystemExit(1)

MULTS = (1.0, 1.5, 2.0, 3.0)
DUREES_H = (4, 24)


def suiveur(barres, sens, pe, stop, mult, duree_s, t0):
    """barres : (t, haut, bas, cloture) triees. Renvoie le R. Stop avant mise a jour dans la meme bougie (prudent). Fin de duree : cloture."""
    achat = sens == "achat"
    courant = pe - stop if achat else pe + stop
    meilleur = pe
    dern = pe
    for t, h, b, c in barres:
        if t - t0 > duree_s:
            break
        if (b <= courant) if achat else (h >= courant):
            return ((courant - pe) if achat else (pe - courant)) / stop
        if achat:
            meilleur = max(meilleur, h)
            courant = max(courant, meilleur - mult * stop)
            if b <= courant:          # prudent : le plus haut vient avant le plus bas de la meme bougie
                return (courant - pe) / stop
        else:
            meilleur = min(meilleur, b)
            courant = min(courant, meilleur + mult * stop)
            if h >= courant:
                return (pe - courant) / stop
        dern = c
    return ((dern - pe) if achat else (pe - dern)) / stop


def fixe(barres, sens, pe, stop, tp1, duree_s, t0):
    achat = sens == "achat"
    ps = pe - stop if achat else pe + stop
    dist = abs(tp1 - pe)
    dern = pe
    for t, h, b, c in barres:
        if t - t0 > duree_s:
            break
        if (b <= ps) if achat else (h >= ps):
            return -1.0
        if (h >= tp1) if achat else (b <= tp1):
            return dist / stop
        dern = c
    return ((dern - pe) if achat else (pe - dern)) / stop


def partie_a(mt5, genre, depuis, spread):
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        trades = trades_complets(list(csv.DictReader(f, delimiter=";")), genre, depuis)
    if not trades:
        print("PARTIE A : aucun trade termine a analyser.")
        return
    tick = mt5.symbol_info_tick(SYMBOLE)
    decalage = (tick.time - time.time()) if tick and tick.time else 0.0
    donnees = []
    for t_ouv, sens, pe, sl, tp1, etat, r in trades:
        reel = t_ouv.timestamp() + decalage
        m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 5 * 3600),
                                  datetime.fromtimestamp(reel + 5 * 3600 + 25 * 3600))
        if m1 is None or len(m1) < 10:
            continue
        brut = sorted((int(x["time"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in m1)
        donnees.append((reel, sens, pe, sl, tp1, etat, r, [(t, h, b) for t, h, b, _ in brut], brut, t_ouv))
    if not donnees:
        print("PARTIE A : aucune bougie exploitable (ouvre un graphique M1 de l'or dans MetaTrader).")
        return
    scores = {h: alignement([d[:8] for d in donnees], h) for h in DECALAGES_H}
    h_ok = max(scores, key=lambda h: scores[h][0])
    print(f"PARTIE A - {len(donnees)} trades | signal : {genre} | depuis le {depuis:%d/%m/%Y} | alignement {100 * scores[h_ok][0]:.0f} % "
          f"(decalage {h_ok:+d} h)")
    if scores[h_ok][0] < 0.7:
        print("ATTENTION : alignement trop faible, resultats non fiables.")
    prep = []
    for reel, sens, pe, sl, tp1, etat, r, _, brut, t_ouv in sorted(donnees, key=lambda d: d[9]):
        t0 = reel + 3600 * h_ok - 60
        barres = [x for x in brut if x[0] >= t0]
        prep.append((sens, pe, abs(pe - sl), tp1, r, barres, t0))
    moitie = len(prep) // 2
    reel_r = sum(p[4] for p in prep)
    print(f"Spread suppose : {spread:.2f} $ par trade, retire de CHAQUE resultat simule (= {spread / statistics.fmean(p[2] for p in prep):.2f} R en moyenne). "
          "Les trades sont rejoues chacun de leur cote : aucune limite du nombre de positions ouvertes en meme temps.")
    print(f"Resultat REEL : {reel_r:+.2f} R ({reel_r / len(prep):+.2f} R/trade)")
    for h in DUREES_H:
        d = h * 3600
        base = [fixe(p[5], p[0], p[1], p[2], p[3], d, p[6]) - spread / p[2] for p in prep]
        print(f"\n  Duree max {h} h - gestion actuelle rejouee (stop + objectif) : {sum(base):+.2f} R ({sum(base) / len(base):+.2f} R/trade)")
        print(f"    {'suiveur':>9} {'R total':>9} {'R/trade':>8} {'reussite':>9} {'1re moitie':>11} {'2e moitie':>10} {'ecart vs actuelle':>18}")
        for m in MULTS:
            res = [suiveur(p[5], p[0], p[1], p[2], m, d, p[6]) - spread / p[2] for p in prep]
            g = 100 * sum(1 for x in res if x > 0) / len(res)
            print(f"    {m:>7.1f}x {sum(res):>+9.2f} {sum(res) / len(res):>+8.2f} {g:>8.0f}% {sum(res[:moitie]):>+11.2f} "
                  f"{sum(res[moitie:]):>+10.2f} {sum(res) - sum(base):>+18.2f}")
    print("\n  Lecture : un suiveur n'est interessant que s'il bat la gestion actuelle dans LES DEUX moities. Ces entrees ont ete choisies pour")
    print("  le scalp : meme si ca ne marche pas ici, ca ne dit rien d'un vrai systeme swing (partie B).")


def atr(h, b, c, n=14):
    tr = [h[0] - b[0]] + [max(h[i] - b[i], abs(h[i] - c[i - 1]), abs(b[i] - c[i - 1])) for i in range(1, len(c))]
    out, cur = [None] * len(c), None
    for i, x in enumerate(tr):
        cur = x if cur is None else (cur * (n - 1) + x) / n
        out[i] = cur if i >= n - 1 else None
    return out


def systeme(barres, N, k, sens, spread):
    """barres : (t, o, h, b, c). Renvoie [(annee, R)]."""
    t = [x[0] for x in barres]
    o = [x[1] for x in barres]
    h = [x[2] for x in barres]
    b = [x[3] for x in barres]
    c = [x[4] for x in barres]
    a = atr(h, b, c)
    res = []
    i = N + 15
    while i < len(c) - 1:
        if a[i] is None:
            i += 1
            continue
        haut = max(h[i - N:i])
        bas = min(b[i - N:i])
        signal = (c[i] > haut) if sens == "achat" else (c[i] < bas)
        if not signal:
            i += 1
            continue
        entree = o[i + 1]
        risque = k * a[i]
        stop = entree - risque if sens == "achat" else entree + risque
        extr = entree
        j = i + 1
        sortie = None
        while j < len(c):
            if (b[j] <= stop) if sens == "achat" else (h[j] >= stop):
                sortie = min(stop, o[j]) if sens == "achat" else max(stop, o[j])
                break
            if sens == "achat":
                extr = max(extr, h[j])
                stop = max(stop, extr - risque)
            else:
                extr = min(extr, b[j])
                stop = min(stop, extr + risque)
            j += 1
        if sortie is None:
            break
        gain = (sortie - entree) if sens == "achat" else (entree - sortie)
        res.append((datetime.fromtimestamp(t[i + 1]).year, (gain - spread) / risque))
        i = j + 1
    return res


def partie_b(mt5, spread):
    brut = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_H4, 0, 12000)
    if brut is None or len(brut) < 500:
        print("PARTIE B : historique H4 insuffisant (ouvre un graphique H4 de l'or dans MetaTrader et fais defiler vers la gauche).")
        return
    barres = sorted((int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in brut)
    d0, d1 = datetime.fromtimestamp(barres[0][0]), datetime.fromtimestamp(barres[-1][0])
    print(f"\nPARTIE B - {len(barres)} bougies H4 du {d0:%d/%m/%Y} au {d1:%d/%m/%Y} | {barres[0][4]:.0f} -> {barres[-1][4]:.0f} "
          f"({100 * (barres[-1][4] / barres[0][4] - 1):+.0f} % : le prix a deja beaucoup monte, favorable aux achats) | spread {spread:.2f} $")
    annees = sorted({datetime.fromtimestamp(x[0]).year for x in barres})
    print(f"  {'sens':>6} {'N':>3} {'k':>3} {'trades':>7} {'reussite':>9} {'R moy':>7} {'R total':>8}   R par annee ({', '.join(str(a) for a in annees)})")
    for sens in ("achat", "vente"):
        for N in (20, 55):
            for k in (2, 3, 4):
                res = systeme(barres, N, k, sens, spread)
                if not res:
                    continue
                rs = [r for _, r in res]
                par = [sum(r for a_, r in res if a_ == an) for an in annees]
                print(f"  {sens:>6} {N:>3} {k:>3} {len(rs):>7} {100 * sum(1 for r in rs if r > 0) / len(rs):>8.0f}% {statistics.fmean(rs):>+7.2f} "
                      f"{sum(rs):>+8.1f}   " + " ".join(f"{x:>+6.1f}" for x in par))
    print("\n  Lecture : cherche une ligne positive dans la plupart des annees, pas seulement une annee. Les achats suivent la hausse de l'or ;")
    print("  une vente rentable de facon reguliere serait plus parlante. Un systeme swing a typiquement 30-40 % de reussite et quelques gros")
    print("  gains : c'est normal. 12 lignes testees : ne retiens pas la meilleure sans la tester sur des donnees nouvelles.")


def main(argv):
    argv = list(argv)
    genre, partie, spread = "scalp_keltner_large", "AB", 0.30
    for opt in ("--genre", "--partie", "--spread"):
        if opt in argv:
            i = argv.index(opt)
            val = argv[i + 1] if i + 1 < len(argv) else ""
            del argv[i:i + 2]
            if opt == "--genre":
                genre = val or genre
            elif opt == "--partie":
                partie = val.upper() or partie
            else:
                try:
                    spread = float(val.replace(",", "."))
                except ValueError:
                    print("Spread attendu en dollars, ex. 0,3")
                    return 1
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(SYMBOLE, True)
        if "A" in partie:
            partie_a(mt5, genre, depuis, spread)
        if "B" in partie:
            partie_b(mt5, spread)
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
