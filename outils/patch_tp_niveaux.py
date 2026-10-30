# -*- coding: utf-8 -*-
"""TP COHERENTS : pour les signaux a objectif fixe (scalps 1,5R, signaux 2R), le bot place le TP sur le
NIVEAU DU MARCHE le plus proche (liquidite, VWAP, POC, Keltner...), comme il place le stop, meme s'il ne
vaut que 1R. Sans niveau valable, le TP fixe du signal est conserve.

  * niveau retenu : le plus proche situe entre `trading_tp_niveau_r_min` (defaut 1,0 R) et l'objectif fixe
    du signal (1,5 R ou 2 R) : le TP n'est jamais plus loin qu'avant ;
  * la cible est placee 0,15 $ avant le niveau (comme pour les autres TP) ;
  * les amis recoivent l'objectif REELLEMENT pose (en multiple du risque) : leur TP suit le tien, meme
    avec l'ancienne version de leur bot.

Retour en arriere sans toucher au code :  trading_tp_niveau: false  dans config.local.yaml.

A lancer sur TON PC, depuis le dossier gimaly (sauvegarde trading.py.avant_tp_niveaux, idempotent) :
  .\\.venv\\Scripts\\python.exe patch_tp_niveaux.py
Puis redemarre le bot.
"""
import shutil
import sys
from pathlib import Path

CIBLE = Path.cwd() / "gimaly" / "trading" / "trading.py"

CONFIG_ANCIEN = '        "tp_r_min": float(lire("trading_tp_r_min", 1.5)),\n'
CONFIG_NOUVEAU = (CONFIG_ANCIEN +
                  '        "tp_niveau": bool(lire("trading_tp_niveau", True)),   # TP des scalps sur un niveau du marche\n'
                  '        "tp_niveau_r_min": float(lire("trading_tp_niveau_r_min", 1.0)),\n')

BLOC_ANCIEN = '''        if (contexte or {}).get("tp_r"):
            # objectif fixe impose par le signal (valeur initiale : 2R, un seul TP)
            tp_r = float(contexte["tp_r"])
            tp = [round(pe_reel + tp_r * distance_reelle if achat else pe_reel - tp_r * distance_reelle, 2)]
            raisons_tp = [f"{tp_r:g}R"]
'''
BLOC_NOUVEAU = BLOC_ANCIEN + '''            if self.reglages.get("tp_niveau", True):
                # TP coherent : le niveau du marche le plus proche (comme pour le stop), meme a 1R
                choix = self.tp_sur_niveau(achat, pe_reel, distance_reelle, tp_r)
                if choix:
                    tp, raisons_tp = [choix[0]], [choix[1]]
'''

METHODES_ANCIEN = "    def objectifs(self, achat, pe, distance):\n"
METHODES_NOUVEAU = '''    def tp_sur_niveau(self, achat, pe, distance, tp_r_max):
        """Signal a objectif fixe : le niveau du marche le plus proche dont le gain est compris entre
        `tp_niveau_r_min` et l'objectif fixe du signal. Renvoie (cible, nom du niveau) ou None (on garde
        alors l'objectif fixe)."""
        if distance <= 0:
            return None
        mini = self.reglages.get("tp_niveau_r_min", 1.0) * distance
        maxi = tp_r_max * distance
        meilleur = None
        for n in self.niveaux_marche():
            try:
                prix = float(n["prix"])
            except (KeyError, TypeError, ValueError):
                continue
            cible = prix - MARGE_TP if achat else prix + MARGE_TP
            gain = (cible - pe) if achat else (pe - cible)
            if gain < mini or gain > maxi:
                continue
            if meilleur is None or gain < meilleur[0]:
                meilleur = (gain, round(cible, 2), n.get("nom", "niveau"))
        return (meilleur[1], meilleur[2]) if meilleur else None

    def _contexte_publie(self, contexte, trade):
        """Contexte envoye aux amis : l'objectif en R est celui REELLEMENT pose (niveau ou fixe), pour que leur
        TP soit le meme multiple du risque que le tien."""
        if not contexte or not contexte.get("tp_r"):
            return contexte
        try:
            risque = abs(float(trade["pe"]) - float(trade["sl"]))
            gain = abs(float(trade["tp"][-1]) - float(trade["pe"]))
            if risque > 0 and gain > 0:
                return {**contexte, "tp_r": round(gain / risque, 2)}
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        return contexte

''' + METHODES_ANCIEN

PUBLIER_ANCIEN = '                "contexte": signal.get("contexte"), "ecarts": signal.get("ecarts") or [],\n'
PUBLIER_NOUVEAU = '                "contexte": self._contexte_publie(signal.get("contexte"), trade), "ecarts": signal.get("ecarts") or [],\n'


def une_fois(texte, ancien, nouveau, nom):
    n = texte.count(ancien)
    if n != 1:
        raise SystemExit(f"{nom} : repere trouve {n} fois (1 attendu) : rien n'a ete change")
    return texte.replace(ancien, nouveau)


def main():
    if not CIBLE.exists():
        raise SystemExit(f"{CIBLE} introuvable : lance ce script depuis le dossier gimaly")
    brut = CIBLE.read_bytes().decode("utf-8")
    if "tp_sur_niveau" in brut:
        print("Deja applique : rien a faire.")
        return
    crlf = "\r\n" in brut
    texte = brut.replace("\r\n", "\n")
    texte = une_fois(texte, CONFIG_ANCIEN, CONFIG_NOUVEAU, "reglages")
    texte = une_fois(texte, BLOC_ANCIEN, BLOC_NOUVEAU, "objectif du signal")
    texte = une_fois(texte, METHODES_ANCIEN, METHODES_NOUVEAU, "methodes")
    texte = une_fois(texte, PUBLIER_ANCIEN, PUBLIER_NOUVEAU, "publication aux amis")
    compile(texte.lstrip("﻿"), str(CIBLE), "exec")                 # jamais d'ecriture d'un fichier invalide
    if crlf:
        texte = texte.replace("\n", "\r\n")
    sauvegarde = CIBLE.with_name("trading.py.avant_tp_niveaux")
    if not sauvegarde.exists():
        shutil.copy2(CIBLE, sauvegarde)
    CIBLE.write_bytes(texte.encode("utf-8"))
    print(f"OK : TP sur niveaux du marche pose dans {CIBLE.name} (sauvegarde : {sauvegarde.name}).")
    print("Redemarre le bot pour qu'il en tienne compte.")
    print("Pour revenir en arriere sans toucher au code : trading_tp_niveau: false dans config.local.yaml.")


if __name__ == "__main__":
    sys.exit(main())
