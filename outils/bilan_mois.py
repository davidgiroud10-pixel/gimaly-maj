# -*- coding: utf-8 -*-
"""Bilan approximatif d'une periode, lu dans trades_bot.csv (lecture seule, rien n'est modifie).

Usage (dossier gimaly) :
  .\\.venv\\Scripts\\python.exe bilan_mois.py                      du 01/10/2026 au 30/10/2026
  .\\.venv\\Scripts\\python.exe bilan_mois.py 01/10/2026 31/10/2026
Fichier : %USERPROFILE%\\GIMALY\\trading\\trades_bot.csv
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

FICHIER = Path.home() / "GIMALY" / "trading" / "trades_bot.csv"


def nombre(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def jour(s):
    return datetime.strptime(s.strip(), "%d/%m/%Y")


def resume(titre, lignes):
    n = len(lignes)
    if not n:
        print(f"  {titre:<22} aucun trade")
        return
    r = [nombre(l.get("R")) for l in lignes]
    r = [v for v in r if v is not None]
    ligue = [v for v in (nombre(l.get("resultat_ligue_pct")) for l in lignes) if v is not None]
    gains = [v for v in (nombre(l.get("gain_devise")) for l in lignes) if v is not None]
    gagnants = sum(1 for v in r if v > 0.05)
    perdants = sum(1 for v in r if v < -0.05)
    neutres = len(r) - gagnants - perdants
    print(f"  {titre:<22} {n:>3} trades | gagnants {gagnants} | perdants {perdants} | neutres/point mort {neutres} | "
          f"R cumule {sum(r):+.2f} | ligue {sum(ligue):+.2f} % | devise {sum(gains):+.2f}")


def main(argv):
    debut = jour(argv[0]) if len(argv) > 0 else datetime(2026, 10, 1)
    fin = jour(argv[1]) if len(argv) > 1 else datetime(2026, 10, 30)
    if not FICHIER.exists():
        raise SystemExit(f"{FICHIER} introuvable")
    with open(FICHIER, encoding="utf-8-sig") as f:
        toutes = [l for l in csv.DictReader(f, delimiter=";") if l.get("resultat") not in ("", "ouvert", None)]
    lignes = []
    for l in toutes:
        try:
            if debut <= jour(l["date"]) <= fin:
                lignes.append(l)
        except (ValueError, KeyError):
            continue
    print(f"BILAN du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} : {len(lignes)} trades termines (sur {len(toutes)} au total)\n")
    resume("Tous", lignes)
    for filtre in ("strict", "exploration"):
        resume(f"filtre {filtre}", [l for l in lignes if l.get("filtre") == filtre])
    print()
    for genre in sorted({l.get("genre", "") for l in lignes}):
        resume(f"signal {genre or '?'}", [l for l in lignes if l.get("genre") == genre])
    print("\nR = multiple du risque ; ligue = resultat en % selon la regle winleague. Approximatif : seul le bilan officiel fait foi.")
    print("Les trades sont comptes a leur date d'ouverture ; un trade encore ouvert n'est pas inclus.")


if __name__ == "__main__":
    main(sys.argv[1:])
