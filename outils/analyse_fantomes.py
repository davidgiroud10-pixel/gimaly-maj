# -*- coding: utf-8 -*-
r"""Que donnent les signaux REFUSES par le bot, suivis en « fantome » (trades_refuses.csv) ? (lecture seule, rien n'est modifie)
Chaque signal refuse est suivi comme s'il avait ete pris (memes prix d'entree, stop, objectif) : on sait donc ce que chaque regle de
refus fait gagner ou perdre. Ce script regroupe les fantomes par MOTIF DE REFUS et par SIGNAL, et donne pour chaque groupe : nombre de
fantomes termines, part de gagnants, R cumule, R moyen, et un intervalle de confiance a 95 % (bootstrap) pour dire si c'est
distinguable du hasard.
Lecture d'un motif : si les fantomes refuses pour un motif GAGNENT nettement (R moyen > 0, intervalle au-dessus de 0), le refus
coute de l'argent ; s'ils PERDENT, le refus protege. Un groupe de moins de 30 fantomes ne prouve rien.
Limites : les fantomes ne comptent pas le spread ; plusieurs signaux peuvent tomber a la meme minute (echantillon plus petit qu'il
n'y parait) ; un meme fantome refuse pour plusieurs raisons apparait dans chacune ; la duree de suivi est limitee.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_fantomes.py                       depuis le 20/10/2026
  .\.venv\Scripts\python.exe analyse_fantomes.py 27/10/2026 --min 15   depuis cette date, groupes d'au moins 15 fantomes"""
import csv
import random
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_refuses.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def motifs(motif):
    """Un fantome peut avoir plusieurs raisons : « hors filtre : a, b » donne a et b ; les chiffres sont neutralises."""
    m = (motif or "").strip().lower()
    if not m:
        return ["(motif vide)"]
    if m.startswith("hors filtre"):
        raisons = [x.strip() for x in m.split(":", 1)[-1].split(",") if x.strip()]
        return ["hors filtre : " + re.sub(r"\d+([.,]\d+)?", "#", r) for r in raisons] or [m]
    return [re.sub(r"\d+([.,]\d+)?", "#", m)]


def lire(lignes, depuis):
    res = []
    for l in lignes:
        try:
            t = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
        except ValueError:
            continue
        r = nombre(l.get("R"))
        if t < depuis or r is None:
            continue                       # non termine ou illisible
        res.append((t, (l.get("genre") or "").strip(), motifs(l.get("motif")), r))
    return res


def ic95(valeurs, tirages=2000):
    rnd = random.Random(7)
    m = sorted(statistics.fmean(rnd.choices(valeurs, k=len(valeurs))) for _ in range(tirages))
    return m[int(0.025 * tirages)], m[int(0.975 * tirages) - 1]


def ligne(nom, rs, mini):
    n = len(rs)
    g = sum(1 for r in rs if r > 0)
    moy = statistics.fmean(rs)
    if n >= mini:
        bas, haut = ic95(rs)
        verdict = ("GAGNE nettement" if bas > 0 else "PERD nettement" if haut < 0 else "indistinguable du hasard")
        ic = f"[{bas:+.2f} ; {haut:+.2f}]"
    else:
        ic, verdict = "", "trop peu de fantomes"
    return f"  {nom[:64]:<64} {n:>5} {100 * g / n:>6.0f}% {sum(rs):>+8.1f} {moy:>+6.2f}  {ic:<16} {verdict}"


def main(argv):
    argv = list(argv)
    mini = 30
    if "--min" in argv:
        i = argv.index("--min")
        try:
            mini = int(argv[i + 1])
        except (IndexError, ValueError):
            print("--min attend un nombre entier, ex. --min 15")
            return 1
        del argv[i:i + 2]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        fantomes = lire(list(csv.DictReader(f, delimiter=";")), depuis)
    if not fantomes:
        print("Aucun fantome termine a analyser.")
        return 0
    tous = [x[3] for x in fantomes]
    print(f"{len(fantomes)} fantomes termines | depuis le {depuis:%d/%m/%Y} | R moyen de l'ensemble : {statistics.fmean(tous):+.3f}")
    print(f"  (groupes de moins de {mini} fantomes : pas d'avis ; --min pour changer)\n")
    entete = f"  {'groupe':<64} {'n':>5} {'gagn.':>7} {'R cumul':>8} {'R moy':>6}  {'intervalle 95 %':<16} verdict"

    par_motif = {}
    for _, _, ms, r in fantomes:
        for m in ms:
            par_motif.setdefault(m, []).append(r)
    print("  A. PAR MOTIF DE REFUS (que valent les trades qu'on a refuses pour cette raison ?)")
    print(entete)
    for m, rs in sorted(par_motif.items(), key=lambda kv: -len(kv[1])):
        print(ligne(m, rs, mini))

    par_genre = {}
    for _, g, _, r in fantomes:
        par_genre.setdefault(g or "(inconnu)", []).append(r)
    print("\n  B. PAR SIGNAL")
    print(entete)
    for g, rs in sorted(par_genre.items(), key=lambda kv: -len(kv[1])):
        print(ligne(g, rs, mini))

    croise = {}
    for _, g, ms, r in fantomes:
        for m in ms:
            croise.setdefault((g, m), []).append(r)
    gros = [(k, v) for k, v in croise.items() if len(v) >= mini]
    if gros:
        print("\n  C. SIGNAL x MOTIF (groupes assez grands)")
        print(entete)
        for (g, m), rs in sorted(gros, key=lambda kv: -len(kv[1])):
            print(ligne(f"{g} / {m}", rs, mini))
    print("\nLecture : 'GAGNE nettement' = le refus a coute de l'argent (a reexaminer) ; 'PERD nettement' = le refus protege ; "
          "'indistinguable du hasard' = on ne sait pas. Beaucoup de groupes testes a la fois : un 'nettement' isole peut etre un hasard, "
          "a reverifier plus tard sur des fantomes jamais vus. Rien n'est modifie par ce script.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
