# -*- coding: utf-8 -*-
r"""Patch bilan des canaux : comprendre le vocabulaire d'Amely (et d'autres) sans toucher a ce qui marche.
1) « Mettez le SL a be » (ecrit « SL A BE ») n'etait pas reconnu comme mise au point mort ;
2) un recapitulatif « Total : +750 pips / +4,16R » etait lu comme le premier R du message (+1,16R) a cause des pips intercales ;
3) chez Amely, le resultat « BE » arrive en IMAGE (reponse sans texte) apres l'ordre « SL a be » : le trade est alors sorti a plat (0 R)
   au lieu de rester « en cours ». Liste des canaux concernes : reglage signal_be_par_image (defaut : amely).
Fichier modifie : gimaly/skills/signals_skill.py (sauvegarde signals_skill.py.avant_amely). Idempotent, rien n'est ecrit si un repere manque.
Usage (dossier gimaly, GIMALY ferme) :  .\.venv\Scripts\python.exe patch_amely.py"""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "skills" / "signals_skill.py"
MARQUE = "signal_be_par_image"

CHANGEMENTS = [
    # 1) « SL A BE »
    ("    if any(forme in haut for forme in FORMES_BE):\n        return True\n",
     "    if any(forme in haut for forme in FORMES_BE) or re.search(r\"\\bSL\\s+A\\s+BE\\b\", haut):\n        return True\n"),
    # 2) total avec pips intercales, et pips du total
    ('        mesure = re.search(r"TOTAL\\s*:?\\s*([+-]?\\s*\\d+(?:[.,]\\d+)?)\\s*RR?\\b", haut)\n',
     '        mesure = re.search(r"TOTAL\\s*:?\\s*(?:[+-]?\\s*\\d+(?:[.,]\\d+)?\\s*PIPS\\s*[/|]?\\s*)?"\n'
     '                           r"([+-]?\\s*\\d+(?:[.,]\\d+)?)\\s*RR?\\b", haut)\n'),
    ('    resultat_pips = re.search(r"([+-]?\\s*[\\d.,]+)\\s*PIPS", haut)\n',
     '    resultat_pips = (re.search(r"TOTAL\\s*:?\\s*([+-]?\\s*[\\d.,]+)\\s*PIPS", haut)\n'
     '                     or re.search(r"([+-]?\\s*[\\d.,]+)\\s*PIPS", haut))\n'),
    # 3) BE annonce par image (reponse sans texte)
    ("            trade.regle_ligue = regle_ligue\n",
     "            trade.regle_ligue = regle_ligue\n"
     "            # Chez certains traders (Amely), le BE touche s'annonce par une IMAGE : reponse sans texte apres\n"
     "            # l'ordre « SL a be ». Reglage signal_be_par_image (liste de canaux, defaut : amely).\n"
     "            canaux_image = tuple(str(c).strip().lower() for c in\n"
     "                                 (getattr(self.config, \"signal_be_par_image\", None) or (\"amely\",)))\n"
     "            if (regle_ligue and canal.strip().lower() in canaux_image and trade.equilibre\n"
     "                    and trade.r_annonce is None and not trade.stoppe and not trade.annule\n"
     "                    and any(not (r or \"\").strip() for r in reponses)):\n"
     "                trade.ferme_a_plat = True\n"
     "                trade.stoppe = True\n"),
]


def appliquer(txt):
    """Renvoie (nouveau texte, erreur)."""
    for ancien, _ in CHANGEMENTS:
        if txt.count(ancien) != 1:
            return None, ancien.strip()[:90]
    for ancien, nouveau in CHANGEMENTS:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    txt = brut.decode("utf-8-sig")
    if MARQUE in txt:
        print("signals_skill.py : deja corrige (rien a faire).")
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
    shutil.copy2(F, F.with_name(F.name + ".avant_amely"))
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + nouveau.encode("utf-8"))
    print("signals_skill.py : corrige (sauvegarde signals_skill.py.avant_amely). Ferme et relance GIMALY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
