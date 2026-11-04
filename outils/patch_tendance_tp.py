# -*- coding: utf-8 -*-
r"""Patch : objectif des moteurs tendance_m5 et tendance_pullback a 3R (au lieu de 2R) et SANS ramener l'objectif vers le niveau de marche
le plus proche (qui le ramenait souvent a 1R-1,5R). Un marche directionnel doit etre exploite : plafond bas = gains trop petits face au stop.
Le contexte du trade porte tp_fixe: true ; le scalp n'est pas touche (il garde sa regle des niveaux). Les amis recoivent le meme objectif
(l'objectif en R reellement pose est deja envoye) ; leur bot ne le ramene pas non plus des qu'il a ce patch (prochaine mise a jour).
Reglage : trading_tendance_tp_r (valeur initiale 3.0). Retour en arriere : trading_tendance_tp_r: 2 (le niveau le plus proche reste ignore
pour ces moteurs ; restaurer trading.py.avant_tp pour tout annuler).
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_tendance_tp.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_tp. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = 'and not (contexte or {}).get("tp_fixe")'

A1 = '"trading_tendance_tp_r", 2.0)'
B1 = '"trading_tendance_tp_r", 3.0)'
A2 = '''"tp_r": r["tendance_tp_r"],
                        "duree_max_min": 240, "prix_xau": prix}'''
B2 = '''"tp_r": r["tendance_tp_r"],
                        "tp_fixe": True, "duree_max_min": 240, "prix_xau": prix}'''
A3 = '"tp_r": r["tendance_tp_r"], "duree_max_min": 240, "prix_xau": prix}'
B3 = '"tp_r": r["tendance_tp_r"], "tp_fixe": True, "duree_max_min": 240, "prix_xau": prix}'
A4 = '            if self.reglages.get("tp_niveau", True):\n'
B4 = '            if self.reglages.get("tp_niveau", True) and not (contexte or {}).get("tp_fixe"):\n'
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
    shutil.copy2(F, F.with_name(F.name + ".avant_tp"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_tp). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
