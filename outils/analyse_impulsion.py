# -*- coding: utf-8 -*-
r"""Le bot entre-t-il plus souvent a perte quand il va CONTRE une impulsion en cours ? (LECTURE SEULE)

Pour chaque trade REEL termine du moteur choisi, on relit les bougies M1 de MetaTrader juste AVANT l'entree et on mesure :
  A) l'impulsion contre le trade : mouvement net des 5 dernieres bougies M1 closes, dans le sens oppose au trade (une vente en pleine
     montee = impulsion contre), en multiples de l'ATR M1 (14). Resultat par tiers : faible / moyenne / forte.
  B) la « confirmation » : la derniere bougie M1 close va-t-elle deja dans le sens du trade ? (oui / non)
  C) le nombre de bougies adverses sur les 5 dernieres (0 a 5).
Chaque groupe : trades, % gagnants, R cumule, R moyen avec intervalle a 95 % (reechantillonnage). Puis la meme lecture sur la 1re et la
2e moitie de la periode : un effet qui n'apparait pas dans les DEUX moities n'est pas fiable. Rien n'est modifie, aucune regle n'est ajoutee.

Usage (dossier gimaly, MetaTrader 5 ouvert) :
  .\.venv\Scripts\python.exe analyse_impulsion.py                          depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_impulsion.py 20/10/2026 --genre tous"""
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
N_BARRES = 5
N_ATR = 14


def _outils():
    spec = importlib.util.spec_from_file_location("analyse_stop_ideal", ICI / "analyse_stop_ideal.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ic95(valeurs, tirages=2000, graine=7):
    if len(valeurs) < 8:
        return None
    rnd = random.Random(graine)
    m = sorted(statistics.fmean(rnd.choices(valeurs, k=len(valeurs))) for _ in range(tirages))
    return m[int(0.025 * tirages)], m[int(0.975 * tirages) - 1]


def ic_ecart(a, b, tirages=2000, graine=11):
    """Intervalle a 95 % de (moyenne a - moyenne b)."""
    if len(a) < 8 or len(b) < 8:
        return None
    rnd = random.Random(graine)
    d = sorted(statistics.fmean(rnd.choices(a, k=len(a))) - statistics.fmean(rnd.choices(b, k=len(b))) for _ in range(tirages))
    return d[int(0.025 * tirages)], d[int(0.975 * tirages) - 1]


def ligne(nom, rs):
    if not rs:
        return f"  {nom:<34}      0"
    g = 100 * sum(1 for r in rs if r > 0.05) / len(rs)
    ic = ic95(rs)
    txt = f"[{ic[0]:+.2f} ; {ic[1]:+.2f}]" if ic else "trop peu"
    return f"  {nom:<34}{len(rs):>5} {g:>6.0f} % {sum(rs):>+8.1f} {statistics.fmean(rs):>+7.3f}  {txt}"


def entete():
    return f"  {'':<34}{'trades':>5} {'gagn.':>8} {'R cumul':>8} {'R moy':>7}  IC 95 % du R moyen"


def mesures(rates, entree_s, sens):
    """Mesures sur les bougies M1 closes avant celle de l'entree. rates : liste de (t, o, h, l, c) triee."""
    avant = [x for x in rates if x[0] < entree_s - 60]
    if len(avant) < N_ATR + N_BARRES:
        return None
    dernieres = avant[-N_BARRES:]
    vrais = [(x[2] - x[3]) for x in avant[-N_ATR:]]
    atr = statistics.fmean(vrais) or 1e-9
    net = dernieres[-1][4] - dernieres[0][1]                       # cloture derniere - ouverture premiere
    contre = (net if sens == "vente" else -net) / atr               # > 0 : le mouvement va contre le trade
    adverses = sum(1 for x in dernieres if ((x[4] > x[1]) if sens == "vente" else (x[4] < x[1])))
    derniere = dernieres[-1]
    confirme = (derniere[4] < derniere[1]) if sens == "vente" else (derniere[4] > derniere[1])
    return contre, adverses, confirme


def tiers(valeurs):
    q = sorted(valeurs)
    n = len(q)
    return q[n // 3], q[2 * n // 3]


def rapport(titre, lots):
    """lots : liste de (contre, adverses, confirme, R)."""
    print(titre)
    print(entete())
    c = [x[0] for x in lots]
    if len(lots) >= 9:
        b1, b2 = tiers(c)
        groupes = [(f"impulsion contre FAIBLE (< {b1:+.2f} ATR)", [x[3] for x in lots if x[0] < b1]),
                   (f"impulsion contre MOYENNE", [x[3] for x in lots if b1 <= x[0] < b2]),
                   (f"impulsion contre FORTE (>= {b2:+.2f} ATR)", [x[3] for x in lots if x[0] >= b2])]
        for nom, rs in groupes:
            print(ligne(nom, rs))
    for nom, rs in (("derniere bougie CONFIRME le trade", [x[3] for x in lots if x[2]]),
                    ("derniere bougie va CONTRE le trade", [x[3] for x in lots if not x[2]])):
        print(ligne(nom, rs))
    for k in range(0, N_BARRES + 1):
        rs = [x[3] for x in lots if x[1] == k]
        if rs:
            print(ligne(f"{k} bougie(s) adverse(s) sur {N_BARRES}", rs))
    if len(lots) >= 9:
        _, b2 = tiers(c)
        fort = [x[3] for x in lots if x[0] >= b2]
        reste = [x[3] for x in lots if x[0] < b2]
        ec = ic_ecart(fort, reste)
        if ec:
            print(f"  ecart R moyen (forte - reste) : {statistics.fmean(fort) - statistics.fmean(reste):+.3f}  IC 95 % [{ec[0]:+.2f} ; {ec[1]:+.2f}]")
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
    fichier = DOSSIER / "trades_bot.csv"
    if not fichier.exists():
        print(f"{fichier} introuvable.")
        return 1
    with open(fichier, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    outils = _outils()
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
                                      datetime.fromtimestamp(reel + 5 * 3600))
            if m1 is None or len(m1) < 40:
                continue
            rates = sorted((int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in m1)
            donnees.append((reel, sens, pe, sl, tp1, etat, r, [(t, h, b) for t, _, h, b, _ in rates], rates))
    finally:
        mt5.shutdown()
    if not donnees:
        print("Aucune bougie exploitable (ouvre un graphique M1 de l'or dans MetaTrader et reessaie).")
        return 0
    scores = {h: outils.alignement([d[:8] for d in donnees], h) for h in outils.DECALAGES_H}
    h_ok = max(scores, key=lambda h: scores[h][0])
    part = scores[h_ok][0]
    print(f"{len(trades)} trades termines | moteur : {genre} | depuis {depuis:%d/%m/%Y} | bougies M1 trouvees pour {len(donnees)}")
    print(f"decalage horaire MetaTrader retenu : {h_ok:+d} h ({100 * part:.0f} % des entrees retombent dans la bougie M1 attendue)")
    if part < 0.6:
        print("ATTENTION : l'alignement des heures est mauvais, les chiffres ci-dessous ne sont pas fiables.")
    print()
    lots = []
    for reel, sens, pe, sl, tp1, etat, r, brut, rates in donnees:
        m = mesures(rates, reel + 3600 * h_ok, sens)
        if m is not None:
            lots.append((m[0], m[1], m[2], r))
    if len(lots) < 9:
        print("Trop peu de trades exploitables pour une lecture.")
        return 0
    rapport(f"TOUTE LA PERIODE ({len(lots)} trades)", lots)
    moitie = len(lots) // 2
    rapport(f"PREMIERE MOITIE ({moitie} trades)", lots[:moitie])
    rapport(f"DEUXIEME MOITIE ({len(lots) - moitie} trades)", lots[moitie:])
    print("Lecture : un effet est credible seulement si (1) l'ecart a un intervalle qui n'inclut pas 0, (2) il va dans le meme sens dans les")
    print("DEUX moities, (3) chaque groupe compte au moins ~30 trades. Les trades d'une meme journee se ressemblent (correlation) : ")
    print("l'intervalle est un peu trop optimiste. On a teste plusieurs coupures a la fois : un resultat isole peut etre un hasard.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
