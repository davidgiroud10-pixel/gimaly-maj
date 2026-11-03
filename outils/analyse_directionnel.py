# -*- coding: utf-8 -*-
r"""Les trades marchent-ils mieux quand le marche est DIRECTIONNEL ? Test sur l'historique, sans attendre : pour chaque
trade termine, on relit les bougies de MetaTrader juste AVANT l'entree et on mesure :
  - le mouvement des 60 dernieres minutes (en $) et si le trade va AVEC ou CONTRE lui ;
  - l'efficacite de ce mouvement (0 = marche en dents de scie, 1 = ligne droite) : c'est la mesure du « directionnel » ;
  - le mouvement des 4 dernieres heures et si le trade va AVEC ou CONTRE lui.
Puis resultats (R, taux de reussite) par tranche. Lecture seule : MetaTrader n'est interroge que pour l'historique des bougies.
Necessite MetaTrader 5 ouvert (le meme que celui du bot).

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_directionnel.py                        depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_directionnel.py 20/10/2026 --genre tous"""
import csv
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
SYMBOLE = "XAUUSD"


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def trades_avec_heure_ouverture(lignes, genre, depuis):
    """Apparie chaque ligne de cloture avec la ligne « ouvert » correspondante (meme sens, entree, stop)."""
    ouverts, res = [], []
    for l in lignes:
        try:
            t = datetime.strptime(f"{(l.get('date') or '').strip()} {(l.get('heure') or '').strip()}", "%d/%m/%Y %H:%M:%S")
        except ValueError:
            continue
        etat = (l.get("resultat") or "").strip()
        cle = ((l.get("sens") or "").strip(), nombre(l.get("pe")), nombre(l.get("sl")), (l.get("genre") or "").strip())
        if etat == "ouvert":
            ouverts.append((t, cle))
            continue
        if etat == "":
            continue
        r, g = nombre(l.get("R")), nombre(l.get("gain_devise"))
        if r is None or g is None or t < depuis or (genre != "tous" and cle[3] != genre):
            continue
        for i in range(len(ouverts) - 1, -1, -1):
            if ouverts[i][1] == cle and ouverts[i][0] <= t:
                res.append((ouverts[i][0], cle[0], r, g))
                del ouverts[i]
                break
    return res


def mesures(cl60, cl4h, sens):
    """cl60 : clotures M1 des 60 min avant l'entree ; cl4h : clotures M5 des 4 h avant. Renvoie (avec60, efficacite, avec4h)."""
    if len(cl60) < 40 or len(cl4h) < 30:
        return None
    mv60 = cl60[-1] - cl60[0]
    chemin = sum(abs(cl60[i] - cl60[i - 1]) for i in range(1, len(cl60)))
    efficacite = abs(mv60) / chemin if chemin else 0.0
    mv4h = cl4h[-1] - cl4h[0]
    achat = sens == "achat"
    return ((mv60 > 0) == achat, efficacite, (mv4h > 0) == achat, mv60, mv4h)


def ligne(nom, t):
    n = len(t)
    g = sum(1 for x in t if x[0] > 0)
    r = sum(x[0] for x in t)
    return f"  {nom:<34} {n:>5} {100 * g / n:>6.0f}% {r:>+8.2f} {r / n:>+6.2f}" + ("" if n >= 30 else "  (peu de trades)")


def tableau(titre, groupes):
    print(titre)
    print(f"  {'':<34} {'trades':>5} {'gagn.':>7} {'R cumul':>8} {'R moy':>6}")
    for nom, t in groupes:
        if t:
            print(ligne(nom, t))
    print()


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
    trades = trades_avec_heure_ouverture(lignes, genre, depuis)
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
    try:
        mt5.symbol_select(SYMBOLE, True)
        tick = mt5.symbol_info_tick(SYMBOLE)
        decalage = (tick.time - time.time()) if tick and tick.time else 0.0
        mesurees = []
        for t_ouv, sens, r, g in trades:
            reel = t_ouv.timestamp() + decalage
            fin = datetime.fromtimestamp(reel)
            m1 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, datetime.fromtimestamp(reel - 3600 - 60), fin)
            m5 = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M5, datetime.fromtimestamp(reel - 4 * 3600 - 300), fin)
            if m1 is None or m5 is None:
                continue
            m = mesures([float(x["close"]) for x in m1], [float(x["close"]) for x in m5], sens)
            if m:
                mesurees.append((r, g) + m)
    finally:
        mt5.shutdown()
    if not mesurees:
        print("Aucune bougie exploitable (historique manquant dans MetaTrader : ouvre un graphique M1 de l'or et reessaie).")
        return 0
    print(f"{len(mesurees)} trades mesures sur {len(trades)} | signal : {genre} | depuis le {depuis:%d/%m/%Y} | "
          f"R {sum(x[0] for x in mesurees):+.2f}\n")
    tableau("Le trade va AVEC ou CONTRE le mouvement des 60 dernieres minutes",
            [("AVEC le mouvement (60 min)", [x for x in mesurees if x[2]]), ("CONTRE le mouvement (60 min)", [x for x in mesurees if not x[2]])])
    tableau("Le trade va AVEC ou CONTRE le mouvement des 4 dernieres heures",
            [("AVEC le mouvement (4 h)", [x for x in mesurees if x[4]]), ("CONTRE le mouvement (4 h)", [x for x in mesurees if not x[4]])])
    eff = sorted(x[3] for x in mesurees)
    b1, b2 = eff[len(eff) // 3], eff[2 * len(eff) // 3]
    bas = [x for x in mesurees if x[3] < b1]
    mil = [x for x in mesurees if b1 <= x[3] < b2]
    haut = [x for x in mesurees if x[3] >= b2]
    tableau(f"Marche directionnel ? (efficacite 60 min : {b1:.2f} / {b2:.2f} = seuils des tiers)",
            [("dents de scie (tiers bas)", bas), ("moyen", mil), ("directionnel (tiers haut)", haut)])
    tableau("Directionnel (tiers haut) selon le sens du trade",
            [("directionnel + AVEC le mouvement", [x for x in haut if x[2]]),
             ("directionnel + CONTRE le mouvement", [x for x in haut if not x[2]]),
             ("dents de scie + AVEC", [x for x in bas if x[2]]),
             ("dents de scie + CONTRE", [x for x in bas if not x[2]])])
    print("Lecture : un contexte qui fait vraiment mieux a un R moyen nettement meilleur ET au moins 30 trades.")
    print("Ce sont des observations sur quelques semaines, pas des causes : a confirmer avant de changer le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
