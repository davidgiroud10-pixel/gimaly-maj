# -*- coding: utf-8 -*-
"""Tes trades vont-ils mieux AVEC ou CONTRE la tendance H1 ?

Usage (depuis C:\\Users\\<toi>\\gimaly, MetaTrader 5 ouvert) :
  .\\.venv\\Scripts\\python.exe diag_tendance.py                     le signal actuel (scalp_keltner_large)
  .\\.venv\\Scripts\\python.exe diag_tendance.py --genre iceberg      un autre type de signal
  .\\.venv\\Scripts\\python.exe diag_tendance.py --tous               tous les types ensemble
Option : --decalage 2   (heures entre UTC et l'heure du serveur MT5, seulement si le programme le demande).

Pour chaque trade termine de trades_bot.csv, il retrouve la tendance H1 AU MOMENT de l'ouverture avec la meme
regle que ton detecteur (EMA 20 au-dessus / au-dessous de l'EMA 50 ET qui monte / descend depuis 3 h, sur des
bougies H1 CLOSES avant l'ouverture), puis compare « avec », « contre » et « mixte ». Rien n'est modifie.
Les heures de trades_bot.csv sont celles de ton PC.

R EN ARGENT : la colonne R du fichier est fausse quand le lot a ete plafonne (ex. -0,3 R pour un stop touche).
Ici le R est recalcule : gain / (lot x distance du stop x valeur du point), la valeur du point (conversion
dollar -> devise du compte) etant calibree sur tes stops propres (R du fichier <= -0,98). Rien n'est modifie.
"""
import bisect
import csv
import datetime as dt
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return None


def lire_trades(genre):
    """Un trade par message_id : ouverture (ligne 'ouvert') + resultat (derniere ligne non 'ouvert')."""
    with open(FICHIER, encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    par_id = {}
    for l in lignes:
        try:
            t = dt.datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
        except (ValueError, KeyError):
            continue
        d = par_id.setdefault(l.get("message_id"), {"genre": l.get("genre", ""), "sens": l.get("sens", ""),
                                                     "ouverture": t, "R": None, "gain": None, "R_fichier": None,
                                                     "volume": None, "pe": None, "sl": None})
        if (l.get("resultat") or "").strip().lower() != "ouvert":
            d["R_fichier"], d["gain"] = nombre(l.get("R")), nombre(l.get("gain_devise"))
            d["volume"], d["pe"], d["sl"] = nombre(l.get("volume")), nombre(l.get("pe")), nombre(l.get("sl"))
    trades = [d for d in par_id.values() if d["R_fichier"] is not None]
    trades = recalculer_r(trades)
    if genre:
        trades = [d for d in trades if d["genre"] == genre]
    return sorted(trades, key=lambda d: d["ouverture"])


def recalculer_r(trades):
    """R en argent = gain / (lot x distance du stop x f). f (valeur du point) est deduit des stops propres."""
    def base(d):
        try:
            return d["volume"] * abs(d["pe"] - d["sl"])
        except TypeError:
            return None
    rapports = sorted(-d["gain"] / base(d) for d in trades
                      if d["R_fichier"] <= -0.98 and d["gain"] and base(d) and base(d) > 0 and d["gain"] < 0)
    if len(rapports) < 5:
        print("Attention : moins de 5 stops propres pour calibrer la valeur du point : R du fichier utilise.")
        for d in trades:
            d["R"] = d["R_fichier"]
        return trades
    f = rapports[len(rapports) // 2]
    ecart = sum(1 for d in trades if base(d) and d["gain"] is not None and abs(d["gain"] / (base(d) * f) - d["R_fichier"]) > 0.15)
    print(f"R recalcule en argent (valeur du point calibree sur {len(rapports)} stops : {f:.4f}). "
          f"{ecart} trade(s) sur {len(trades)} ont un R du fichier different de plus de 0,15.")
    for d in trades:
        b = base(d)
        d["R"] = d["gain"] / (b * f) if b and b > 0 and d["gain"] is not None else d["R_fichier"]
    return trades


def tendance_h1(bougies_h1):
    """Meme regle que gimaly/trading/valeurs_initiales.py : heure -> haussiere / baissiere / mixte,
    sur les seules bougies H1 closes avant cette heure."""
    if not bougies_h1 or len(bougies_h1) < 60:
        return lambda t: ""

    def ema(valeurs, n):
        k, sortie, m = 2 / (n + 1), [], None
        for v in valeurs:
            m = v if m is None else m + k * (v - m)
            sortie.append(m)
        return sortie

    heures = [b[0] for b in bougies_h1]
    closes = [b[4] for b in bougies_h1]
    e20, e50 = ema(closes, 20), ema(closes, 50)

    def lire(t):
        i = bisect.bisect_right(heures, t - 3600) - 1
        if i < 53:
            return ""
        if e20[i] > e50[i] and e20[i] > e20[i - 3]:
            return "haussiere"
        if e20[i] < e50[i] and e20[i] < e20[i - 3]:
            return "baissiere"
        return "mixte"
    return lire


def accord(tendance, sens):
    if not tendance:
        return "inconnu"
    if tendance == "mixte":
        return "mixte"
    achat = sens.strip().lower() in ("achat", "acheteur", "buy")
    return "avec" if (tendance == "haussiere") == achat else "contre"


def moyenne_et_erreur(rs):
    n = len(rs)
    m = sum(rs) / n
    sd = (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5 if n > 1 else float("nan")
    return m, sd / math.sqrt(n) if n > 1 else float("nan")


def ligne(nom, ts):
    rs = [t["R"] for t in ts]
    if not rs:
        return f"  {nom:<14} n=   0"
    m, se = moyenne_et_erreur(rs)
    return (f"  {nom:<14} n={len(rs):>4}  gagnants {sum(r > 0 for r in rs) / len(rs):4.0%}  "
            f"total {sum(rs):+7.1f} R  moyenne {m:+.2f} R (±{se:.2f})")


def decalage_serveur(mt5, sym, force):
    if force is not None:
        return force * 3600
    tick = mt5.symbol_info_tick(sym)
    ecart = float(tick.time) - time.time()
    heures = round(ecart / 3600)
    if abs(ecart - heures * 3600) > 600 or abs(heures) > 12:
        sys.exit("Impossible de deduire l'heure du serveur MT5 (marche ferme ?). Relance avec --decalage 2 "
                 "(ou 3 en heure d'ete) : c'est l'ecart en heures entre UTC et l'heure affichee par MT5.")
    return heures * 3600


def charger_h1(mt5, sym, debut_srv, fin_srv):
    d0 = dt.datetime.fromtimestamp(debut_srv, dt.timezone.utc)      # MT5 lit l'heure serveur comme de l'UTC
    d1 = dt.datetime.fromtimestamp(fin_srv, dt.timezone.utc)
    for _ in range(6):
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, d0, d1)
        if rates is not None and len(rates) > 0:
            return rates
        time.sleep(1.5)
    return None


def main():
    args = sys.argv[1:]
    force = None
    if "--decalage" in args:
        i = args.index("--decalage")
        force = float(args[i + 1])
        del args[i:i + 2]
    if "-h" in args or "--help" in args:
        sys.exit(__doc__)
    genre = "scalp_keltner_large"
    if "--tous" in args:
        genre = None
    elif "--genre" in args:
        genre = args[args.index("--genre") + 1]
    if not FICHIER.exists():
        sys.exit(f"{FICHIER} introuvable")
    trades = lire_trades(genre)
    if len(trades) < 20:
        sys.exit(f"seulement {len(trades)} trade(s) termine(s) pour ce signal : trop peu pour comparer")

    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MetaTrader 5 introuvable : ouvre-le et connecte-toi")
    try:
        try:
            sys.path.insert(0, str(Path.cwd()))
            from gimaly.trading.symbole import symbole_or
            sym = symbole_or()
        except Exception:  # noqa: BLE001
            sym = "XAUUSD"
        mt5.symbol_select(sym, True)
        decalage = decalage_serveur(mt5, sym, force)
        debut = trades[0]["ouverture"].timestamp() + decalage - 14 * 86400      # chauffe des moyennes
        fin = trades[-1]["ouverture"].timestamp() + decalage + 3 * 3600
        rates = charger_h1(mt5, sym, debut, fin)
    finally:
        mt5.shutdown()
    if rates is None or len(rates) < 60:
        sys.exit("pas assez de bougies H1 dans MT5 : ouvre un graphique H1 de l'or, fais defiler vers la gauche "
                 "pour charger l'historique, puis relance")
    h1 = [(int(r["time"]) - decalage, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
          for r in rates]
    h1.sort()
    lire = tendance_h1(h1)

    for t in trades:
        t["tendance"] = lire(t["ouverture"].timestamp())
        t["accord"] = accord(t["tendance"], t["sens"])

    titre = genre or "tous les signaux"
    print(f"\nTendance H1 (EMA 20/50) au moment de l'ouverture - {titre}")
    print(f"{len(trades)} trades termines du {trades[0]['ouverture']:%d/%m/%Y} au {trades[-1]['ouverture']:%d/%m/%Y}\n")
    groupes = defaultdict(list)
    for t in trades:
        groupes[t["accord"]].append(t)
    print("PAR ACCORD AVEC LA TENDANCE")
    print(ligne("tous", trades))
    for k in ("avec", "contre", "mixte", "inconnu"):
        if groupes.get(k):
            print(ligne(k, groupes[k]))
    print("\nPAR SENS ET ACCORD")
    sg = defaultdict(list)
    for t in trades:
        sg[(t["sens"], t["accord"])].append(t)
    for k in sorted(sg):
        print(ligne(f"{k[0]} {k[1]}", sg[k]))

    a, c = groupes.get("avec", []), groupes.get("contre", [])
    print("\nCONCLUSION")
    if len(a) >= 10 and len(c) >= 10:
        ma, sa = moyenne_et_erreur([t["R"] for t in a])
        mc, sc = moyenne_et_erreur([t["R"] for t in c])
        diff, se = ma - mc, (sa ** 2 + sc ** 2) ** 0.5
        print(f"  avec - contre = {diff:+.2f} R par trade (erreur ±{se:.2f})")
        if abs(diff) < 2 * se:
            print("  -> Pas de difference DEMONTREE : l'ecart est dans la marge d'erreur. Rien ne prouve qu'il faille")
            print("     filtrer la tendance. Relance quand tu auras plus de trades.")
        else:
            mieux = "AVEC" if diff > 0 else "CONTRE"
            print(f"  -> Les trades {mieux} la tendance font mieux, et l'ecart depasse la marge d'erreur (2x).")
            print("     Ca merite un filtre, a confirmer sur de nouveaux trades avant de l'imposer.")
    else:
        print("  Trop peu de trades dans un des groupes (moins de 10) pour conclure.")
    print("\nRappel : sur quelques dizaines de trades, seul un grand ecart est visible. Un resultat 'sans difference'")
    print("ne veut pas dire que la tendance est sans effet, seulement qu'elle n'est pas mesurable ici.\n")


if __name__ == "__main__":
    main()
