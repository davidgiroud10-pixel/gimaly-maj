# -*- coding: utf-8 -*-
r"""La bougie ENGLOBANTE apres la touche de la bande Keltner ameliore-t-elle le rebond ? (lecture seule, aucun ordre)
Regles fixees a l'avance (Keltner du bot : EMA 20, 2 x ATR 10 ; reglages de l'indicateur TradingView inconnus, script verrouille) :
  - signal de touche = celui de rejeu_keltner.py (bougie i). On entre toujours a la CLOTURE de la bougie suivante (i+1), pour comparer a armes egales.
  - ENGLOBANTE d'achat : la bougie i+1 est haussiere, son corps englobe celui de la bougie i (ouverture <= bas du corps de i, cloture >= haut du corps de i) ;
    ENGLOBANTE de vente : symetrique. Sinon, le signal est « sans englobante ».
  - stop = 0,3 $ au-dela de la meche la plus extreme des bougies i et i+1, puis distance doublee (comme le bot) ; objectif 1,5 R ; sortie au marche apres 60 min ;
    stop avant objectif dans la meme bougie ; stop maximum 40 $ ; spread deduit (--spread, 0,20 $).
Une seule comparaison (englobante - sans englobante), IC a 95 % regroupe par jour, stabilite des deux moities. A retenir seulement si l'IC exclut 0 ET que les deux
moities vont dans le meme sens ; meme alors, a confirmer sur des trades non encore vus.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_englobante.py [jj/mm/aaaa] [--spread 0.20]"""
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


def jour(t):
    return datetime.fromtimestamp(t, timezone.utc).date()


def engloutit(achat, bi, bj):
    """bi, bj = (t, o, h, l, c) de la bougie de touche et de la suivante."""
    lo, hi = min(bi[1], bi[4]), max(bi[1], bi[4])
    if achat:
        return bj[4] > bj[1] and bj[1] <= lo and bj[4] >= hi
    return bj[4] < bj[1] and bj[1] >= hi and bj[4] <= lo


def bootstrap(pa, pb, n=4000, graine=11):
    random.seed(graine)
    jours = sorted(set(pa) | set(pb))
    out = []
    for _ in range(n):
        s = [random.choice(jours) for _ in jours]
        a = [x for j in s for x in pa.get(j, [])]
        b = [x for j in s for x in pb.get(j, [])]
        if a and b:
            out.append(statistics.fmean(a) - statistics.fmean(b))
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


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
    if len(b) < 2000:
        print("Historique M1 insuffisant : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche.")
        return 0
    lignes = []
    for i, sens, _, _ in rk.signaux(b):
        j = i + 1
        if j >= len(b) - 1 or b[j][0] - b[i][0] != 60:
            continue
        if datetime.fromtimestamp(b[i][0], timezone.utc).replace(tzinfo=None) < depuis:
            continue
        achat = sens == "achat"
        entree = b[j][4]
        meche = min(b[i][3], b[j][3]) if achat else max(b[i][2], b[j][2])
        sl0 = round(meche - 0.3 if achat else meche + 0.3, 2)
        dist = abs(entree - sl0) * 2
        if dist <= 0 or dist > 40.0 or (achat and entree <= sl0) or (not achat and entree >= sl0):
            continue
        sl = round(entree - dist if achat else entree + dist, 2)
        r0, _, stop = tf.jouer(b, j, sens, entree, sl)
        lignes.append({"t": b[j][0], "eng": engloutit(achat, b[i], b[j]), "r": r0 - spread / dist, "jour": jour(b[j][0])})
    if len(lignes) < 300:
        print("Trop peu de signaux.")
        return 0
    lignes.sort(key=lambda x: x["t"])
    oui = [l for l in lignes if l["eng"]]
    non = [l for l in lignes if not l["eng"]]
    print(f"{len(lignes)} signaux (entree a la cloture de la bougie suivante), spread {spread:.2f} $, du {lignes[0]['jour']:%d/%m/%Y} au {lignes[-1]['jour']:%d/%m/%Y}")
    print(f"  avec englobante : {len(oui)} ({100 * len(oui) / len(lignes):.0f} %) | sans : {len(non)}")
    if len(oui) < 100:
        print("  moins de 100 signaux avec englobante : pas d'avis.")
        return 0
    mo, mn = statistics.fmean(l["r"] for l in oui), statistics.fmean(l["r"] for l in non)
    pa, pb = {}, {}
    for l in oui:
        pa.setdefault(l["jour"], []).append(l["r"])
    for l in non:
        pb.setdefault(l["jour"], []).append(l["r"])
    lo, hi = bootstrap(pa, pb)
    m = lignes[len(lignes) // 2]["t"]
    def moit(g, avant):
        v = [l["r"] for l in g if (l["t"] < m) == avant]
        return statistics.fmean(v) if v else float("nan")
    print(f"  R/trade : avec englobante {mo:+.3f} | sans {mn:+.3f} | difference {mo - mn:+.3f}   IC 95 % (jours) [{lo:+.3f} ; {hi:+.3f}]")
    print(f"  stops : avec {100 * sum(1 for l in oui if l['r'] < -0.5) / len(oui):.0f} % | sans {100 * sum(1 for l in non if l['r'] < -0.5) / len(non):.0f} %")
    print(f"  deux moities (difference) : {moit(oui, True) - moit(non, True):+.3f} puis {moit(oui, False) - moit(non, False):+.3f}")
    print("  => " + ("NON distinguable du hasard" if lo <= 0 <= hi else ("l'englobante AIDE (a confirmer)" if lo > 0 else "l'englobante NUIT")))
    print("\nLecture : si l'IC contient 0, la bougie englobante ne change rien de mesurable sur cet historique. Une seule comparaison a ete faite (pas de reglage essaye).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
