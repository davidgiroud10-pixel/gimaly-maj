# -*- coding: utf-8 -*-
r"""Verification (LECTURE SEULE) du R reel du canal : tient-il compte du NOMBRE de TP de chaque signal (4 ou 5, pas 2) ?
Lit ~\GIMALY\trades.db. Pour chaque signal clos :
  - compte ses objectifs (colonne objectifs) ; le TP atteint est DEDUIT du R ecrit (le statut ne dit que gagne / perdu / nul) ;
  - RECALCULE le R encaisse avec la regle du canal : la position est repartie a parts egales entre les n TP, chaque TP atteint encaisse sa part a son R, le stop du reste passe au
    point mort apres TP1 (reste = 0), un stop avant TP1 = -1 R ;
  - le compare au % ecrit dans le message (1 % de risque = 1 R), que bilan_canal.py utilise comme « R reel ».
Affiche : repartition du nombre de TP, des statuts, l'accord entre le R recalcule et le % lu, le R total recalcule, et les signaux les plus eloignes (a verifier sur Telegram).
Si le total recalcule est proche de celui du % lu, le bilan tient bien compte des TP multiples ; sinon, on sait de combien et sur quels signaux.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe verif_tp_canal.py [--canal "coin trader"] [--depuis jj/mm/aaaa]"""
import json
import re
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DATA = Path.home() / "GIMALY"
IGNORES = ("en cours", "non déclenché", "clos sans chiffre")


def niveaux(txt):
    if txt is None:
        return []
    try:
        v = json.loads(txt) if isinstance(txt, str) else txt
        if isinstance(v, (list, tuple)):
            return [float(x) for x in v]
    except (ValueError, TypeError):
        pass
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+[.,]?\d*", str(txt))]


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
    b = sqlite3.connect(f"file:{DATA / 'trades.db'}?mode=ro", uri=True)
    b.row_factory = sqlite3.Row
    rows = [dict(x) for x in b.execute("""SELECT t.message_id, t.date, t.sens, t.entree, t.stop, t.objectifs,
        COALESCE(c.statut,t.statut) statut, COALESCE(c.r,t.r) r, COALESCE(c.pourcentage,t.pourcentage) pct,
        COALESCE(c.annule,t.annule) annule FROM trades t LEFT JOIN corrections c ON c.canal=t.canal AND c.message_id=t.message_id
        WHERE t.canal=? ORDER BY t.date""", (canal,))]
    b.close()
    clos = []
    for x in rows:
        if x["annule"] or x["statut"] in IGNORES or x["r"] is None:
            continue
        try:
            t = datetime.fromisoformat(x["date"]).astimezone().replace(tzinfo=None)
        except ValueError:
            continue
        if depuis and t < depuis:
            continue
        x["t"] = t
        clos.append(x)
    if not clos:
        print("Aucun signal clos.")
        return 0
    print(f"{len(clos)} signaux clos. Exemple de colonnes : objectifs={clos[0]['objectifs']!r} statut={clos[0]['statut']!r} r={clos[0]['r']} pct={clos[0]['pct']}")
    nb = Counter(len(niveaux(x["objectifs"])) for x in clos)
    print("\nNombre de TP par signal :", ", ".join(f"{k} TP : {v}" for k, v in sorted(nb.items())))
    print("Statuts :", ", ".join(f"{k} : {v}" for k, v in Counter(str(x['statut']) for x in clos).most_common()))
    # Le statut ne donne pas le TP atteint (gagne / perdu / nul) : on le DEDUIT du R ecrit (r), en testant trois lectures de ce R :
    #   A : r = R du dernier TP atteint ; B : r = somme des R des TP atteints ; C : r = somme des R des TP atteints divisee par n.
    prep = []
    for x in clos:
        tps = niveaux(x["objectifs"])
        try:
            entree, stop = float(x["entree"]), float(x["stop"])
            lu = float(x["pct"]) if x["pct"] is not None else None
            r = float(x["r"])
        except (TypeError, ValueError):
            continue
        risque = abs(entree - stop)
        if not tps or risque <= 0 or lu is None:
            continue
        rs = [abs(t - entree) / risque for t in tps]
        prep.append((x, rs, r, lu))
    if not prep:
        print("Aucun signal exploitable (colonnes entree/stop/objectifs/r/pct manquantes ?).")
        return 0

    def trouve(rs, r, lecture):
        n = len(rs)
        best = None
        for k in range(1, n + 1):
            v = {"A": rs[k - 1], "B": sum(rs[:k]), "C": sum(rs[:k]) / n}[lecture]
            d = abs(v - r)
            if best is None or d < best[0]:
                best = (d, k)
        return best

    gagn = [z for z in prep if z[2] > 0.05]
    print(f"\nQuelle lecture du R ecrit colle aux niveaux de TP ? ({len(gagn)} signaux gagnants, tolerance 0,05 R)")
    scores = {}
    for lecture, texte in (("A", "r = R du dernier TP atteint"), ("B", "r = somme des R des TP atteints"), ("C", "r = somme des R des TP atteints / nombre de TP")):
        n_ok = sum(1 for _, rs, r, _ in gagn if trouve(rs, r, lecture)[0] <= 0.05)
        scores[lecture] = n_ok
        print(f"  {lecture} ({texte}) : {n_ok} / {len(gagn)} ({100 * n_ok / max(len(gagn), 1):.0f} %)")
    meilleure = max(scores, key=scores.get)
    print(f"Lecture retenue : {meilleure}")
    print("\nRapport % lu / R ecrit, par nombre de TP (si le 1 % de risque est partage entre n TP, on s'attend a 1/n x 100 pour une lecture B) :")
    par_n = {}
    for x, rs, r, lu in gagn:
        if abs(lu) < 50:                      # les % absurdes (>= 50 %) sont des erreurs de lecture, ecartees ici
            par_n.setdefault(len(rs), []).append(lu / r)
    for n in sorted(par_n):
        print(f"  {n} TP : {len(par_n[n])} signaux, % / R median {statistics.median(par_n[n]):.2f} (1/n = {1 / n:.2f})")
    ok = []
    absurdes = [x for x, rs, r, lu in prep if abs(lu) >= 50]
    tot_calc = tot_lu = 0.0
    for x, rs, r, lu in prep:
        if abs(lu) >= 50:
            continue
        n = len(rs)
        if r > 0.05:
            d, k = trouve(rs, r, meilleure)
            k = k if d <= 0.05 else 0
        elif r < -0.05:
            k = 0
        else:
            k = None
        if k is None:
            calc = 0.0
        elif k == 0:
            calc = -1.0 if r < -0.05 else float("nan")
        else:
            calc = sum(rs[:k]) / n
        if calc != calc:                       # gagnant dont le TP n'est pas retrouve : non comparable
            continue
        tot_calc += calc
        tot_lu += lu
        ok.append((abs(calc - lu), x, calc, lu, k if k is not None else 0, n))
    print(f"\n{len(ok)} signaux comparables ; {len(absurdes)} ecartes car % lu absurde (>= 50 %) : " + ", ".join(f"id {x['message_id']} ({lu:+.0f} %)" for x, _, _, lu in [(a, None, None, float(a['pct'])) for a in absurdes][:8]))
    print(f"R total RECALCULE (parts egales entre les n TP, point mort apres TP1) : {tot_calc:+.1f} R")
    print(f"R total LU dans les % des messages (memes signaux)                    : {tot_lu:+.1f} R")
    ecart = [a for a, *_ in ok]
    proches = sum(1 for a in ecart if a <= 0.15)
    print(f"Signaux dont le recalcul est a moins de 0,15 R du % lu : {proches} / {len(ok)} ({100 * proches / max(len(ok), 1):.0f} %) ; ecart median {statistics.median(ecart):.2f} R")
    print("\nLes 12 plus gros ecarts (a verifier sur Telegram) :")
    for a, x, calc, lu, k, n in sorted(ok, key=lambda z: -z[0])[:12]:
        print(f"  id {x['message_id']:>7} {x['date'][:16]} {x['sens']:<5} {x['statut']!s:<7} {n} TP, {k} atteint(s) : recalcule {calc:+.2f} R | lu {lu:+.2f} R")
    print("\nLecture : un recalcul proche du % lu confirme que le bilan tient compte des TP multiples. Un recalcul nettement plus haut ou plus bas indique une autre regle de partage")
    print("(parts inegales, stop jamais remonte...) : dis-moi laquelle et je recalcule avec.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
