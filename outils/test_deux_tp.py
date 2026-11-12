# -*- coding: utf-8 -*-
r"""Deux objectifs avec mise a l'abri : la moitie de la position est prise au TP1, le stop du reste passe a l'ENTREE (point mort), et le reste vise le TP2. (lecture seule, aucun ordre)
Compare, sur les memes signaux que rejeu_keltner.py (rebond sur bande Keltner M1, stop large du bot), a la reference « un seul objectif a 1,5 R » :
  B  moitie a 1,0 R, puis point mort, le reste vise 2,0 R
  C  moitie a 1,0 R, puis point mort, le reste vise 3,0 R
Regles fixees a l'avance : meme entree et meme stop ; stop avant objectif dans la meme bougie ; apres le TP1, le point mort et le TP2 ne comptent qu'a partir de la bougie SUIVANTE
(prudent) ; le reste sort au marche apres --duree minutes (60 par defaut, comme le bot) ; spread deduit sur toute la position (--spread, 0,20 $) ; point mort a l'entree exacte
(le glissement et le spread de sortie d'une vente ne sont pas modelises : ordre de grandeur). 2 variantes -> IC corrige Bonferroni (97,5 %), difference appariee signal par signal,
regroupee par jour, stabilite des deux moities. A retenir seulement si l'IC exclut 0 ET que les deux moities vont dans le meme sens ; a confirmer sur des trades non vus.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_deux_tp.py [jj/mm/aaaa] [--spread 0.20] [--duree 60]"""
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
VARIANTES = (("B  moitie a 1,0 R + point mort, reste vise 2,0 R", 1.0, 2.0), ("C  moitie a 1,0 R + point mort, reste vise 3,0 R", 1.0, 3.0))


def jouer_deux(b, i, sens, entree, sl, r1, r2, part=0.5):
    """R brut (avant spread) de la position complete."""
    achat = sens == "achat"
    dist = abs(entree - sl)
    s = 1 if achat else -1
    tp1, tp2 = entree + s * r1 * dist, entree + s * r2 * dist
    t0 = b[i][0]
    etat, dern = 0, entree          # 0 : avant TP1 ; 1 : TP1 pris, stop a l'entree
    for j in range(i + 1, len(b)):
        t, o, h, l, c = b[j]
        if t - t0 > rk.DUREE_S:
            break
        dern = c
        if etat == 0:
            if (l <= sl) if achat else (h >= sl):
                return -1.0
            if (h >= tp1) if achat else (l <= tp1):
                etat = 1                                    # le point mort et le TP2 comptent des la bougie suivante
        else:
            if (l <= entree) if achat else (h >= entree):
                return part * r1                            # le reste sort a l'entree
            if (h >= tp2) if achat else (l <= tp2):
                return part * r1 + (1 - part) * r2
    reste = ((dern - entree) if achat else (entree - dern)) / dist
    return reste if etat == 0 else part * r1 + (1 - part) * reste


def main(argv):
    argv = list(argv)
    spread, duree = 0.20, 60
    for nom in ("--spread", "--duree"):
        if nom in argv:
            i = argv.index(nom)
            v = float(argv[i + 1].replace(",", "."))
            if nom == "--spread":
                spread = v
            else:
                duree = int(v)
            del argv[i:i + 2]
    depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 1, 1)
    rk.DUREE_S = duree * 60
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
    for i, sens, entree, sl in rk.signaux(b):
        t = b[i][0]
        if datetime.fromtimestamp(t, timezone.utc).replace(tzinfo=None) < depuis:
            continue
        d = abs(entree - sl)
        ref, _, _ = tf.jouer(b, i, sens, entree, sl)
        rs = {"ref": (ref, ref - spread / d)}
        for nom, r1, r2 in VARIANTES:
            g = jouer_deux(b, i, sens, entree, sl, r1, r2)
            rs[nom] = (g, g - spread / d)
        lignes.append({"t": t, "rs": rs, "jour": datetime.fromtimestamp(t, timezone.utc).date()})
    if len(lignes) < 300:
        print("Trop peu de signaux.")
        return 0
    lignes.sort(key=lambda x: x["t"])
    n, h = len(lignes), len(lignes) // 2
    print(f"{n} signaux du {lignes[0]['jour']:%d/%m/%Y} au {lignes[-1]['jour']:%d/%m/%Y}, spread {spread:.2f} $, sortie au marche apres {duree} min")
    print(f"\n{'variante':<54}{'R/trade':>9}{'avant spread':>14}   difference vs reference [IC 97,5 %, par jour]   moities")
    base = [l["rs"]["ref"][1] for l in lignes]
    print(f"{'reference : un seul objectif a 1,5 R':<54}{statistics.fmean(base):>+9.3f}{statistics.fmean(l['rs']['ref'][0] for l in lignes):>+14.3f}   (reference)")
    for nom, _, _ in VARIANTES:
        par_jour = {}
        for l in lignes:
            par_jour.setdefault(l["jour"], []).append(l["rs"][nom][1] - l["rs"]["ref"][1])
        m, lo, hi = tf.ic_jours(par_jour, n, Z)
        d1 = statistics.fmean(l["rs"][nom][1] - l["rs"]["ref"][1] for l in lignes[:h])
        d2 = statistics.fmean(l["rs"][nom][1] - l["rs"]["ref"][1] for l in lignes[h:])
        marque = "" if lo <= 0 <= hi else ("  <- MIEUX" if lo > 0 else "  <- PIRE")
        print(f"{nom:<54}{statistics.fmean(l['rs'][nom][1] for l in lignes):>+9.3f}{statistics.fmean(l['rs'][nom][0] for l in lignes):>+14.3f}   "
              f"{m:>+.3f} [{lo:+.3f} ; {hi:+.3f}]   {d1:+.3f} / {d2:+.3f}{marque}")
    print("\nLecture : si « avant spread » reste <= 0, un « MIEUX » n'est qu'un effet de coût. A confirmer sur des trades non vus ; le bot n'est pas touche.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
