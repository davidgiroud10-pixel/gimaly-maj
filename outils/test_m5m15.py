# -*- coding: utf-8 -*-
r"""Le MEME signal (rebond sur bande Keltner, stop large, objectif 1,5 R) sur bougies M5 et M15 au lieu de M1 : le spread pese-t-il moins ? (lecture seule)
Regles fixees a l'avance : canal EMA 20 / 2 x ATR(10) sur les bougies de l'unite ; achat si bas <= bande basse < cloture, vente si haut >= bande haute > cloture ;
entree a la cloture ; stop = 0,3 $ au-dela de la meche puis distance cloture-stop doublee ; objectif 1,5 R ; pause de 3 bougies par sens ; sortie au marche
apres 12 bougies (M5 = 60 min, M15 = 180 min) ; stop avant objectif dans la meme bougie ; stop maximum 40 $ ; spread deduit (--spread, 0,20 $).
M1 est rejoue en reference. 2 variantes (M5, M15) -> intervalle corrige Bonferroni (97,5 %), regroupe par jour. Un resultat n'est a retenir que si l'IC exclut 0
ET que les deux moities sont positives ; meme alors, il faut le confirmer sur des trades non encore vus avant de toucher au bot.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_m5m15.py [jj/mm/aaaa] [--spread 0.20]"""
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

Z = 2.24


def agreger(barres, tfs):
    d = {}
    for t, o, h, b, c in barres:
        k = t - t % tfs
        if k not in d:
            d[k] = [o, h, b, c]
        else:
            d[k][1] = max(d[k][1], h)
            d[k][2] = min(d[k][2], b)
            d[k][3] = c
    return [(k, *v) for k, v in sorted(d.items())]


def signaux_tf(b, tfs):
    k = rk.canal(b)
    der = {"achat": -10 ** 9, "vente": -10 ** 9}
    out = []
    for i in range(60, len(b)):
        if k[i] is None:
            continue
        t, o, h, l, c = b[i]
        for sens, touche in (("achat", l <= k[i][2] < c), ("vente", h >= k[i][1] > c)):
            if not touche or t - der[sens] < 3 * tfs:
                continue
            der[sens] = t
            sl = round(l - 0.3 if sens == "achat" else h + 0.3, 2)
            dist = abs(c - sl) * 2
            if dist <= 0 or dist > 40.0:
                continue
            out.append((i, sens, c, round(c - dist if sens == "achat" else c + dist, 2)))
    return out


def jouer_tf(b, i, sens, entree, sl, nb):
    achat = sens == "achat"
    dist = abs(entree - sl)
    tp = entree + rk.TP_R * dist if achat else entree - rk.TP_R * dist
    dern = entree
    for j in range(i + 1, min(len(b), i + 1 + nb)):
        t, o, h, l, c = b[j]
        if (l <= sl) if achat else (h >= sl):
            return -1.0
        if (h >= tp) if achat else (l <= tp):
            return rk.TP_R
        dern = c
    return ((dern - entree) if achat else (entree - dern)) / dist


def evaluer(nom, b, tfs, nb, spread, depuis):
    lignes = []
    for i, sens, entree, sl in signaux_tf(b, tfs):
        t = b[i][0]
        if datetime.fromtimestamp(t, timezone.utc).replace(tzinfo=None) < depuis:
            continue
        dist = abs(entree - sl)
        lignes.append((t, jouer_tf(b, i, sens, entree, sl, nb) - spread / dist, dist))
    if len(lignes) < 100:
        print(f"{nom} : trop peu de signaux ({len(lignes)}).")
        return
    rs = [x[1] for x in lignes]
    par_jour = {}
    for t, r, _ in lignes:
        par_jour.setdefault(datetime.fromtimestamp(t, timezone.utc).date(), []).append(r)
    m, lo, hi = tf.ic_jours(par_jour, len(rs), Z)
    h = len(rs) // 2
    print(f"{nom:<5} {len(rs):>5} signaux | stop moyen {statistics.fmean(x[2] for x in lignes):>5.2f} $ | stops {100 * sum(1 for x in rs if x < -0.5) / len(rs):>3.0f} % | "
          f"R/trade {m:>+7.3f}  IC [{lo:+.3f} ; {hi:+.3f}] | moities {statistics.fmean(rs[:h]):+.3f} / {statistics.fmean(rs[h:]):+.3f}"
          f" | spread/stop {100 * spread / statistics.fmean(x[2] for x in lignes):.1f} %")


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
        m1 = rk.charger(mt5, depuis - timedelta(days=3))
    finally:
        mt5.shutdown()
    if len(m1) < 2000:
        print("Historique M1 insuffisant : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche.")
        return 0
    print(f"{len(m1)} bougies M1, spread deduit {spread:.2f} $ ; R moyen par trade apres spread, IC 97,5 % regroupe par jour\n")
    evaluer("M1", m1, 60, 60, spread, depuis)
    evaluer("M5", agreger(m1, 300), 300, 12, spread, depuis)
    evaluer("M15", agreger(m1, 900), 900, 12, spread, depuis)
    print("\nLecture : on cherche un IC qui EXCLUT 0 avec les deux moities positives. M1 sert de reference (la meme chose que le bot, sans ses filtres).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
