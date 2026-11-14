# -*- coding: utf-8 -*-
r"""Un filtre CVD (CVD au-dessus / en dessous de son EMA, en M5 et M15) aurait-il ameliore les trades REELS du bot ? (lecture seule, rien n'est modifie)

Lit ~\GIMALY\trading\trades_bot.csv (trades termines : date, heure, sens, resultat, R) et ~\GIMALY\trading\flux_minute.csv (CVD de session, 1 valeur / minute).
Pour chaque trade, a l'instant de son ouverture (heure du PC), avec UNIQUEMENT des bougies deja fermees :
  EMA(n) des clotures du CVD par bougie M5 (ou M15), n = 9 ; le CVD du moment est compare a cette EMA.
  « AVEC » : achat avec CVD > EMA, vente avec CVD < EMA. « CONTRE » : l'inverse. Le CVD repart de zero a 22:00 UTC : pas de calcul avant n bougies de session.
DEFINITIONS FIXEES D'AVANCE : 2 tests (M5-EMA9, M15-EMA9), ecart R moyen « AVEC - CONTRE », seuil de rigueur p < 0,025 (0,05/2), bootstrap sur les JOURS.
Les EMA 5 et 14 sont affichees a titre INDICATIF seulement (pas de conclusion). Un test n'est fait que si chaque groupe compte >= 30 trades.
HYPOTHESE A VERIFIER : l'heure de la ligne de trades_bot.csv est celle de l'ouverture du trade (le script affiche un exemple pour controle).
Un resultat « non significatif » ne veut pas dire « inutile » : avec peu de trades on ne peut pas trancher. Aucune garantie de gain.
OPTION --fantomes : ajoute le meme test sur les signaux REFUSES suivis en fantome (trades_refuses.csv : entree, stop, objectif simules, SANS spread ; un seul
signal par minute et par sens). Les 2 groupes (reels, fantomes) sont testes separement, jamais melanges : 4 tests, seuil p < 0,0125 (0,05/4).
Usage (dossier gimaly) : .\.venv\Scripts\python.exe analyse_filtre_cvd.py [JJ/MM/AAAA depuis] [--fantomes]"""
import bisect
import csv
import random
import statistics
import sys
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
TF = (("M5", 300), ("M15", 900))
EMAS = (5, 9, 14)
PRINCIPAL = 9
MIN_GROUPE = 30
SEUIL = 0.025
SEUIL_FANTOMES = 0.0125


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return None


def lire_flux():
    ts, cvd, sess = [], [], []
    with open(DOSSIER / "flux_minute.csv", newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            t, c, s = nombre(l.get("ts")), nombre(l.get("cvd")), nombre(l.get("session"))
            if None in (t, c, s):
                continue
            ts.append(t)
            cvd.append(c)
            sess.append(int(s))
    ordre = sorted(range(len(ts)), key=ts.__getitem__)
    return [ts[i] for i in ordre], [cvd[i] for i in ordre], [sess[i] for i in ordre]


def etat_cvd(flux, t, duree, n):
    """+1 / -1 / None : CVD actuel vs EMA(n) des clotures de bougies `duree` s deja fermees, dans la session du trade."""
    ts, cvd, sess = flux
    k = bisect.bisect_right(ts, t) - 1
    if k < 0 or t - ts[k] > 180:
        return None
    s = sess[k]
    bougie = int(t // duree)
    clot = {}                               # bougie -> derniere valeur de la bougie (cloture)
    j = k
    while j >= 0 and sess[j] == s and int(ts[j] // duree) >= bougie - 400:
        b = int(ts[j] // duree)
        if b < bougie and b not in clot:
            clot[b] = cvd[j]
        j -= 1
    if len(clot) < n:
        return None
    a, ema = 2.0 / (n + 1), None
    prec = None
    for b in sorted(clot):
        if prec is not None and b - prec > 3:        # trou de donnees : on n'interpole pas
            ema = None
        ema = clot[b] if ema is None else a * clot[b] + (1 - a) * ema
        prec = b
    if ema is None or bougie - prec > 3:
        return None
    return 1 if cvd[k] > ema else -1 if cvd[k] < ema else 0


def lire_trades(depuis, fantomes=False):
    out, vus = [], set()
    with open(DOSSIER / ("trades_refuses.csv" if fantomes else "trades_bot.csv"), newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            if fantomes:
                if (l.get("issue") or "").strip() in ("", "en cours", "ouvert"):
                    continue
            elif (l.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            sens = (l.get("sens") or "").strip()
            r = nombre(l.get("R"))
            if sens not in ("achat", "vente") or r is None:
                continue
            try:
                t = datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
            except (ValueError, KeyError):
                continue
            cle = (t.replace(second=0), sens)
            if fantomes and cle in vus:
                continue
            vus.add(cle)
            if t >= depuis:
                out.append((t, sens, r))
    return out


def bootstrap(avec, contre, essais=4000):
    """p bilatere de l'ecart de moyennes, en retirant des JOURS entiers. avec/contre : listes (jour, R)."""
    def moy(l):
        return sum(r for _, r in l) / len(l)
    ecart = moy(avec) - moy(contre)
    jours = sorted({j for j, _ in avec + contre})
    par = {j: ([r for d, r in avec if d == j], [r for d, r in contre if d == j]) for j in jours}
    rng = random.Random(23)
    sims = []
    for _ in range(essais):
        a, c = [], []
        for j in (rng.choice(jours) for _ in jours):
            a += par[j][0]
            c += par[j][1]
        if a and c:
            sims.append(sum(a) / len(a) - sum(c) / len(c))
    sims.sort()
    if len(sims) < 100:
        return ecart, None, None, None
    lo, hi = sims[int(0.025 * len(sims))], sims[int(0.975 * len(sims)) - 1]
    centre = [s - statistics.mean(sims) for s in sims]
    p = sum(1 for s in centre if abs(s) >= abs(ecart)) / len(centre)
    return ecart, lo, hi, p


def analyser(titre, trades, flux, seuil):
    trades = [t for t in trades if flux[0][0] <= t[0].timestamp() <= flux[0][-1] + 120]
    print(f"=== {titre} : {len(trades)} signaux couverts par ce CVD ===")
    if trades:
        t, s, r = trades[0]
        print(f"Controle : 1er lu = {t:%d/%m/%Y %H:%M:%S} {s} R={r:+.2f}  (doit etre l'heure d'OUVERTURE / du signal)")
    if len(trades) < 2 * MIN_GROUPE:
        print("Trop peu pour comparer (il en faut au moins 60). Aucune conclusion possible.\n")
        return
    base = statistics.mean(r for _, _, r in trades)
    print(f"Tous : R moyen {base:+.3f}, taux de reussite {100 * sum(1 for *_, r in trades if r > 0) / len(trades):.0f} %")
    for nom, duree in TF:
        for n in EMAS:
            avec, contre = [], []
            for t, sens, r in trades:
                e = etat_cvd(flux, t.timestamp(), duree, n)
                if e in (None, 0):
                    continue
                (avec if (e == 1) == (sens == "achat") else contre).append((t.date(), r))
            tag = "TEST" if n == PRINCIPAL else "indicatif"
            if len(avec) < MIN_GROUPE or len(contre) < MIN_GROUPE:
                print(f"{nom} EMA{n} [{tag}] : AVEC {len(avec)} / CONTRE {len(contre)} : trop peu (min {MIN_GROUPE}).")
                continue
            ecart, lo, hi, p = bootstrap(avec, contre)
            ma, mc = statistics.mean(r for _, r in avec), statistics.mean(r for _, r in contre)
            verdict = ""
            if n == PRINCIPAL and p is not None:
                verdict = "  -> SIGNIFICATIF" if p < seuil else "  -> non significatif"
            ptxt = f"p={p:.3f}, IC95 [{lo:+.2f} ; {hi:+.2f}]" if p is not None else "p n/d"
            print(f"{nom} EMA{n} [{tag}] : AVEC {len(avec)} R moyen {ma:+.3f} | CONTRE {len(contre)} R moyen {mc:+.3f} | ecart {ecart:+.3f} R ({ptxt}){verdict}")
    print()


def main(argv):
    argv = list(argv)
    fant = "--fantomes" in argv
    argv = [a for a in argv if a != "--fantomes"]
    depuis = datetime(2026, 1, 1)
    if argv:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y")
    try:
        flux = lire_flux()
        reels = lire_trades(depuis)
        fantomes = lire_trades(depuis, True) if fant else None
    except OSError as e:
        print(f"Fichier introuvable ({e}). Lance depuis ton PC GIMALY.")
        return 1
    if not flux[0]:
        print("flux_minute.csv vide.")
        return 1
    print(f"CVD disponible du {datetime.fromtimestamp(flux[0][0]):%d/%m/%Y %H:%M} au {datetime.fromtimestamp(flux[0][-1]):%d/%m/%Y %H:%M}\n")
    analyser("TRADES REELS", reels, flux, SEUIL_FANTOMES if fant else SEUIL)
    if fant:
        analyser("FANTOMES (signaux refuses, sans spread)", fantomes, flux, SEUIL_FANTOMES)
    print("Lecture : un filtre n'aide que si AVEC > CONTRE de facon significative ET stable. Prudence avec peu de trades ; les fantomes ne prouvent rien sur les vrais gains.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
