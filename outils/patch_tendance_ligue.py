# -*- coding: utf-8 -*-
r"""Correctif de patch_tendance : les trades tendance_m5 sont ANNONCES DANS LA LIGUE (ils comptent au classement) au lieu d'etre prives.
Ils ne sont JAMAIS envoyes aux amis (signaux signes) : seuls les signaux du detecteur le sont. Retour au prive : trading_tendance_ligue: false.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_tendance_ligue.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_ligue. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "tendance_ligue"
CHANGEMENTS = [
    ('        "tendance_pause_min": float(lire("trading_tendance_pause_min", 30)),\n',
     '        "tendance_pause_min": float(lire("trading_tendance_pause_min", 30)),\n'
     '        "tendance_ligue": bool(lire("trading_tendance_ligue", True)),   # true = annonce dans la ligue (jamais aux amis)\n'),
    ('contexte = {"prive": True, "risque_facteur"', 'contexte = {"prive": not r.get("tendance_ligue", True), "risque_facteur"'),
]


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
    shutil.copy2(F, F.with_name(F.name + ".avant_ligue"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_ligue). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
