# -*- coding: utf-8 -*-
"""Correctif 7.11 : un fichier config.local.yaml illisible ne doit plus jamais rendre le bot muet sans que personne le sache.

Contexte : l'ancien terminal_dedie.py ecrivait  trading_mt5_chemin: "C:\\Program Files\\..."  (guillemets doubles). En YAML,
\\P est invalide : TOUT le fichier devenait illisible et le bot retombait en silence sur ses valeurs par defaut (inactif,
pas de signaux distants). Ce patch, a lancer dans TON dossier gimaly (celui d'ou tu generes le paquet) :
  1. outils_v7\\lancer.py : au lancement puis toutes les 10 min, verifie que config.local.yaml est lisible ; repare la ligne
     trading_mt5_chemin si c'est elle ; sinon l'ecrit dans le journal du lanceur ET le signale dans le signe de vie
     (la fenetre Amis affichera « CONFIG ILLISIBLE ») ;
  2. gimaly\\trading\\trading.py : si une seule ligne est invalide, le bot lit les autres lignes et l'ecrit dans son journal ;
  3. creer_installateur_v7.py : le terminal_dedie.py du paquet ecrit desormais le chemin entre guillemets simples.
Sauvegardes : *.avant_cfg. Idempotent. Rien n'est ecrit si un repere manque.
Usage (dossier gimaly) :  .\\.venv\\Scripts\\python.exe patch_config_robuste.py
Ensuite : publier_maj.py (comme d'habitude) pour que tes amis l'aient automatiquement.
"""
import base64
import re
import shutil
import sys
import zlib
from pathlib import Path

RACINE = Path.cwd()
LANCEUR = RACINE / "outils_v7" / "lancer.py"
GENERATEUR = RACINE / "creer_installateur_v7.py"
TRADING = RACINE / "gimaly" / "trading" / "trading.py"
BLOB = "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"

# ------------------------------------------------------------------------------------------------ lancer.py
L_FONCTIONS = '''CONFIG = RACINE / "config.local.yaml"
_CONFIG_SIGNALEE = {"msg": None}


def verifier_config():
    """True si config.local.yaml est lisible. Sinon le bot retombe en silence sur ses valeurs par defaut (inactif, sans
    signaux) : on repare le cas connu (chemin MT5 entre guillemets doubles) ou on le dit clairement."""
    import re
    try:
        import yaml
    except ImportError:
        return True
    try:
        brut = CONFIG.read_bytes()
    except OSError:
        return True
    erreur = ""
    try:
        texte = brut.decode("utf-8-sig")
        yaml.safe_load(texte)
        _CONFIG_SIGNALEE["msg"] = None
        return True
    except Exception as exc:  # noqa: BLE001
        erreur = (str(exc).splitlines() or [repr(exc)])[0]
        texte = brut.decode("utf-8-sig", "replace")
    nouveau = re.sub(r'(?m)^(trading_mt5_chemin:[ \\t]*)"([^"\\r\\n]*)"',
                     lambda m: m.group(1) + "'" + m.group(2).replace("'", "''") + "'", texte)
    if nouveau != texte:
        try:
            yaml.safe_load(nouveau)
            copie = CONFIG.with_name("config.local.yaml.avant_reparation")
            if not copie.exists():
                copie.write_bytes(brut)
            CONFIG.write_bytes((b"\\xef\\xbb\\xbf" if brut.startswith(b"\\xef\\xbb\\xbf") else b"") + nouveau.encode("utf-8"))
            journal("config.local.yaml : ligne trading_mt5_chemin reparee (guillemets doubles illisibles pour le bot)")
            _CONFIG_SIGNALEE["msg"] = None
            return True
        except Exception:  # noqa: BLE001
            pass
    msg = (f"ALERTE config.local.yaml illisible ({erreur}) : le bot tourne avec ses valeurs par defaut, donc SANS trader. "
           f"Previens l'editeur.")
    if _CONFIG_SIGNALEE["msg"] != msg:
        journal(msg)
        _CONFIG_SIGNALEE["msg"] = msg
    return False


'''
L_MODIFS = [
    ("_VERROU_MT5 = threading.Lock()\n", L_FONCTIONS + "_VERROU_MT5 = threading.Lock()\n"),
    ("    journal(\"lanceur demarre (Ctrl+C ou fichier lanceur.stop pour l'arreter)\")\n",
     "    journal(\"lanceur demarre (Ctrl+C ou fichier lanceur.stop pour l'arreter)\")\n    verifier_config()\n"),
    ('                    etat_bot = "arrete" if not vivant else ("pause" if STOP_TRADES.exists() else "actif")\n',
     '                    etat_bot = "arrete" if not vivant else ("pause" if STOP_TRADES.exists() else "actif")\n'
     '                    if vivant and not verifier_config():\n'
     '                        etat_bot = "config"              # visible dans la fenetre Amis de l\'editeur\n'),
]

# ------------------------------------------------------------------------------------------------ trading.py
T_HELPER = '''_YAML_SIGNALE = set()


def _lire_yaml_tolerant(yaml, fichier):
    """yaml.safe_load, mais si UNE ligne est invalide (par exemple un chemin Windows entre guillemets doubles), on lit les
    autres lignes au lieu de perdre TOUT le fichier (le bot retomberait en silence sur ses valeurs par defaut)."""
    texte = fichier.read_text(encoding="utf-8-sig")
    try:
        return yaml.safe_load(texte)
    except Exception as exc:  # noqa: BLE001
        donnees, ignorees = {}, []
        for ligne in texte.splitlines():
            if not ligne.strip() or ligne[0] in " \\t#" or ":" not in ligne:
                continue
            try:
                un = yaml.safe_load(ligne)
            except Exception:  # noqa: BLE001
                ignorees.append(ligne.split(":", 1)[0])
                continue
            if isinstance(un, dict):
                donnees.update(un)
        cle = (str(fichier), tuple(ignorees))
        if cle not in _YAML_SIGNALE:
            _YAML_SIGNALE.add(cle)
            premiere = (str(exc).splitlines() or [repr(exc)])[0]
            journal(f"ALERTE {fichier.name} : ligne(s) illisible(s) ignoree(s) : {', '.join(ignorees) or '?'} ({premiere})")
        return donnees


'''
T_MODIFS = [
    ("def _yaml_local():\n", T_HELPER + "def _yaml_local():\n"),
    ('            donnees = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}\n',
     "            donnees = _lire_yaml_tolerant(yaml, fichier) or {}\n"),
]


def lire(chemin):
    brut = chemin.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    texte = brut.decode("utf-8-sig")
    crlf = "\r\n" in texte
    return bom, crlf, texte.replace("\r\n", "\n")


def ecrire(chemin, bom, crlf, texte):
    copie = chemin.with_name(chemin.name + ".avant_cfg")
    if not copie.exists():
        shutil.copy2(chemin, copie)
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    chemin.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def appliquer(chemin, marque, modifs, nom):
    """Renvoie (bom, crlf, nouveau_texte) ou None si deja fait ; SystemExit si un repere manque."""
    bom, crlf, t = lire(chemin)
    if marque in t:
        print(f"{nom} : deja a jour")
        return None
    for ancien, nouveau in modifs:
        if t.count(ancien) != 1:
            raise SystemExit(f"{nom} : repere introuvable (une fois attendu) : RIEN ecrit. Envoie-moi ce fichier.\n{ancien[:90]}")
        t = t.replace(ancien, nouveau, 1)
    compile(t.lstrip("\ufeff"), nom, "exec")
    return bom, crlf, t


def generateur():
    bom, crlf, t = lire(GENERATEUR)
    nouveau = zlib.decompress(base64.b64decode(BLOB)).decode("utf-8")
    compile(nouveau, "terminal_dedie.py", "exec")
    m = re.search(r"TERMINAL_DEDIE_B64 = \((.*?)\n\)\n", t, re.S)
    if not m:
        raise SystemExit("creer_installateur_v7.py : TERMINAL_DEDIE_B64 introuvable : RIEN ecrit")
    actuel = zlib.decompress(base64.b64decode("".join(re.findall(r'"([^"]*)"', m.group(1))))).decode("utf-8")
    if actuel == nouveau:
        print("creer_installateur_v7.py : terminal_dedie deja a jour")
        return None
    lignes = [BLOB[i:i + 100] for i in range(0, len(BLOB), 100)]
    bloc = "TERMINAL_DEDIE_B64 = (\n" + "\n".join(f'    "{x}"' for x in lignes) + "\n)\n"
    t = t[:m.start()] + bloc + t[m.end():]
    compile(t.lstrip("\ufeff"), "creer_installateur_v7.py", "exec")
    return bom, crlf, t


def main():
    for f in (LANCEUR, GENERATEUR, TRADING):
        if not f.exists():
            raise SystemExit(f"{f} introuvable : lance ce script depuis le dossier gimaly (celui d'ou tu generes le paquet)")
    travaux = [(LANCEUR, appliquer(LANCEUR, "def verifier_config", L_MODIFS, "outils_v7/lancer.py")),
               (TRADING, appliquer(TRADING, "_lire_yaml_tolerant", T_MODIFS, "gimaly/trading/trading.py")),
               (GENERATEUR, generateur())]
    for chemin, res in travaux:            # tout est verifie avant d'ecrire quoi que ce soit
        if res is not None:
            ecrire(chemin, *res)
            print(f"{chemin.name} : corrige (sauvegarde {chemin.name}.avant_cfg)")
    print("Termine. Prochaine etape : publier_maj.py (comme d'habitude).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
