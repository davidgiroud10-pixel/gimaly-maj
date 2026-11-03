# -*- coding: utf-8 -*-
r"""Banc d'essai AVEC FRAIS (lecture seule, aucun ordre, rien n'est modifie). Pour chaque trade termine du bot, on rejoue le marche
minute par minute (bougies M1 de MetaTrader) avec le MEME prix d'entree, le MEME stop et le MEME objectif, en comptant le SPREAD :
l'achat sort au prix bid (= les bougies), la vente sort au prix ask (= bougies + spread). Puis on essaie des variantes (objectif plus
proche / plus loin, stop remis a l'entree apres un gain de x R) pour voir ce qui change le resultat net.

Sorties :
  1. controle de fiabilite : la simulation retrouve-t-elle le resultat reel ? (au-dessus de 80 %, credible)
  2. resultat net selon le spread (0 a 0,8 $) : a partir de quel spread l'avantage disparait-il ?
  3. intervalle de confiance du R moyen (bootstrap) : l'avantage est-il distinguable du hasard ?
  4. variantes d'objectif et de point mort, au spread mesure.
Le spread mesure vient de couts_trades.csv (ecrit par patch_couts_ia.py) ; sinon --spread (defaut 0,25 $).
Approximations : stop et objectif dans la meme bougie = stop (prudent) ; pas de TP2, pas de partiel ; commission non comptee
(--frais_r 0.02 ajoute 0,02 R de frais par trade). Plus la serie est courte, plus tout cela est incertain : regarde l'intervalle.

Usage (dossier du programme, MetaTrader 5 ouvert) :
  .\.venv\Scripts\python.exe banc_essai.py                         depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe banc_essai.py 20/10/2026 --genre tous --spread 0.3 --frais_r 0.02"""
import csv
import importlib.util
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
DOSSIER = Path.home() / "GIMALY" / "trading"
SYMBOLE = "XAUUSD"
DUREE_MAX_S = 120 * 60
SPREADS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
FACTEURS_TP = (0.75, 1.0, 1.25, 1.5)
POINTS_MORTS_R = (0.0, 0.5, 0.75)        # 0 = pas de point mort ; sinon stop a l'entree apres un gain de x R


def _outils():
    """Reprend les fonctions de lecture de analyse_stop_ideal.py (meme dossier)."""
    spec = importlib.util.spec_from_file_location("analyse_stop_ideal", ICI / "analyse_stop_ideal.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rejouer(barres, sens, pe, stop, tp, spread=0.0, be_r=0.0):
    """barres : liste de (haut, bas) en prix BID. Renvoie ('tp'|'sl'|'be'|None, R).
    Achat : sort au bid. Vente : sort a l'ask = bid + spread. Stop et objectif dans la meme bougie : stop.
    be_r > 0 : apres un gain de be_r x stop, le stop passe a l'entree (applique a partir de la bougie suivante)."""
    achat = sens == "achat"
    prix_stop = pe - stop if achat else pe + stop
    dist_tp = abs(tp - pe)
    arme = False
    for haut, bas in barres:
        h, b = (haut, bas) if achat else (haut + spread, bas + spread)
        touche_stop = b <= prix_stop if achat else h >= prix_stop
        touche_tp = h >= tp if achat else b <= tp
        if touche_stop:
            return ("be", 0.0) if arme else ("sl", -1.0)
        if touche_tp:
            return "tp", dist_tp / stop
        if be_r and not arme:
            gain = (h - pe) if achat else (pe - b)
            if gain >= be_r * stop:
                arme = True
                prix_stop = pe
    return None, 0.0


def stats(liste):
    n = len(liste)
    if not n:
        return 0, 0.0, 0.0
    return n, sum(liste), sum(liste) / n


def bootstrap_ic(valeurs, tirages=2000, graine=7):
    """Intervalle a 95 % du R moyen (reechantillonnage). Renvoie (bas, haut)."""
    if len(valeurs) < 5:
        return None
    rnd = random.Random(graine)
    moyennes = sorted(statistics.fmean(rnd.choices(valeurs, k=len(valeurs))) for _ in range(tirages))
    return moyennes[int(0.025 * tirages)], moyennes[int(0.975 * tirages) - 1]


def spread_mesure(depuis):
    f = DOSSIER / "couts_trades.csv"
    if not f.exists():
        return None, 0
    vals = []
    with open(f, newline="", encoding="utf-8-sig") as fh:
        for l in csv.DictReader(fh, delimiter=";"):
            try:
                vals.append(float(str(l["spread"]).replace(",", ".")))
            except (KeyError, ValueError):
                pass
    return (statistics.median(vals), len(vals)) if vals else (None, 0)


def serie(prepares, spread, frais_r, tp_facteur=1.0, be_r=0.0):
    """R net de chaque trade resolu."""
    rs, non = [], 0
    for sens, pe, stop, tp1, etat, r, barres in prepares:
        tp = pe + (tp1 - pe) * tp_facteur
        issue, gain = rejouer(barres, sens, pe, stop, tp, spread, be_r)
        if issue is None:
            non += 1
            continue
        rs.append(gain - frais_r)
    return rs, non


def main(argv, mt5=None):
    argv = list(argv)

    def option(nom, defaut):
        if nom in argv:
            i = argv.index(nom)
            v = argv[i + 1] if i + 1 < len(argv) else defaut
            del argv[i:i + 2]
            return v
        return defaut
    genre = option("--genre", "scalp_keltner_large")
    spread_arg = option("--spread", None)
    frais_r = float(str(option("--frais_r", "0")).replace(",", "."))
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    outils = _outils()
    fichier = DOSSIER / "trades_bot.csv"
    if not fichier.exists():
        print(f"{fichier} introuvable.")
        return 1
    with open(fichier, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    trades = outils.trades_complets(lignes, genre, depuis)
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
            m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 5 * 3600),
                                      datetime.fromtimestamp(reel + 5 * 3600 + DUREE_MAX_S))
            if m1 is None or len(m1) < 10:
                continue
            brut = sorted((int(x["time"]), float(x["high"]), float(x["low"])) for x in m1)
            donnees.append((reel, sens, pe, sl, tp1, etat, r, brut))
    finally:
        mt5.shutdown()
    if not donnees:
        print("Aucune bougie exploitable (ouvre un graphique M1 de l'or dans MetaTrader et reessaie).")
        return 0
    scores = {h: outils.alignement(donnees, h) for h in outils.DECALAGES_H}
    h_ok = max(scores, key=lambda h: scores[h][0])
    part = scores[h_ok][0]
    prepares = []
    for reel, sens, pe, sl, tp1, etat, r, brut in donnees:
        debut = reel + 3600 * h_ok - 60
        prepares.append((sens, pe, abs(pe - sl), tp1, etat, r, outils.barres_apres(brut, debut, debut + 60 + DUREE_MAX_S)))

    mesure, n_mesure = spread_mesure(depuis)
    if spread_arg is not None:
        spread, source = float(str(spread_arg).replace(",", ".")), "donne par --spread"
    elif mesure is not None:
        spread, source = mesure, f"mediane mesuree sur {n_mesure} entrees (couts_trades.csv)"
    else:
        spread, source = 0.25, "hypothese par defaut (pas encore de mesure : patch_couts_ia.py enregistre le vrai spread)"
    print(f"{len(prepares)} trades rejoues | signal : {genre} | depuis le {depuis:%d/%m/%Y} | decalage horaire {h_ok:+d} h")
    if part < 0.7:
        print(f"ATTENTION : alignement des bougies faible ({100 * part:.0f} %) : resultats non fiables, envoie-moi cette sortie.")

    # 1. controle de fiabilite (stop et objectif reels, spread 0 : la sortie reelle est deja nette du spread, mais on teste le sens)
    accord = total = 0
    for sens, pe, stop, tp1, etat, r, barres in prepares:
        issue, _ = rejouer(barres, sens, pe, stop, tp1, spread)
        if issue is None:
            continue
        total += 1
        accord += (issue == "tp") == (r > 0)
    if total:
        print(f"Controle : la simulation (spread {spread:.2f} $) retrouve le resultat reel dans {100 * accord / total:.0f} % des cas "
              f"({accord}/{total}). Credible au-dessus de 80 %.")
    reel_r = [x[5] for x in prepares]
    print(f"Resultat REEL : {sum(reel_r):+.2f} R, {statistics.fmean(reel_r):+.2f} R par trade "
          f"(deja net du spread paye ; commission eventuelle non comprise).")
    print(f"Spread utilise : {spread:.2f} $ ({source}) | frais supplementaires : {frais_r:.3f} R par trade\n")

    # 2. R net selon le spread
    print("  A. Resultat selon le spread (stop et objectif d'origine)")
    print(f"  {'spread':>8} {'trades':>7} {'R cumul':>8} {'R moy':>7}   non resolus")
    for s in SPREADS:
        rs, non = serie(prepares, s, frais_r)
        n, tot, moy = stats(rs)
        print(f"  {s:>6.2f} $ {n:>7} {tot:>+8.2f} {moy:>+7.2f}   {non}")
    # 3. intervalle
    rs, _ = serie(prepares, spread, frais_r)
    ic = bootstrap_ic(rs)
    print(f"\n  B. R moyen au spread utilise : {statistics.fmean(rs):+.3f} R sur {len(rs)} trades", end="")
    if ic:
        verdict = ("l'intervalle reste au-dessus de 0 : avantage probable" if ic[0] > 0 else
                   "l'intervalle contient 0 : on ne peut PAS distinguer cet avantage du hasard" if ic[1] > 0 else
                   "l'intervalle est sous 0 : perdant")
        print(f"\n     intervalle a 95 % : [{ic[0]:+.3f} ; {ic[1]:+.3f}] -> {verdict}")
    else:
        print("\n     (trop peu de trades pour un intervalle)")
    # 4. variantes
    print(f"\n  C. Variantes au spread de {spread:.2f} $ (objectif = fraction/multiple de l'objectif d'origine ; PM = stop a l'entree apres x R)")
    print(f"  {'objectif':>9} {'PM':>6} {'trades':>7} {'gagn.':>6} {'R cumul':>8} {'R moy':>7}")
    meilleur = None
    for k in FACTEURS_TP:
        for be in POINTS_MORTS_R:
            rs, _ = serie(prepares, spread, frais_r, k, be)
            n, tot, moy = stats(rs)
            if not n:
                continue
            gagn = 100 * sum(1 for x in rs if x > 0) / n
            marque = "  <- d'origine" if (k == 1.0 and be == 0.0) else ""
            print(f"  {k:>8.2f}x {('aucun' if not be else f'{be:g} R'):>6} {n:>7} {gagn:>5.0f}% {tot:>+8.2f} {moy:>+7.2f}{marque}")
            if meilleur is None or moy > meilleur[0]:
                meilleur = (moy, k, be)
    print("\nLecture : 12 variantes testees sur la meme serie = une partie des ecarts est du hasard. Une variante n'est a retenir que si "
          "(1) elle bat l'origine NETTEMENT, (2) le controle est credible, (3) elle tient sur des trades non encore vus. "
          "Rien n'est applique : ce script ne fait que mesurer.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
