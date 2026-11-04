# -*- coding: utf-8 -*-
r"""Patch : le moteur tendance_m5 n'ENTRE plus sur la cassure, il attend le RETOUR sur le niveau casse (cassure + retest).
  1. une bougie M5 cloture au-dela de l'extreme des 6 dernieres : le bot memorise le niveau casse, sans entrer ;
  2. il attend jusqu'a 30 min (trading_tendance_retest_min) que le prix revienne vers ce niveau (a 0,3 ATR, trading_tendance_retest_atr) ;
  3. il entre quand une bougie M5 repart dans le bon sens (cloture du bon cote du niveau), stop sous le creux du retour (0,2 ATR de
     marge, 7 $ maximum, plancher habituel) ; objectif 3R comme avant ;
  4. il abandonne si le retour n'arrive pas dans le delai, si le prix revient de plus d'1 ATR de l'autre cote du niveau, ou si le creux est
     trop profond (stop > 7 $). Un marche qui part sans jamais revenir n'est PAS poursuivi.
Le pullback (tendance_pullback) et le scalp ne sont pas touches. Retour a l'ancienne entree : trading_tendance_retest: false.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_tendance_retest.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_retest. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = '"tendance_retest"'

A1 = '        "tendance_cassure_barres": int(lire("trading_tendance_cassure_barres", 6)),\n'
B1 = A1 + '''        "tendance_retest": bool(lire("trading_tendance_retest", True)),        # true = entree sur le retour au niveau casse
        "tendance_retest_min": float(lire("trading_tendance_retest_min", 30)),  # delai maximum du retour (minutes)
        "tendance_retest_atr": float(lire("trading_tendance_retest_atr", 0.3)),  # tolerance de « retour au niveau » (en ATR M5)
'''
A2 = "            self._tend_barre = barre\n"
B2 = A2 + '''            _att = self.__dict__.get("_tend_attente")
            if _att and t > _att["expire"]:
                journal(f"tendance_m5 : retour sur {_att['niveau']:.2f} non venu en {r.get('tendance_retest_min', 30):g} min, cassure abandonnee")
                self._tend_attente = None
'''
A3 = '''            if baisse and not derniere[2] < min(x[1] for x in avant):
                return
            if not baisse and not derniere[2] > max(x[0] for x in avant):
                return
'''
B3 = '''            declenche = (derniere[2] < min(x[1] for x in avant)) if baisse else (derniere[2] > max(x[0] for x in avant))
            retest = bool(r.get("tendance_retest", True))
            attente = self.__dict__.get("_tend_attente")
            if retest and attente is not None and attente["sens"] != ("vente" if baisse else "achat"):
                self._tend_attente = attente = None             # le sens du marche a change : on oublie la cassure memorisee
            if not declenche and not (retest and attente):
                return
'''
A4 = '''            if abs(prix - derniere[2]) > 0.5 * distance:
                return                              # le prix a deja trop couru depuis la cassure
'''
B4 = '''            if retest:
                niveau_cassure = min(x[1] for x in avant) if baisse else max(x[0] for x in avant)
                if declenche:
                    # 1re etape : cassure. On memorise le niveau casse, on n'entre PAS (un retour sur le niveau est attendu)
                    if attente is None:
                        journal(f"tendance_m5 : cassure {'basse' if baisse else 'haute'} detectee, niveau {niveau_cassure:.2f}, "
                                f"attente du retour (max {r['tendance_retest_min']:g} min)")
                    self._tend_attente = {"sens": "vente" if baisse else "achat", "niveau": niveau_cassure, "t": t,
                                          "expire": t + r["tendance_retest_min"] * 60,
                                          "extreme": derniere[0] if baisse else derniere[1], "touche": 0}
                    return
                # 2e etape : le prix est-il revenu sur le niveau puis reparti dans le sens de la tendance ?
                o_b, h_b, l_b, c_b = (float(m5[-2][k]) for k in ("open", "high", "low", "close"))
                niveau, marge = attente["niveau"], r["tendance_retest_atr"] * atr
                if baisse:
                    attente["extreme"] = max(attente["extreme"], h_b)
                    invalide, touche = c_b > niveau + atr, h_b >= niveau - marge
                    confirme = c_b < o_b and c_b < niveau
                else:
                    attente["extreme"] = min(attente["extreme"], l_b)
                    invalide, touche = c_b < niveau - atr, l_b <= niveau + marge
                    confirme = c_b > o_b and c_b > niveau
                if invalide:
                    journal(f"tendance_m5 : le prix a rendu plus d'1 ATR au-dela de {niveau:.2f}, cassure abandonnee")
                    self._tend_attente = None
                    return
                if touche:
                    attente["touche"] = barre
                if not (confirme and attente["touche"] and barre - attente["touche"] <= 600):
                    return                          # pas encore de retour confirme : on attend la bougie suivante
                distance = ((attente["extreme"] + 0.2 * atr) - prix) if baisse else (prix - (attente["extreme"] - 0.2 * atr))
                if distance > 7.0:
                    journal(f"tendance_m5 : retour trop profond (stop {distance:.1f} $ > 7 $), cassure abandonnee")
                    self._tend_attente = None
                    return
                distance = max(distance, plancher)
                if abs(prix - c_b) > 0.5 * distance:
                    return                          # le prix a deja trop couru depuis la bougie de reprise
            elif abs(prix - derniere[2]) > 0.5 * distance:
                return                              # le prix a deja trop couru depuis la cassure
'''
A5 = '''            raison = (f"tendance M5 : cassure {'basse' if baisse else 'haute'} des {n} bougies, efficacite 60 min "
                      f"{eff60:.2f}, mouvement 60 min {n60:+.1f} $, stop {distance:.1f} $")
'''
B5 = '''            raison = (f"tendance M5 : cassure {'basse' if baisse else 'haute'} des {n} bougies, efficacite 60 min "
                      f"{eff60:.2f}, mouvement 60 min {n60:+.1f} $, stop {distance:.1f} $"
                      + (f", entree sur le retour au niveau {attente['niveau']:.2f}" if retest else ""))
'''
A6 = '            journal(f"{sens} (tendance_m5) : {message}")\n'
B6 = A6 + '            self._tend_attente = None                # une cassure ne sert qu\'une fois (trade pris ou refuse)\n'
CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3), (A4, B4), (A5, B5), (A6, B6)]


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
    shutil.copy2(F, F.with_name(F.name + ".avant_retest"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_retest). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
