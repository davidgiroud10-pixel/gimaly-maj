# -*- coding: utf-8 -*-
r"""Simule des regles de PROTECTION DU JOUR sur l'historique de trades_bot.csv (lecture seule, rien n'est modifie).
Pour chaque jour : sommet de la journee (en R), resultat final, ce qui a ete rendu. Puis compare le resultat total
avec et sans chaque regle :
  - arret du jour apres +X R
  - arret du jour quand on rend D R depuis le sommet (sommet >= 3 R)
  - arret du jour apres N stops de suite
  - pause de 60 min apres N stops de suite
Approximation : on ne connait que l'heure de FIN de chaque trade ; un trade qui se termine apres le declenchement
de la regle est considere comme non pris. Les vrais resultats pourraient differer un peu.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe analyse_jours.py                      depuis le 20/10/2026, scalp_keltner_large
  .\.venv\Scripts\python.exe analyse_jours.py 01/10/2026 --genre tous"""
import csv
import sys
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def instant(d, h):
    try:
        return datetime.strptime(f"{d.strip()} {h.strip()}", "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def charger(depuis, genre):
    with open(FICHIER, newline="", encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    jours = OrderedDict()
    for l in lignes:
        if (l.get("resultat") or "").strip() in ("", "ouvert"):
            continue
        t = instant(l.get("date") or "", l.get("heure") or "")
        r, g = nombre(l.get("R")), nombre(l.get("gain_devise"))
        gn = l.get("genre") or l.get("signal") or "?"
        if t is None or r is None or g is None or t < depuis:
            continue
        if genre != "tous" and gn != genre:
            continue
        jours.setdefault(t.date(), []).append((t, r, g))
    for j in jours:
        jours[j].sort()
    return jours


def jouer(trades, regle):
    """Retourne (R, devise, nb_trades_pris) pour une journee avec la regle."""
    cum = sommet = 0.0
    r_tot = g_tot = 0.0
    pris = 0
    serie = 0
    bloque_jusque = None
    arret = False
    for t, r, g in trades:
        if arret or (bloque_jusque and t < bloque_jusque):
            continue
        r_tot += r
        g_tot += g
        pris += 1
        cum += r
        sommet = max(sommet, cum)
        serie = serie + 1 if r < 0 else 0
        kind, val = regle
        if kind == "gain" and cum >= val:
            arret = True
        elif kind == "rendu" and sommet >= 3 and sommet - cum >= val:
            arret = True
        elif kind == "serie_jour" and serie >= val:
            arret = True
        elif kind == "serie_pause" and serie >= val:
            bloque_jusque = t + timedelta(minutes=60)
            serie = 0
    return r_tot, g_tot, pris


def main(argv):
    argv = list(argv)
    genre = "scalp_keltner_large"
    if "--genre" in argv:
        i = argv.index("--genre")
        genre = argv[i + 1] if i + 1 < len(argv) else genre
        del argv[i:i + 2]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else datetime(2026, 10, 20)
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    jours = charger(depuis, genre)
    if not jours:
        print("Aucun trade termine exploitable.")
        return 0
    print(f"Signal : {genre} | depuis le {depuis:%d/%m/%Y} | {len(jours)} jours\n")
    print(f"{'jour':>10} {'trades':>6} {'sommet R':>9} {'final R':>8} {'rendu':>6} {'devise':>8}")
    for j, tr in jours.items():
        cum = som = 0.0
        for _, r, _g in tr:
            cum += r
            som = max(som, cum)
        print(f"{j:%d/%m/%Y} {len(tr):>6} {som:>+9.2f} {cum:>+8.2f} {max(0.0, som - cum):>6.2f} {sum(x[2] for x in tr):>+8.0f}")
    base = [jouer(tr, ("aucune", 0)) for tr in jours.values()]
    br, bg = sum(x[0] for x in base), sum(x[1] for x in base)
    print(f"\nSANS regle : R {br:+.2f} | devise {bg:+.0f} | {sum(x[2] for x in base)} trades\n")
    regles = [("arret du jour apres +3 R", ("gain", 3)), ("arret du jour apres +4 R", ("gain", 4)),
              ("arret du jour apres +5 R", ("gain", 5)), ("arret si on rend 3 R du sommet", ("rendu", 3)),
              ("arret si on rend 4 R du sommet", ("rendu", 4)), ("arret apres 4 stops de suite", ("serie_jour", 4)),
              ("arret apres 5 stops de suite", ("serie_jour", 5)), ("pause 1 h apres 3 stops de suite", ("serie_pause", 3)),
              ("pause 1 h apres 4 stops de suite", ("serie_pause", 4))]
    print(f"{'regle':<36} {'R':>8} {'diff R':>8} {'devise':>8} {'diff $':>8} {'trades':>7}")
    for nom, rg in regles:
        res = [jouer(tr, rg) for tr in jours.values()]
        r, g, n = sum(x[0] for x in res), sum(x[1] for x in res), sum(x[2] for x in res)
        print(f"{nom:<36} {r:>+8.2f} {r - br:>+8.2f} {g:>+8.0f} {g - bg:>+8.0f} {n:>7}")
    print("\nLecture : 'diff' positif = la regle aurait fait mieux que sans regle. Peu de jours = peu de fiabilite ;")
    print("ne change rien au bot sur la base d'une seule regle qui gagne de peu.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
