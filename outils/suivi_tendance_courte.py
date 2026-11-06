# -*- coding: utf-8 -*-
r"""SUIVI PRE-ENREGISTRE : les trades pris CONTRE la tendance court terme (M5 et M15) font-ils moins bien que les autres ? (lecture seule, aucun ordre)

Pourquoi : sur le rejeu de 4 062 signaux (analyse_tendance_courte.py), la tendance court terme n'a rien montre de mesurable (0 test sur 6 au seuil
de rigueur). Mais le sentiment « il se fait avoir par la tendance des grosses unites de temps » vient de trades REELS, donc on le suit sur les trades
reels du bot (resultat reel en R, trades_bot.csv), a partir de donnees qu'on n'avait pas regardees.

REGLE FIXEE D'AVANCE (a ne pas changer apres avoir vu le resultat) :
  Groupe « CONTRE » = trade pris quand la tendance M5 ET la tendance M15 vont toutes deux a l'inverse du sens du trade (meme definition que
  analyse_tendance_courte.py : cloture au-dessus/en dessous de la moyenne exponentielle 20 qui monte/descend, bougies fermees avant l'entree).
  Groupe « AUTRES » = tous les autres trades du bot (meme genre).
  Test unique : R reel par trade des AUTRES moins celui du groupe CONTRE. La regle « ne pas prendre un trade quand M5 et M15 sont contre » est
  consideree UTILE si cet ecart est d'au moins +0,10 R avec un p unilateral < 0,05 (bootstrap sur les jours), avec au moins 100 trades dans CHAQUE groupe.
  - moins de 100 trades dans un groupe : PAS ASSEZ DE DONNEES (on attend) ;
  - sinon UTILE ou NON CONFIRMEE selon la regle ci-dessus. Meme alors, on la teste d'abord en simulation avant de toucher au bot.
Le script donne aussi, a titre d'information (non utilise pour decider) : le score M1+M5+M15, et le resultat des trades « CONTRE » parmi ceux ou H1 va
dans le sens du trade (le cas que tu decris).
Ce script lit trades_bot.csv (une ligne « ouvert » a l'ouverture, une ligne de cloture avec le R reel ; si un trade a plusieurs lignes de cloture, seule la
premiere est comptee) et l'historique M1 de MetaTrader.
La date de depart fixee est le 06/11/2026 ; avec une autre date (--depuis 20/10/2026) le resultat est EXPLORATOIRE (ces trades ont deja ete vus).

Usage (dossier gimaly, MetaTrader 5 ouvert avec l'historique M1 charge) :
  .\.venv\Scripts\python.exe suivi_tendance_courte.py                      depuis le 06/11/2026
  .\.venv\Scripts\python.exe suivi_tendance_courte.py --depuis 20/10/2026  exploration sur ce qui a deja ete vu
  .\.venv\Scripts\python.exe suivi_tendance_courte.py --genre tous"""
import bisect
import csv
import statistics
import sys
from datetime import datetime, timedelta

try:
    import voir_trades as vt
except ImportError:
    print("Place ce script a cote de voir_trades.py, analyse_tendance_courte.py, plan_du_jour.py et rejeu_keltner.py (dossier gimaly).")
    raise SystemExit(1)

atc, rk = vt.atc, vt.rk
DEPART = "06/11/2026"
MIN_PAR_GROUPE, ECART_MIN, P_MAX = 100, 0.10, 0.05


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def trades_reels(depuis, genre):
    """[(heure_entree, genre, sens, pe, R reel)] : chaque ligne de cloture est rattachee a la derniere ligne « ouvert » de meme (genre, sens, pe, sl, tp1)."""
    with open(rk.FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    ouverts, out = {}, []
    for l in lignes:
        try:
            cle = ((l.get("genre") or "").strip(), (l.get("sens") or "").strip(), nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("tp1")))
            t = datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
        except (ValueError, KeyError, AttributeError):
            continue
        if cle[1] not in ("achat", "vente") or None in cle[2:]:
            continue
        etat = (l.get("resultat") or "").strip()
        if etat == "ouvert":
            ouverts[cle] = t
            continue
        r = nombre(l.get("R"))
        if r is None or cle not in ouverts or (genre != "tous" and cle[0] != genre):
            continue
        t0 = ouverts.pop(cle)
        if t0 >= depuis:
            out.append((t0, cle[0], cle[1], cle[2], r))
    return out


def distance_prix(barres, i, pe):
    t, o, h, b, c = barres[i]
    return 0.0 if b - 0.5 <= pe <= h + 0.5 else min(abs(pe - b), abs(pe - h))


def index_bougie(barres, t_list, t_pc, pe):
    """Indice de la bougie M1 et decalage (1 h ou 2 h selon les changements d'heure) pour lesquels le prix d'entree reel colle a la bougie."""
    meilleur = None
    for dec in (1, 2):
        i = bisect.bisect_right(t_list, vt.epoch_serveur(t_pc, dec)) - 1
        if i < 100:
            continue
        d = distance_prix(barres, i, pe)
        if meilleur is None or d < meilleur[0] - 1e-9:
            meilleur = (d, i, dec)
    return meilleur


def main(argv):
    argv = list(argv)
    genre, depuis_txt = "scalp_keltner_large", DEPART
    for opt in ("--genre", "--depuis"):
        if opt in argv:
            i = argv.index(opt)
            v = argv[i + 1]
            del argv[i:i + 2]
            if opt == "--genre":
                genre = v
            else:
                depuis_txt = v
    try:
        depuis = datetime.strptime(depuis_txt, "%d/%m/%Y")
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not rk.FICHIER.exists():
        print(f"{rk.FICHIER} introuvable.")
        return 1
    trades = trades_reels(depuis, genre)
    if not trades:
        print(f"Aucun trade termine depuis le {depuis_txt} ({genre}).")
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
        barres = rk.charger(mt5, min(t[0] for t in trades) - timedelta(days=6))
    finally:
        mt5.shutdown()
    if len(barres) < 3000:
        print("Historique M1 insuffisant : charge l'historique M1 de l'or dans MetaTrader puis relance.")
        return 0
    unites = atc.preparer(barres)
    t_list = [x[0] for x in barres]
    lignes, ecartes = [], 0
    for t, g, sens, pe, r in trades:
        m = index_bougie(barres, t_list, t, pe)
        if m is None or m[0] > 1.5:
            ecartes += 1
            continue
        _, i, dec = m
        t_srv = vt.epoch_serveur(t, dec)
        rels = {nom: atc.rel(atc.etat(unites, nom, i, t_srv), sens) for nom, _ in atc.UNITES}
        if None in rels.values():
            ecartes += 1
            continue
        score = sum(1 if rels[n] == "avec" else -1 if rels[n] == "contre" else 0 for n in ("M1", "M5", "M15"))
        lignes.append((t.date(), r, rels, score))
    expl = depuis_txt != DEPART
    print(f"{len(lignes)} trades termines depuis le {depuis_txt} ({genre}), {ecartes} ecartes (prix d'entree non retrouve dans les bougies)."
          + ("  EXPLORATOIRE : date differente de la date fixee, ces trades ont deja ete vus." if expl else ""))
    if not lignes:
        return 0
    jours = sorted({x[0] for x in lignes})
    milieu = jours[len(jours) // 2]
    contre = [(x[0], x[1]) for x in lignes if x[2]["M5"] == "contre" and x[2]["M15"] == "contre"]
    autres = [(x[0], x[1]) for x in lignes if not (x[2]["M5"] == "contre" and x[2]["M15"] == "contre")]
    print(f"\n  {'':<34}{'trades':>8}{'jours':>6}   R reel par trade (1re moitie / 2e moitie)")
    print(atc.ligne_groupe("tous les trades", [(x[0], x[1]) for x in lignes], milieu))
    print(atc.ligne_groupe("M5 ET M15 contre (CONTRE)", contre, milieu))
    print(atc.ligne_groupe("autres trades (AUTRES)", autres, milieu))
    e = atc.ecart(autres, contre) if contre and autres else None
    print("\nTEST FIXE D'AVANCE : R(AUTRES) - R(CONTRE) >= +0,10 R, p unilateral < 0,05, au moins 100 trades par groupe")
    if e is None:
        print("  pas assez de trades pour calculer.")
    else:
        obs, lo, hi, p = e
        p_uni = p / 2 if obs > 0 else 1 - p / 2
        print(f"  ecart {obs:+.3f} R   IC 95 % [{lo:+.3f} ; {hi:+.3f}]   p unilateral = {p_uni:.4f}   ({len(autres)} AUTRES, {len(contre)} CONTRE)")
        if min(len(autres), len(contre)) < MIN_PAR_GROUPE:
            verdict = f"PAS ASSEZ DE DONNEES (il faut {MIN_PAR_GROUPE} trades dans chaque groupe) : on attend, ce n'est ni une confirmation ni un echec."
        elif obs >= ECART_MIN and p_uni < P_MAX:
            verdict = "UTILE : la regle « pas de trade quand M5 et M15 sont contre » aurait ete benefique. A tester en simulation avant de toucher au bot."
        else:
            verdict = "NON CONFIRMEE : sur ces trades, le filtre n'apporte pas de gain mesurable."
        print(f"  VERDICT : {verdict}" + ("  (exploratoire : pas de valeur de confirmation)" if expl else ""))
    print("\nA TITRE D'INFORMATION (non utilise pour decider) :")
    for s in (-3, -2, -1, 0, 1, 2, 3):
        g = [(x[0], x[1]) for x in lignes if x[3] == s]
        if g:
            print(atc.ligne_groupe(f"score M1+M5+M15 = {s:+d}", g, milieu))
    piege = [(x[0], x[1]) for x in lignes if x[2]["H1"] == "avec" and x[2]["M5"] == "contre" and x[2]["M15"] == "contre"]
    if piege:
        print(atc.ligne_groupe("H1 AVEC mais M5+M15 CONTRE", piege, milieu))
    print("\nLecture : deux semaines de trades ne suffisent pas toujours. Si le verdict est « pas assez de donnees », relance dans une semaine.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
