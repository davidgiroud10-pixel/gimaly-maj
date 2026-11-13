# -*- coding: utf-8 -*-
r"""Patch : le bot ne perd plus le graphique / le contexte quand MT5 renvoie des bougies M1 vides.
Probleme vu le 13/11 : chaque minute « Liquidite non calculee : UnboundLocalError('bougies') » -> prix, graphique, liquidite et contexte figes.
Ce que fait le patch (gimaly/trading/icebergs.py, methode _maj_mt5) :
  1. `bougies` part de la derniere serie connue (au lieu de ne pas exister) : plus d'UnboundLocalError ;
  2. si MT5 renvoie < 51 bougies M1 : le bot note l'erreur MT5 (last_error) dans la console, re-selectionne le symbole, attend 1 s et REESSAIE une fois, puis ecrit le resultat
     (« Bougies M1 MT5 vides (n=..., erreur ...) : nouvel essai -> n=... ») : on saura enfin POURQUOI MT5 ne repond pas.
Aucune regle de trading n'est touchee. Sauvegarde icebergs.py.avant_bougies_vides. Retour arriere : --annuler. Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_bougies_vides.py [--annuler]   puis redemarrer le bot (redemarrer_bot.py)."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "icebergs.py"
SAUV = F.with_name(F.name + ".avant_bougies_vides")
MARQUE = "Bougies M1 MT5 vides"
ANCRE = ("                rates = self.mt5.copy_rates_from_pos(symbole_or(), self.mt5.TIMEFRAME_M1, 1, 1500)\n"
         "                if rates is not None and len(rates) > 50:\n")
NOUVEAU = (
    "                bougies = self._bougies_m1 or []          # 13/11 : derniere serie connue si MT5 ne renvoie rien\n"
    "                rates = self.mt5.copy_rates_from_pos(symbole_or(), self.mt5.TIMEFRAME_M1, 1, 1500)\n"
    "                if rates is None or len(rates) <= 50:\n"
    "                    _n1 = None if rates is None else len(rates)\n"
    "                    _err = self.mt5.last_error()\n"
    "                    try:\n"
    "                        self.mt5.symbol_select(symbole_or(), True)\n"
    "                        time.sleep(1.0)\n"
    "                        rates = self.mt5.copy_rates_from_pos(symbole_or(), self.mt5.TIMEFRAME_M1, 1, 1500)\n"
    "                    except Exception as _e_r:\n"
    "                        print(f\"Bougies M1 MT5 : nouvel essai impossible ({_e_r!r})\")\n"
    "                    print(f\"Bougies M1 MT5 vides (n={_n1}, erreur {_err}) : nouvel essai -> n={None if rates is None else len(rates)}\")\n"
    "                if rates is not None and len(rates) > 50:\n")


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    if "--annuler" in sys.argv:
        if SAUV.exists():
            shutil.copy2(SAUV, F)
            print("icebergs.py restaure. Redemarre le bot.")
        else:
            print("Aucune sauvegarde : rien a annuler.")
        return 0
    brut = F.read_bytes()
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), brut.count(b"\r\n") > brut.count(b"\n") / 2
    if MARQUE in txt:
        print("Deja installe (rien a faire).")
        return 0
    if txt.count(ANCRE) != 1:
        print("REPERE INTROUVABLE (ou en double) dans icebergs.py : rien n'est modifie. Envoie-moi gimaly\\trading\\icebergs.py.")
        return 2
    nouveau = txt.replace(ANCRE, NOUVEAU)
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, SAUV)
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("Installe (sauvegarde icebergs.py.avant_bougies_vides). Redemarre le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
