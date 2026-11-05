# -*- coding: utf-8 -*-
r"""« Je me prends des stops a quelques pips du TP » : est-ce frequent, et une protection aurait-elle aide ? (lecture seule)

Rejoue chaque trade termine avec les bougies M1 de MetaTrader, avec le stop et l'objectif (tp1) REELS du trade.
1) Compte les stops qui sont passes PRES de l'objectif avant de se faire toucher (a 50 / 70 / 80 / 90 % de la distance, ou a
   moins de 3 / 5 pips de l'objectif).
2) Teste une regle simple : des que le prix a parcouru X % du chemin vers l'objectif, le stop est ramene au point d'entree.
   On compare le R total avec la regle et sans, sur la meme simulation (les memes trades, les memes bougies), et sur chaque moitie
   de la periode pour voir si l'effet tient.
Une protection a un cout : elle transforme aussi en 0 des trades qui auraient fini a l'objectif apres un petit retour. Le script
les compte. Si l'effet n'est pas stable entre les deux moities, ce n'est pas une regle a adopter.
Approximations : pas de spread ; stop et objectif dans la meme bougie = stop ; la regle agit a partir de la bougie suivante.
Necessite MetaTrader 5 ouvert. Rien n'est modifie, aucun ordre.

Usage (dossier gimaly, ce script a cote de analyse_stop_ideal.py) :
  .\.venv\Scripts\python.exe analyse_presque_tp.py                      depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_presque_tp.py 20/10/2026 --genre tous"""
import csv
import sys
import time
from datetime import datetime

from analyse_stop_ideal import (DECALAGES_H, DUREE_MAX_S, FICHIER, SYMBOLE, alignement, barres_apres, trades_complets)

SEUILS = (0.5, 0.6, 0.7, 0.8, 0.9)


def rejouer(barres, sens, pe, stop, tp1, seuil=None):
    """Renvoie (issue, R, mfe_avant_stop). issue : tp / sl / be / None. mfe en $ (barres strictement avant la sortie)."""
    achat = sens == "achat"
    dist = abs(tp1 - pe)
    courant = pe - stop if achat else pe + stop
    protege = False
    mfe = 0.0
    for haut, bas in barres:
        if (bas <= courant) if achat else (haut >= courant):
            return ("be", 0.0, mfe) if protege else ("sl", -1.0, mfe)
        if (haut >= tp1) if achat else (bas <= tp1):
            return "tp", dist / stop, mfe
        fav = (haut - pe) if achat else (pe - bas)
        mfe = max(mfe, fav)
        if seuil is not None and not protege and fav >= seuil * dist:
            protege, courant = True, pe
    return None, 0.0, mfe


def main(argv):
    argv = list(argv)
    genre = "scalp_keltner_large"
    spread = 0.30
    if "--genre" in argv:
        i = argv.index("--genre")
        genre = argv[i + 1] if i + 1 < len(argv) else genre
        del argv[i:i + 2]
    if "--spread" in argv:
        i = argv.index("--spread")
        try:
            spread = float(argv[i + 1].replace(",", "."))
        except (ValueError, IndexError):
            print("Spread attendu en dollars, ex. 0,3")
            return 1
        del argv[i:i + 2]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        trades = trades_complets(list(csv.DictReader(f, delimiter=";")), genre, depuis)
    if not trades:
        print("Aucun trade termine a analyser.")
        return 0
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    donnees = []
    try:
        mt5.symbol_select(SYMBOLE, True)
        tick = mt5.symbol_info_tick(SYMBOLE)
        decalage = (tick.time - time.time()) if tick and tick.time else 0.0
        for t_ouv, sens, pe, sl, tp1, etat, r in trades:
            reel = t_ouv.timestamp() + decalage
            m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 5 * 3600),
                                      datetime.fromtimestamp(reel + 5 * 3600 + DUREE_MAX_S))
            if m1 is None or len(m1) < 10:
                continue
            brut = sorted((int(x["time"]), float(x["high"]), float(x["low"])) for x in m1)
            donnees.append((reel, sens, pe, sl, tp1, etat, r, brut, t_ouv))
    finally:
        mt5.shutdown()
    if not donnees:
        print("Aucune bougie exploitable (ouvre un graphique M1 de l'or dans MetaTrader et reessaie).")
        return 0
    scores = {h: alignement([d[:8] for d in donnees], h) for h in DECALAGES_H}
    h_ok = max(scores, key=lambda h: scores[h][0])
    part = scores[h_ok][0]
    print(f"{len(donnees)} trades rejoues | signal : {genre} | depuis le {depuis:%d/%m/%Y} | alignement {100 * part:.0f} % (decalage {h_ok:+d} h)")
    if part < 0.7:
        print("ATTENTION : alignement trop faible, resultats non fiables. Envoie-moi cette sortie.")
    prep = []
    for reel, sens, pe, sl, tp1, etat, r, brut, t_ouv in donnees:
        debut = reel + 3600 * h_ok - 60
        prep.append((t_ouv, sens, pe, abs(pe - sl), tp1, etat, r, barres_apres(brut, debut, debut + 60 + DUREE_MAX_S)))
    prep.sort(key=lambda x: x[0])
    base = [(p, rejouer(p[7], p[1], p[2], p[3], p[4])) for p in prep]
    base = [(p, res) for p, res in base if res[0] is not None]
    accord = sum((res[0] == "tp") == (p[6] > 0) for p, res in base)
    print(f"Controle : la simulation retrouve le resultat reel dans {100 * accord / len(base):.0f} % des cas ({accord}/{len(base)}).")
    stops = [(p, res) for p, res in base if res[0] == "sl"]
    gagn = [(p, res) for p, res in base if res[0] == "tp"]
    print(f"\n{len(stops)} trades finissent au stop, {len(gagn)} a l'objectif (simulation).")
    print("\n1) Les stops qui sont passes pres de l'objectif avant de ceder :")
    for s in SEUILS:
        n = sum(1 for p, res in stops if res[2] >= s * abs(p[4] - p[2]))
        print(f"   au moins {100 * s:.0f} % du chemin : {n:>3} stops ({100 * n / len(stops):.0f} % des stops)")
    for pips in (3, 5):
        n = sum(1 for p, res in stops if abs(p[4] - p[2]) - res[2] <= pips / 10.0)
        print(f"   a moins de {pips} pips de l'objectif : {n:>3} stops ({100 * n / len(stops):.0f} % des stops)")
    print("   (les barres de la bougie du stop ne sont pas comptees : ces chiffres sont plutot un minimum)")
    moitie = len(prep) // 2
    print("\n2) Regle « stop au point d'entree apres X % du chemin » (R sur les memes trades) :")
    r_base = sum(res[1] for _, res in base)
    cout = sum(spread / p[3] for p, _ in base)
    print(f"   sans regle : {r_base:+.2f} R sur {len(base)} trades ({r_base / len(base):+.2f} R/trade) ; apres un spread de {spread:.2f} $ par trade "
          f"(-{cout:.1f} R) : {r_base - cout:+.2f} R")
    print("   Le spread se paie avec ou sans regle : il baisse le niveau, pas l'ecart. Les colonnes « R total » sont donc donnees apres spread.")
    print(f"   {'X':>5} {'R total':>9} {'ecart':>8} {'1re moitie':>11} {'2e moitie':>10} {'stops sauves':>13} {'gagnants coupes':>16}")
    ref = {id(p): res for p, res in base}
    idx = {id(p): i for i, p in enumerate(prep)}
    for s in SEUILS:
        tot = e1 = e2 = sauves = coupes = 0.0
        for p, res0 in base:
            res = rejouer(p[7], p[1], p[2], p[3], p[4], s)
            if res[0] is None:
                continue
            ecart = res[1] - res0[1]
            tot += ecart
            if idx[id(p)] < moitie:
                e1 += ecart
            else:
                e2 += ecart
            if res0[0] == "sl" and res[0] == "be":
                sauves += 1
            if res0[0] == "tp" and res[0] == "be":
                coupes += 1
        print(f"   {100 * s:>4.0f}% {r_base - cout + tot:>+9.2f} {tot:>+8.2f} {e1:>+11.2f} {e2:>+10.2f} {int(sauves):>13} {int(coupes):>16}")
    print("\nLecture : « stops sauves » = trades qui auraient fini au stop et finissent a 0 ; « gagnants coupes » = trades qui auraient fini a")
    print("l'objectif et finissent a 0. Une regle n'est credible que si l'ecart est positif dans LES DEUX moities et que les gagnants")
    print("coupes ne mangent pas le gain. Ignore le spread. Cinq seuils testes : un seul bon resultat peut etre du hasard, ne rien changer")
    print("sur ce seul test ; a refaire sur les trades futurs (pre-enregistre) avant toute regle.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
