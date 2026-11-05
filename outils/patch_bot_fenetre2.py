# -*- coding: utf-8 -*-
r"""Patch : la fenetre BOT utilise le « poste de pilotage » du bot (FenetrePanneau) au lieu du volet etire.

Probleme corrige : en agrandissant la fenetre BOT, le graphique, le tableau des icebergs et le bloc « BOT DE TRADING » se
superposaient (le volet empile tout dans une colonne qui a une hauteur minimale). FenetrePanneau est la vraie fenetre prevue pour
ca : graphique et tableau dans un separateur, onglets BOT / FLUX / CALENDRIER / MACRO / SIGNAUX / BILAN qui defilent. Elle ne lance
ni le bot ni le detecteur (le panneau cache de GIMALY s'en charge deja) : aucun double ordre possible.
Remplace la version de patch_bot_fenetre si elle est deja installee. Modifie gimaly/v2/app/integre.py seulement.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_bot_fenetre2.py   puis redemarrer GIMALY (fenetre principale).
Sauvegarde : integre.py.avant_bot_fenetre2. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "v2" / "app" / "integre.py"
MARQUE = "FenetrePanneau(self.hud.assistant"

METHODE_ANCIENNE = '    def ouvrir_fenetre_bot(self) -> None:\n        """Le bot XAUUSD dans sa propre fenetre : elle reste ouverte quand on clique ailleurs."""\n        from PySide6.QtCore import Qt\n        from PySide6.QtWidgets import QVBoxLayout, QWidget\n\n        panneau = getattr(self.hud, "panneau_icebergs", None)\n        if panneau is None:\n            return\n        fenetre = getattr(self, "_fenetre_bot", None)\n        if fenetre is None:\n            fenetre = QWidget(None, Qt.WindowType.Window)\n            fenetre.setObjectName("fenetre_bot")\n            fenetre.setWindowTitle("BOT XAUUSD - GIMALY")\n            fenetre.setStyleSheet("QWidget#fenetre_bot{background:#070d14;}")\n            boite = QVBoxLayout(fenetre)\n            boite.setContentsMargins(12, 12, 12, 12)\n            boite.addWidget(panneau)\n            fenetre.resize(1280, 820)\n            self._fenetre_bot = fenetre\n        panneau.show()\n        if fenetre.isMinimized():\n            fenetre.showNormal()\n        fenetre.show()\n        fenetre.raise_()\n        fenetre.activateWindow()\n\n'
METHODE = '    def ouvrir_fenetre_bot(self) -> None:\n        """Le bot XAUUSD dans sa propre fenetre (le « poste de pilotage » de l\'ancien bouton PLEIN ECRAN) :\n        graphique redimensionnable, onglets qui defilent, rien ne se superpose. Echap = fermer, F11 = plein ecran."""\n        from PySide6.QtGui import QGuiApplication\n\n        panneau = getattr(self.hud, "panneau_icebergs", None)\n        if panneau is None:\n            return\n        fenetre = getattr(self, "_fenetre_bot", None)\n        if fenetre is not None:\n            try:\n                if fenetre.isMinimized():\n                    fenetre.showNormal()\n                fenetre.show()\n                fenetre.raise_()\n                fenetre.activateWindow()\n                return\n            except RuntimeError:          # fenetre deja detruite par sa croix\n                self._fenetre_bot = None\n        from gimaly.ui.icebergs_panneau import FenetrePanneau\n\n        fenetre = FenetrePanneau(self.hud.assistant, getattr(panneau, "police", None))\n        fenetre.destroyed.connect(lambda *_: setattr(self, "_fenetre_bot", None))\n        ecran = QGuiApplication.primaryScreen()\n        if ecran is not None:\n            zone = ecran.availableGeometry()\n            fenetre.resize(int(zone.width() * 0.85), int(zone.height() * 0.85))\n        self._fenetre_bot = fenetre\n        fenetre.show()\n        fenetre.raise_()\n        fenetre.activateWindow()\n\n'
ANCRE_ACTIONS = "    def actions(self, ouvrir_console: Callable[[], None]) -> dict[str, Callable[[], None]]:\n"
ANCRE_TABLE = '        if "bot" not in table:\n            table["bot"] = ouvrir_console\n'
SUITE_TABLE = '        elif getattr(hud, "panneau_icebergs", None) is not None:\n            table["bot"] = self.ouvrir_fenetre_bot\n'


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), brut.count(b"\r\n") > brut.count(b"\n") / 2
    if MARQUE in txt:
        print("integre.py : deja corrige (rien a faire).")
        return 0
    if METHODE_ANCIENNE in txt:
        txt = txt.replace(METHODE_ANCIENNE, METHODE)
    elif "def ouvrir_fenetre_bot" in txt:
        print("REPERE INTROUVABLE : la methode ouvrir_fenetre_bot a une forme inattendue. Rien n'est modifie. Envoie-moi integre.py.")
        return 2
    else:
        if txt.count(ANCRE_ACTIONS) != 1 or txt.count(ANCRE_TABLE) != 1:
            print("REPERE INTROUVABLE (ou en double) dans integre.py : rien n'est modifie.")
            return 2
        txt = txt.replace(ANCRE_ACTIONS, METHODE + ANCRE_ACTIONS).replace(ANCRE_TABLE, ANCRE_TABLE + SUITE_TABLE)
    try:
        compile(txt, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_bot_fenetre2"))
    sortie = txt.replace("\n", "\r\n") if crlf else txt
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("integre.py : corrige (sauvegarde integre.py.avant_bot_fenetre2). Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
