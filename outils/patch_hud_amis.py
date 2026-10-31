# -*- coding: utf-8 -*-
"""Ajoute un bouton « AMIS » dans la barre du HUD GIMALY : il ouvre la fenetre de suivi des amis (suivi_amis.py,
dans un processus a part : le HUD n'est pas ralenti, et une erreur dans la fenetre ne peut pas l'arreter).

A lancer depuis le dossier gimaly (apres patch_amis.py et le telechargement de suivi_amis.py) :
  .\\.venv\\Scripts\\python.exe patch_hud_amis.py
Sauvegarde : gimaly\\ui\\hud.py.avant_amis. Idempotent. Rien n'est ecrit si un repere manque.
Ensuite : relance GIMALY (le HUD) pour voir le bouton.
"""
import shutil
import sys
from pathlib import Path

HUD = Path.cwd() / "gimaly" / "ui" / "hud.py"
ANCRE_BOUTON = '            ("FOND", self.choisir_fond, "Changer l\'image de fond"),\n'
AJOUT_BOUTON = ('            ("AMIS", self.ouvrir_amis,\n'
                '             "Amis : qui est connecte au bot, a jour, alertes, nouvelles installations"),\n')
ANCRE_METHODE = "    def _montrer_bulle(self, texte: str) -> None:\n"
METHODE = '''    def ouvrir_amis(self) -> None:
        """Ouvre la fenetre « Amis » (suivi_amis.py) dans un processus a part, une seule a la fois."""
        import subprocess
        import sys as _sys

        existant = getattr(self, "_processus_amis", None)
        if existant is not None and existant.poll() is None:
            return
        script = ROOT_PROJET / "suivi_amis.py"
        if not script.exists():
            self._montrer_bulle("suivi_amis.py est introuvable dans le dossier gimaly")
            return
        options = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self._processus_amis = subprocess.Popen([_sys.executable, str(script)], cwd=str(ROOT_PROJET), **options)
        except Exception as exc:  # noqa: BLE001
            self._montrer_bulle(f"fenetre Amis impossible : {exc}"[:120])

'''


def main():
    if not HUD.exists():
        raise SystemExit(f"{HUD} introuvable : lance ce script depuis le dossier gimaly")
    brut = HUD.read_bytes()
    texte = brut.decode("utf-8")
    crlf = "\r\n" in texte
    t = texte.replace("\r\n", "\n")
    if "def ouvrir_amis" in t:
        print("hud.py : deja a jour")
        return 0
    for nom, a in (("bouton FOND", ANCRE_BOUTON), ("_montrer_bulle", ANCRE_METHODE)):
        if t.count(a) != 1:
            raise SystemExit(f"hud.py : repere '{nom}' introuvable (une fois attendu) : RIEN ecrit. Envoie-moi hud.py.")
    t = t.replace(ANCRE_BOUTON, AJOUT_BOUTON + ANCRE_BOUTON, 1).replace(ANCRE_METHODE, METHODE + ANCRE_METHODE, 1)
    compile(t, str(HUD), "exec")
    copie = HUD.with_name(HUD.name + ".avant_amis")
    if not copie.exists():
        shutil.copy2(HUD, copie)
    HUD.write_bytes((t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("hud.py : bouton AMIS ajoute (sauvegarde : hud.py.avant_amis). Relance GIMALY pour le voir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
