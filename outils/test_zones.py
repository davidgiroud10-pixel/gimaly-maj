# -*- coding: utf-8 -*-
r"""Les zones cles (FVG / IFVG / Order Blocks H1 et H4) et la tendance H1 / H4 aident-ils le signal scalp_keltner_large ? (lecture seule)
Definitions OBJECTIVES, FIXEES A L'AVANCE (une zone discretionnaire ne se teste pas ; celle-ci est mecanique, donc approximative) :
  FVG  : 3 bougies i-2, i-1, i ; haussier si bas(i) > haut(i-2) (zone [haut(i-2) ; bas(i)]), baissier si haut(i) < bas(i-2) ; taille >= 0,25 x ATR(14) de l'unite.
         Connu a la CLOTURE de la bougie i. Cloture au-dela de l'autre bord -> la zone s'INVERSE (IFVG, polarite opposee) ; une 2e cloture inverse l'efface.
  OB   : derniere bougie baissiere (haussiere) avant une impulsion haussiere (baissiere) : haut des 3 bougies suivantes - cloture >= 1,5 x ATR(14).
         Zone = [bas ; haut] de la bougie ; connue apres les 3 bougies d'impulsion ; effacee par une cloture au-dela de son bord oppose.
  Tendance : cloture de la derniere bougie terminee > EMA(50) = haussier, sinon baissier.
Un signal est « ALIGNE » si son entree est DANS une zone active de meme sens (achat dans zone haussiere...), « CONTRE » si dans une zone de sens oppose
(un signal a la fois dans les deux = ignore). Pour la tendance : aligne = signal dans le sens de la tendance.
6 familles pre-enregistrees : FVG+IFVG H1, FVG+IFVG H4, OB H1, OB H4, tendance H1, tendance H4 -> IC corrige Bonferroni (6).
Mesure : R moyen par trade des signaux ALIGNES moins celui des signaux CONTRE (aligne - contre), IC par bootstrap des JOURS, stabilite des deux moities.
Limites : historique M1 limite a ce que MetaTrader a charge ; definitions mecaniques ; une famille « positive » de justesse = a confirmer en suivi, pas a installer.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_zones.py [jj/mm/aaaa] [--spread 0.20]"""
import random
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import rejeu_keltner as rk
    import test_freins as tf
except ImportError:
    print("Place ce script a cote de rejeu_keltner.py et test_freins.py (dossier gimaly).")
    raise SystemExit(1)

INF = float("inf")
Q_BAS, Q_HAUT = 0.05 / 6 / 2, 1 - 0.05 / 6 / 2


def atr14(b):
    out, a, tr = [], None, []
    for i, (t, o, h, l, c) in enumerate(b):
        tr.append(h - l if i == 0 else max(h - l, abs(h - b[i - 1][4]), abs(l - b[i - 1][4])))
        if len(tr) == 14:
            a = sum(tr) / 14
        elif len(tr) > 14:
            a = (a * 13 + tr[-1]) / 14
        out.append(a)
    return out


def zones_fvg(b, tfs):
    """Liste de (t_debut, t_fin, bas, haut, sens) incluant les IFVG."""
    a, res = atr14(b), []
    for i in range(2, len(b)):
        if not a[i]:
            continue
        for sens, ok, lo, hi in ((1, b[i][3] > b[i - 2][2], b[i - 2][2], b[i][3]), (-1, b[i][2] < b[i - 2][3], b[i][2], b[i - 2][3])):
            if not ok or hi - lo < 0.25 * a[i]:
                continue
            t0 = b[i][0] + tfs
            inv = efface = INF
            for j in range(i + 1, len(b)):
                c = b[j][4]
                if inv == INF and ((c < lo) if sens == 1 else (c > hi)):
                    inv = b[j][0] + tfs
                elif inv != INF and ((c > hi) if sens == 1 else (c < lo)):
                    efface = b[j][0] + tfs
                    break
            res.append((t0, inv, lo, hi, sens))
            if inv != INF:
                res.append((inv, efface, lo, hi, -sens))
    return res


def zones_ob(b, tfs):
    a, res = atr14(b), []
    for i in range(len(b) - 3):
        if not a[i]:
            continue
        t, o, h, l, c = b[i]
        hh = max(x[2] for x in b[i + 1:i + 4])
        ll = min(x[3] for x in b[i + 1:i + 4])
        for sens, ok in ((1, c < o and hh - c >= 1.5 * a[i]), (-1, c > o and c - ll >= 1.5 * a[i])):
            if not ok:
                continue
            fin = INF
            for j in range(i + 4, len(b)):
                if (b[j][4] < l) if sens == 1 else (b[j][4] > h):
                    fin = b[j][0] + tfs
                    break
            res.append((b[i + 3][0] + tfs, fin, l, h, sens))
    return res


def tendance(b, tfs, n=50):
    """[(t_connu, sens)] : sens de la cloture vs EMA(n)."""
    k, ema, out = 2 / (n + 1), None, []
    for t, o, h, l, c in b:
        ema = c if ema is None else k * c + (1 - k) * ema
        out.append((t + tfs, 1 if c > ema else -1))
    return out


def etat_zone(zs, t, px):
    """(aligne_possible : ensemble des sens des zones actives contenant px)."""
    return {s for (t0, t1, lo, hi, s) in zs if t0 <= t < t1 and lo <= px <= hi}


def bootstrap(par_jour_a, par_jour_c, graine=7, n=4000):
    random.seed(graine)
    jours = sorted(set(par_jour_a) | set(par_jour_c))
    out = []
    for _ in range(n):
        s = [random.choice(jours) for _ in jours]
        a = [x for j in s for x in par_jour_a.get(j, [])]
        c = [x for j in s for x in par_jour_c.get(j, [])]
        if a and c:
            out.append(statistics.fmean(a) - statistics.fmean(c))
    out.sort()
    return out[int(Q_BAS * len(out))], out[min(len(out) - 1, int(Q_HAUT * len(out)))]


def famille(nom, lignes, cle):
    al = [l for l in lignes if l[cle] == 1]
    co = [l for l in lignes if l[cle] == -1]
    print(f"\n{nom}")
    print(f"  alignes {len(al)} | contre {len(co)} | sans zone / ambigu {len(lignes) - len(al) - len(co)}")
    if len(al) < 100 or len(co) < 100:
        print("  trop peu de signaux dans un des groupes (< 100) : pas d'avis.")
        return
    ma, mc = statistics.fmean(l["r"] for l in al), statistics.fmean(l["r"] for l in co)
    pa, pc = {}, {}
    for l in al:
        pa.setdefault(l["jour"], []).append(l["r"])
    for l in co:
        pc.setdefault(l["jour"], []).append(l["r"])
    lo, hi = bootstrap(pa, pc)
    m = lignes[len(lignes) // 2]["t"]
    def moit(g, avant):
        v = [l["r"] for l in g if (l["t"] < m) == avant]
        return statistics.fmean(v) if v else float("nan")
    print(f"  R/trade : alignes {ma:+.3f} | contre {mc:+.3f} | aligne - contre {ma - mc:+.3f}   IC (jours, Bonferroni 6) [{lo:+.3f} ; {hi:+.3f}]")
    print(f"  moitie 1 : {moit(al, True) - moit(co, True):+.3f} | moitie 2 : {moit(al, False) - moit(co, False):+.3f}")
    print("  => " + ("NON distinguable du hasard" if lo <= 0 <= hi else ("aligne MIEUX (a confirmer)" if lo > 0 else "aligne PIRE")))


def charger_tf(mt5, tf, debut):
    out = []
    r = mt5.copy_rates_range(rk.SYMBOLE, tf, debut, datetime.now() + timedelta(days=1))
    if r is not None:
        out = [(int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in r]
    return sorted(set(out))


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
        h1 = charger_tf(mt5, mt5.TIMEFRAME_H1, depuis - timedelta(days=40))
        h4 = charger_tf(mt5, mt5.TIMEFRAME_H4, depuis - timedelta(days=120))
    finally:
        mt5.shutdown()
    if len(barres) < 2000 or len(h1) < 100 or len(h4) < 50:
        print("Historique insuffisant (M1, H1 ou H4) : ouvre ces graphiques dans MetaTrader et fais-les defiler vers la gauche.")
        return 0
    fvg1, fvg4 = zones_fvg(h1, 3600), zones_fvg(h4, 14400)
    ob1, ob4 = zones_ob(h1, 3600), zones_ob(h4, 14400)
    tr1, tr4 = tendance(h1, 3600), tendance(h4, 14400)

    def sens_tendance(tr, t):
        v = 0
        for tk, s in tr:
            if tk > t:
                break
            v = s
        return v

    lignes = []
    for i, sens, entree, sl in rk.signaux(barres):
        t = barres[i][0]
        if datetime.utcfromtimestamp(t) < depuis:
            continue
        dist = abs(entree - sl)
        r0, j, stop = tf.jouer(barres, i, sens, entree, sl)
        d = 1 if sens == "achat" else -1
        ligne = {"t": t, "r": r0 - spread / dist, "jour": datetime.utcfromtimestamp(t).date()}
        for nom, zs in (("fvg1", fvg1), ("fvg4", fvg4), ("ob1", ob1), ("ob4", ob4)):
            e = etat_zone(zs, t, entree)
            ligne[nom] = 1 if e == {d} else (-1 if e == {-d} else 0)
        for nom, tr in (("tr1", tr1), ("tr4", tr4)):
            s = sens_tendance(tr, t)
            ligne[nom] = 0 if s == 0 else (1 if s == d else -1)
        lignes.append(ligne)
    lignes.sort(key=lambda x: x["t"])
    if len(lignes) < 300:
        print("Trop peu de signaux.")
        return 0
    print(f"{len(lignes)} signaux rejoues, spread {spread:.2f} $, R moyen de reference {statistics.fmean(l['r'] for l in lignes):+.3f}")
    for nom, cle in (("FVG + IFVG H1", "fvg1"), ("FVG + IFVG H4", "fvg4"), ("Order Blocks H1", "ob1"), ("Order Blocks H4", "ob4"),
                     ("Tendance H1 (cloture vs EMA50)", "tr1"), ("Tendance H4 (cloture vs EMA50)", "tr4")):
        famille(nom, lignes, cle)
    print("\nLecture : une famille n'a de valeur que si son IC exclut 0 apres correction ET que les deux moities vont dans le meme sens. Sinon, la zone ne")
    print("« lit » rien de plus que le hasard sur cet historique. Ces definitions sont mecaniques : une lecture a la main peut etre meilleure, mais elle n'est pas testable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
