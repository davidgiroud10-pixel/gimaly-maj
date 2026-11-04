# -*- coding: utf-8 -*-
r"""Point mort precoce et trailing stop : que serait devenu le R de tes trades PASSES ? (LECTURE SEULE : le bot n'est pas modifie.)

Usage (depuis C:\Users\<toi>\gimaly, MetaTrader 5 ouvert) :
  .\.venv\Scripts\python.exe analyse_be_trailing.py --jours 14
  .\.venv\Scripts\python.exe analyse_be_trailing.py --jours 30 --source fantomes --genre scalp_keltner_large
Options : --source reels|fantomes|tous (defaut tous) ; --genre NOM ; --duree 240 (minutes, horizon de chaque trade) ;
          --decalage 2 (heures UTC -> heure serveur MT5, seulement si le programme le demande).

Chaque trade (reels : trades_bot.csv, objectif = TP1 ; fantomes : trades_refuses.csv) est rejoue sur les bougies M1 de MT5 avec le meme
stop et le meme objectif, puis avec des variantes : point mort a X R, trailing stop, trailing sans objectif. Tout est en R (1 R = distance
entree-stop). Hypotheses PRUDENTES : quand stop et objectif (ou nouveau stop) tombent dans la meme minute, le stop passe d'abord ; une vente
se rachete a l'ask (haut + spread) ; pas de glissement ni de commission. Sortie a la cloture de la derniere bougie a l'horizon.
ATTENTION : echantillon court, trades correles (plusieurs signaux le meme jour), 10 variantes comparees = risque de trouver du hasard.
Un ecart plus petit que l'erreur type n'est PAS significatif ; la 2e moitie de la periode sert de controle (une variante qui ne tient
pas sur les deux moities n'est pas fiable). Valider sur des jours NON vus avant toute activation."""
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))

VERROU = 0.2                  # le point mort verrouille +0,2 $ (couvre le spread)
FICHIER_REFUSES = Path.home() / "GIMALY" / "trading" / "trades_refuses.csv"
VARIANTES = [
    {"nom": "actuel (stop/objectif)"},
    {"nom": "point mort a 0,5 R", "be": 0.5},
    {"nom": "point mort a 0,8 R", "be": 0.8},
    {"nom": "point mort a 1,0 R", "be": 1.0},
    {"nom": "trailing 0,5 R des 0,8 R", "trail": (0.8, 0.5)},
    {"nom": "trailing 0,5 R des 1,0 R", "trail": (1.0, 0.5)},
    {"nom": "trailing 1,0 R des 1,0 R", "trail": (1.0, 1.0)},
    {"nom": "trailing 1,0 R des 1,0 R, SANS objectif", "trail": (1.0, 1.0), "sans_tp": True},
    {"nom": "trailing 1,0 R des 1,5 R, SANS objectif", "trail": (1.5, 1.0), "sans_tp": True},
    {"nom": "trailing 1,0 R des 2,0 R, SANS objectif", "trail": (2.0, 1.0), "sans_tp": True},
]


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return None


def rejouer(achat, pe, sl, tp, bougies, pt, v, verrou=VERROU):
    """R d'un trade rejoue avec la variante v ; None si non rejouable (stop nul, objectif du mauvais cote, aucune bougie)."""
    risque = abs(pe - sl)
    if risque <= 0 or not len(bougies):
        return None
    s = 1 if achat else -1
    gain_tp = None if v.get("sans_tp") else (tp - pe) * s
    if gain_tp is not None and gain_tp <= 0:
        return None
    stop, meilleur = sl, pe
    mieux = max if achat else min
    dernier = None
    for r in bougies:
        haut, bas, sp = float(r["high"]), float(r["low"]), float(r["spread"]) * pt
        adverse = bas if achat else haut + sp
        favorable = haut if achat else bas
        dernier = r
        if (adverse <= stop) if achat else (adverse >= stop):
            return (stop - pe) * s / risque
        if gain_tp is not None and ((favorable >= tp) if achat else (favorable <= tp)):
            return gain_tp / risque
        meilleur = mieux(meilleur, favorable)
        mfe = (meilleur - pe) * s
        nouveau = stop
        if v.get("be") is not None and mfe >= v["be"] * risque:
            nouveau = mieux(nouveau, pe + s * verrou)
        if v.get("trail") and mfe >= v["trail"][0] * risque:
            nouveau = mieux(nouveau, meilleur - s * v["trail"][1] * risque)
        if nouveau != stop:
            stop = nouveau
            if (adverse <= stop) if achat else (adverse >= stop):
                return (stop - pe) * s / risque          # prudent : meme minute, le stop passe d'abord
    sortie = float(dernier["close"]) + (0.0 if achat else float(dernier["spread"]) * pt)
    return (sortie - pe) * s / risque


def stats(rs):
    n = len(rs)
    if n == 0:
        return n, 0.0, 0.0, 0.0, 0.0
    moy = sum(rs) / n
    var = sum((x - moy) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    return n, 100.0 * sum(1 for x in rs if x >= 0.25) / n, moy, (var / n) ** 0.5, sum(rs)


def tableau(titre, trades, rates, pt, decalage, duree):
    """trades : liste triee par date de {t, achat, pe, sl, tp, genre}."""
    donnees = []
    for tr in trades:
        a = tr["t"].timestamp() + decalage
        a = (a // 60) * 60 + 60                       # on commence APRES la minute d'entree
        b = a + duree * 60
        bougies = [r for r in rates if a <= float(r["time"]) <= b]
        if bougies:
            donnees.append((tr["t"], tr["achat"], tr["pe"], tr["sl"], tr["tp"], bougies, tr.get("r_reel")))
    print(f"\n=== {titre} : {len(donnees)} trade(s) rejoues sur {len(trades)} (horizon {duree} min) ===")
    if len(donnees) < 8:
        print("trop peu de trades pour comparer quoi que ce soit.")
        return
    calibrage(donnees, pt)
    moitie = len(donnees) // 2
    print(f"{'variante':<42}{'n':>4}{'R>=0,25':>9}{'R moyen':>9}{'+/-':>7}{'R total':>9}   {'1re moitie':>10}{'2e moitie':>10}")
    for v in VARIANTES:
        res = []
        for t, achat, pe, sl, tp, bougies, _ref in donnees:
            res.append(rejouer(achat, pe, sl, tp, bougies, pt, v))
        ok = [(i, r) for i, r in enumerate(res) if r is not None]
        n, pct, moy, se, tot = stats([r for _, r in ok])
        m1 = [r for i, r in ok if i < moitie]
        m2 = [r for i, r in ok if i >= moitie]
        a1 = sum(m1) / len(m1) if m1 else 0.0
        a2 = sum(m2) / len(m2) if m2 else 0.0
        print(f"{v['nom']:<42}{n:>4}{pct:>8.0f}%{moy:>+9.3f}{se:>7.3f}{tot:>+9.1f}   {a1:>+10.3f}{a2:>+10.3f}")


def calibrage(donnees, pt):
    """Le rejeu 'actuel' reproduit-il ce qui s'est VRAIMENT passe ? Si non, les variantes ne sont pas fiables."""
    paires = []
    for t, achat, pe, sl, tp, bougies, ref in donnees:
        r = rejouer(achat, pe, sl, tp, bougies, pt, VARIANTES[0])
        if r is not None and ref is not None:
            paires.append((r, ref))
    if not paires:
        print("calibrage : aucun R enregistre a comparer.")
        return
    moy_rejeu = sum(a for a, _ in paires) / len(paires)
    moy_reel = sum(b for _, b in paires) / len(paires)
    classe = lambda x: "gain" if x >= 0.25 else ("perte" if x < 0 else "neutre")
    memes = sum(1 for a, b in paires if classe(a) == classe(b))
    print(f"CALIBRAGE sur {len(paires)} trades : R enregistre moyen {moy_reel:+.3f} | rejeu 'actuel' {moy_rejeu:+.3f} | "
          f"meme verdict (gain/perte/neutre) pour {100.0 * memes / len(paires):.0f} % des trades")
    if abs(moy_rejeu - moy_reel) > 0.15 or memes / len(paires) < 0.8:
        print("  -> le rejeu s'ecarte de la realite : lis les lignes ci-dessous comme des ordres de grandeur, PAS comme des resultats.")


def lire_reels(limite, genre):
    import diag_tp
    sortie = []
    for tr in diag_tp.lire_trades():
        l = tr["ligne"]
        pe, sl, tp = nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp1"))
        if tr["ouverture"] < limite or None in (pe, sl, tp) or pe == sl:
            continue
        if genre and (l.get("genre") or "").strip() != genre:
            continue
        sortie.append({"t": tr["ouverture"], "achat": l["sens"] == "achat", "pe": pe, "sl": sl, "tp": tp,
                       "genre": l.get("genre"), "r_reel": nombre(l.get("R"))})
    return sorted(sortie, key=lambda x: x["t"])


def lire_fantomes(limite, genre):
    if not FICHIER_REFUSES.exists():
        return []
    sortie = []
    with open(FICHIER_REFUSES, encoding="utf-8-sig", newline="") as f:
        for l in csv.DictReader(f, delimiter=";"):
            try:
                t = dt.datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
            except (ValueError, KeyError, AttributeError):
                continue
            pe, sl, tp = nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp"))
            if t < limite or None in (pe, sl, tp) or pe == sl:
                continue
            if genre and (l.get("genre") or "").strip() != genre:
                continue
            sortie.append({"t": t, "achat": l.get("sens") == "achat", "pe": pe, "sl": sl, "tp": tp, "genre": l.get("genre"),
                           "r_reel": nombre(l.get("R"))})
    return sorted(sortie, key=lambda x: x["t"])


def main():
    args = sys.argv[1:]

    def option(nom, defaut, cast=str):
        if nom in args:
            i = args.index(nom)
            val = cast(args[i + 1])
            del args[i:i + 2]
            return val
        return defaut

    if any(a in ("-h", "--help") for a in args):
        sys.exit(__doc__)
    jours = option("--jours", 14, int)
    source = option("--source", "tous")
    genre = option("--genre", None)
    duree = option("--duree", 240, int)
    force = option("--decalage", None, float)
    limite = dt.datetime.now() - dt.timedelta(days=jours)
    jeux = []
    if source in ("reels", "tous"):
        jeux.append(("trades REELS (objectif = TP1)", lire_reels(limite, genre)))
    if source in ("fantomes", "tous"):
        jeux.append(("trades FANTOMES (refuses par le bot)", lire_fantomes(limite, genre)))
    jeux = [(t, x) for t, x in jeux if x]
    if not jeux:
        sys.exit("aucun trade sur cette periode")

    import diag_tp
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
        debut = min(x[0]["t"] for _, x in jeux).timestamp() + decalage - 3600
        fin = max(x[-1]["t"] for _, x in jeux).timestamp() + decalage + (duree + 60) * 60
        rates = diag_tp.charger_bougies(mt5, sym, debut, fin)
        if rates is None:
            sys.exit("MT5 ne fournit pas les bougies M1 de cette periode : ouvre un graphique " + sym + " en M1 et fais-le defiler "
                     "vers la gauche jusqu'au debut de la periode, puis relance.")
        print(f"{sym} : {len(rates)} bougies M1 chargees, {jours} jours" + (f", genre {genre}" if genre else ""))
        for titre, trades in jeux:
            tableau(titre, trades, rates, pt, decalage, duree)
        print("\nLecture : R moyen = gain moyen par trade en multiples du risque ; '+/-' = erreur type (ordre de grandeur du hasard). "
              "Compare chaque ligne a 'actuel' ET verifie que les deux moities vont dans le meme sens. Ne change rien au bot sur ce seul tableau.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
