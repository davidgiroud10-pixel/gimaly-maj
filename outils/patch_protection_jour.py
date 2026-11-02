# -*- coding: utf-8 -*-
r"""Protection du gain du jour (7.17) : le bot s'arrete pour la journee quand le resultat en R a rendu D R depuis le
sommet de la journee (le sommet devant avoir atteint au moins S R). Calcul a partir des trades termines de
trades_bot.csv (colonne R), depuis minuit ou la derniere reprise manuelle. Ne ferme aucun trade ouvert : elle refuse seulement
les NOUVEAUX trades, donc aussi les signaux envoyes aux amis (ils ne partent que si le bot de l'editeur accepte le trade).

DESACTIVEE PAR DEFAUT. Pour l'activer, dans config.local.yaml :
    trading_rendu_max_r: 3          # 0 = desactive ; ici : on arrete quand on rend 3 R depuis le sommet
    trading_rendu_sommet_min_r: 3   # la protection n'agit que si le sommet du jour a atteint au moins 3 R
Redemarrer le bot pour que le reglage soit pris en compte.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_protection_jour.py   puis redemarrer le bot / publier_maj.py.
Sauvegarde trading.py.avant_prot. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_protection_jour"

REGLAGE_A = '''        "perte_max_jour": float(lire("trading_perte_max_jour", 2.0)),
'''
REGLAGE_B = '''        "perte_max_jour": float(lire("trading_perte_max_jour", 2.0)),
        "rendu_max_r": float(lire("trading_rendu_max_r", 0)),                # 0 = protection du gain du jour desactivee
        "rendu_sommet_min_r": float(lire("trading_rendu_sommet_min_r", 3)),
'''

APPEL_A = '''        if perte <= -abs(r["perte_max_jour"]) / 100 * self.capital():
            return False, f"perte du jour atteinte ({perte:.2f})"
'''
APPEL_B = '''        if perte <= -abs(r["perte_max_jour"]) / 100 * self.capital():
            return False, f"perte du jour atteinte ({perte:.2f})"
        bloque, raison = self._protection_jour()
        if bloque:
            return False, raison
'''

METHODE_A = '''    def _decalage_serveur(self):
'''
METHODE_B = '''    def _protection_jour(self):
        """(bloque, raison). Protection du gain du jour : voir trading_rendu_max_r. Ne ferme rien ; ne bloque que les
        nouveaux trades. Toute erreur de lecture laisse le bot trader (jamais bloquant par accident)."""
        r = self.reglages
        rendu = r.get("rendu_max_r", 0) or 0
        if rendu <= 0:
            return False, ""
        try:
            cache = getattr(self, "_prot_cache", None)
            if cache and time.time() - cache[0] < 20:
                return cache[1]
            debut = self.depuis()
            trades = []
            if FICHIER_TRADES.exists():
                with open(FICHIER_TRADES, newline="", encoding="utf-8-sig") as f:
                    for l in csv.DictReader(f, delimiter=";"):
                        if (l.get("resultat") or "").strip() in ("", "ouvert") or not (l.get("R") or "").strip():
                            continue
                        try:
                            t = datetime.strptime(f"{l['date'].strip()} {l['heure'].strip()}", "%d/%m/%Y %H:%M:%S")
                            trades.append((t, float(str(l["R"]).replace(",", "."))))
                        except (ValueError, KeyError):
                            continue
            trades = sorted(x for x in trades if x[0].timestamp() >= debut)
            cum = sommet = 0.0
            for _t, rr in trades:
                cum += rr
                sommet = max(sommet, cum)
            resultat = (False, "")
            if sommet >= r.get("rendu_sommet_min_r", 3) and sommet - cum >= rendu:
                resultat = (True, f"protection du gain du jour : sommet {sommet:+.2f} R, maintenant {cum:+.2f} R "
                                  f"(rendu {sommet - cum:.2f} R sur {rendu:g}) : arret pour aujourd'hui")
                if getattr(self, "_prot_signalee", None) != datetime.now().date():
                    self._prot_signalee = datetime.now().date()
                    journal(resultat[1])
            self._prot_cache = (time.time(), resultat)
            return resultat
        except Exception as exc:  # noqa: BLE001
            journal(f"protection du jour illisible : {exc!r}")
            return False, ""

    def _decalage_serveur(self):
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt = F.read_text(encoding="utf-8")
    if MARQUE in txt:
        print("trading.py : deja corrige (rien a faire).")
        return 0
    for a in (REGLAGE_A, APPEL_A, METHODE_A):
        if txt.count(a) != 1:
            print("REPERE INTROUVABLE (ou en double) : rien n'est modifie. Envoie-moi cette erreur :")
            print(a.strip()[:80])
            return 2
    nouveau = txt.replace(REGLAGE_A, REGLAGE_B).replace(APPEL_A, APPEL_B).replace(METHODE_A, METHODE_B)
    try:
        compile(nouveau.lstrip("\ufeff"), str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_prot"))
    F.write_text(nouveau, encoding="utf-8")
    print("trading.py : corrige (sauvegarde trading.py.avant_prot). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
