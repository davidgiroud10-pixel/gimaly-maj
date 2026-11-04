# -*- coding: utf-8 -*-
r"""Patch : les trades des moteurs tendance_m5 ET tendance_pullback sont aussi ENVOYES AUX AMIS (testeurs), par le meme canal de signaux
signes que le scalp. Leur bot recoit le sens, le genre, la distance du stop et l'objectif en R, et ouvre avec ses propres securites
(demo seulement, capital, perte du jour...) et son propre risque. Conditions : trading_signaux_publier: true, canal et secret configures
(comme pour le scalp), et trade annonce dans la ligue (trading_tendance_ligue: true). Retour en arriere : trading_tendance_amis: false.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_tendance_amis.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_amis. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "def _tendance_signal_amis"

A1 = '        "tendance_ligue": bool(lire("trading_tendance_ligue", True)),   # true = annonce dans la ligue (jamais aux amis)\n'
B1 = A1 + '        "tendance_amis": bool(lire("trading_tendance_amis", True)),     # true = signal aussi envoye aux bots des amis\n'
A2 = '''            if trade is not None:
                self._tend_jour = (jour, self._tend_jour[1] + 1)
                self._tend_dernier = t
'''
B2 = A2 + '''                self._tendance_signal_amis(sens, "tendance_m5", raison, contexte, trade, t)
'''
A3 = "    def _charger_fantomes(self) -> list:\n"
B3 = '''    def _tendance_signal_amis(self, sens, genre, raison, contexte, trade, t):
        """Envoie le trade tendance aux bots des amis (testeurs). Ne leve jamais ; _publier_signal verifie lui-meme
        signaux_publier, canal, secret et que le trade est « strict » (annonce dans la ligue)."""
        try:
            if not self.reglages.get("tendance_amis", True):
                return
            partage = {k: v for k, v in (contexte or {}).items() if k not in ("prive", "risque_facteur")}
            self._publier_signal({"sens": sens, "genre": genre, "raison": raison, "marche": None,
                                  "contexte": partage, "ecarts": [], "t": t}, trade)
        except Exception as exc:
            journal(f"signal tendance aux amis : {exc!r}")

    def _charger_fantomes(self) -> list:
'''
CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3)]


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
    shutil.copy2(F, F.with_name(F.name + ".avant_amis"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_amis). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
