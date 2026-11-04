# -*- coding: utf-8 -*-
r"""Patch : un trade REPRIS apres un redemarrage ne peut plus prendre l'objectif d'un AUTRE trade.
Bug constate le 04/11 15:58 : apres un redemarrage avec un trade ouvert, le bot a retrouve le trade dans trades_bot.csv par le seul prix
d'entree (a 0,5 $ pres), sans verifier le SENS. Un ACHAT a 4037,21 a recupere l'objectif (4034,56) d'une VENTE entree au meme prix : un
objectif SOUS l'entree pour un achat est « touche » aussitot, le bot a ferme au marche et annonce « TP1 » pour -112 EUR (-0,55 R).
Corrections : (1) le trade du journal doit etre du meme sens ; (2) un objectif du mauvais cote de l'entree est refuse et recalcule.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_reprise.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_reprise. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "objectif du journal du mauvais cote"

A1 = "            ligne = self._ligne_journal(p.price_open)\n"
B1 = '            ligne = self._ligne_journal(p.price_open, "achat" if achat else "vente")\n'
A2 = "    def _ligne_journal(self, pe):\n"
B2 = "    def _ligne_journal(self, pe, sens=None):\n"
A3 = '''            try:
                if abs(float(ligne["pe"]) - pe) < 0.5:
                    return ligne
'''
B3 = '''            try:
                if sens and (ligne.get("sens") or "").strip() != sens:
                    continue                        # meme prix d'entree mais autre sens : ce n'est pas le meme trade
                if abs(float(ligne["pe"]) - pe) < 0.5:
                    return ligne
'''
A4 = "            # TP deja pris avant le redemarrage ? Le prix d'ouverture ne le dit\n"
B4 = '''            if tp and not all(((t > p.price_open) if achat else (t < p.price_open)) for t in tp):
                journal("position reprise : objectif du journal du mauvais cote de l'entree (autre trade ?), objectifs recalcules")
                tp, raisons = self.objectifs(achat, p.price_open, distance)
''' + A4
CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3), (A4, B4)]


def appliquer(txt):
    manquants = [a.strip()[:90] for a, _ in CHANGEMENTS if txt.count(a) != 1]
    if manquants:
        return None, "\n".join(manquants)
    for ancien, nouveau in CHANGEMENTS:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    crlf = brut.count(b"\r\n") > brut.count(b"\n") / 2
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    nouveau, erreur = appliquer(txt)
    if erreur:
        print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
        print(erreur)
        return 2
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_reprise"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_reprise). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
