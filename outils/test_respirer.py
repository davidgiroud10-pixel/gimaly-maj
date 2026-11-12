# -*- coding: utf-8 -*-
r"""Laisser le trade « respirer » : stop ET objectif multiplies par k (meme rapport 1,5 R), risque constant en R. (lecture seule, aucun ordre)
Question : sur l'or volatil, un stop k fois plus loin avec un objectif k fois plus loin (donc un lot plus petit, 1 R = 1 R) donne-t-il un meilleur R par trade ?
Regles fixees a l'avance : memes signaux que rejeu_keltner.py (rebond sur bande Keltner M1, stop large du bot), k = 1 (reference), 1,5, 2, 3 ; entree identique ;
stop avant objectif dans la meme bougie ; sortie au marche apres --duree minutes (60 par defaut, comme le bot ; 120 permet aux grands objectifs d'arriver) ;
spread deduit (--spread, 0,20 $) : il pese moins sur un grand stop, c'est le vrai gain mecanique de k > 1. Seuls les signaux dont le stop x 3 reste <= 40 $ sont gardes
(meme jeu pour tous les k). 3 comparaisons (1,5 / 2 / 3 contre 1) -> IC corrige Bonferroni (99,17 %), regroupe par jour, difference APPARIEE signal par signal.
A retenir seulement si l'IC exclut 0 ET que les deux moities vont dans le meme sens ; meme alors, a confirmer sur des trades non vus avant de toucher au bot.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de rejeu_keltner.py et test_freins.py) :
  .\.venv\Scripts\python.exe test_respirer.py [jj/mm/aaaa] [--spread 0.20] [--duree 60]"""
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

KS = (1.0, 1.5, 2.0, 3.0)
Z = 2.64


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
        d0 = abs(entree - sl)
        if d0 * max(KS) > 40.0:
            continue
        achat = sens == "achat"
        rs, brut = {}, {}
        for k in KS:
            slk = round(entree - k * d0 if achat else entree + k * d0, 2)
            r, _, _ = tf.jouer(b, i, sens, entree, slk)
            rs[k] = r - spread / (k * d0)
            brut[k] = r
        lignes.append({"t": t, "d0": d0, "rs": rs, "brut": brut, "jour": datetime.fromtimestamp(t, timezone.utc).date()})
    if len(lignes) < 300:
        print("Trop peu de signaux.")
        return 0
    lignes.sort(key=lambda x: x["t"])
    n = len(lignes)
    print(f"{n} signaux (stop x 3 <= 40 $), du {lignes[0]['jour']:%d/%m/%Y} au {lignes[-1]['jour']:%d/%m/%Y}, spread {spread:.2f} $, sortie au marche apres {duree} min")
    print(f"stop de reference moyen {statistics.fmean(l['d0'] for l in lignes):.2f} $")
    print(f"\n{'k':>5}{'stop moyen':>12}{'gagn.':>7}{'R/trade':>9}{'avant spread':>14}   difference vs k=1 [IC 99 %, par jour]   moities (diff)")
    h = n // 2
    for k in KS:
        v = [l["rs"][k] for l in lignes]
        gag = 100 * sum(1 for x in v if x > 0.25) / n
        if k == 1.0:
            print(f"{k:>5.1f}{statistics.fmean(l['d0'] * k for l in lignes):>10.2f} $ {gag:>5.0f}%{statistics.fmean(v):>+9.3f}{statistics.fmean(l['brut'][k] for l in lignes):>+14.3f}   (reference)")
            continue
        par_jour = {}
        for l in lignes:
            par_jour.setdefault(l["jour"], []).append(l["rs"][k] - l["rs"][1.0])
        m, lo, hi = tf.ic_jours(par_jour, n, Z)
        d1 = statistics.fmean(l["rs"][k] - l["rs"][1.0] for l in lignes[:h])
        d2 = statistics.fmean(l["rs"][k] - l["rs"][1.0] for l in lignes[h:])
        marque = "" if lo <= 0 <= hi else ("  <- MIEUX" if lo > 0 else "  <- PIRE")
        print(f"{k:>5.1f}{statistics.fmean(l['d0'] * k for l in lignes):>10.2f} $ {gag:>5.0f}%{statistics.fmean(v):>+9.3f}{statistics.fmean(l['brut'][k] for l in lignes):>+14.3f}   {m:>+.3f} [{lo:+.3f} ; {hi:+.3f}]   {d1:+.3f} / {d2:+.3f}{marque}")
    print("\nATTENTION : un grand stop reduit mecaniquement le poids du spread. Si « avant spread » reste <= 0 pour tous les k, le « MIEUX » n'est que cet effet du spread :")
    print("le signal lui-meme n'a pas gagne d'avantage, et il ne faut pas y voir une raison de passer en grand stop avant d'avoir un R/trade positif de facon nette.")
    print("\nLecture : si aucune ligne k > 1 n'a un IC qui exclut 0 avec les deux moities dans le meme sens, laisser respirer le trade ne change rien de mesurable.")
    print("Essaye aussi --duree 120 (un grand objectif a besoin de temps) ; ce n'est PAS un reglage a chercher : une seule duree sera retenue, annoncee avant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
