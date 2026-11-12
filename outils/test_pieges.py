# -*- coding: utf-8 -*-
r"""Fausses cassures et meches : le signal se fait-il piéger ? (lecture seule, aucun ordre)
PARTIE 1 - « stoppe puis objectif atteint » : parmi les trades stoppes, quelle part voit quand meme le prix atteindre l'objectif dans les 60 min qui suivent le stop ?
  Comparee a un TEMOIN : meme nombre d'entrees tirees au hasard (heure, sens au hasard, meme distance de stop), meme regle. Si le signal se faisait piéger par les meches,
  son taux serait nettement SUPERIEUR au temoin ; s'il est egal, ces retours sont le simple hasard du marche. Pour k = 1 ; 1,5 ; 2 (stop plus large = moins de stops).
PARTIE 2 - confirmation avant d'entrer (stop identique, objectif 1,5 R recalcule sur la nouvelle entree, spread deduit) :
  C1 = on entre a la cloture de la bougie SUIVANTE seulement si elle va dans le sens du trade (cloture > ouverture pour un achat) et ne casse pas le stop ;
  C2 = comme C1 et en plus la bougie suivante ne fait pas de nouveau extreme au-dela de la meche du signal.
  Mesures : R/trade des trades pris ; effet du retard d'entree (meme signaux, entree normale contre entree confirmee, difference appariee, IC 97,5 % regroupe par jour) ;
  VERDICT : R/trade des trades confirmes moins R/trade de reference (tous les signaux, entree normale), IC regroupe par jour. Deux comparaisons -> IC corrige Bonferroni.
A retenir seulement si le VERDICT a un IC qui exclut 0 ET que les deux moities vont dans le meme sens. (Un filtre qui retire des trades parait « aider » quand le R moyen est negatif : le verdict le corrige en comparant a la moyenne.)
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_pieges.py [jj/mm/aaaa] [--spread 0.20]"""
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import rejeu_keltner as rk
    import test_freins as tf
except ImportError:
    print("Place ce script a cote de rejeu_keltner.py et test_freins.py (dossier gimaly).")
    raise SystemExit(1)

KS = (1.0, 1.5, 2.0)
Z2 = 2.24


def retour(b, j, sens, tp, duree=3600):
    """Le prix atteint-il `tp` dans les `duree` secondes apres la bougie de stop j (bougie du stop exclue) ?"""
    achat = sens == "achat"
    t0 = b[j][0]
    for m in range(j + 1, len(b)):
        if b[m][0] - t0 > duree:
            return False
        if (b[m][2] >= tp) if achat else (b[m][3] <= tp):
            return True
    return False


def partie1(b, sigs, depuis):
    rng = random.Random(20261112)
    idx = [i for i in range(60, len(b) - 70) if datetime.fromtimestamp(b[i][0], timezone.utc).replace(tzinfo=None) >= depuis]
    out = {}
    for k in KS:
        sig_n = sig_ret = tem_n = tem_ret = 0
        for i, sens, entree, sl in sigs:
            d = abs(entree - sl) * k
            slk = round(entree - d if sens == "achat" else entree + d, 2)
            r, j, stop = tf.jouer(b, i, sens, entree, slk)
            if stop:
                sig_n += 1
                tp = entree + rk.TP_R * d if sens == "achat" else entree - rk.TP_R * d
                sig_ret += retour(b, j, sens, tp)
            # temoin : entree au hasard, sens au hasard, meme distance de stop
            ii = rng.choice(idx)
            s2 = rng.choice(("achat", "vente"))
            e2 = b[ii][4]
            sl2 = round(e2 - d if s2 == "achat" else e2 + d, 2)
            r2, j2, st2 = tf.jouer(b, ii, s2, e2, sl2)
            if st2:
                tem_n += 1
                tp2 = e2 + rk.TP_R * d if s2 == "achat" else e2 - rk.TP_R * d
                tem_ret += retour(b, j2, s2, tp2)
        out[k] = (sig_n, sig_ret, tem_n, tem_ret)
    return out


def jouer_conf(b, i, sens, entree, sl, strict):
    """(R brut, entree confirmee) ou None si pas de confirmation. Entree a la cloture de la bougie i+1."""
    achat = sens == "achat"
    t, o, h, l, c = b[i + 1]
    if achat:
        ok = c > o and l > sl
        if strict:
            ok = ok and l >= b[i][3]
    else:
        ok = c < o and h < sl
        if strict:
            ok = ok and h <= b[i][2]
    if not ok:
        return None
    r, _, _ = tf.jouer(b, i + 1, sens, c, sl)
    return r, c


def partie2(b, sigs, depuis, spread):
    res = {1: [], 2: []}
    base_all = []
    for i, sens, entree, sl in sigs:
        if i + 2 >= len(b):
            continue
        d0 = abs(entree - sl)
        jour = datetime.fromtimestamp(b[i][0], timezone.utc).date()
        r0, _, _ = tf.jouer(b, i, sens, entree, sl)
        r0n = r0 - spread / d0
        base_all.append(r0n)
        for v, strict in ((1, False), (2, True)):
            x = jouer_conf(b, i, sens, entree, sl, strict)
            if x is None:
                continue
            r, c = x
            dist = abs(c - sl)
            if dist <= 0:
                continue
            res[v].append({"t": b[i][0], "jour": jour, "r0": r0n, "rc": r - spread / dist})
    return res, base_all


def ic(par_jour, n):
    return tf.ic_jours(par_jour, n, Z2)


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
        b = rk.charger(mt5, depuis - timedelta(days=3))
    finally:
        mt5.shutdown()
    return analyser(b, depuis, spread)


def analyser(b, depuis, spread):
    if len(b) < 2000:
        print("Historique M1 insuffisant : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche.")
        return 0
    sigs = [s for s in rk.signaux(b) if datetime.fromtimestamp(b[s[0]][0], timezone.utc).replace(tzinfo=None) >= depuis]
    if len(sigs) < 300:
        print("Trop peu de signaux.")
        return 0
    print(f"{len(sigs)} signaux du {datetime.fromtimestamp(b[sigs[0][0]][0], timezone.utc):%d/%m/%Y} au {datetime.fromtimestamp(b[sigs[-1][0]][0], timezone.utc):%d/%m/%Y}")
    print("\n=== PARTIE 1 : stoppe puis objectif atteint dans les 60 min qui suivent le stop ===")
    p1 = partie1(b, sigs, depuis)
    print(f"{'k':>5}{'stops signal':>14}{'retour':>9}{'stops temoin':>14}{'retour':>9}   ecart (signal - temoin)")
    for k in KS:
        sn, sr, tn, tr = p1[k]
        ps, pt = (sr / sn if sn else 0), (tr / tn if tn else 0)
        se = ((ps * (1 - ps) / sn if sn else 0) + (pt * (1 - pt) / tn if tn else 0)) ** 0.5
        e = ps - pt
        marque = "" if abs(e) <= Z2 * se else ("  <- PLUS DE RETOURS QUE LE HASARD" if e > 0 else "  <- MOINS")
        print(f"{k:>5.1f}{sn:>14}{100 * ps:>8.0f}%{tn:>14}{100 * pt:>8.0f}%   {100 * e:+.1f} pts (+/- {100 * Z2 * se:.1f}){marque}")
    print("(IC naif sur les trades, plus etroit qu'un IC par jour : un ecart juste au bord n'est PAS une preuve.)")
    print("\n=== PARTIE 2 : confirmation avant d'entrer ===")
    res, base_all = partie2(b, sigs, depuis, spread)
    moy_all = statistics.fmean(base_all)
    print(f"reference (tous les signaux, entree normale) : {len(base_all)} trades, {moy_all:+.3f} R/trade apres spread")
    noms = {1: "C1 bougie suivante dans le sens", 2: "C2 + pas de nouvel extreme"}
    for v in (1, 2):
        L = res[v]
        n = len(L)
        if n < 100:
            print(f"{noms[v]} : trop peu de trades ({n}).")
            continue
        r_c = statistics.fmean(x["rc"] for x in L)
        r_0 = statistics.fmean(x["r0"] for x in L)
        pj = {}
        for x in L:
            pj.setdefault(x["jour"], []).append(x["rc"] - x["r0"])
        m, lo, hi = ic(pj, n)
        pq = {}
        for x in L:
            pq.setdefault(x["jour"], []).append(x["rc"] - moy_all)
        mq, loq, hiq = ic(pq, n)
        L.sort(key=lambda x: x["t"])
        h = n // 2
        d1 = statistics.fmean(x["rc"] - x["r0"] for x in L[:h])
        d2 = statistics.fmean(x["rc"] - x["r0"] for x in L[h:])
        print(f"\n{noms[v]} : {n} trades pris sur {len(base_all)} ({100 * n / len(base_all):.0f} %)")
        print(f"  R/trade confirme {r_c:+.3f}  |  meme signaux entree normale {r_0:+.3f}")
        print(f"  effet du retard d'entree (confirme - normal) : {m:+.3f} [{lo:+.3f} ; {hi:+.3f}]  moities {d1:+.3f} / {d2:+.3f}")
        print(f"  VERDICT : R/trade confirme moins R/trade de reference (tous signaux, entree normale) : {mq:+.3f} [{loq:+.3f} ; {hiq:+.3f}]")
    print("\nLecture : seule la ligne VERDICT compte (IC > 0 qui exclut 0, les deux moities dans le meme sens). Les signaux gardes ressemblent a de meilleurs trades AVANT le retard")
    print("simplement parce que la bougie de confirmation fait deja partie de leur trajet (biais mecanique) : ne juge pas le filtre sur « meme signaux entree normale ».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
