# -*- coding: utf-8 -*-
r"""Le stop des VENTES doit-il etre decale du spread du courtier ? Test sur tes trades deja faits (lecture seule, rien n'est modifie)

Rappel : une vente se ferme a l'ASK ; son stop se declenche donc quand le graphique (bid) est encore a un spread du niveau. Le bot corrige deja
l'objectif d'une vente de ce spread, pas son stop. Sur un courtier au spread plus large, les ventes sont stoppees plus tot que chez toi.
Correctif etudie : stop envoye a MetaTrader = stop publie + marge (marge = spread du courtier, avec un plancher « au plus large »), et le volume est
calcule sur la distance AGRANDIE (le risque en euros reste le meme ; 1 R = distance + marge).
Chaque trade termine est rejoue sur les bougies M1 de MetaTrader. Pour un courtier dont le spread est plus large que le tien de e dollars, on compare :
  A  toi, sans correctif (reference)
  B  courtier plus large de e, SANS correctif (ce que voient tes amis aujourd'hui)
  C  courtier plus large de e, marge = son spread (adaptative)
  D  courtier plus large de e, marge = max(son spread, plancher)  (plancher 0,55 $ par defaut : « au plus large »)
  E  toi avec marge = ton spread (si on appliquait le correctif aussi a ton bot)
R moyen par trade (tous les trades ; les achats ne changent pas), difference avec A et intervalle regroupe par jour (95 %).
Hypotheses prudentes : stop avant objectif dans la meme minute, vente rachetee a l'ask, meme prix d'entree pour tous les courtiers, volume arrondi ignore.
Usage (dossier gimaly, MetaTrader 5 ouvert, historique M1 charge, a cote de analyse_be_trailing.py et diag_tp.py) :
  .\.venv\Scripts\python.exe analyse_marge_stop.py                    trades reels scalp_keltner_large depuis le 20/10/2026
  .\.venv\Scripts\python.exe analyse_marge_stop.py --plancher 0.7 --depuis 06/11/2026"""
import bisect
import datetime as dt
import math
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

ECARTS = (0.2, 0.5)


def avec_spread(rates, extra, pt):
    r = rates.copy()
    r["spread"] = r["spread"] + int(round(extra / pt))
    return r


def rejouer_marge(d, rates, pt, marge):
    """R du trade d avec le stop des ventes decale de `marge` (achats inchanges)."""
    achat, pe, sl, tp, bougies = d["achat"], d["pe"], d["sl"], d["tp"], d["bougies"]
    if not achat:
        sl = sl + marge
    return abt.rejouer(achat, pe, sl, tp, bougies, pt, {})


def ic_jours(par_jour):
    n = sum(len(v) for v in par_jour.values())
    m = sum(sum(v) for v in par_jour.values()) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par_jour.values())) / n
    return m, m - 1.96 * se, m + 1.96 * se


def evaluer(donnees, rates, pt, plancher, s0):
    """donnees : liste de {t, achat, pe, sl, tp, i0, i1}. Renvoie {nom: [R par trade]} (None si non rejouable)."""
    res = {}
    def jouer(r, marge):
        out = []
        for d in donnees:
            d2 = dict(d, bougies=r[d["i0"]:d["i1"]])
            out.append(rejouer_marge(d2, r, pt, marge))
        return out
    res["A  toi, sans correctif"] = jouer(rates, 0.0)
    res["E  toi, marge = ton spread"] = jouer(rates, s0)
    for e in ECARTS:
        r = avec_spread(rates, e, pt)
        res[f"B  courtier +{e:.1f} $, sans correctif"] = jouer(r, 0.0)
        res[f"C  courtier +{e:.1f} $, marge = son spread"] = jouer(r, s0 + e)
        res[f"D  courtier +{e:.1f} $, marge = max(spread, {plancher:g})"] = jouer(r, max(s0 + e, plancher))
    return res


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
    plancher = float(option("--plancher", "0.55").replace(",", "."))
    force = option("--decalage", None)
    force = float(force.replace(",", ".")) if force else None
    trades = []
    for tr in diag_tp.lire_trades():
        l = tr["ligne"]
        pe, sl, tp = abt.nombre(l.get("pe")), abt.nombre(l.get("sl")), abt.nombre(l.get("tp1"))
        if tr["ouverture"] < depuis or None in (pe, sl, tp) or pe == sl:
            continue
        if genre and (l.get("genre") or "").strip() != genre:
            continue
        trades.append({"t": tr["ouverture"], "t1": tr["fermeture"], "achat": l.get("sens") == "achat", "pe": pe, "sl": sl, "tp": tp})
    if not trades:
        sys.exit("aucun trade sur cette periode")
    trades.sort(key=lambda x: x["t"])
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
        debut = min(x["t"] for x in trades).timestamp() + decalage - 7200
        fin = max(x["t1"] for x in trades).timestamp() + decalage + 7200
        rates = diag_tp.charger_bougies(mt5, sym, debut, fin)
    finally:
        mt5.shutdown()
    if rates is None:
        sys.exit("MT5 ne fournit pas les bougies M1 de cette periode : ouvre un graphique M1 de l'or et fais-le defiler vers la gauche, puis relance.")
    temps = [float(r["time"]) for r in rates]
    ouvertures = {int(r["time"]): float(r["open"]) for r in rates}
    donnees, rejetes = [], 0
    for tr in trades:
        al = abt.aligner(tr["t"].timestamp(), tr["pe"], decalage, ouvertures)
        if al is None or al[2] > 3:
            rejetes += 1
            continue
        a = al[0]
        i0, i1 = bisect.bisect_left(temps, a), bisect.bisect_right(temps, a + 3600)       # le bot coupe a 60 min
        if i1 > i0:
            donnees.append({**tr, "i0": i0, "i1": i1})
        else:
            rejetes += 1
    ventes = sum(1 for d in donnees if not d["achat"])
    s0 = statistics.median(float(r["spread"]) for r in rates) * pt
    print(f"{len(donnees)} trades rejoues ({ventes} ventes, {len(donnees) - ventes} achats), {rejetes} ecartes | spread median de ton courtier sur la periode : {s0:.2f} $ | depuis le {depuis:%d/%m/%Y}")
    if len(donnees) < 30:
        print("trop peu de trades.")
        return
    res = evaluer(donnees, rates, pt, plancher, s0)
    base = res["A  toi, sans correctif"]
    print(f"\n{'scenario':<52}{'R moyen':>9}{'diff vs A':>11}   IC 95 % (par jour)")
    for nom, r in res.items():
        ok = [i for i in range(len(donnees)) if r[i] is not None and base[i] is not None]
        moy = statistics.fmean(r[i] for i in ok)
        if nom.startswith("A"):
            print(f"{nom:<52}{moy:>+9.3f}{'-':>11}")
            continue
        par_jour = {}
        for i in ok:
            par_jour.setdefault(donnees[i]["t"].date(), []).append(r[i] - base[i])
        m, lo, hi = ic_jours(par_jour)
        print(f"{nom:<52}{moy:>+9.3f}{m:>+11.3f}   [{lo:+.3f} ; {hi:+.3f}]")
    arret = lambda x: x is not None and x <= -0.95
    print(f"\nPARITE AVEC TOI : sur {len(donnees)} trades, combien finissent differemment de chez toi ?")
    print(f"{'scenario':<52}{'ami stoppe, toi pas':>21}{'toi stoppe, ami pas':>21}   dont ventes (1re colonne)")
    for nom, r in res.items():
        if nom.startswith("A"):
            continue
        ok = [i for i in range(len(donnees)) if r[i] is not None and base[i] is not None]
        pire = [i for i in ok if arret(r[i]) and not arret(base[i])]
        mieux = [i for i in ok if arret(base[i]) and not arret(r[i])]
        print(f"{nom:<52}{len(pire):>21}{len(mieux):>21}   {sum(1 for i in pire if not donnees[i]['achat'])}")
    print("\nLecture : B montre ce que perdent aujourd'hui les courtiers au spread plus large ; C et D ce que le correctif leur rend ; E ce qu'il te ferait a toi.")
    print("Le correctif n'a de sens que si C (ou D) est nettement meilleur que B et se rapproche de A. Les achats ne sont pas touches par le spread.")


if __name__ == "__main__":
    main()
