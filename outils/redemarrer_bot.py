# -*- coding: utf-8 -*-
r"""Redemarre le bot de trading en un geste (cree le fichier bot.stop ; le moteur / lanceur relance le bot tout seul).
Refuse s'il y a un trade ouvert (le bot en cours n'a pas fini de le gerer), sauf avec --force. Attend la confirmation
« bot lance » dans trading.log et l'affiche. Aucune donnee n'est touchee.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe redemarrer_bot.py            redemarrage (refuse si trade ouvert)
  .\.venv\Scripts\python.exe redemarrer_bot.py --force    redemarre meme avec un trade ouvert (il est repris, stop et objectif restent)
Fichiers lus : %USERPROFILE%\GIMALY\trading\trading_etat.json et trading.log"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
ETAT = DOSSIER / "trading_etat.json"
LOG = DOSSIER / "trading.log"
STOP = DOSSIER / "bot.stop"
ATTENTE_S = 120


def lire_etat():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def taille_log():
    try:
        return LOG.stat().st_size
    except OSError:
        return 0


def nouvelles_lignes(depuis):
    try:
        with open(LOG, "rb") as f:
            f.seek(depuis)
            return f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def main(argv):
    force = "--force" in argv
    etat = lire_etat()
    if etat is None:
        print("Etat du bot illisible (trading_etat.json) : le bot ne tourne peut-etre pas. Je continue quand meme.")
    else:
        try:
            age = (datetime.now() - datetime.strptime(etat.get("maj", ""), "%d/%m/%Y %H:%M:%S")).total_seconds()
        except ValueError:
            age = None
        if age is not None and age > 90:
            print(f"Attention : l'etat du bot date d'il y a {age / 60:.0f} min (le bot est peut-etre deja arrete).")
        ouverts = etat.get("en_cours") or []
        if ouverts and not force:
            print(f"{len(ouverts)} trade(s) ouvert(s) :")
            for t in ouverts:
                print(f"  {t.get('sens', '')} {t.get('genre', '')} entree {t.get('pe')} stop {t.get('sl')}")
            print("Redemarrage REFUSE : attends la fin du trade, ou relance avec --force (le trade est repris apres le redemarrage).")
            return 2
    debut = taille_log()
    STOP.write_text("", encoding="utf-8")
    print("Redemarrage demande (bot.stop cree). Attente du nouveau bot...")
    t0 = time.time()
    arrete = lance = False
    while time.time() - t0 < ATTENTE_S:
        for l in nouvelles_lignes(debut):
            if "bot arr" in l:
                arrete = True
            if "bot lanc" in l and arrete:
                lance = True
        if lance:
            break
        time.sleep(2)
    if lance:
        print("OK : le bot a redemarre.")
        for l in nouvelles_lignes(debut)[-6:]:
            print("  " + l)
        return 0
    print(f"Pas de confirmation apres {ATTENTE_S} s. bot.stop existe encore : {STOP.exists()}.")
    for l in nouvelles_lignes(debut)[-6:]:
        print("  " + l)
    print("Envoie-moi cette sortie si le bot ne repart pas.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
