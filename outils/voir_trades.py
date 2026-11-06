# -*- coding: utf-8 -*-
r"""Que montrait le marche au moment de chaque trade ? (lecture seule, aucun ordre, rien n'est modifie)

Pour les trades ouverts par le bot dans une fenetre de temps (heure de ton PC), affiche pour chacun :
  * le trade : heure, type, sens, entree, stop, objectif, distance du stop ;
  * la tendance de M1 / M5 / M15 / H1 JUSTE AVANT l'entree (meme definition que analyse_tendance_courte.py : cloture au-dessus / en dessous de la
    moyenne exponentielle 20, qui monte / descend), et si elle va AVEC ou CONTRE le sens du trade ;
  * ce que le prix avait fait dans les 15, 30 et 60 minutes d'avant (en dollars) ;
  * ce qui s'est passe ensuite sur les bougies M1 de MetaTrader : stop ou objectif touche en premier, et apres combien de minutes, plus le pire
    et le meilleur point atteints pendant 60 minutes. C'est une SIMULATION a partir des vrais niveaux du trade (stop et objectif lus dans
    trades_bot.csv) ; elle peut differer du resultat reel (glissement, gestion en cours de trade, sortie anticipee).
Necessite MetaTrader 5 ouvert avec l'historique M1 des derniers jours, et analyse_tendance_courte.py / plan_du_jour.py / rejeu_keltner.py dans le dossier.

Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe voir_trades.py "05/11/2026 18:00" "06/11/2026 03:00"     fenetre debut / fin (fin facultative : maintenant)
  .\.venv\Scripts\python.exe voir_trades.py "05/11/2026 18:00" --decalage 1             decalage heure du serveur MetaTrader - PC (1 h chez toi)"""
import bisect
import csv
import sys
from calendar import timegm
from datetime import datetime, timedelta

try:
    import analyse_tendance_courte as atc
except ImportError:
    print("Place ce script a cote de analyse_tendance_courte.py, plan_du_jour.py et rejeu_keltner.py (dossier gimaly).")
    raise SystemExit(1)

rk, pj = atc.rk, atc.pj
NOMS = {1: "haussiere", -1: "baissiere", 0: "mixte"}


def lire_trades(debut, fin):
    if not rk.FICHIER.exists():
        return []
    with open(rk.FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    out = []
    for l in lignes:
        if (l.get("resultat") or "").strip() != "ouvert":
            continue
        try:
            t = datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
            pe, sl, tp = (float(str(l[k]).replace(",", ".")) for k in ("pe", "sl", "tp1"))
        except (ValueError, KeyError, TypeError):
            continue
        if debut <= t <= fin and (l.get("sens") or "").strip() in ("achat", "vente"):
            out.append((t, (l.get("genre") or "").strip(), l["sens"].strip(), pe, sl, tp))
    return out


def epoch_serveur(t_pc, dec):
    """Heure du PC -> « epoch » des bougies MetaTrader (heure du serveur lue comme du temps universel : timegm, PAS timestamp())."""
    return timegm((t_pc + timedelta(hours=dec)).timetuple())


def calibrer(barres, trades, t_list, force):
    """Decalage serveur - PC retenu : celui pour lequel le prix des bougies colle le mieux au prix d'entree reel des trades."""
    if force is not None:
        return force, None
    meilleur = None
    for dec in (-1, 0, 1, 2, 3):
        ecarts = []
        for t, genre, sens, pe, sl, tp in trades:
            i = bisect.bisect_right(t_list, epoch_serveur(t, dec)) - 1
            if i >= 0:
                ecarts.append(abs(barres[i][4] - pe))
        if ecarts:
            m = sum(ecarts) / len(ecarts)
            if meilleur is None or m < meilleur[1]:
                meilleur = (dec, m)
    return meilleur[0], meilleur[1]


def simuler(barres, i, sens, pe, sl, tp, minutes=360):
    achat = sens == "achat"
    t0 = barres[i][0]
    pire = meilleur = 0.0
    for j in range(i + 1, len(barres)):
        t, o, h, b, c = barres[j]
        mn = (t - t0) / 60
        if mn > minutes:
            break
        if mn <= 60:
            pire = min(pire, (b - pe) if achat else (pe - h))
            meilleur = max(meilleur, (h - pe) if achat else (pe - b))
        stop = (b <= sl) if achat else (h >= sl)
        cible = (h >= tp) if achat else (b <= tp)
        if stop:
            return ("STOP touche", mn, pire, meilleur)
        if cible:
            return ("OBJECTIF touche", mn, pire, meilleur)
    return ("ni stop ni objectif", None, pire, meilleur)


def main(argv):
    argv = list(argv)
    dec_force = None
    if "--decalage" in argv:
        i = argv.index("--decalage")
        dec_force = float(argv[i + 1].replace(",", "."))
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        return 1
    try:
        debut = datetime.strptime(argv[0], "%d/%m/%Y %H:%M")
        fin = datetime.strptime(argv[1], "%d/%m/%Y %H:%M") if len(argv) > 1 else datetime.now() + timedelta(hours=1)
    except ValueError:
        print('Dates attendues entre guillemets : "jj/mm/aaaa hh:mm"')
        return 1
    trades = lire_trades(debut, fin)
    if not trades:
        print("Aucun trade ouvert par le bot dans cette fenetre (heure du PC).")
        return 0
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(rk.SYMBOLE, True)
        barres = rk.charger(mt5, debut - timedelta(days=6))
    finally:
        mt5.shutdown()
    if len(barres) < 3000:
        print("Historique M1 insuffisant : charge l'historique M1 de l'or dans MetaTrader puis relance.")
        return 0
    unites = atc.preparer(barres)
    m5 = unites["M5"]
    atr5 = pj.ema_atr(m5[0], n_ema=20)[1]
    t_srv_list = [x[0] for x in barres]
    dec, ecart_prix = calibrer(barres, trades, t_srv_list, dec_force)
    print(f"{len(trades)} trade(s) du {debut:%d/%m/%Y %H:%M} au {fin:%d/%m/%Y %H:%M} (heure du PC) | decalage serveur - PC : {dec:g} h"
          + (f" (choisi car les prix des bougies collent aux prix d'entree reels : ecart moyen {ecart_prix:.2f} $)" if ecart_prix is not None else " (impose)"))
    if ecart_prix is not None and ecart_prix > 3:
        print("  ATTENTION : meme avec le meilleur decalage, les prix des bougies s'ecartent de plus de 3 $ des prix d'entree : resultats non fiables.")
    for t, genre, sens, pe, sl, tp in trades:
        t_srv = epoch_serveur(t, dec)
        i = bisect.bisect_right(t_srv_list, t_srv) - 1
        if i < 100 or t_srv - barres[i][0] > 180:
            print(f"\n{t:%d/%m %H:%M:%S} {genre} {sens} : pas de bougie M1 correspondante (decalage ou historique ?)")
            continue
        dist = abs(pe - sl)
        if abs(barres[i][4] - pe) > 3:
            print(f"  (info) prix de la bougie M1 a l'entree : {barres[i][4]:.2f} contre {pe:.2f} dans le journal")
        print(f"\n=== {t:%d/%m/%Y %H:%M:%S}  {genre}  {sens.upper()}  entree {pe:.2f}  stop {sl:.2f} ({dist:.2f} $)  objectif {tp:.2f} ===")
        etats = []
        for nom, _ in atc.UNITES:
            tend = atc.etat(unites, nom, i, t_srv)
            r = atc.rel(tend, sens)
            etats.append(f"{nom} {NOMS.get(tend, '?')} ({r.upper() if r else '?'})")
        print("  Tendance juste avant : " + " | ".join(etats))
        c = barres[i][4]
        k5 = bisect.bisect_right(m5[2], t_srv - 300) - 1
        a5 = atr5[k5] if k5 >= 0 else None
        mouv = []
        for mn in (15, 30, 60):
            c0 = barres[i - mn][4]
            mouv.append(f"{mn} min : {c - c0:+.1f} $")
        print("  Mouvement avant l'entree : " + " | ".join(mouv) + (f"   (ATR M5 = {a5:.1f} $)" if a5 else ""))
        sens_mv = c - barres[i - 30][4]
        if (sens == "achat" and sens_mv < 0) or (sens == "vente" and sens_mv > 0):
            print("  -> le bot est entre CONTRE le mouvement des 30 dernieres minutes (rebond).")
        else:
            print("  -> le bot est entre DANS le sens du mouvement des 30 dernieres minutes.")
        res, mn, pire, meilleur = simuler(barres, i, sens, pe, sl, tp)
        quand = f" apres {mn:.0f} min" if mn is not None else ""
        print(f"  Simulation : {res}{quand} | dans l'heure : pire point {pire:+.1f} $ ({pire / dist:+.2f} R), meilleur point {meilleur:+.1f} $ ({meilleur / dist:+.2f} R)")
    print("\nLecture : c'est un cas par cas. Deux trades ne prouvent rien ; ils servent a voir si le M5 / M15 disaient quelque chose d'evident.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
