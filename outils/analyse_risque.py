# -*- coding: utf-8 -*-
r"""Combien chaque trade a-t-il RISQUE en argent, et qui fait le resultat en euros ? (lecture seule, rien n'est modifie)
Le lot est plafonne (trading_lots_max, 1,5 par defaut) : quand le stop est court, le plafond limite le risque ; quand le stop est large,
on risque jusqu'a 1 % du capital. Le R reste juste, mais les euros suivent les gros stops. Ce script mesure :
  - le risque reel par trade (perte d'un -1 R, en devise du compte) selon la taille du stop ;
  - le resultat en R ET en argent pour chaque tranche de stop ;
  - ce que le compte aurait fait si chaque trade avait risque la meme somme (risque median).
Le risque par trade = |gain / R| (R = gain divise par le risque reellement pris, deja calcule par le bot).

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_risque.py                       depuis le 20/10/2026, tous les signaux
  .\.venv\Scripts\python.exe analyse_risque.py 03/11/2026 --genre scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_risque.py 20/10/2026 --genre scalp_keltner_large --stop 2.5     zoom sur les stops d'environ 25 pips
  (--stop 2.5 = de 2,2 a 2,8 $ ; --stop 2.3 2.7 = bornes au choix, en dollars, 10 pips = 1 $)"""
import csv
import random
import statistics
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"
TRANCHES = ((0, 2.0, "moins de 2 $"), (2.0, 3.0, "2 a 3 $"), (3.0, 5.0, "3 a 5 $"), (5.0, 8.0, "5 a 8 $"), (8.0, 1e9, "8 $ et plus"))


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def lire(lignes, depuis, genre):
    """Lignes de CLOTURE exploitables : (date, genre, stop en $, gain, R, risque en devise)."""
    res = []
    for l in lignes:
        etat = (l.get("resultat") or "").strip()
        if etat in ("", "ouvert"):
            continue
        try:
            t = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
        except ValueError:
            continue
        g = (l.get("genre") or "").strip()
        if t < depuis or (genre != "tous" and g != genre):
            continue
        pe, sl, gain, r = nombre(l.get("pe")), nombre(l.get("sl")), nombre(l.get("gain_devise")), nombre(l.get("R"))
        if None in (pe, sl, gain, r) or not r:
            continue
        res.append((t, g, abs(pe - sl), gain, r, abs(gain / r)))
    return res


def main(argv):
    argv = list(argv)
    genre = "tous"
    if "--genre" in argv:
        i = argv.index("--genre")
        genre = argv[i + 1] if i + 1 < len(argv) else genre
        del argv[i:i + 2]
    zoom = None
    if "--stop" in argv:
        i = argv.index("--stop")
        vals = []
        j = i + 1
        while j < len(argv) and len(vals) < 2 and nombre(argv[j]) is not None:
            vals.append(nombre(argv[j]))
            j += 1
        if not vals:
            print("--stop attend 1 ou 2 nombres (dollars), ex. --stop 2.5")
            return 1
        zoom = (vals[0] - 0.3, vals[0] + 0.3) if len(vals) == 1 else (min(vals), max(vals))
        del argv[i:j]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        trades = lire(list(csv.DictReader(f, delimiter=";")), depuis, genre)
    if not trades:
        print("Aucun trade termine a analyser.")
        return 0
    risques = [t[5] for t in trades]
    med = statistics.median(risques)
    r_tot = sum(t[4] for t in trades)
    e_tot = sum(t[3] for t in trades)
    print(f"{len(trades)} trades termines | depuis le {depuis:%d/%m/%Y} | signal : {genre}")
    print(f"Risque par trade (perte d'un -1 R) : mediane {med:,.0f} | min {min(risques):,.0f} | max {max(risques):,.0f}  (devise du compte)")
    print(f"Resultat : {r_tot:+.2f} R  |  {e_tot:+,.0f} en argent  |  si chaque trade avait risque la mediane : {r_tot * med:+,.0f}\n")
    print(f"  {'stop':<14} {'trades':>6} {'risque moy':>11} {'R cumul':>8} {'R moy':>6} {'argent':>10} {'part des pertes/gains':>22}")
    abs_tot = sum(abs(t[3]) for t in trades) or 1.0
    for bas, haut, nom in TRANCHES:
        lot = [t for t in trades if bas <= t[2] < haut]
        if not lot:
            continue
        r = sum(t[4] for t in lot)
        e = sum(t[3] for t in lot)
        part = 100 * sum(abs(t[3]) for t in lot) / abs_tot
        print(f"  {nom:<14} {len(lot):>6} {statistics.fmean(t[5] for t in lot):>11,.0f} {r:>+8.2f} {r / len(lot):>+6.2f} {e:>+10,.0f} {part:>20.0f} %")
    print("\n  Les 5 trades qui pesent le plus en argent :")
    for t in sorted(trades, key=lambda x: -abs(x[3]))[:5]:
        print(f"    {t[0]:%d/%m} {t[1]:<22} stop {t[2]:5.2f} $  R {t[4]:+5.2f}  argent {t[3]:+9,.0f}")
    if zoom:
        bande = [x for x in trades if zoom[0] <= x[2] < zoom[1]]
        print(f"\n  ZOOM stops de {zoom[0]:.2f} a {zoom[1]:.2f} $ ({zoom[0] * 10:.0f} a {zoom[1] * 10:.0f} pips)")
        if not bande:
            print("  aucun trade dans cette bande.")
        else:
            rs = [x[4] for x in bande]
            gagn = sum(1 for r in rs if r > 0)
            print(f"  {len(bande)} trades | gagnants {gagn} ({100 * gagn / len(bande):.0f} %) | R cumul {sum(rs):+.2f} | R moyen {statistics.fmean(rs):+.3f} | "
                  f"argent {sum(x[3] for x in bande):+,.0f}")
            if len(rs) >= 5:
                rnd = random.Random(7)
                m = sorted(statistics.fmean(rnd.choices(rs, k=len(rs))) for _ in range(2000))
                bas, haut = m[50], m[1949]
                print(f"  intervalle a 95 % du R moyen : [{bas:+.3f} ; {haut:+.3f}]  -> "
                      + ("avantage probable" if bas > 0 else "perdant probable" if haut < 0 else "indistinguable du hasard"))
            par_jour = {}
            for x in bande:
                par_jour.setdefault(x[0], []).append(x[4])
            print("  par jour : " + "  ".join(f"{d:%d/%m} {len(v)}t {sum(v):+.1f}R" for d, v in sorted(par_jour.items())))
            pires = sorted(rs)[:3]
            print(f"  les 3 pires : {', '.join(f'{r:+.2f}' for r in pires)} | les 3 meilleurs : {', '.join(f'{r:+.2f}' for r in sorted(rs)[-3:])}")
    print("\nLecture : si une tranche a un 'risque moy' tres superieur aux autres, ses trades dominent le resultat en argent. Un ecart entre "
          "'argent' et 'si chaque trade avait risque la mediane' montre l'effet du plafond de lot. Peu de trades par tranche = prudence.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
