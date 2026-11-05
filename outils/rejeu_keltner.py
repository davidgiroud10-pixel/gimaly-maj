# -*- coding: utf-8 -*-
r"""Rejeu du signal scalp_keltner_large sur tout l'historique M1 de MetaTrader (lecture seule, aucun ordre).

Le signal est reconstruit comme dans le detecteur de GIMALY (icebergs.py / respiration.py) :
  * canal de Keltner M1 : EMA 20 des clotures, bandes a 2 x ATR(10) ;
  * achat si la bougie touche la bande basse (bas <= bande < cloture), vente si elle touche la bande haute (haut >= bande > cloture) ;
  * un meme signal au plus toutes les 15 minutes par sens ;
  * stop initial a 0,3 $ au-dela de la meche ; variante « large » : stop au double de la distance cloture-stop ; objectif 1,5 R ;
  * le trade est coupe au marche apres 60 minutes.
Etapes : (1) controle : combien de tes trades reels retrouve-t-on dans le rejeu (et inversement) ; (2) resultat du rejeu mois par mois et
semaine par semaine, avec le spread ; (3) intervalle de confiance du R moyen (bootstrap), achats / ventes, deux moities.
Ce que le rejeu NE contient PAS : les filtres du bot (sessions Londres / New York, limite de positions, lots, spread du moment), la gestion
en cours de trade, le glissement. Stop et objectif dans la meme bougie : stop (prudent). Ordre de grandeur, pas une promesse.
Necessite MetaTrader 5 ouvert ; plus l'historique M1 est charge (graphique M1 de l'or, defiler vers la gauche), plus la periode est longue.

Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe rejeu_keltner.py                     depuis le 01/01/2026, spread 0,20 $
  .\.venv\Scripts\python.exe rejeu_keltner.py 01/06/2026 --spread 0.25"""
import csv
import math
import random
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SYMBOLE = "XAUUSD"
FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
LONGUEUR, MULT, N_ATR = 20, 2.0, 10
PAUSE_S, DUREE_S, TP_R = 900, 3600, 1.5
GENRE = "scalp_keltner_large"


def charger(mt5, debut):
    """Bougies M1 (t, o, h, b, c) depuis `debut`, par blocs d'une semaine (limites de MetaTrader)."""
    out, t = [], debut
    fin = datetime.now() + timedelta(days=1)
    while t < fin:
        suite = t + timedelta(days=7)
        r = mt5.copy_rates_range(SYMBOLE, mt5.TIMEFRAME_M1, t, suite)
        if r is not None and len(r):
            out.extend((int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in r)
        t = suite
    out = sorted(set(out))
    return out


def canal(barres):
    """Listes (milieu, haut, bas) pour chaque bougie, EMA/ATR recursifs sur toute la serie (equivalent a la fenetre du bot apres convergence)."""
    a = 2 / (LONGUEUR + 1)
    ema = barres[0][4]
    tr, atr = [], None
    res = []
    for i, (t, o, h, b, c) in enumerate(barres):
        if i:
            ema = a * c + (1 - a) * ema
            tr.append(max(h - b, abs(h - barres[i - 1][4]), abs(b - barres[i - 1][4])))
            if len(tr) == N_ATR:
                atr = sum(tr) / N_ATR
            elif len(tr) > N_ATR:
                atr = (atr * (N_ATR - 1) + tr[-1]) / N_ATR
        res.append((ema, ema + MULT * atr, ema - MULT * atr) if atr else None)
    return res


def signaux(barres):
    """[(indice, sens, entree, stop_large)] ; sens = 'achat' / 'vente'."""
    k = canal(barres)
    derniere = {"achat": -10 ** 9, "vente": -10 ** 9}
    out = []
    for i in range(60, len(barres)):
        if k[i] is None:
            continue
        t, o, h, b, c = barres[i]
        for sens, touche in (("achat", b <= k[i][2] < c), ("vente", h >= k[i][1] > c)):
            if not touche or t - derniere[sens] < PAUSE_S:
                continue
            derniere[sens] = t
            sl = round(b - 0.3 if sens == "achat" else h + 0.3, 2)
            dist = abs(c - sl) * 2
            if dist <= 0 or dist > 40.0:            # sl_max_pips 400 = 40 $
                continue
            out.append((i, sens, c, round(c - dist if sens == "achat" else c + dist, 2)))
    return out


def jouer(barres, i, sens, entree, sl):
    """R du trade (avant spread) ; suit les bougies suivantes pendant 60 min."""
    achat = sens == "achat"
    dist = abs(entree - sl)
    tp = entree + TP_R * dist if achat else entree - TP_R * dist
    t0 = barres[i][0]
    dern = entree
    for j in range(i + 1, len(barres)):
        t, o, h, b, c = barres[j]
        if t - t0 > DUREE_S:
            break
        if (b <= sl) if achat else (h >= sl):
            return -1.0
        if (h >= tp) if achat else (b <= tp):
            return TP_R
        dern = c
    return ((dern - entree) if achat else (entree - dern)) / dist


def reels(depuis):
    if not FICHIER.exists():
        return []
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    out = []
    for l in lignes:
        if (l.get("resultat") or "").strip() != "ouvert" or (l.get("genre") or "").strip() != GENRE:
            continue
        try:
            t = datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
        except (ValueError, KeyError):
            continue
        if t >= depuis:
            out.append((t, (l.get("sens") or "").strip()))
    return out


def controle(mt5, barres, sigs, depuis):
    r = reels(max(depuis, datetime(2026, 10, 20)))
    if not r or not sigs:
        print("Controle : aucun trade reel a comparer.")
        return 0, set()
    tick = mt5.symbol_info_tick(SYMBOLE)
    decalage = (tick.time - time.time()) if tick and tick.time else 0.0
    instants = {s: [barres[i][0] for i, sens, _, _ in sigs if sens == s] for s in ("achat", "vente")}
    meilleur = (-1, 0)
    for h in range(-4, 5):
        n = 0
        for t, sens in r:
            cible = t.timestamp() + decalage + 3600 * h
            n += any(abs(x - cible) <= 150 for x in instants.get(sens, ()))
        if n > meilleur[0]:
            meilleur = (n, h)
    trouves, h_ok = meilleur
    pris = set()
    for t, sens in r:
        cible = t.timestamp() + decalage + 3600 * h_ok
        for i, s_, _, _ in sigs:
            if s_ == sens and abs(barres[i][0] - cible) <= 150:
                pris.add(i)
    print(f"Controle : {trouves} de tes {len(r)} trades reels ({100 * trouves / len(r):.0f} %) correspondent a un signal rejoue "
          f"(meme sens, a 2,5 min pres, decalage horaire {h_ok:+d} h).")
    debut_s = min(t.timestamp() for t, _ in r) + decalage + 3600 * h_ok - 300
    dans = [s for s in sigs if barres[s[0]][0] >= debut_s]
    print(f"           Sur la meme periode, le rejeu produit {len(dans)} signaux contre {len(r)} trades pris par le bot : "
          f"le bot en filtre environ {100 * (1 - len(r) / max(len(dans), 1)):.0f} % (sessions, limites de positions...).")
    if trouves / len(r) < 0.7:
        print("           ATTENTION : moins de 70 % de tes trades sont retrouves, le rejeu ne reproduit pas bien le signal : "
              "resultats a prendre avec beaucoup de prudence (envoie-moi cette sortie).")
    return h_ok, pris


def stats_groupe(rs):
    if not rs:
        return "-"
    g = sum(x for x in rs if x > 0)
    p = -sum(x for x in rs if x < 0)
    return (f"{len(rs):>5} trades  reussite {100 * sum(1 for x in rs if x > 0) / len(rs):>3.0f} %  R {sum(rs):>+8.1f}  "
            f"R/trade {sum(rs) / len(rs):>+6.3f}  PF {g / p if p else float('nan'):>5.2f}")


def main(argv):
    argv = list(argv)
    spread = 0.20
    if "--spread" in argv:
        i = argv.index("--spread")
        try:
            spread = float(argv[i + 1].replace(",", "."))
        except (ValueError, IndexError):
            print("Spread attendu en dollars, ex. 0,2")
            return 1
        del argv[i:i + 2]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 1, 1)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Module MetaTrader5 introuvable : lance ce script avec le Python du bot (.venv).")
        return 1
    if not mt5.initialize():
        print(f"MetaTrader 5 injoignable ({mt5.last_error()}). Ouvre MetaTrader 5 puis relance.")
        return 1
    try:
        mt5.symbol_select(SYMBOLE, True)
        barres = charger(mt5, depuis - timedelta(days=3))
        if len(barres) < 2000:
            print("Historique M1 insuffisant : ouvre un graphique M1 de l'or dans MetaTrader et fais-le defiler vers la gauche, puis relance.")
            return 0
        d0, d1 = datetime.fromtimestamp(barres[0][0]), datetime.fromtimestamp(barres[-1][0])
        print(f"{len(barres)} bougies M1 du {d0:%d/%m/%Y} au {d1:%d/%m/%Y} (limite : ce que ton MetaTrader a charge) | spread suppose {spread:.2f} $")
        sigs = signaux(barres)
        h_ok, pris = controle(mt5, barres, sigs, depuis)
    finally:
        mt5.shutdown()
    lignes = []
    for i, sens, entree, sl in sigs:
        t = datetime.fromtimestamp(barres[i][0])
        if t < depuis:
            continue
        dist = abs(entree - sl)
        lignes.append((t, sens, jouer(barres, i, sens, entree, sl) - spread / dist, i))
    if not lignes:
        print("Aucun signal rejoue.")
        return 0
    rs = [x[2] for x in lignes]
    print(f"\nREJEU : {stats_groupe(rs)}")
    print(f"  achats : {stats_groupe([x[2] for x in lignes if x[1] == 'achat'])}")
    print(f"  ventes : {stats_groupe([x[2] for x in lignes if x[1] == 'vente'])}")
    random.seed(1)
    moy = sorted(statistics.fmean(random.choices(rs, k=len(rs))) for _ in range(3000))
    print(f"  R moyen par trade : {statistics.fmean(rs):+.3f}  (intervalle a 95 % : {moy[75]:+.3f} a {moy[2925]:+.3f} ; "
          f"si l'intervalle contient 0, rien ne le distingue du hasard)")
    m = len(rs) // 2
    print(f"  deux moities : {sum(rs[:m]):+.1f} R puis {sum(rs[m:]):+.1f} R")
    mois, sem = {}, {}
    for t, sens, r, _ in lignes:
        mois.setdefault(t.strftime("%Y-%m"), []).append(r)
        sem.setdefault(t.strftime("%G-S%V"), []).append(r)
    print("\nMois par mois :")
    for k, v in sorted(mois.items()):
        print(f"  {k}  {stats_groupe(v)}")
    pos = sum(1 for v in sem.values() if sum(v) > 0)
    print(f"\nSemaines positives : {pos} sur {len(sem)} ({100 * pos / len(sem):.0f} %)")
    if pris:
        debut_pris = min(barres[i][0] for i in pris)
        meme = [x for x in lignes if barres[x[3]][0] >= debut_pris]
        a = [x[2] for x in meme if x[3] in pris]
        b = [x[2] for x in meme if x[3] not in pris]
        print("\nSignaux PRIS par le bot ou non, depuis ses premiers trades (memes regles de rejeu) :")
        print(f"  pris par le bot     : {stats_groupe(a)}")
        print(f"  filtres par le bot  : {stats_groupe(b)}")
        print("  (le bot filtre sessions, limite de positions... Si les signaux pris sont meilleurs que les filtres, ses filtres aident ;")
        print("   sur quelques semaines, l'ecart peut aussi etre du hasard.)")
    print("\nPar tranche de 2 heures, heure de ton PC (R/trade apres spread ; 1re moitie / 2e moitie de la periode) :")
    print(f"  {'heures':>9} {'trades':>7} {'R/trade':>8} {'1re':>7} {'2e':>7}")
    m2 = lignes[len(lignes) // 2][0]
    for tr in range(0, 24, 2):
        v = [x for x in lignes if (((x[0] - timedelta(hours=h_ok)).hour) // 2) * 2 == tr]
        if len(v) < 30:
            continue
        v1 = [x[2] for x in v if x[0] < m2]
        v2 = [x[2] for x in v if x[0] >= m2]
        f = lambda z: f"{statistics.fmean(z):>+7.3f}" if z else "      -"
        print(f"  {tr:>2}h-{tr + 2:>2}h {len(v):>7} {statistics.fmean([x[2] for x in v]):>+8.3f} {f(v1)} {f(v2)}")
    print("  (une tranche n'est interessante que si les DEUX moities sont positives ; 12 tranches regardees = risque de hasard.)")
    print("\nLecture : un vrai avantage doit se voir sur la plupart des mois (pas seulement un ou deux), avec un intervalle qui exclut 0 apres")
    print("spread. Rejeu = tous les signaux, sans les filtres du bot. Un resultat a refaire sur les mois a venir avant toute decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
