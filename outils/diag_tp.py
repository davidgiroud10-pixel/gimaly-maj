# -*- coding: utf-8 -*-
"""Diagnostic des TP rates : sur tes trades passes, le prix a-t-il VRAIMENT touche le TP, et a combien pres ?

Usage (depuis C:\\Users\\<toi>\\gimaly, MetaTrader 5 ouvert) :
  .\\.venv\\Scripts\\python.exe diag_tp.py --jours 7            tous les trades des 7 derniers jours dont le TP1 n'a pas ete atteint
  .\\.venv\\Scripts\\python.exe diag_tp.py "28/10/2026 11:56"    un trade precis (date et heure d'ouverture)
  .\\.venv\\Scripts\\python.exe diag_tp.py --simuler 7        et si le TP1 etait pris X cents plus tot ? (tous les trades, indicatif)

Pour chaque trade, il lit les bougies M1 de MT5 (prix bid, comme le graphique) entre l'ouverture et la
fermeture et dit : meilleur prix atteint, distance au TP1, et pour une VENTE la meme mesure a l'ask (prix
reel de fermeture d'une vente). Rien n'est modifie. Les heures sont celles de ton PC.
Option : --decalage 2   (heures entre UTC et l'heure du serveur MT5, seulement si le programme le demande).
"""
import csv
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return None


def horodatage(date, heure):
    return dt.datetime.strptime(f"{date.strip()} {heure.strip()}", "%d/%m/%Y %H:%M:%S")


def lire_trades():
    """Apparie chaque ligne de resultat avec la ligne 'ouvert' correspondante."""
    with open(FICHIER, encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    ouverts, trades = [], []
    for l in lignes:
        try:
            t = horodatage(l["date"], l["heure"])
        except (ValueError, KeyError):
            continue
        cle = (l.get("sens"), nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp1")))
        if (l.get("resultat") or "").strip().lower() == "ouvert":
            ouverts.append((cle, t, l))
            continue
        for i in range(len(ouverts) - 1, -1, -1):
            if ouverts[i][0] == cle and ouverts[i][1] <= t:
                _, t0, l0 = ouverts.pop(i)
                trades.append({"ouverture": t0, "fermeture": t, "ligne": l})
                break
    return trades


def decalage_serveur(mt5, sym, force):
    """Heures entre UTC et le temps du serveur MT5 (deduit du dernier tick, ou impose avec --decalage)."""
    if force is not None:
        return force * 3600
    tick = mt5.symbol_info_tick(sym)
    ecart = float(tick.time) - time.time()
    heures = round(ecart / 3600)
    if abs(ecart - heures * 3600) > 600 or abs(heures) > 12:
        sys.exit("Impossible de deduire l'heure du serveur MT5 (marche ferme ?). Relance avec --decalage 2 "
                 "(ou 3 en heure d'ete) : c'est l'ecart en heures entre UTC et l'heure affichee par MT5.")
    return heures * 3600


def charger_bougies(mt5, sym, debut_srv, fin_srv):
    """Toutes les bougies M1 entre deux heures SERVEUR (epoch). MT5 telecharge l'historique a la demande :
    la premiere reponse peut etre vide, on redemande quelques fois."""
    # MT5 compte les bougies en 'heure serveur lue comme UTC' : on lui passe donc directement l'heure serveur
    d0 = dt.datetime.fromtimestamp(debut_srv, dt.timezone.utc)
    d1 = dt.datetime.fromtimestamp(fin_srv, dt.timezone.utc)
    for essai in range(5):
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, d0, d1)
        if rates is not None and len(rates) > 0:
            return rates
        time.sleep(1.5)
    return None


def analyser(mt5, sym, pt, decalage, trade, rates):
    ligne = trade["ligne"]
    achat = ligne["sens"] == "achat"
    tp = nombre(ligne["tp1"])
    a = trade["ouverture"].timestamp() + decalage          # heure locale du PC -> heure du serveur
    b = trade["fermeture"].timestamp() + decalage + 60
    if rates is None:
        return None
    fen = [r for r in rates if a - 60 <= float(r["time"]) <= b]
    if not fen:
        return None
    sp_max = max(float(r["spread"]) for r in fen) * pt
    if achat:
        meilleur = max(float(r["high"]) for r in fen)
        manque = tp - meilleur
        verdict = "TOUCHE au bid (a verifier)" if manque <= 0 else f"manque {manque:.2f} $"
        return meilleur, manque, None, sp_max, verdict
    meilleur = min(float(r["low"]) for r in fen)
    meilleur_ask = min(float(r["low"]) + float(r["spread"]) * pt for r in fen)
    manque, manque_ask = meilleur - tp, meilleur_ask - tp
    if manque_ask <= 0:
        verdict = "TOUCHE (bid et ask)"
    elif manque <= 0:
        verdict = f"SPREAD : touche au graphique, rate de {manque_ask:.2f} $ a l'ask"
    else:
        verdict = f"manque {manque:.2f} $"
    return meilleur, manque, manque_ask, sp_max, verdict


MARGES = [0.0, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5]
FRACTIONS_BE = [0.5, 0.6, 0.7, 0.8, 0.9]      # part du chemin vers le TP1 a partir de laquelle le stop passe au point mort
DECALAGE_BE = 0.2                              # le point mort verrouille +0,2 $ (couvre le spread)


def jouer(donnees, pt, marge=0.0, frac_be=None):
    """Rejoue les trades sur les bougies M1. Renvoie (n_tp, n_sl, n_be, n_neutre, somme_R, liste des R de TP).
    Ordre dans une meme minute : inconnu, hypothese PRUDENTE (SL, puis point mort, puis TP)."""
    n_tp = n_sl = n_be = n_ne = 0
    somme_r, r1s = 0.0, []
    for achat, pe, sl, tp, bougies in donnees:
        tpm = tp - marge if achat else tp + marge
        risque = abs(pe - sl)
        gain = (tpm - pe) if achat else (pe - tpm)
        if gain <= 0:
            n_ne += 1
            continue
        declencheur = (pe + frac_be * gain) if (frac_be and achat) else (pe - frac_be * gain) if frac_be else None
        niveau_be = (pe + DECALAGE_BE) if achat else (pe - DECALAGE_BE)
        arme, issue = False, None
        for r in bougies:
            haut, bas, sp = float(r["high"]), float(r["low"]), float(r["spread"]) * pt
            sl_touche = bas <= sl if achat else haut + sp >= sl
            if sl_touche and not arme:
                issue = "sl"
                break
            if arme:
                be_touche = bas <= niveau_be if achat else haut + sp >= niveau_be
                if be_touche:
                    issue = "be"
                    break
            elif declencheur is not None and (haut >= declencheur if achat else bas <= declencheur):
                arme = True
                be_touche = bas <= niveau_be if achat else haut + sp >= niveau_be
                if be_touche:                    # declenchement et retour dans la meme minute : prudent
                    issue = "be"
                    break
            if (haut >= tpm) if achat else (bas <= tpm):
                issue = "tp"
                break
        if issue == "tp":
            n_tp += 1
            somme_r += gain / risque
            r1s.append(gain / risque)
        elif issue == "sl":
            n_sl += 1
            somme_r -= 1.0
        elif issue == "be":
            n_be += 1
            somme_r += DECALAGE_BE / risque
        else:
            n_ne += 1
    return n_tp, n_sl, n_be, n_ne, somme_r, r1s


def simuler(trades, rates, pt, decalage):
    """Rejoue chaque trade sur les bougies M1 : (1) avec un TP1 avance de quelques cents, (2) avec un stop
    qui passe au point mort avant le TP1. Simplifie : TP1 contre SL seulement (ni partiels, ni TP2)."""
    donnees = []
    for tr in trades:
        l = tr["ligne"]
        pe, sl, tp = nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp1"))
        if None in (pe, sl, tp) or pe == sl:
            continue
        achat = l["sens"] == "achat"
        a = tr["ouverture"].timestamp() + decalage
        a = (a // 60) * 60 + 60                          # on commence APRES la minute d'entree
        b = tr["fermeture"].timestamp() + decalage + 60
        bougies = [r for r in rates if a <= float(r["time"]) <= b]
        donnees.append((achat, pe, sl, tp, bougies))
    print(f"{len(donnees)} trades rejoues.\n")

    def ligne(titre, res):
        n_tp, n_sl, n_be, n_ne, somme, r1s = res
        decides = n_tp + n_sl + n_be
        esp = somme / decides if decides else 0.0
        r1 = sum(r1s) / len(r1s) if r1s else 0.0
        pct = 100.0 * n_tp / decides if decides else 0.0
        print(f"{titre:<24}{n_tp:>8}{n_sl:>6}{n_be:>6}{n_ne:>8}{pct:>7.0f}%{r1:>9.2f}{esp:>+11.3f}")

    entete = f"{'':<24}{'TP1':>8}{'SL':>6}{'BE':>6}{'neutre':>8}{'% TP1':>8}{'R du TP1':>9}{'esperance':>11}"
    print("1) TP1 pris plus tot (le prix demande est avance de la marge)\n" + entete)
    for m in MARGES:
        ligne(f"marge {m:.1f} $", jouer(donnees, pt, marge=m))
    print("\n2) Stop au point mort avant le TP1 (des que le prix a parcouru X % du chemin vers le TP1 ; "
          f"le stop passe a l'entree +{DECALAGE_BE:.1f} $)\n" + entete)
    ligne("sans point mort", jouer(donnees, pt))
    for f in FRACTIONS_BE:
        ligne(f"point mort a {int(f * 100)} %", jouer(donnees, pt, frac_be=f))
    print("\nesperance = R moyen par trade decide (TP1 = +R du TP1, SL = -1, BE = petit gain). Echantillon court : tendance, "
          "pas preuve. Hypothese prudente quand SL et point mort/TP tombent dans la meme minute.")


def main():
    args = sys.argv[1:]
    force = None
    if "--decalage" in args:
        i = args.index("--decalage")
        force = float(args[i + 1])
        del args[i:i + 2]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if not FICHIER.exists():
        sys.exit(f"{FICHIER} introuvable")
    trades = lire_trades()
    if args[0] == "--simuler":
        n = int(args[1]) if len(args) > 1 else 7
        limite = dt.datetime.now() - dt.timedelta(days=n)
        choisis = [t for t in trades if t["ouverture"] >= limite]
    elif args[0] == "--jours":
        n = int(args[1]) if len(args) > 1 else 7
        limite = dt.datetime.now() - dt.timedelta(days=n)
        choisis = [t for t in trades if t["ouverture"] >= limite and (t["ligne"].get("tp1_atteint") or "").strip().lower() != "oui"]
    else:
        voulu = args[0].strip()
        choisis = [t for t in trades if t["ouverture"].strftime("%d/%m/%Y %H:%M").startswith(voulu[:16])]
        if not choisis:
            sys.exit(f"aucun trade termine ouvert a '{voulu}' dans trades_bot.csv")
    if not choisis:
        sys.exit("aucun trade a analyser sur cette periode")

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
        decalage = decalage_serveur(mt5, sym, force)
        print(f"\n{sym} : {len(choisis)} trade(s) analyse(s) (bougies M1, prix bid ; ask approxime par bid + spread de la bougie)\n")
        debut = min(t["ouverture"] for t in choisis).timestamp() + decalage - 4 * 3600   # marge : on filtre ensuite
        fin = max(t["fermeture"] for t in choisis).timestamp() + decalage + 4 * 3600
        rates = charger_bougies(mt5, sym, debut, fin)
        if rates is None:
            sys.exit("MT5 ne fournit pas les bougies M1 de cette periode. Dans MT5 : ouvre un graphique " + sym +
                     " en M1 et fais-le defiler vers la gauche jusqu'au debut de la periode (cela telecharge l'historique), "
                     "puis relance.")
        print(f"{len(rates)} bougies M1 chargees.\n")
        if args[0] == "--simuler":
            simuler(choisis, rates, pt, decalage)
            return
        print(f"{'ouverture':<17}{'sens':<7}{'TP1':>9}{'meilleur':>10}{'manque':>8}{'manq.ask':>9}{'spr.max':>8}  {'resultat':<19}diagnostic")
        resume = {"spread": 0, "touche": 0, "manque": 0, "inconnu": 0}
        for t in choisis:
            r = analyser(mt5, sym, pt, decalage, t, rates)
            l = t["ligne"]
            tete = f"{t['ouverture']:%d/%m %H:%M:%S}  {l['sens']:<7}{nombre(l['tp1']):>9.2f}"
            if r is None:
                resume["inconnu"] += 1
                print(f"{tete}  (aucune bougie M1 entre ouverture et fermeture : historique incomplet ?)")
                continue
            meilleur, manque, manque_ask, sp, verdict = r
            if verdict.startswith("SPREAD"):
                resume["spread"] += 1
            elif verdict.startswith("TOUCHE"):
                resume["touche"] += 1
            else:
                resume["manque"] += 1
            ma = f"{manque_ask:>9.2f}" if manque_ask is not None else f"{'':>9}"
            print(f"{tete}{meilleur:>10.2f}{manque:>8.2f}{ma}{sp:>8.2f}  {(l.get('resultat') or ''):<19}{verdict}")
        print(f"\nBilan : {resume['spread']} rate(s) a cause du spread ; {resume['touche']} trade(s) ou le TP1 a ete touche "
              f"mais pas pris ; {resume['manque']} ou le prix n'est jamais arrive au TP1 ; {resume['inconnu']} sans donnees.")
        print("manque = distance restante au TP1 (negatif ou 0 = atteint). Une vente se ferme a l'ask : manq.ask est la mesure reelle.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
