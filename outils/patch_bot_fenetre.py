# -*- coding: utf-8 -*-
r"""Patch : le module BOT s'ouvre dans sa propre fenetre (comme PERFORMANCE et AMIS) au lieu d'un volet qui se referme.

Avant : BOT ouvrait un volet dans la fenetre principale ; un seul volet a la fois, donc il se fermait des qu'on ouvrait autre chose.
Apres : BOT ouvre une vraie fenetre independante avec le meme panneau (graphique, flux d'ordres, icebergs...), qui reste ouverte
quand on clique ailleurs ; elle se ferme avec sa croix et un nouveau clic sur BOT la remet devant.
Modifie : gimaly/v2/app/integre.py (rien dans le bot, rien dans hud.py).
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_bot_fenetre.py   puis redemarrer GIMALY (fenetre principale).
Sauvegarde : integre.py.avant_bot_fenetre. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "v2" / "app" / "integre.py"
MARQUE = "ouvrir_fenetre_bot"

METHODE = '''    def ouvrir_fenetre_bot(self) -> None:
        """Le bot XAUUSD dans sa propre fenetre : elle reste ouverte quand on clique ailleurs."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        panneau = getattr(self.hud, "panneau_icebergs", None)
        if panneau is None:
            return
        fenetre = getattr(self, "_fenetre_bot", None)
        if fenetre is None:
            fenetre = QWidget(None, Qt.WindowType.Window)
            fenetre.setObjectName("fenetre_bot")
            fenetre.setWindowTitle("BOT XAUUSD - GIMALY")
            fenetre.setStyleSheet("QWidget#fenetre_bot{background:#070d14;}")
            boite = QVBoxLayout(fenetre)
            boite.setContentsMargins(12, 12, 12, 12)
            boite.addWidget(panneau)
            fenetre.resize(1280, 820)
            self._fenetre_bot = fenetre
        panneau.show()
        if fenetre.isMinimized():
            fenetre.showNormal()
        fenetre.show()
        fenetre.raise_()
        fenetre.activateWindow()

'''
CH = [
    ("    def actions(self, ouvrir_console: Callable[[], None]) -> dict[str, Callable[[], None]]:\n",
     METHODE + "    def actions(self, ouvrir_console: Callable[[], None]) -> dict[str, Callable[[], None]]:\n"),
    ('        if "bot" not in table:\n            table["bot"] = ouvrir_console\n',
     '        if "bot" not in table:\n            table["bot"] = ouvrir_console\n'
     '        elif getattr(hud, "panneau_icebergs", None) is not None:\n            table["bot"] = self.ouvrir_fenetre_bot\n'),
]


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
    manquants = [a.strip()[:90] for a, _ in CH if txt.count(a) != 1]
    if manquants:
        print("REPERE INTROUVABLE (ou en double) dans integre.py : rien n'est modifie. Envoie-moi cette erreur :")
        print("\n".join(manquants))
        return 2
    for a, b in CH:
        txt = txt.replace(a, b)
    try:
        compile(txt, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_bot_fenetre"))
    sortie = txt.replace("\n", "\r\n") if crlf else txt
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("integre.py : corrige (sauvegarde integre.py.avant_bot_fenetre). Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
