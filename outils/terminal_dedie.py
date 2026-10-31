# -*- coding: utf-8 -*-
"""TERMINAL MT5 DEDIE AU BOT : le bot se connecte a un AUTRE MetaTrader 5 que celui que tu utilises toi-meme.

Un MetaTrader 5 ne peut etre connecte qu'a UN compte a la fois. Si tu trades a la main sur un compte reel et que
le bot a un compte demo, ils se genent : le bot attend « son » compte, ou lit le solde du mauvais compte.
Solution : DEUX MetaTrader 5 installes cote a cote. Le premier (le tien, avec ton compte reel) n'est jamais touche ;
le second, reserve au bot, reste connecte au compte demo.

1) Installe un 2e MetaTrader 5 dans un AUTRE dossier (par ex. C:\\MT5-Bot) : installe-le depuis le site de ton courtier,
   en choisissant ce dossier, puis connecte-le au compte DEMO du bot (« Enregistrer le mot de passe » coche) et
   active le bouton Algo Trading.
2) Lance ce script depuis le dossier gimaly :
     .\\.venv\\Scripts\\python.exe terminal_dedie.py "C:\\MT5-Bot\\terminal64.exe"
   (sans argument, il cherche les terminal64.exe installes et te les liste)
3) Redemarre GIMALY / le bot.

Ce que fait le script (sauvegardes, rejouable sans risque) :
  * ecrit  trading_mt5_chemin: "<chemin>"  dans config.local.yaml ;
  * ajoute un petit fichier  sitecustomize.py  dans .venv\\Lib\\site-packages : il dit a la liaison MetaTrader 5 de
    Python (dans le bot ET dans le panneau) d'ouvrir CE terminal-la ;
  * ne touche a aucun autre fichier.
Retour en arriere :  .\\.venv\\Scripts\\python.exe terminal_dedie.py --retirer   (ou supprime la ligne de config).
"""
import re
import shutil
import site
import sys
from pathlib import Path

RACINE = Path.cwd()
CONFIG = RACINE / "config.local.yaml"
MARQUE = "# GIMALY-TERMINAL-DEDIE"

SITECUSTOMIZE = MARQUE + '''
# Genere par terminal_dedie.py : oriente MetaTrader5.initialize() vers le terminal choisi pour le bot
# (cle trading_mt5_chemin de config.local.yaml). Sans cle, comportement normal.
try:
    import os as _os
    import re as _re

    _GIMALY_CONFIG = r"%s"

    def _gimaly_chemin():
        try:
            with open(_GIMALY_CONFIG, encoding="utf-8-sig") as _f:
                _m = _re.search(r'(?m)^trading_mt5_chemin:[ \\t]*["\\']?([^"\\'#\\r\\n]+?)["\\']?[ \\t]*(?:#.*)?$', _f.read())
        except OSError:
            return ""
        _p = _m.group(1).strip() if _m else ""
        return _p if _p and _os.path.isfile(_p) else ""

    import MetaTrader5 as _mt5

    if not getattr(_mt5, "_gimaly_dedie", False):
        _initialize_origine = _mt5.initialize

        def _initialize_dedie(*args, **kwargs):
            if not args and "path" not in kwargs:
                _chemin = _gimaly_chemin()
                if _chemin:
                    kwargs["path"] = _chemin
            return _initialize_origine(*args, **kwargs)

        _mt5.initialize = _initialize_dedie
        _mt5._gimaly_dedie = True
except Exception:
    pass
'''


def dossier_site():
    for d in site.getsitepackages():
        if d.lower().endswith("site-packages") and Path(d).is_dir():
            return Path(d)
    raise SystemExit("dossier site-packages du venv introuvable : lance ce script avec .venv\\Scripts\\python.exe")


def ecrire_config(valeur):
    texte = CONFIG.read_bytes().decode("utf-8-sig") if CONFIG.exists() else ""
    crlf = "\r\n" in texte
    texte = texte.replace("\r\n", "\n")
    motif = re.compile(r"(?m)^trading_mt5_chemin:[^\n]*$")
    ligne = f'trading_mt5_chemin: "{valeur}"' if valeur else "trading_mt5_chemin: \"\""
    if motif.search(texte):
        texte = motif.sub(lambda m: ligne, texte, count=1)
    else:
        texte = (texte.rstrip("\n") + "\n\n# terminal MetaTrader 5 reserve au bot (terminal_dedie.py)\n" + ligne + "\n")
    if crlf:
        texte = texte.replace("\n", "\r\n")
    if CONFIG.exists():
        sauvegarde = CONFIG.with_name("config.local.avant_terminal.yaml")
        if not sauvegarde.exists():
            shutil.copy2(CONFIG, sauvegarde)
    CONFIG.write_bytes(texte.encode("utf-8"))


def trouver_terminaux():
    bases = [Path(p) for p in (r"C:\Program Files", r"C:\Program Files (x86)", r"C:\\", str(Path.home()))]
    vus = []
    for b in bases:
        if not b.is_dir():
            continue
        try:
            for niveau in ("*/terminal64.exe", "*/*/terminal64.exe"):
                for f in b.glob(niveau):
                    if f not in vus:
                        vus.append(f)
        except OSError:
            pass
    return vus


def main(args):
    if not CONFIG.exists():
        sys.exit(f"{CONFIG} introuvable : lance ce script depuis le dossier gimaly")
    cible = dossier_site() / "sitecustomize.py"
    if args and args[0] == "--retirer":
        ecrire_config("")
        if cible.exists() and MARQUE in cible.read_text(encoding="utf-8", errors="ignore"):
            cible.unlink()
        print("OK : terminal dedie retire (le bot reprend le comportement normal). Redemarre GIMALY.")
        return
    if not args:
        liste = trouver_terminaux()
        print("Indique le terminal MT5 du bot, par exemple :")
        print('  .\\.venv\\Scripts\\python.exe terminal_dedie.py "C:\\MT5-Bot\\terminal64.exe"\n')
        print("terminal64.exe trouves sur ce PC :" if liste else "Aucun terminal64.exe trouve automatiquement.")
        for f in liste:
            print("  " + str(f))
        return
    chemin = Path(args[0].strip('"'))
    if chemin.name.lower() != "terminal64.exe" or not chemin.is_file():
        sys.exit(f"{chemin} n'est pas un terminal64.exe existant : rien n'a ete change")
    if cible.exists() and MARQUE not in cible.read_text(encoding="utf-8", errors="ignore"):
        sys.exit(f"{cible} existe deja et n'est pas de GIMALY : rien n'a ete change")
    cible.write_text(SITECUSTOMIZE % str(CONFIG), encoding="utf-8")
    compile(cible.read_text(encoding="utf-8"), str(cible), "exec")
    ecrire_config(str(chemin))
    print(f"OK : le bot utilisera le terminal {chemin}")
    print("Dans CE terminal : connecte le compte DEMO du bot et active Algo Trading. Puis redemarre GIMALY.")


if __name__ == "__main__":
    main(sys.argv[1:])
