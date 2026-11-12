# -*- coding: utf-8 -*-
"""Signal scalp_keltner_large : stop ET objectif multiplies par k (reglage trading_keltner_large_k, 1,5 par defaut une fois installe), risque constant en R.
Pourquoi : test_respirer.py (12/11/2026, 11 864 signaux sur 10 mois) montre que la meme strategie avec stop et objectif x1,5 / x2 / x3 coute moins cher en spread
(+0,03 a +0,045 R par trade, intervalle qui exclut 0, deux moities dans le meme sens). Le signal brut ne gagne pas plus : c'est un gain de COUT, pas de prevision.
Ce que fait le patch : dans trading.py, pour un signal PROPRE au bot (genre scalp_keltner_large, ni signal recu d'un editeur, ni distance imposee), la distance au stop
mesuree au moment de l'ordre est multipliee par k ; l'objectif (1,5 R de la nouvelle distance) et le volume (1 % de risque) suivent. Les amis recoivent des
distances deja multipliees (distance publiee = celle du trade). k = 1 ou reglage absent = comportement actuel.
Ajoute aussi trading_keltner_large_k: 1.5 dans config.local.yaml (sauvegarde config.local.yaml.avant_keltner_k) et note la date dans GIMALY\\trading\\notes_reglages.txt.
Option --lots : ramene trading_lots_max a (valeur d'origine / k), pour que le risque en euros par trade reste celui d'avant quand le plafond de lots est atteint (voir ci-dessous).
Retour arriere : --annuler (restaure trading.py et config.local.yaml). Pour changer k : modifier la valeur dans config.local.yaml puis redemarrer le bot.
Idempotent. Rien n'est ecrit si un repere manque ou si le fichier ne compile plus.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_keltner_large_k.py [--annuler]   puis .\\.venv\\Scripts\\python.exe redemarrer_bot.py"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
SAUVEGARDE = F.with_name(F.name + ".avant_keltner_k")
CFG = Path.cwd() / "config.local.yaml"
CFG_SAUV = CFG.with_name(CFG.name + ".avant_keltner_k")
NOTES = Path.home() / "GIMALY" / "trading" / "notes_reglages.txt"
K = "1.5"
CLE = "trading_keltner_large_k"

REMPLACEMENTS = [
    ("reglage keltner_large_k",
     '        "sl_min_pips": float(lire("trading_sl_min_pips", 15)),     # stop jamais plus court\n',
     '        "sl_min_pips": float(lire("trading_sl_min_pips", 15)),     # stop jamais plus court\n'
     '        "keltner_large_k": float(lire("trading_keltner_large_k", 1.0)),   # scalp_keltner_large : stop ET objectif x k (12/11)\n'),
    ("stop x k",
     '        distance = abs(pe - sl)\n'
     '        minimum = self.reglages["sl_min_pips"] / PIPS_PAR_DOLLAR\n'
     '        if distance < minimum:\n'
     '            # 29/09',
     '        k_large = float(self.reglages.get("keltner_large_k") or 1.0)\n'
     '        if genre == "scalp_keltner_large" and not distant and not distance_ref and sl_prix is not None and abs(k_large - 1.0) > 1e-9:\n'
     '            # 12/11 : stop ET objectif x k (le volume suit : 1 % de risque), moins de spread paye par R risque (test_respirer.py)\n'
     '            sl = pe - k_large * abs(pe - sl) if achat else pe + k_large * abs(pe - sl)\n'
     '        distance = abs(pe - sl)\n'
     '        minimum = self.reglages["sl_min_pips"] / PIPS_PAR_DOLLAR\n'
     '        if distance < minimum:\n'
     '            # 29/09'),
]


def lire_fichier(p):
    brut = p.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    crlf = "\r\n" in src
    return src.replace("\r\n", "\n"), bom, crlf


def ecrire_fichier(p, texte, bom, crlf):
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def lire_cle(texte, cle, defaut):
    m = re.search(rf"^\s*{cle}\s*:\s*([0-9.]+)", texte or "", re.M)
    return float(m.group(1)) if m else defaut


def regler_lots():
    """trading_lots_max = valeur d'origine / k. Valeur d'origine lue dans la sauvegarde de la config (avant le patch), sinon 1,5 (defaut du bot)."""
    if not CFG.exists():
        print("config.local.yaml introuvable.")
        return 1
    cfg, bom, crlf = lire_fichier(CFG)
    k = lire_cle(cfg, CLE, 1.0)
    base = 1.5
    if CFG_SAUV.exists():
        base = lire_cle(lire_fichier(CFG_SAUV)[0], "trading_lots_max", 1.5)
    else:
        base = lire_cle(cfg, "trading_lots_max", 1.5) * (k if "trading_lots_max_k" in cfg else 1.0)
        shutil.copy2(CFG, CFG_SAUV)
    cible = round(base / k, 2) if k > 0 else base
    ligne = f"trading_lots_max: {cible:g}          # 12/11 : plafond d'origine {base:g} / k {k:g} = meme risque en euros par trade"
    if re.search(r"^\s*trading_lots_max\s*:", cfg, re.M):
        nouveau = re.sub(r"^\s*trading_lots_max\s*:[^\r\n]*", ligne, cfg, flags=re.M)
    else:
        nouveau = cfg.rstrip("\n") + "\n" + ligne + "\n"
    ecrire_fichier(CFG, nouveau, bom, crlf)
    try:
        NOTES.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%d/%m/%Y %H:%M} : trading_lots_max = {cible:g} (origine {base:g} / k {k:g})\n")
    except OSError:
        pass
    print(f"trading_lots_max = {cible:g} (origine {base:g}, k = {k:g}). Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


def main():
    if "--lots" in sys.argv:
        return regler_lots()
    if "--annuler" in sys.argv:
        ok = False
        for src, dst in ((SAUVEGARDE, F), (CFG_SAUV, CFG)):
            if src.exists():
                shutil.copy2(src, dst)
                print(f"Restaure : {dst.name}")
                ok = True
        if not ok:
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        print("Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
        return 0
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    src, bom, crlf = lire_fichier(F)
    if '"keltner_large_k"' in src:
        print("Deja installe dans trading.py. (Pour changer k : modifie trading_keltner_large_k dans config.local.yaml puis redemarre le bot.)")
        return 0
    nouveau = src
    for nom, ancien, remplacant in REMPLACEMENTS:
        if nouveau.count(ancien) != 1:
            print(f"Repere introuvable ou ambigu ({nom}) : ton trading.py differe de celui que j'ai teste. RIEN n'est modifie.")
            return 1
        nouveau = nouveau.replace(ancien, remplacant)
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as e:
        print(f"Le fichier modifie ne compile pas ({e}) : RIEN n'est modifie.")
        return 1
    cfg_txt = cfg_bom = cfg_crlf = None
    if CFG.exists():
        cfg_txt, cfg_bom, cfg_crlf = lire_fichier(CFG)
        if re.search(rf"^\s*{CLE}\s*:", cfg_txt, re.M):
            print(f"{CLE} est deja dans config.local.yaml : je ne le modifie pas.")
            cfg_txt = None
        else:
            cfg_txt = cfg_txt.rstrip("\n") + f"\n{CLE}: {K}          # 12/11 : stop et objectif x k pour scalp_keltner_large (1 = comportement d'avant)\n"
    shutil.copy2(F, SAUVEGARDE)
    ecrire_fichier(F, nouveau, bom, crlf)
    if cfg_txt is not None:
        shutil.copy2(CFG, CFG_SAUV)
        ecrire_fichier(CFG, cfg_txt, cfg_bom, cfg_crlf)
    elif not CFG.exists():
        print("config.local.yaml introuvable : ajoute a la main la ligne  " + f"{CLE}: {K}  (sinon k reste a 1 = comportement d'avant).")
    try:
        NOTES.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%d/%m/%Y %H:%M} : {CLE} = {K} (stop et objectif x k, scalp_keltner_large)\n")
    except OSError:
        pass
    print(f"Installe ({len(REMPLACEMENTS)} modifications, sauvegarde {SAUVEGARDE.name}). Relance le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
