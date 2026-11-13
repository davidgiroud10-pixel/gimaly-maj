# -*- coding: utf-8 -*-
r"""Bilan quotidien de la SIMULATION CVD M3 (EMA 5 / 9 / 14) - lecture seule des journaux ~\GIMALY\trading\cvd_m3_ema*_trades.csv.
Par jour (date du signal) et par EMA : nombre de trades, winrate, resultat net ($ et R), Profit Factor, drawdown maximal du jour (sur la courbe des
positions fermees), nombre maximal de positions simultanees, repartition BUY/SELL, + cumul depuis le debut (avec intervalle de confiance par jour) et
rappel du seuil : SL 2 $ / TP 4 $ + spread -> il faut ~37 % de gagnants pour ne pas perdre. Resultats APPROXIMATIFS (voir l'en-tete de cvd_m3_sim.py).
Ecrit aussi cvd_m3_bilan_jours.csv. Usage : .\.venv\Scripts\python.exe cvd_m3_bilan.py [--jours N] [--dossier CHEMIN]"""
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EMAS = (5, 9, 14)


def lire(dossier, n):
    p = Path(dossier) / f"cvd_m3_ema{n}_trades.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f, delimiter=";") if r.get("pnl_usd") not in (None, "")]


def stats(rows):
    pnl = [float(r["pnl_usd"]) for r in sorted(rows, key=lambda r: float(r["ts_sortie"]))]
    r_ = [float(r["r"]) for r in rows]
    g = sum(x for x in pnl if x > 0)
    pe = -sum(x for x in pnl if x < 0)
    pic = cree = 0.0
    dd = 0.0
    for x in pnl:
        cree += x
        pic = max(pic, cree)
        dd = max(dd, pic - cree)
    ev = []
    for r in rows:
        ev.append((float(r["ts_signal"]), 1))
        ev.append((float(r["ts_sortie"]), -1))
    ev.sort(key=lambda e: (e[0], e[1]))
    cur = mx = 0
    for _, d in ev:
        cur += d
        mx = max(mx, cur)
    buy = sum(1 for r in rows if r["sens"] == "BUY")
    return {"n": len(rows), "win": 100 * sum(1 for x in pnl if x > 0) / len(pnl) if pnl else 0, "net": sum(pnl), "r": sum(r_), "pf": (g / pe) if pe else (math.inf if g else 0),
            "dd": dd, "simult": max([mx] + [int(r["simultanees"]) for r in rows]) if rows else 0, "buy": buy, "sell": len(rows) - buy}


def ligne(j, s):
    pf = "inf" if s["pf"] == math.inf else f'{s["pf"]:.2f}'
    return (f'{j:<12}{s["n"]:>7}{s["win"]:>8.1f} %{s["net"]:>10.2f}{s["r"]:>8.1f}{pf:>7}{s["dd"]:>9.2f}{s["simult"]:>7}   {s["buy"]}/{s["sell"]}')


def main():
    a = sys.argv[1:]
    dossier = Path.home() / "GIMALY" / "trading"
    if "--dossier" in a:
        dossier = Path(a[a.index("--dossier") + 1])
    njours = int(a[a.index("--jours") + 1]) if "--jours" in a else 14
    sortie = []
    for n in EMAS:
        rows = lire(dossier, n)
        print(f"\n===== EMA {n} - lot 0.02, SL 2 $, TP 4 $ (approximatif : CVD du GC, prix XAUUSD MT5) =====")
        if not rows:
            print("  aucun trade ferme pour l'instant.")
            continue
        jours = defaultdict(list)
        for r in rows:
            jours[r["date_signal"][:10]].append(r)
        print(f'{"jour":<12}{"trades":>7}{"winrate":>10}{"net $":>10}{"R":>8}{"PF":>7}{"DD $":>9}{"simult":>7}   BUY/SELL')
        for j in sorted(jours)[-njours:]:
            s = stats(jours[j])
            print(ligne(j, s))
            sortie.append([f"EMA{n}", j, s["n"], round(s["win"], 1), round(s["net"], 2), round(s["r"], 1), s["pf"] if s["pf"] != math.inf else "inf", round(s["dd"], 2), s["simult"], s["buy"], s["sell"]])
        tot = stats(rows)
        print(ligne("CUMUL", tot) + f"   ({len(jours)} jours)")
        nets = [stats(v)["net"] for v in jours.values()]
        if len(nets) >= 5:
            m, sd = statistics.mean(nets), statistics.stdev(nets)
            h = 2.39 * sd / math.sqrt(len(nets))
            print(f"  moyenne par jour {m:+.2f} $ , IC 95 % par jour [{m - h:+.2f} ; {m + h:+.2f}] (corrige pour 3 EMA)  -> {'significatif' if m - h > 0 or m + h < 0 else 'NON concluant'}")
        else:
            print(f"  seulement {len(nets)} jour(s) : trop tot pour conclure (objectif : au moins 30 jours).")
    if sortie:
        with open(dossier / "cvd_m3_bilan_jours.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["ema", "jour", "trades", "winrate_pct", "net_usd", "r", "pf", "drawdown_usd", "simultanees_max", "buy", "sell"])
            w.writerows(sortie)
        print(f"\nTableau ecrit : {dossier / 'cvd_m3_bilan_jours.csv'}")
    print("\nRepere : avec SL 2 $, TP 4 $ et ~0,20 $ de spread, il faut ~37 % de gagnants pour etre a l'equilibre ; sans avantage reel on attend ~ -0,10 R par trade.")


if __name__ == "__main__":
    main()
