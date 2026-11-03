# -*- coding: utf-8 -*-
r"""Patch 7.19 : le CONTEXTE de chaque signal refuse est enregistre dans un NOUVEAU fichier, fantomes_contexte.csv (trades_refuses.csv
ne change pas). Une ligne par fantome cree, avec : carnet (son cote / en face, ajouts et retraits sur 60 s, desequilibre), gros ordres
sur 5 min (dans le sens / contre), vitesse du tape, delta 5 min, accord avec la tendance H1, valeur initiale, et le spread au moment du
signal. Cle de jointure avec trades_refuses.csv : date + heure + genre + sens + pe. ENREGISTREMENT SEUL : aucune decision n'en depend,
rien ne change pour les trades. Toute erreur est avalee (jamais bloquant).

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_fantomes_contexte.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_fantctx. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_contexte_fantome"

APPEL_A = '''            self._sauver_fantomes(fantomes)
            return f" | aurait ete : SL {sl:.2f}, TP {tp:.2f}"
'''
APPEL_B = '''            self._sauver_fantomes(fantomes)
            self._contexte_fantome(maintenant, genre, achat, pe, motif, contexte)
            return f" | aurait ete : SL {sl:.2f}, TP {tp:.2f}"
'''

METHODE_A = "    def _charger_fantomes(self) -> list:\n"
METHODE_B = '''    COLONNES_CTX_FANTOMES = ["date", "heure", "genre", "sens", "pe", "motif", "spread", "carnet_son_cote", "carnet_en_face",
                             "carnet_desequilibre", "gros_ordres", "tape_vitesse", "tendance_h1_accord", "valeur_initiale",
                             "tape_1min", "gros_son_sens", "gros_contre", "delta_5min", "carnet_ajout_son_cote",
                             "carnet_retrait_son_cote", "carnet_ajout_en_face", "carnet_retrait_en_face"]

    def _contexte_fantome(self, t, genre, achat, pe, motif, contexte):
        """Contexte du signal refuse -> fantomes_contexte.csv. ENREGISTREMENT SEUL, ne leve jamais."""
        try:
            ctx = dict(contexte or {})
            try:
                ctx.update(observations(contexte))
            except Exception:
                pass
            try:
                tick = self._mt5().symbol_info_tick(SYMBOLE)
                spread = round(max(0.0, float(tick.ask) - float(tick.bid)), 2)
            except Exception:
                spread = ""
            debut = datetime.fromtimestamp(t)
            ligne = {"date": debut.strftime("%d/%m/%Y"), "heure": debut.strftime("%H:%M:%S"), "genre": genre,
                     "sens": "achat" if achat else "vente", "pe": pe, "motif": str(motif)[:160], "spread": spread}
            for cle in self.COLONNES_CTX_FANTOMES[7:]:
                v = ctx.get(cle, "")
                ligne[cle] = "" if v is None else v
            fichier = DOSSIER / "fantomes_contexte.csv"
            DOSSIER.mkdir(parents=True, exist_ok=True)
            neuf = not fichier.exists()
            with open(fichier, "a", newline="", encoding="utf-8-sig") as f:
                e = csv.DictWriter(f, fieldnames=self.COLONNES_CTX_FANTOMES, delimiter=";", extrasaction="ignore")
                if neuf:
                    e.writeheader()
                e.writerow(ligne)
        except Exception as exc:
            journal(f"contexte du fantome non enregistre : {exc!r}")

    def _charger_fantomes(self) -> list:
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt = F.read_text(encoding="utf-8")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    for a in (APPEL_A, METHODE_A):
        if txt.count(a) != 1:
            print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
            print(a.strip()[:80])
            return 2
    nouveau = txt.replace(APPEL_A, APPEL_B).replace(METHODE_A, METHODE_B)
    try:
        compile(nouveau.lstrip("﻿"), str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_fantctx"))
    F.write_text(nouveau, encoding="utf-8")
    print("trading.py : corrige (sauvegarde trading.py.avant_fantctx). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
