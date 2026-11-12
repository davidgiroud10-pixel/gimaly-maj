# -*- coding: utf-8 -*-
r"""Tes derniers trades auraient-ils passe avec un stop plus large ? (lecture seule, rien n'est modifie, aucun ordre)
Pour chaque trade termine recent du bot, on rejoue le marche minute par minute (bougies M1 de MetaTrader, spread compris) avec la MEME entree et un stop
et un objectif multiplies par k (1 = ce qui s'est passe, 1,5 = le reglage trading_keltner_large_k, 2, 3), risque constant en R. Sortie : le R de chaque variante.
ATTENTION : un trade isole est une anecdote. Sur 6 a 10 trades, la plupart des « il aurait passe » sont compensees par des « il aurait ete stoppe plus loin et
perdu plus de temps » : regarde le TOTAL en bas, et rappelle-toi que test_respirer.py (10 mois, 11 864 signaux) est la mesure fiable, pas ces quelques lignes.
Usage (dossier gimaly, MetaTrader 5 ouvert, a cote de analyse_be_trailing.py et diag_tp.py) :
  .\.venv\Scripts\python.exe rejouer_k.py                 les 8 derniers trades scalp_keltner_large
  .\.venv\Scripts\python.exe rejouer_k.py --n 20          les 20 derniers
  .\.venv\Scripts\python.exe rejouer_k.py --depuis 11/11/2026"""
import bisect
import datetime as dt
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import analyse_be_trailing as abt
    import diag_tp
except ImportError:
    print("Place ce script a cote de analyse_be_trailing.py et diag_tp.py (dossier gimaly).")
    raise SystemExit(1)

KS = (1.0, 1.5, 2.0, 3.0)


def main(argv):
    argv = list(argv)

    def option(nom, defaut):
        if nom in argv:
            i = argv.index(nom)
            v = argv[i + 1]
            del argv[i:i + 2]
            return v
        return defaut

    n = int(option("--n", "8"))
    depuis = option("--depuis", None)
    genre = option("--genre", "scalp_keltner_large")
    genre = None if genre == "tous" else genre
    trades = []
    for tr in diag_tp.lire_trades():
        l = tr["ligne"]
        pe, sl, tp = abt.nombre(l.get("pe")), abt.nombre(l.get("sl")), abt.nombre(l.get("tp1"))
        if None in (pe, sl, tp) or pe == sl or tr.get("fermeture") is None:
            continue
        if genre and (l.get("genre") or "").strip() != genre:
            continue
        trades.append({"t": tr["ouverture"], "t1": tr["fermeture"], "achat": l.get("sens") == "achat", "pe": pe, "sl": sl, "tp": tp,
                       "r_reel": abt.nombre(l.get("R")), "sortie": (l.get("resultat") or "").strip()})
    trades.sort(key=lambda x: x["t"])
    if depuis:
        d0 = dt.datetime.strptime(depuis, "%d/%m/%Y")
        trades = [t for t in trades if t["t"] >= d0]
    else:
        trades = trades[-n:]
    if not trades:
        sys.exit("aucun trade termine trouve")
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MetaTrader 5 introuvable : ouvre-le et connecte-toi")
    try:
        try:
            from gimaly.trading.symbole import symbole_or
            sym = symbole_or()
        except Exception:  # noqa: BLE001
            sym = "XAUUSD"
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        pt = float(info.point) if info else 0.01
        decalage = diag_tp.decalage_serveur(mt5, sym, None)
        debut = min(x["t"] for x in trades).timestamp() + decalage - 7200
        fin = max(x["t1"] for x in trades).timestamp() + decalage + 7200
        rates = diag_tp.charger_bougies(mt5, sym, debut, fin)
    finally:
        mt5.shutdown()
    if rates is None:
        sys.exit("MT5 ne fournit pas les bougies M1 de cette periode : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche, puis relance.")
    temps = [float(r["time"]) for r in rates]
    ouvertures = {int(r["time"]): float(r["open"]) for r in rates}
    lignes, ecartes = [], 0
    for tr in trades:
        al = abt.aligner(tr["t"].timestamp(), tr["pe"], decalage, ouvertures)
        if al is None or al[2] > 3:
            ecartes += 1
            continue
        a = al[0]
        i0, i1 = bisect.bisect_left(temps, a), bisect.bisect_right(temps, a + 3600)
        if i1 <= i0:
            ecartes += 1
            continue
        bougies = rates[i0:i1]
        res = {}
        for k in KS:
            sl = tr["pe"] - k * (tr["pe"] - tr["sl"])
            tp = tr["pe"] + k * (tr["tp"] - tr["pe"])
            res[k] = abt.rejouer(tr["achat"], tr["pe"], sl, tp, bougies, pt, {})
        lignes.append((tr, res))
    print(f"{len(lignes)} trades rejoues ({ecartes} ecartes : bougies non alignees) | stop et objectif x k, risque constant en R\n")
    print(f"{'ouverture':<13}{'sens':<7}{'stop $':>7}{'reel R':>8}" + "".join(f"{'k=' + format(k, 'g'):>9}" for k in KS))
    for tr, res in lignes:
        reel = f"{tr['r_reel']:+.2f}" if tr["r_reel"] is not None else "  ?"
        print(f"{tr['t']:%d/%m %H:%M}  {'achat' if tr['achat'] else 'vente':<7}{abs(tr['pe'] - tr['sl']):>7.2f}{reel:>8}"
              + "".join(f"{res[k]:>+9.2f}" if res[k] is not None else f"{'n/a':>9}" for k in KS))
    print(f"\n{'TOTAL R':<35}" + "".join(f"{sum(r[k] for _, r in lignes if r[k] is not None):>+9.2f}" for k in KS))
    stoppes = lambda k: sum(1 for _, r in lignes if r[k] is not None and r[k] <= -0.95)
    print(f"{'trades stoppes':<35}" + "".join(f"{stoppes(k):>9}" for k in KS))
    print("\nLecture : compare les colonnes sur le TOTAL et le nombre de stops, pas ligne par ligne. Peu de trades = anecdote, pas preuve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
