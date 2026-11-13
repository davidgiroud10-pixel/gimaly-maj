# -*- coding: utf-8 -*-
r"""CVD M3 : etapes 1 a 3 de ton cahier des charges + premier rejeu (LECTURE SEULE, AUCUN ORDRE).
ETAPE 1-2 : inventaire de ce que GIMALY sait lire : le CVD de GIMALY (flux d'ordres futures GC, cumule par session) enregistre chaque minute dans flux_minute.csv, la politique de compte
  (hedging ou netting), la fraicheur des donnees. Ton indicateur CVD de TradingView (courbe + ligne de signal) n'est PAS lisible par GIMALY : indicateur sur invitation, aucun acces aux valeurs.
ETAPE 3 : limites. Le CVD de GIMALY n'est pas celui de ton graphique (autre calcul, autre source) et ta « ligne de signal » n'a pas de definition ici : on la prend comme une moyenne mobile
  exponentielle (EMA) du CVD echantillonne en M3, de longueur 5, 9 ou 14, A TITRE D'ESSAI. Ces trois essais sont des comparaisons multiples : seul un resultat net clair sur les trois compte.
REJEU (sur les minutes enregistrees, pas sur ton indicateur) : croisement detecte a chaque minute, pendant la bougie M3 (valeur en cours contre EMA qui inclut la valeur en cours), 1 position
  par croisement, SL 2,00 $ / TP 4,00 $ depuis le dernier cours M1 ferme, SL/TP touches dans la meme bougie M1 = SL d'abord (prudent), spread 0,20 $ deduit, positions independantes,
  aucune fermeture sur signal inverse, rien dans les 30 min apres un changement de session (initialisation). Mesures : R par trade (1 R = 2 $), win rate, facteur de profit, creux, IC regroupe par jour.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe test_cvd_m3.py [--spread 0.20] [--fichier chemin\flux_minute.csv]"""
import csv
import math
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SL, TP = 2.0, 4.0
LONGUEURS = (5, 9, 14)
Z = 2.39          # Bonferroni pour 3 essais (IC ~98,3 %)


def lire(fichier):
    rows = []
    with open(fichier, newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            try:
                rows.append({"ts": int(l["ts"]), "cvd": float(l["cvd"]), "frais": int(float(l["flux_frais"] or 0)), "session": l["session"],
                             "mt": l["min_t"], "h": float(l["min_h"]), "l": float(l["min_l"]), "c": float(l["min_c"])})
            except (ValueError, KeyError, TypeError):
                continue
    rows.sort(key=lambda r: r["ts"])
    return rows


def barres(rows):
    """Une barre M1 fermee par minute (la derniere vue sur la ligne), dedupliquee."""
    out, vus, idx = [], {}, []
    for i, r in enumerate(rows):
        cle = r["mt"]
        if cle not in vus:
            vus[cle] = len(out)
            out.append((r["h"], r["l"], r["c"]))
        idx.append(vus[cle])
    return out, idx


def signaux(rows, n, ignore_s=1800):
    a = 2.0 / (n + 1)
    sigs = []
    s_close, bucket, x_last, prev, session, debut = None, None, None, None, None, 0
    for i, r in enumerate(rows):
        if not r["frais"]:
            prev = None
            continue
        if r["session"] != session:
            session, s_close, bucket, x_last, prev, debut = r["session"], None, None, None, None, r["ts"]
        b = r["ts"] // 180
        if bucket is None:
            bucket, s_close = b, r["cvd"]
        elif b != bucket:
            s_close = a * x_last + (1 - a) * s_close
            bucket = b
        x_last = r["cvd"]
        s_now = a * r["cvd"] + (1 - a) * s_close
        d = r["cvd"] - s_now
        sg = 1 if d > 1e-9 else -1 if d < -1e-9 else 0
        if sg != 0 and prev is not None and sg != prev and r["ts"] - debut >= ignore_s:
            sigs.append((i, "BUY" if sg > 0 else "SELL"))
        if sg != 0:
            prev = sg
    return sigs


def jouer(bars, idx, rows, sigs, spread):
    trades = []
    for i, sens in sigs:
        k = idx[i]
        entree = bars[k][2]
        tp_p, sl_p = (entree + TP, entree - SL) if sens == "BUY" else (entree - TP, entree + SL)
        res, j = None, k + 1
        while j < len(bars):
            h, l, _ = bars[j]
            if sens == "BUY":
                if l <= sl_p:
                    res = -SL
                    break
                if h >= tp_p:
                    res = TP
                    break
            else:
                if h >= sl_p:
                    res = -SL
                    break
                if l <= tp_p:
                    res = TP
                    break
            j += 1
        if res is None:
            continue                              # encore ouvert en fin de donnees : non compte
        trades.append({"ts": rows[i]["ts"], "sens": sens, "brut": res / SL, "net": (res - spread) / SL, "fin": j})
    return trades


def ic_jours(trades, cle="net"):
    par = {}
    for t in trades:
        par.setdefault(datetime.fromtimestamp(t["ts"]).date(), []).append(t[cle])
    n = len(trades)
    m = sum(t[cle] for t in trades) / n
    se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in par.values())) / n
    return m, m - Z * se, m + Z * se


def main(argv):
    argv = list(argv)
    spread, fichier = 0.20, Path.home() / "GIMALY" / "trading" / "flux_minute.csv"
    if "--spread" in argv:
        i = argv.index("--spread")
        spread = float(argv[i + 1].replace(",", "."))
        del argv[i:i + 2]
    if "--fichier" in argv:
        i = argv.index("--fichier")
        fichier = Path(argv[i + 1])
        del argv[i:i + 2]
    print("=== ETAPES 1-2 : ce que GIMALY peut lire ===")
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            c = mt5.account_info()
            mode = {0: "NETTING (positions fusionnees : bot impossible tel que demande)", 1: "EXCHANGE", 2: "HEDGING (plusieurs positions independantes possibles)"}.get(getattr(c, "margin_mode", -1), "inconnu")
            print(f"Compte MT5 : {'DEMO' if c.trade_mode == 0 else 'REEL'} | mode de marge : {mode}")
            mt5.shutdown()
    except Exception as e:
        print(f"MT5 : non lu ({e!r})")
    if not fichier.exists():
        print(f"{fichier} introuvable : le patch flux_minute n'est pas installe ou le bot n'a pas tourne avec. Rien a rejouer.")
        return 0
    rows = lire(fichier)
    if len(rows) < 500:
        print(f"Seulement {len(rows)} minutes enregistrees : insuffisant.")
        return 0
    jours = sorted({datetime.fromtimestamp(r['ts']).date() for r in rows})
    frais = sum(r["frais"] for r in rows)
    print(f"flux_minute.csv : {len(rows)} minutes du {jours[0]:%d/%m/%Y} au {jours[-1]:%d/%m/%Y} ({len(jours)} jours) | donnees fraiches : {100 * frais / len(rows):.0f} % des minutes")
    print("Sessions vues :", ", ".join(f"{k} ({v})" for k, v in Counter(r['session'] for r in rows).most_common(6)))
    print("Indicateur CVD de ton graphique TradingView (courbe + ligne de signal) : NON LISIBLE par GIMALY (aucune API, script sur invitation).")
    print("CVD de GIMALY : cumul achat - vente des transactions futures GC (flux KMM), remis a zero a chaque session : ce n'est PAS la meme courbe.")
    bars, idx = barres(rows)
    print(f"\n=== REJEU : croisement CVD GIMALY / EMA(n) en M3, SL {SL:g} $ TP {TP:g} $ (1 R = {SL:g} $), spread {spread:g} $ ===")
    print(f"{'n':>3}{'trades':>8}{'/jour':>7}{'BUY/SELL':>10}{'win':>6}{'R brut':>8}{'R net':>8}{'IC net (3 essais)':>24}{'PF net':>8}{'creux R':>9}{'max simult.':>12}")
    for n in LONGUEURS:
        sigs = signaux(rows, n)
        tr = jouer(bars, idx, rows, sigs, spread)
        if len(tr) < 30:
            print(f"{n:>3}{len(tr):>8}  trop peu de trades")
            continue
        net = [t["net"] for t in tr]
        g = [x for x in net if x > 0]
        p = [x for x in net if x < 0]
        cum = pic = creux = 0.0
        for x in net:
            cum += x
            pic = max(pic, cum)
            creux = max(creux, pic - cum)
        evts = sorted([(t["ts"], 1) for t in tr] + [(rows[min(t["fin"], len(rows) - 1)]["ts"], -1) for t in tr])
        cur = maxs = 0
        for _, d in evts:
            cur += d
            maxs = max(maxs, cur)
        m, lo, hi = ic_jours(tr)
        nb = Counter(t["sens"] for t in tr)
        print(f"{n:>3}{len(tr):>8}{len(tr) / len(jours):>7.0f}{nb['BUY']:>5}/{nb['SELL']:<4}{100 * len(g) / len(tr):>5.0f}%{statistics.fmean(t['brut'] for t in tr):>+8.3f}{m:>+8.3f}   [{lo:>+6.3f} ; {hi:>+6.3f}]{(sum(g) / -sum(p) if p else float('inf')):>8.2f}{creux:>9.1f}{maxs:>12}")
    print(f"\nRepere : avec SL 2 $ / TP 4 $ et un spread de {spread:g} $, le seuil de rentabilite est un win rate d'environ {100 * (SL + spread) / (SL + TP):.0f} % ; sans edge, on attend un R net proche de {-spread / SL:+.2f} par trade.")
    print("Lecture : un resultat n'est a retenir que si l'IC exclut 0 pour les TROIS longueurs. Ce rejeu utilise des minutes (pas des ticks) : l'intrabougie M3 est approchee, pas reproduite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
