# -*- coding: utf-8 -*-
r"""Quelle largeur de stop aurait ete la meilleure ? Test retroactif avec les bougies M1 de MetaTrader (lecture seule).
Pour chaque trade termine, on rejoue le marche minute par minute depuis l'entree, avec le MEME objectif (tp1) et plusieurs
largeurs de stop (15, 20, 25, 30, 35, 40, 50 pips ; 10 pips = 1 $). Un stop plus large = lot plus petit (risque constant),
donc le resultat est compte en R : objectif atteint = distance objectif / largeur, stop touche = -1 R.
Si l'objectif et le stop sont dans la meme bougie, on compte le stop (hypothese prudente).
Un controle compare la simulation, avec le stop reel de chaque trade, au resultat reel (gagnant / perdant).
Approximations : pas de spread, pas de gestion en cours de trade (pas de deplacement de stop, pas de TP2) ; a prendre comme un ordre de grandeur.
Necessite MetaTrader 5 ouvert (celui du bot). Rien n'est modifie, aucun ordre.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_stop_ideal.py                   depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_stop_ideal.py 20/10/2026 --genre tous"""
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
SYMBOLE = "XAUUSD"
LARGEURS_PIPS = (15, 20, 25, 30, 35, 40, 50)
DUREE_MAX_MIN = 120


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def trades_complets(lignes, genre, depuis):
    """Apparie cloture et ouverture ; renvoie (heure_ouverture, sens, pe, sl, tp1, resultat, R)."""
    ouverts, res = [], []
    for l in lignes:
        try:
            t = datetime.strptime(f"{(l.get('date') or '').strip()} {(l.get('heure') or '').strip()}", "%d/%m/%Y %H:%M:%S")
        except ValueError:
            continue
        etat = (l.get("resultat") or "").strip()
        sens = (l.get("sens") or "").strip()
        pe, sl, tp1 = nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp1"))
        cle = (sens, pe, sl, (l.get("genre") or "").strip())
        if etat == "ouvert":
            ouverts.append((t, cle))
            continue
        if etat == "":
            continue
        r = nombre(l.get("R"))
        if r is None or tp1 is None or pe is None or sl is None or t < depuis or (genre != "tous" and cle[3] != genre):
            continue
        for i in range(len(ouverts) - 1, -1, -1):
            if ouverts[i][1] == cle and ouverts[i][0] <= t:
                res.append((ouverts[i][0], sens, pe, sl, tp1, etat, r))
                del ouverts[i]
                break
    return res


def rejouer(barres, sens, pe, stop, tp1):
    """barres : liste de (haut, bas). Renvoie 'tp', 'sl' ou None (non resolu). Stop et objectif dans la meme bougie : stop."""
    achat = sens == "achat"
    prix_stop = pe - stop if achat else pe + stop
    for haut, bas in barres:
        touche_stop = bas <= prix_stop if achat else haut >= prix_stop
        touche_tp = haut >= tp1 if achat else bas <= tp1
        if touche_stop:
            return "sl"
        if touche_tp:
            return "tp"
    return None


def main(argv, mt5=None):
    argv = list(argv)
    genre = "scalp_keltner_large"
    if "--genre" in argv:
        i = argv.index("--genre")
        genre = argv[i + 1] if i + 1 < len(argv) else genre
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
        lignes = list(csv.DictReader(f, delimiter=";"))
    trades = trades_complets(lignes, genre, depuis)
    if not trades:
        print("Aucun trade termine (avec sa ligne d'ouverture) a analyser.")
        return 0
    if mt5 is None:
        try:
            import MetaTrader5 as mt5  # noqa: N813
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
            m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 60),
                                      datetime.fromtimestamp(reel + DUREE_MAX_MIN * 60))
            if m1 is None or len(m1) < 5:
                continue
            barres = [(float(x["high"]), float(x["low"])) for x in m1]
            donnees.append((sens, pe, sl, tp1, etat, r, barres))
    finally:
        mt5.shutdown()
    if not donnees:
        print("Aucune bougie exploitable (historique manquant dans MetaTrader : ouvre un graphique M1 de l'or et reessaie).")
        return 0
    # controle : simulation avec le stop reel contre le resultat reel
    accord = total = 0
    for sens, pe, sl, tp1, etat, r, barres in donnees:
        sim = rejouer(barres, sens, pe, abs(pe - sl), tp1)
        if sim is None:
            continue
        total += 1
        accord += (sim == "tp") == (r > 0)
    print(f"{len(donnees)} trades rejoues | signal : {genre} | depuis le {depuis:%d/%m/%Y}")
    if total:
        print(f"Controle : avec le stop reel, la simulation retrouve le resultat reel dans {100 * accord / total:.0f} % des cas "
              f"({accord}/{total}). Plus c'est haut, plus les chiffres ci-dessous sont credibles.\n")
    reel_r = sum(x[5] for x in donnees)
    print(f"Resultat REEL de ces trades : {reel_r:+.2f} R ({reel_r / len(donnees):+.2f} R par trade)\n")
    print(f"  {'stop':>8} {'rejoues':>8} {'gagn.':>7} {'R cumul':>8} {'R moy':>6}   non resolus")
    for pips in LARGEURS_PIPS:
        stop = pips / 10.0
        n = g = 0
        r_tot = 0.0
        non = 0
        for sens, pe, sl, tp1, etat, r, barres in donnees:
            sim = rejouer(barres, sens, pe, stop, tp1)
            if sim is None:
                non += 1
                continue
            n += 1
            if sim == "tp":
                g += 1
                r_tot += abs(tp1 - pe) / stop
            else:
                r_tot -= 1.0
        if n:
            print(f"  {pips:>5} pips {n:>8} {100 * g / n:>6.0f}% {r_tot:>+8.2f} {r_tot / n:>+6.2f}   {non}")
    print("\nLecture : cherche la ligne dont le R moyen est nettement meilleur. Un ecart faible entre deux largeurs n'est pas significatif.")
    print("Cette simulation ignore le spread et la gestion du trade en cours : ordre de grandeur seulement, a confirmer avant de changer quoi que ce soit.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
