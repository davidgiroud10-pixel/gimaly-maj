# -*- coding: utf-8 -*-
"""Ajoute un bouton « AMIS » dans la barre de commande de GIMALY V2 (gimaly/v2/ui/main_window.py).

Le bouton ouvre la fenetre de suivi des amis (suivi_amis.py) dans un processus a part : l'interface n'est pas
ralentie et une erreur dans cette fenetre ne peut pas la faire tomber. Le bouton n'est PAS un module du moteur :
la liste des modules, les raccourcis F1-F12 et les apercus ne sont pas touches.

A lancer depuis le dossier gimaly :
  .\\.venv\\Scripts\\python.exe patch_v2_amis.py
Sauvegarde : main_window.py.avant_amis. Idempotent. Rien n'est ecrit si un repere manque.
Ensuite : ferme puis relance GIMALY.
"""
import shutil
import sys
from pathlib import Path

CIBLE = Path.cwd() / "gimaly" / "v2" / "ui" / "main_window.py"

A_ANCRE = "class CommandDock(QFrame):\n"
A_AJOUT = '''_PROCESSUS_AMIS = None


def ouvrir_fenetre_amis() -> None:
    """Ouvre la fenetre « Amis » (suivi_amis.py, a la racine du projet) dans un processus a part, une seule a la fois."""
    global _PROCESSUS_AMIS
    import os
    import subprocess
    import sys
    from pathlib import Path

    if _PROCESSUS_AMIS is not None and _PROCESSUS_AMIS.poll() is None:
        return
    racine = Path(__file__).resolve().parents[3]
    script = racine / "suivi_amis.py"
    if not script.exists():
        journal.warning("suivi_amis.py introuvable dans %s", racine)
        return
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        _PROCESSUS_AMIS = subprocess.Popen([sys.executable, str(script)], cwd=str(racine), **options)
    except Exception:  # noqa: BLE001 - la fenetre Amis ne doit jamais faire tomber l'interface
        journal.exception("Fenetre Amis impossible")


'''
B_ANCRE = "        ligne.addSpacing(12)\n        menu = QPushButton(MODULE_MENU.libelle, self)\n"
B_AJOUT = '''        amis = QPushButton("AMIS", self)
        amis.setObjectName("commande")
        amis.setCursor(Qt.CursorShape.PointingHandCursor)
        amis.setToolTip("Amis : qui est connecté au bot, à jour, alertes, nouvelles installations")
        amis.setMinimumWidth(4 * 9 + 26)
        amis.clicked.connect(lambda _=False: ouvrir_fenetre_amis())
        ligne.addSpacing(12)
        ligne.addWidget(amis, 0, Qt.AlignmentFlag.AlignBottom)
'''
C_ANCRE = "QSize(1366, 720)"
C_NOUVEAU = "QSize(1480, 720)"


def main():
    if not CIBLE.exists():
        raise SystemExit(f"{CIBLE} introuvable : lance ce script depuis le dossier gimaly")
    brut = CIBLE.read_bytes().decode("utf-8")
    crlf = "\r\n" in brut
    t = brut.replace("\r\n", "\n")
    if "def ouvrir_fenetre_amis" in t:
        print("main_window.py : deja a jour")
        return 0
    for nom, a in (("CommandDock", A_ANCRE), ("bouton MENU", B_ANCRE), ("taille minimale", C_ANCRE)):
        if t.count(a) != 1:
            raise SystemExit(f"main_window.py : repere '{nom}' introuvable (une fois attendu) : RIEN ecrit. Envoie-moi le fichier.")
    t = t.replace(A_ANCRE, A_AJOUT + A_ANCRE, 1).replace(B_ANCRE, B_AJOUT + B_ANCRE, 1).replace(C_ANCRE, C_NOUVEAU, 1)
    compile(t, str(CIBLE), "exec")
    copie = CIBLE.with_name(CIBLE.name + ".avant_amis")
    if not copie.exists():
        shutil.copy2(CIBLE, copie)
    CIBLE.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("main_window.py : bouton AMIS ajoute (sauvegarde : main_window.py.avant_amis). Ferme puis relance GIMALY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
