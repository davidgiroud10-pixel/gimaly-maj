# -*- coding: utf-8 -*-
"""Diagnostic : le prix a-t-il VRAIMENT touche le TP (ou le SL) d'un trade, et a combien pres ?

Usage (depuis C:\\Users\\<toi>\\gimaly, MT5 ouvert) :
  .\\.venv\\Scripts\\python.exe diag_tp.py achat 16:22 17:09 4030.27 4016.99
                                         sens  debut fin  TP      SL        (heures de ton PC, aujourd'hui)

Lit les bougies M1 de MetaTrader 5 (prix bid, comme le graphique) entre le debut et la fin du trade et dit :
  * le plus haut / le plus bas atteint et sa distance au TP et au SL ;
  * pour une VENTE, le meme calcul a l'ask (prix reel de fermeture), avec le spread de la bougie ;
  * le spread maximal rencontre. Rien n'est modifie.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    sens, debut, fin, tp, sl = sys.argv[1].lower(), sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
    if sens not in ("achat", "vente"):
        sys.exit("le sens doit etre achat ou vente")
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MetaTrader 5 introuvable : ouvre-le et connecte-toi")
    try:
        from gimaly.trading.symbole import symbole_or
        sym = symbole_or()
    except Exception:  # noqa: BLE001
        sym = "XAUUSD"
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    maintenant = dt.datetime.now()
    h = lambda s: maintenant.replace(hour=int(s.split(":")[0]), minute=int(s.split(":")[1]), second=0, microsecond=0)
    d0, d1 = h(debut), h(fin)
    # heure du serveur MT5 = heure du dernier tick ; on en deduit le decalage sans supposer de fuseau
    srv = lambda local: float(tick.time) - (maintenant - local).total_seconds()
    t0, t1 = srv(d0) - 60, srv(d1) + 60
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 1500)
    if rates is None or len(rates) == 0:
        sys.exit("aucune bougie M1 recue")
    fen = [r for r in rates if t0 <= r["time"] <= t1]
    if not fen:
        sys.exit("aucune bougie dans cette fenetre : verifie les heures (heure de ton PC, aujourd'hui)")
    pt = info.point if info else 0.01
    local = lambda t: (maintenant - dt.timedelta(seconds=float(tick.time) - float(t))).strftime("%H:%M")
    hi = max(fen, key=lambda r: r["high"]); lo = min(fen, key=lambda r: r["low"])
    pt = float(pt)
    sp_max = float(max(r["spread"] for r in fen)) * pt
    print(f"\nSymbole {sym} - {sens} - {len(fen)} bougies M1 entre {debut} et {fin}")
    print(f"TP {tp:.2f}   SL {sl:.2f}   spread maximal rencontre : {sp_max:.2f} $\n")
    print(f"Plus haut  (bid) : {hi['high']:.2f} a {local(hi['time'])}   -> {hi['high'] - tp:+.2f} $ par rapport au TP, {hi['high'] - sl:+.2f} $ par rapport au SL")
    print(f"Plus bas   (bid) : {lo['low']:.2f} a {local(lo['time'])}   -> {lo['low'] - tp:+.2f} $ par rapport au TP, {lo['low'] - sl:+.2f} $ par rapport au SL")
    if sens == "achat":
        verdict = "TP TOUCHE au bid (il aurait du se declencher)" if hi["high"] >= tp else f"TP NON touche : il a manque de {tp - hi['high']:.2f} $"
        print(f"\nAchat : fermeture au BID. {verdict}")
        sl_touche = lo["low"] <= sl
        print(f"SL {'touche' if sl_touche else 'non touche'} au bid (plus bas {lo['low']:.2f}).")
    else:
        bas_ask = min(fen, key=lambda r: r["low"] + r["spread"] * pt)
        ask = bas_ask["low"] + bas_ask["spread"] * pt
        print(f"Plus bas   (ask) : {ask:.2f} a {local(bas_ask['time'])}   (bid {bas_ask['low']:.2f} + spread {bas_ask['spread'] * pt:.2f})")
        if lo["low"] <= tp:
            if ask <= tp:
                print("\nVente : TP touche au bid ET a l'ask : il aurait du se declencher.")
            else:
                print(f"\nVente : TP touche au BID (graphique) mais PAS a l'ASK : il a manque de {ask - tp:.2f} $ a cause du spread.")
        else:
            print(f"\nVente : TP non touche meme au bid : il a manque de {lo['low'] - tp:.2f} $.")
    print("\n(Les bougies M1 donnent le plus haut/plus bas de chaque minute : une mèche de quelques secondes y figure.)")
    mt5.shutdown()


if __name__ == "__main__":
    main()
