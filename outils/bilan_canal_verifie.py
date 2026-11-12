# -*- coding: utf-8 -*-
r"""Bilan PRUDENT du canal « Le Coin Trader » : seuls les signaux VERIFIES comptent (LECTURE SEULE, rien n'est modifie).
Un signal est verifie quand son R ecrit correspond a l'un de ses niveaux de TP (a 0,05 R pres) ET que son % lu est plausible (< 50 %). Les perdants et les nuls sont toujours gardes
(un stop a -1 R se verifie tout seul). Les GAGNANTS dont le TP atteint n'est pas retrouve (R ecrit au-dela des niveaux, % illisible...) sont comptes A ZERO : ils restent dans le
nombre de signaux, mais n'apportent aucun gain. Le bilan est donc un MINIMUM : il ne peut pas etre gonfle par un message mal lu.
R reel = % du capital du message (1 % de risque par signal partage entre les TP = 1 R) ; verifie par verif_tp_canal.py (recalcul a parts egales, point mort apres TP1).
Resultats theoriques : hors spread, commission, glissement. Signaux « non declenches », « sans chiffre », « en cours » et ajustements manuels non comptes.
Usage (dossier gimaly, a cote de verif_tp_canal.py) :  .\.venv\Scripts\python.exe bilan_canal_verifie.py [--canal "coin trader"] [--depuis jj/mm/aaaa]"""
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))
try:
    import verif_tp_canal as vt
except ImportError:
    print("Place ce script a cote de verif_tp_canal.py (dossier gimaly).")
    raise SystemExit(1)

DATA = Path.home() / "GIMALY"


def charger(canal, depuis):
    b = sqlite3.connect(f"file:{DATA / 'trades.db'}?mode=ro", uri=True)
    b.row_factory = sqlite3.Row
    rows = [dict(x) for x in b.execute("""SELECT t.message_id, t.date, t.sens, t.entree, t.stop, t.objectifs,
        COALESCE(c.statut,t.statut) statut, COALESCE(c.r,t.r) r, COALESCE(c.pourcentage,t.pourcentage) pct,
        COALESCE(c.annule,t.annule) annule FROM trades t LEFT JOIN corrections c ON c.canal=t.canal AND c.message_id=t.message_id
        WHERE t.canal=? ORDER BY t.date""", (canal,))]
    b.close()
    out = []
    for x in rows:
        if x["annule"] or x["statut"] in vt.IGNORES or x["r"] is None:
            continue
        try:
            t = datetime.fromisoformat(x["date"]).astimezone().replace(tzinfo=None)
            r = float(x["r"])
            lu = float(x["pct"]) if x["pct"] is not None else None
        except (ValueError, TypeError):
            continue
        if depuis and t < depuis:
            continue
        x.update({"t": t, "jour": t.date(), "r_ecrit": r, "lu": lu})
        out.append(x)
    return out


def verifie(x):
    """(valeur R reel retenue, raison d'exclusion ou None)."""
    r, lu = x["r_ecrit"], x["lu"]
    if r <= 0.05:
        if lu is None or abs(lu) >= 50:
            return (-1.0 if r < -0.05 else 0.0), None      # perdant : -1 R par definition du stop ; nul : 0
        return lu, None
    if lu is None:
        return 0.0, "gagnant sans %"
    if abs(lu) >= 50:
        return 0.0, f"% illisible ({lu:+.0f} %)"
    try:
        entree, stop = float(x["entree"]), float(x["stop"])
        risque = abs(entree - stop)
        rs = [abs(t - entree) / risque for t in vt.niveaux(x["objectifs"])]
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0, "niveaux illisibles"
    if not rs:
        return 0.0, "pas de TP"
    if min(abs(v - r) for v in rs) > 0.05:
        return 0.0, "TP atteint non retrouve"
    return lu, None


def ic_jours(L, z=1.96):
    par = {}
    for t in L:
        par.setdefault(t["jour"], []).append(t["v"])
    n = len(L)
    m = sum(t["v"] for t in L) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par.values())) / n
    return m, m - z * se, m + z * se


def ligne(nom, L):
    if not L:
        return f"  {nom:<22} aucun signal"
    v = [t["v"] for t in L]
    g = [a for a in v if a > 0.05]
    p = [a for a in v if a < -0.05]
    pf = sum(g) / -sum(p) if p else float("inf")
    return f"  {nom:<22}{len(L):>5} sig. | gagn. {100 * len(g) / len(L):>3.0f} % | R total {sum(v):>+7.1f} | R/signal {statistics.fmean(v):>+5.2f} | facteur de profit {pf:>4.2f}"


def main(argv):
    argv = list(argv)
    canal, depuis = "coin trader", None
    if "--canal" in argv:
        i = argv.index("--canal")
        canal = argv[i + 1].lower()
        del argv[i:i + 2]
    if "--depuis" in argv:
        i = argv.index("--depuis")
        depuis = datetime.strptime(argv[i + 1], "%d/%m/%Y")
        del argv[i:i + 2]
    clos = charger(canal, depuis)
    if not clos:
        print("Aucun signal clos.")
        return 0
    exclus = []
    for x in clos:
        x["v"], raison = verifie(x)
        if raison:
            exclus.append((x, raison))
    clos.sort(key=lambda t: t["t"])
    n = len(clos)
    v = [t["v"] for t in clos]
    g = [a for a in v if a > 0.05]
    p = [a for a in v if a < -0.05]
    m, lo, hi = ic_jours(clos)
    print(f"Canal « {canal} » : {n} signaux clos du {clos[0]['t']:%d/%m/%Y} au {clos[-1]['t']:%d/%m/%Y} ; {len(exclus)} gagnants non verifies COMPTES A ZERO (liste plus bas)")
    print(f"\nR REEL MINIMUM {sum(v):+.1f} R | R moyen par signal {m:+.3f} [IC 95 % par jour : {lo:+.3f} ; {hi:+.3f}]")
    if g and p:
        print(f"gagnants {100 * len(g) / n:.0f} % ({len(g)}) | gain moyen {statistics.fmean(g):+.2f} R | perte moyenne {statistics.fmean(p):+.2f} R ({len(p)}) | facteur de profit {sum(g) / -sum(p):.2f}")
    cur = pire_s = 0
    cum = pic = creux = 0.0
    for a in v:
        cur = cur + 1 if a < -0.05 else (0 if a > 0.05 else cur)
        pire_s = max(pire_s, cur)
        cum += a
        pic = max(pic, cum)
        creux = max(creux, pic - cum)
    print(f"plus longue serie de pertes : {pire_s} | pire creux : -{creux:.1f} R (soit environ -{creux:.0f} % du capital a 1 % de risque par signal)")
    print("\nPar mois :")
    mois = {}
    for t in clos:
        mois.setdefault(t["t"].strftime("%Y-%m"), []).append(t)
    for k in sorted(mois):
        print(ligne(k, mois[k]))
    print("\nPeriodes recentes :")
    fin = clos[-1]["t"]
    for jours in (30, 90):
        print(ligne(f"{jours} derniers jours", [t for t in clos if t["t"] >= fin - timedelta(days=jours)]))
    if exclus:
        tot = sum((x["lu"] or 0) for x, _ in exclus if x["lu"] is not None and abs(x["lu"]) < 50)
        print(f"\n{len(exclus)} gagnants comptes a zero (a verifier sur Telegram ; leur % lu, s'il etait exact, ajouterait {tot:+.1f} R) :")
        for x, raison in sorted(exclus, key=lambda z: -abs(z[0]["lu"] or 0))[:30]:
            print(f"  id {x['message_id']:>7} {x['date'][:16]} {x['sens']:<5} R ecrit {x['r_ecrit']:+.2f} | % lu {x['lu'] if x['lu'] is not None else float('nan'):+.2f} | {raison}")
    print("\nLecture : c'est un MINIMUM prudent. Si l'IC contient 0, on ne peut pas dire que l'esperance est positive. Theorique, hors frais, passe non garanti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
