# -*- coding: utf-8 -*-
"""CALCUL DU R CORRIGE : le R du journal (colonne R de trades_bot.csv) devient  gain / risque REELLEMENT pris,
c'est-a-dire  lot x distance du stop x valeur du point  (la meme valeur que celle utilisee pour calculer le lot).

Avant : R = gain / (risque% x solde). Faux des que le lot est plafonne (lots_max) ou au lot minimum : un stop
touche pouvait s'afficher -0,3 R au lieu de -1 R. Si MT5 ne repond pas, l'ancienne formule sert de secours.

Les lignes DEJA ecrites ne sont pas modifiees (diag_tendance.py recalcule le R en argent).

A lancer sur TON PC, depuis le dossier gimaly (sauvegarde trading.py.avant_calcul_r, idempotent) :
  .\\.venv\\Scripts\\python.exe patch_calcul_r.py
Puis redemarre le bot (quand aucun trade n'est ouvert).
"""
import shutil
import sys
from pathlib import Path

CIBLE = Path.cwd() / "gimaly" / "trading" / "trading.py"

R_ANCIEN = '''            "R": round(gain / (self.reglages["risque"] / 100 * max(self.capital(), 1)), 2)
            if gain else "",
'''
R_NOUVEAU = '''            "R": round(gain / self._risque_pris(trade), 2) if gain else "",
'''

METHODE_ANCIEN = "    def _journal(self, trade, resultat, gain=0.0):\n"
METHODE_NOUVEAU = '''    def _risque_pris(self, trade):
        """Argent risque sur CE trade = lot x distance du stop x valeur du point (comme dans volume()).
        Secours : risque% x solde (ancienne formule) si MT5 ne repond pas."""
        try:
            info = self._mt5().symbol_info(SYMBOLE)
            valeur_point = info.trade_tick_value / max(info.trade_tick_size, 1e-9)
            risque = float(trade["volume"]) * abs(float(trade["pe"]) - float(trade["sl"])) * valeur_point
            if risque > 0:
                return risque
        except Exception:  # noqa: BLE001
            pass
        return max(self.reglages["risque"] / 100 * max(self.capital(), 1), 1e-9)

''' + METHODE_ANCIEN


def une_fois(texte, ancien, nouveau, nom):
    n = texte.count(ancien)
    if n != 1:
        raise SystemExit(f"{nom} : repere trouve {n} fois (1 attendu) : rien n'a ete change")
    return texte.replace(ancien, nouveau)


def main():
    if not CIBLE.exists():
        raise SystemExit(f"{CIBLE} introuvable : lance ce script depuis le dossier gimaly")
    brut = CIBLE.read_bytes().decode("utf-8")
    if "_risque_pris" in brut:
        print("Deja applique : rien a faire.")
        return
    crlf = "\r\n" in brut
    texte = brut.replace("\r\n", "\n")
    texte = une_fois(texte, R_ANCIEN, R_NOUVEAU, "calcul du R")
    texte = une_fois(texte, METHODE_ANCIEN, METHODE_NOUVEAU, "methode")
    compile(texte.lstrip("﻿"), str(CIBLE), "exec")
    if crlf:
        texte = texte.replace("\n", "\r\n")
    sauvegarde = CIBLE.with_name("trading.py.avant_calcul_r")
    if not sauvegarde.exists():
        shutil.copy2(CIBLE, sauvegarde)
    CIBLE.write_bytes(texte.encode("utf-8"))
    print(f"OK : R calcule sur le risque reel dans {CIBLE.name} (sauvegarde : {sauvegarde.name}).")
    print("Redemarre le bot quand aucun trade n'est ouvert.")


if __name__ == "__main__":
    sys.exit(main())
