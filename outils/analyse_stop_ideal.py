# -*- coding: utf-8 -*-
r"""Faut-il relever le stop MINIMUM du bot (trading_sl_min_pips, 15 pips aujourd'hui) ? Test retroactif avec les bougies M1 de
MetaTrader (lecture seule). Pour chaque trade termine, on rejoue le marche minute par minute depuis l'entree, avec le MEME objectif
(tp1) et un stop = le plus grand entre le stop reel du trade et un plancher de 15, 20, 25, 30, 35, 40 ou 50 pips (10 pips = 1 $).
Stop plus large = lot plus petit (risque constant), donc le resultat est compte en R : objectif atteint = distance objectif / stop,
stop touche = -1 R. Si l'objectif et le stop sont dans la meme bougie, on compte le stop (hypothese prudente).
Avant tout, le script verifie que les bougies tombent bien a l'heure des trades (le prix d'entree doit etre dans la bougie d'entree)
et corrige tout seul un decalage horaire d'une ou plusieurs heures. Il compare ensuite la simulation avec le stop reel au resultat reel
(gagnant / perdant) : si ce controle est bas, les chiffres ne sont pas fiables et le script le dit.
Approximations : pas de spread, pas de gestion en cours de trade (pas de deplacement de stop, pas de TP2). Ordre de grandeur seulement.
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
PLANCHERS_PIPS = (15, 20, 25, 30, 35, 40, 50)
DUREE_MAX_S = 120 * 60
DECALAGES_H = range(-4, 5)


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


def barres_apres(brut, debut_s, fin_s):
    """brut : liste (heure_serveur, haut, bas), triee. Barres dont l'heure est dans [debut_s, fin_s]."""
    return [(h, b) for t, h, b in brut if debut_s <= t <= fin_s]


def alignement(donnees, decalage_h):
    """Part des trades dont le prix d'entree est dans la bougie M1 d'entree (a 0,5 $ pres)."""
    bons = total = 0
    for reel, sens, pe, sl, tp1, etat, r, brut in donnees:
        cible = reel + 3600 * decalage_h
        for t, h, b in brut:
            if cible - 60 < t <= cible:
                total += 1
                bons += (b - 0.5) <= pe <= (h + 0.5)
                break
    return (bons / total) if total else 0.0, total


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
            reel = t_ouv.timestamp() + decalage          # heure du trade, a l'heure du serveur MetaTrader
            m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 5 * 3600),
                                      datetime.fromtimestamp(reel + 5 * 3600 + DUREE_MAX_S))
            if m1 is None or len(m1) < 10:
                continue
            brut = sorted((int(x["time"]), float(x["high"]), float(x["low"])) for x in m1)
            donnees.append((reel, sens, pe, sl, tp1, etat, r, brut))
    finally:
        mt5.shutdown()
    if not donnees:
        print("Aucune bougie exploitable (historique manquant dans MetaTrader : ouvre un graphique M1 de l'or et reessaie).")
        return 0
    scores = {h: alignement(donnees, h) for h in DECALAGES_H}
    h_ok = max(scores, key=lambda h: scores[h][0])
    part, _n = scores[h_ok]
    print(f"{len(donnees)} trades rejoues | signal : {genre} | depuis le {depuis:%d/%m/%Y}")
    print(f"Alignement des bougies : {100 * part:.0f} % des trades ont leur prix d'entree dans la bougie d'entree"
          f" (decalage horaire detecte : {h_ok:+d} h).")
    if part < 0.7:
        print("ATTENTION : alignement trop faible, les bougies ne correspondent pas aux trades (autre serveur / autre symbole ?). "
              "Resultats non fiables : envoie-moi cette sortie.")
    prepares = []
    for reel, sens, pe, sl, tp1, etat, r, brut in donnees:
        debut = reel + 3600 * h_ok - 60
        prepares.append((sens, pe, abs(pe - sl), tp1, etat, r, barres_apres(brut, debut, debut + 60 + DUREE_MAX_S)))
    accord = total = 0
    for sens, pe, stop, tp1, etat, r, barres in prepares:
        sim = rejouer(barres, sens, pe, stop, tp1)
        if sim is None:
            continue
        total += 1
        accord += (sim == "tp") == (r > 0)
    if total:
        print(f"Controle : avec le stop reel, la simulation retrouve le resultat reel dans {100 * accord / total:.0f} % des cas "
              f"({accord}/{total}). Au-dessus de 80 %, les chiffres sont credibles ; en dessous, a prendre avec beaucoup de prudence.\n")
    reel_r = sum(x[5] for x in prepares)
    print(f"Resultat REEL de ces trades : {reel_r:+.2f} R ({reel_r / len(prepares):+.2f} R par trade)\n")
    print(f"  {'plancher':>9} {'rejoues':>8} {'gagn.':>7} {'R cumul':>8} {'R moy':>6} {'stops changes':>14}   non resolus")
    for pips in PLANCHERS_PIPS:
        plancher = pips / 10.0
        n = g = changes = non = 0
        r_tot = 0.0
        for sens, pe, stop_reel, tp1, etat, r, barres in prepares:
            stop = max(stop_reel, plancher)
            if stop > stop_reel + 1e-9:
                changes += 1
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
            print(f"  {pips:>5} pips {n:>8} {100 * g / n:>6.0f}% {r_tot:>+8.2f} {r_tot / n:>+6.2f} {changes:>14}   {non}")
    print("\nLecture : le plancher actuel est 15 pips (premiere ligne). Cherche un plancher dont le R moyen est nettement meilleur ;")
    print("un ecart faible entre deux lignes n'est pas significatif. Ignore spread et gestion du trade : ordre de grandeur seulement.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
