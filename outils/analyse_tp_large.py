# -*- coding: utf-8 -*-
r"""Objectifs plus LARGES + point mort + stop SUIVEUR sur tes trades deja faits : peut-on limiter les stops pleins ? (lecture seule, rien n'est modifie)

Chaque trade termine (trades_bot.csv, ou les fantomes avec --source) est rejoue sur les bougies M1 de MetaTrader depuis son entree avec le MEME
stop de depart, puis avec 9 variantes fixees d'avance (1 R = distance entree-stop de depart) :
  objectif 2 R ou 3 R ou 4 R au lieu de l'objectif actuel ; point mort (stop remonte au prix d'entree + 0,2 $) quand le trade a gagne 0,8 R ou 1 R ;
  stop suiveur (le stop suit le meilleur prix a 0,8 R, 1 R ou 1,5 R en arriere) une fois un certain gain atteint.
Reference : le rejeu « actuel » (stop + objectif d'origine) sur la meme periode, pas le R reellement enregistre (le rejeu peut differer du reel : spread,
glissement). Le tableau donne pour chaque variante : part de trades qui finissent en STOP PLEIN (R <= -0,9), R moyen, difference avec « actuel » et son
intervalle (calcule PAR JOUR, car les trades d'un meme jour se ressemblent), puis chaque moitie de la periode.
Une variante n'est credible que si l'intervalle de la difference EXCLUT 0 au niveau corrige pour 9 variantes (99,4 %), que la difference est positive dans
les deux moities et qu'il y a assez de jours. Hypotheses prudentes (meme que analyse_be_trailing.py) : stop avant objectif dans la meme minute, vente
rachetee a l'ask, sortie forcee a la fin de l'horizon (240 min par defaut). Attention : un objectif plus large allonge la duree des trades (le bot coupe
a 60 min aujourd'hui) et diminue la part de trades gagnants.
Usage (dossier gimaly, MetaTrader 5 ouvert, historique M1 charge, a cote de analyse_be_trailing.py et diag_tp.py) :
  .\.venv\Scripts\python.exe analyse_tp_large.py                       trades reels scalp_keltner_large depuis le 20/10/2026
  .\.venv\Scripts\python.exe analyse_tp_large.py --depuis 06/11/2026   seulement les nouveaux trades (test hors echantillon)
  .\.venv\Scripts\python.exe analyse_tp_large.py --genre tous --source tous"""
import datetime as dt
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import analyse_be_trailing as abt
    import diag_tp
except ImportError:
    print("Place ce script a cote de analyse_be_trailing.py et diag_tp.py (dossier gimaly).")
    raise SystemExit(1)

Z_BONF = 2.77          # 99,4 % bilateral : 9 variantes comparees
VARIANTES = [
    {"nom": "actuel (stop/objectif d'origine)"},
    {"nom": "objectif 2 R", "tp_r": 2.0},
    {"nom": "objectif 3 R", "tp_r": 3.0},
    {"nom": "objectif 2 R + point mort a 1 R", "tp_r": 2.0, "be": 1.0},
    {"nom": "objectif 3 R + point mort a 1 R", "tp_r": 3.0, "be": 1.0},
    {"nom": "objectif 2 R + pt mort 0,8 R + suiveur 0,8 R des 1,2 R", "tp_r": 2.0, "be": 0.8, "trail": (1.2, 0.8)},
    {"nom": "objectif 3 R + pt mort 0,8 R + suiveur 1 R des 1,5 R", "tp_r": 3.0, "be": 0.8, "trail": (1.5, 1.0)},
    {"nom": "objectif 3 R + pt mort 1 R + suiveur 1 R des 2 R", "tp_r": 3.0, "be": 1.0, "trail": (2.0, 1.0)},
    {"nom": "objectif 4 R + pt mort 1 R + suiveur 1,5 R des 2 R", "tp_r": 4.0, "be": 1.0, "trail": (2.0, 1.5)},
]
_rejouer_origine = abt.rejouer


def rejouer(achat, pe, sl, tp, bougies, pt, v):
    if v.get("tp_r"):
        s = 1 if achat else -1
        risque = abs(pe - sl)
        tp = pe + s * v["tp_r"] * risque
        v = {k: x for k, x in v.items() if k != "tp_r"}
    return _rejouer_origine(achat, pe, sl, tp, bougies, pt, v)


def ic_jours(valeurs_par_jour, z):
    """(n, jours, moyenne, bas, haut) avec erreur type regroupee par jour."""
    n = sum(len(v) for v in valeurs_par_jour.values())
    if not n:
        return None
    m = sum(sum(v) for v in valeurs_par_jour.values()) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in valeurs_par_jour.values())) / n
    return n, len(valeurs_par_jour), m, m - z * se, m + z * se


def preparer(trades, rates, duree):
    ouvertures = {int(r["time"]): float(r["open"]) for r in rates}
    temps = [float(r["time"]) for r in rates]
    import bisect
    donnees, rejetes = [], 0
    for tr in trades:
        al = abt.aligner(tr["t"].timestamp(), tr["pe"], DECALAGE[0], ouvertures)
        if al is None or al[2] > 3:
            rejetes += 1
            continue
        a = al[0]
        i0, i1 = bisect.bisect_left(temps, a), bisect.bisect_right(temps, a + duree * 60)
        bougies = rates[i0:i1]
        if len(bougies):
            donnees.append((tr["t"], tr["achat"], tr["pe"], tr["sl"], tr["tp"], bougies))
    return donnees, rejetes


DECALAGE = [0.0]


def tableau(titre, trades, rates, pt, duree):
    donnees, rejetes = preparer(trades, rates, duree)
    print(f"\n=== {titre} : {len(donnees)} trade(s) rejoues sur {len(trades)} ({rejetes} ecartes : prix d'entree non retrouve) | horizon {duree} min ===")
    if len(donnees) < 30:
        print("trop peu de trades pour comparer quoi que ce soit.")
        return
    jours = sorted({d[0].date() for d in donnees})
    milieu = jours[len(jours) // 2]
    res = {v["nom"]: [rejouer(d[1], d[2], d[3], d[4], d[5], pt, v) for d in donnees] for v in VARIANTES}
    base = res[VARIANTES[0]["nom"]]
    print(f"{len(jours)} jours, 2e moitie a partir du {milieu:%d/%m/%Y}")
    print(f"{'variante':<58}{'n':>4}{'stop plein':>11}{'R moyen':>9}{'diff vs actuel':>16}{'IC corrige 99,4 %':>22}  {'1re':>7}{'2e':>7}")
    for v in VARIANTES:
        r = res[v["nom"]]
        ok = [i for i in range(len(donnees)) if r[i] is not None and base[i] is not None]
        if not ok:
            continue
        rs = [r[i] for i in ok]
        pleins = 100 * sum(1 for x in rs if x <= -0.9) / len(rs)
        diffs = {}
        for i in ok:
            diffs.setdefault(donnees[i][0].date(), []).append(r[i] - base[i])
        ic = ic_jours(diffs, Z_BONF)
        d1 = [r[i] - base[i] for i in ok if donnees[i][0].date() < milieu]
        d2 = [r[i] - base[i] for i in ok if donnees[i][0].date() >= milieu]
        f = lambda z: f"{statistics.fmean(z):>+7.3f}" if len(z) >= 10 else "  (peu)"
        if v is VARIANTES[0]:
            print(f"{v['nom']:<58}{len(rs):>4}{pleins:>10.0f}%{statistics.fmean(rs):>+9.3f}{'-':>16}{'-':>22}  {f([x for i, x in zip(ok, rs) if donnees[i][0].date() < milieu]):>7}{f([x for i, x in zip(ok, rs) if donnees[i][0].date() >= milieu]):>7}")
            continue
        n, nj, m, lo, hi = ic
        marque = " *" if lo > 0 and statistics.fmean(d1) > 0 and statistics.fmean(d2) > 0 else ""
        print(f"{v['nom']:<58}{len(rs):>4}{pleins:>10.0f}%{statistics.fmean(rs):>+9.3f}{m:>+16.3f}  [{lo:>+7.3f} ; {hi:>+7.3f}]  {f(d1):>7}{f(d2):>7}{marque}")
    print("  (* = intervalle corrige au-dessus de 0 ET difference positive dans les deux moities ; sans *, la variante ne se distingue pas du hasard)")


def main():
    args = sys.argv[1:]

    def option(nom, defaut):
        if nom in args:
            i = args.index(nom)
            val = args[i + 1]
            del args[i:i + 2]
            return val
        return defaut

    abt.VARIANTES = VARIANTES
    depuis = dt.datetime.strptime(option("--depuis", "20/10/2026"), "%d/%m/%Y")
    genre = option("--genre", "scalp_keltner_large")
    genre = None if genre == "tous" else genre
    source = option("--source", "reels")
    duree = int(option("--duree", "240"))
    force = option("--decalage", None)
    force = float(force.replace(",", ".")) if force else None
    jeux = []
    if source in ("reels", "tous"):
        jeux.append(("trades REELS", abt.lire_reels(depuis, genre)))
    if source in ("fantomes", "tous"):
        jeux.append(("trades FANTOMES (refuses par le bot)", abt.lire_fantomes(depuis, genre)))
    jeux = [(t, x) for t, x in jeux if x]
    if not jeux:
        sys.exit("aucun trade sur cette periode")
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MetaTrader 5 introuvable : ouvre-le et connecte-toi")
    try:
        try:
            from gimaly.trading.symbole import symbole_or
            sym = symbole_or()
        except Exception:  # noqa: BLE001
            sym = "XAUUSD"
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        pt = float(info.point) if info else 0.01
        DECALAGE[0] = diag_tp.decalage_serveur(mt5, sym, force)
        debut = min(x[0]["t"] for _, x in jeux).timestamp() + DECALAGE[0] - 3600 * 2
        fin = max(x[-1]["t"] for _, x in jeux).timestamp() + DECALAGE[0] + (duree + 60) * 60 + 3600
        rates = diag_tp.charger_bougies(mt5, sym, debut, fin)
        if rates is None:
            sys.exit("MT5 ne fournit pas les bougies M1 de cette periode : ouvre un graphique " + sym + " en M1 et fais-le defiler vers la gauche, puis relance.")
        print(f"{sym} : {len(rates)} bougies M1 chargees, depuis le {depuis:%d/%m/%Y}" + (f", genre {genre}" if genre else ", tous genres"))
        for titre, trades in jeux:
            tableau(titre, trades, rates, pt, duree)
        print("\nLecture : 'stop plein' = part de trades qui finissent a -0,9 R ou pire. Si une variante baisse les stops pleins mais fait baisser le R moyen, tu changes")
        print("de profil (moins de gros stops, gains plus petits) sans gagner d'argent. Une variante n'a de sens que si elle porte un *. A refaire sur les trades a venir.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
