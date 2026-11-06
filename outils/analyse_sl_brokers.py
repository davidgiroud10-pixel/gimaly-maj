# -*- coding: utf-8 -*-
r"""Un autre courtier (spread plus large, prix un peu different) se fait-il stopper sur des trades ou ton bot « frole » le stop ? (lecture seule)

Contexte : le bot place le stop a une DISTANCE du prix d'entree. Une VENTE se ferme au prix ASK, donc son stop se declenche quand l'ask touche le
niveau, c'est-a-dire quand le graphique (prix bid) est encore a un spread en dessous : sur un courtier au spread plus large, les ventes sont stoppees
plus tot. (Le bot corrige deja l'OBJECTIF d'une vente du spread ; pas son stop.) Un ACHAT se ferme au bid, comme le graphique : l'ecart entre courtiers y vient
seulement de la difference de cotation.
Pour chaque trade termine (trades_bot.csv), on rejoue les bougies M1 de MetaTrader depuis l'entree jusqu'a la sortie reelle et on mesure la MARGE : de combien
le stop a ete evite (en dollars, ask pour une vente, bid pour un achat). Puis on simule un courtier « plus defavorable de e dollars » (spread plus large ou cotation
differente), e = 0,2 / 0,3 / 0,5 / 1,0 : combien de tes trades NON stoppes auraient ete stoppes chez lui, et combien de R cela coute par trade.
Rappel : 1 R = distance du stop. Les ecarts de cotation sont aleatoires (parfois dans ton sens) ; seul le spread est systematique.
Usage (dossier gimaly, MetaTrader 5 ouvert, historique M1 charge, a cote de analyse_be_trailing.py et diag_tp.py) :
  .\.venv\Scripts\python.exe analyse_sl_brokers.py                       trades reels scalp_keltner_large depuis le 20/10/2026
  .\.venv\Scripts\python.exe analyse_sl_brokers.py --genre tous --depuis 23/09/2026"""
import bisect
import datetime as dt
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

ECARTS = (0.2, 0.3, 0.5, 1.0)


def main():
    args = sys.argv[1:]

    def option(nom, defaut):
        if nom in args:
            i = args.index(nom)
            val = args[i + 1]
            del args[i:i + 2]
            return val
        return defaut

    depuis = dt.datetime.strptime(option("--depuis", "20/10/2026"), "%d/%m/%Y")
    genre = option("--genre", "scalp_keltner_large")
    genre = None if genre == "tous" else genre
    force = option("--decalage", None)
    force = float(force.replace(",", ".")) if force else None
    trades = []
    for tr in diag_tp.lire_trades():
        l = tr["ligne"]
        pe, sl = abt.nombre(l.get("pe")), abt.nombre(l.get("sl"))
        if tr["ouverture"] < depuis or None in (pe, sl) or pe == sl:
            continue
        if genre and (l.get("genre") or "").strip() != genre:
            continue
        trades.append({"t0": tr["ouverture"], "t1": tr["fermeture"], "achat": l.get("sens") == "achat", "pe": pe, "sl": sl,
                       "r": abt.nombre(l.get("R")), "stop": "stop" in (l.get("resultat") or "").lower()})
    if not trades:
        sys.exit("aucun trade sur cette periode")
    trades.sort(key=lambda x: x["t0"])
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
        decalage = diag_tp.decalage_serveur(mt5, sym, force)
        debut = min(x["t0"] for x in trades).timestamp() + decalage - 7200
        fin = max(x["t1"] for x in trades).timestamp() + decalage + 7200
        rates = diag_tp.charger_bougies(mt5, sym, debut, fin)
    finally:
        mt5.shutdown()
    if rates is None:
        sys.exit("MT5 ne fournit pas les bougies M1 de cette periode : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche, puis relance.")
    temps = [float(r["time"]) for r in rates]
    ouvertures = {int(r["time"]): float(r["open"]) for r in rates}
    mesures, rejetes = [], 0
    for tr in trades:
        al = abt.aligner(tr["t0"].timestamp(), tr["pe"], decalage, ouvertures)
        if al is None or al[2] > 3:
            rejetes += 1
            continue
        a = al[0]
        duree = max(60.0, (tr["t1"] - tr["t0"]).total_seconds()) + 60
        i0, i1 = bisect.bisect_left(temps, a), bisect.bisect_right(temps, a + duree)
        seg = rates[i0:i1]
        if not len(seg):
            rejetes += 1
            continue
        if tr["achat"]:
            marge = float(min(seg["low"])) - tr["sl"]                      # bid : comme le graphique
            marge_graphique = marge
        else:
            marge = tr["sl"] - max(float(r["high"]) + float(r["spread"]) * pt for r in seg)     # ask
            marge_graphique = tr["sl"] - float(max(seg["high"]))
        mesures.append({**tr, "marge": marge, "marge_graphique": marge_graphique, "dist": abs(tr["pe"] - tr["sl"])})
    print(f"{len(mesures)} trades analyses sur {len(trades)} ({rejetes} ecartes : prix d'entree non retrouve) | depuis le {depuis:%d/%m/%Y}"
          + (f" | genre {genre}" if genre else " | tous genres"))
    if len(mesures) < 30:
        print("trop peu de trades.")
        return
    ventes = [m for m in mesures if not m["achat"]]
    achats = [m for m in mesures if m["achat"]]
    stop_v = [m for m in ventes if m["stop"]]
    print(f"\n1. TES VENTES STOPPEES PAR L'ASK : sur {len(stop_v)} ventes stoppees, {sum(1 for m in stop_v if m['marge_graphique'] > 0)} "
          f"({100 * sum(1 for m in stop_v if m['marge_graphique'] > 0) / max(len(stop_v), 1):.0f} %) n'ont PAS vu le graphique (bid) toucher le stop : seul l'ask l'a touche.")
    nons = [m for m in mesures if not m["stop"]]
    print(f"\n2. TRADES « FROLES » (non stoppes, marge faible avant le stop), sur {len(nons)} trades non stoppes :")
    for seuil in (0.2, 0.5, 1.0, 2.0):
        print(f"   marge < {seuil:.1f} $ : {sum(1 for m in nons if m['marge'] < seuil):>3} trades ({100 * sum(1 for m in nons if m['marge'] < seuil) / len(nons):.0f} %)")
    print("\n3. COURTIER PLUS DEFAVORABLE DE e DOLLARS (spread plus large ou cotation differente) : trades NON stoppes chez toi, stoppes chez lui")
    print(f"   {'e':>5} | {'ventes':>7} {'achats':>7} {'dont gagnants':>14} | cout en R par trade (tous trades)")
    for e in ECARTS:
        flips = [m for m in nons if m["marge"] < e]
        gagnants = [m for m in flips if (m["r"] or 0) > 0]
        cout = sum((m["r"] or 0) + 1 for m in gagnants) + sum(1 + (m["r"] or 0) for m in flips if (m["r"] or 0) <= 0 and (m["r"] or 0) > -1)
        print(f"   {e:>4.1f}$ | {sum(1 for m in flips if not m['achat']):>7} {sum(1 for m in flips if m['achat']):>7} {len(gagnants):>14} | -{cout / len(mesures):.3f} R "
              f"({len(flips)} trades de plus stoppes sur {len(mesures)})")
    print("\nLecture : un trade « de plus stoppe » chez l'autre courtier perd environ 1 R au lieu de ce que tu as gagne (cout = R gagne + 1). Seules les VENTES sont touchees")
    print("systematiquement par le spread (l'ask declenche le stop) ; pour les achats, l'ecart vient des differences de cotation, dans les deux sens.")
    print("Correction possible sans toucher a tes propres trades : ajouter le spread du courtier de l'ami au stop des ventes (comme le bot le fait deja pour l'objectif).")


if __name__ == "__main__":
    main()
