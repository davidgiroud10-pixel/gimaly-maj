# -*- coding: utf-8 -*-
r"""Correction AUTOMATIQUE des anciens « R » gonfles (x ~10) de trades_bot.csv (7.18).
Des anciennes versions calculaient le R avec une valeur de lot 10 fois trop faible (serveur MetaQuotes-Demo) : un stop
s'affichait a -9 ou -10 R, un gain a +10 R. Au demarrage, le bot recalcule UNE FOIS ces lignes avec la vraie valeur du lot
(demandee a MetaTrader) : R = gain / (lot x distance du stop x valeur reelle). Une ligne n'est touchee que si son R colle a
l'ancienne formule (R x 10 = gain / (lot x distance), a 3 % pres) ; les lignes deja justes ne bougent pas, donc le passage
est sans danger et ne se refait pas. Sauvegarde trades_bot.csv.avant_corr_r (une seule fois). Journal : « R corriges ... ».
Ne touche ni aux trades ouverts ni aux gains en argent.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_corriger_r_auto.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_rauto. Idempotent. Rien n'est ecrit si un repere manque (il faut avant patch_volume_garde.py)."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_corriger_anciens_r"

METHODE_A = '''    def _risque_pris(self, trade):
'''
METHODE_B = '''    def _corriger_anciens_r(self):
        """Une seule fois par demarrage : recalcule les R de trades_bot.csv gonfles par l'ancienne valeur du lot (x ~10)."""
        if getattr(self, "_r_corriges", False) or time.time() < getattr(self, "_r_prochain", 0):
            return
        self._r_prochain = time.time() + 60
        try:
            mt5 = self._mt5()
            valeur = _valeur_par_dollar(mt5, mt5.symbol_info(SYMBOLE))
        except Exception:  # noqa: BLE001
            return                                     # MetaTrader pas pret : on reessaie dans 1 min
        if not valeur:
            return
        self._r_corriges = True
        if valeur < 30 or not FICHIER_TRADES.exists():
            return                                     # valeur reelle proche de 10 : rien n'etait gonfle
        try:
            with open(FICHIER_TRADES, newline="", encoding="utf-8-sig") as f:
                lecteur = csv.DictReader(f, delimiter=";")
                colonnes = lecteur.fieldnames
                lignes = list(lecteur)
            if not colonnes or "R" not in colonnes:
                return
            changees = 0
            for l in lignes:
                if (l.get("resultat") or "").strip() in ("", "ouvert") or not (l.get("R") or "").strip():
                    continue
                try:
                    r_ancien = float(str(l["R"]).replace(",", "."))
                    gain = float(str(l.get("gain_devise")).replace(",", "."))
                    lot = float(str(l.get("volume")).replace(",", "."))
                    dist = abs(float(str(l.get("pe")).replace(",", ".")) - float(str(l.get("sl")).replace(",", ".")))
                except (TypeError, ValueError):
                    continue
                if not gain or lot <= 0 or dist <= 0:
                    continue
                q = gain / (lot * dist)                  # argent par lot et par $ reellement obtenu
                if abs(r_ancien * 10 - q) <= 0.03 * abs(q):
                    l["R"] = f"{round(gain / (lot * dist * valeur), 2):g}"
                    changees += 1
            if not changees:
                return
            sauvegarde = FICHIER_TRADES.with_name(FICHIER_TRADES.name + ".avant_corr_r")
            if not sauvegarde.exists():
                shutil.copy2(FICHIER_TRADES, sauvegarde)
            with open(FICHIER_TRADES, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=colonnes, delimiter=";")
                w.writeheader()
                w.writerows(lignes)
            journal(f"R corriges dans trades_bot.csv : {changees} ligne(s) (ancienne valeur du lot)")
        except Exception as exc:  # noqa: BLE001
            journal(f"correction des anciens R impossible : {exc!r}")

    def _risque_pris(self, trade):
'''

APPEL_A = '''                self.traiter_signaux()
                self.surveiller()
'''
APPEL_B = '''                self._corriger_anciens_r()
                self.traiter_signaux()
                self.surveiller()
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt = F.read_text(encoding="utf-8")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    for a in (METHODE_A, APPEL_A):
        if txt.count(a) != 1:
            print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
            print(a.strip()[:80])
            return 2
    nouveau = txt.replace(METHODE_A, METHODE_B).replace(APPEL_A, APPEL_B)
    if "\nimport shutil\n" not in nouveau:
        nouveau = nouveau.replace("\nimport re\n", "\nimport re\nimport shutil\n", 1)
        if "\nimport shutil\n" not in nouveau:
            print("REPERE INTROUVABLE (import) : rien n'est modifie.")
            return 2
    try:
        compile(nouveau.lstrip("﻿"), str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_rauto"))
    F.write_text(nouveau, encoding="utf-8")
    print("trading.py : corrige (sauvegarde trading.py.avant_rauto). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
