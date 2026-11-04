# -*- coding: utf-8 -*-
r"""Patch 7.21 : 2e MOTEUR « tendance_m5 » (suiveur de tendance), EN REEL, complementaire du scalp actuel (qui joue surtout le contre-mouvement).
Il ne trade que lorsque le marche est DIRECTIONNEL, dans le sens du mouvement, a la cassure d'un extreme recent :
  1. regime : efficacite du mouvement sur 60 min >= 0,16 (le tiers haut d'octobre), mouvement 60 min et 4 h dans le meme sens,
     tendance H1 (EMA 20/50) dans ce sens ;
  2. declencheur : la derniere bougie M5 CLOSE casse le plus bas (vente) / le plus haut (achat) des 6 bougies precedentes (30 min) ;
  3. stop : 1,5 x l'ATR(14) M5, borne entre 2,5 $ et 7 $ ; objectif 2 R ; sortie au temps 4 h ; une evaluation par bougie M5.
Garde-fous : MEMES securites que le bot (demo, STOP, perte du jour, protection du gain, annonces) ; risque = 100 % du risque normal (1 %), reglable
(trading_tendance_risque_facteur) ; 2 trades/jour au plus ; 30 min entre deux ; jamais en meme temps qu'une autre position ; laisse
toujours une place du quota du jour au scalp ; ses trades sont PRIVES : jamais publies a la ligue ni aux amis (signaux), etiquette
genre = tendance_m5 dans trades_bot.csv (analyses : --genre tendance_m5). Interrupteur : trading_tendance_actif: false.
Reglages (config.local.yaml, tous facultatifs) : trading_tendance_actif (true), _risque_facteur (1.0 = 1 % comme le scalp ; 0.5 = moitie), _max_jour (2), _eff_min (0.16),
_tp_r (2.0), _sl_atr (1.5), _cassure_barres (6), _pause_min (30), _heures ([9, 21] = heure du PC : Londres + New York).
PAS de filtre d'annonces economiques sur ce moteur (le detecteur n'en fournit pas) : c'est un risque connu, .
ATTENTION : logique NON validee sur historique avant mise en service (a la demande de Dav) ; son resultat se mesure separement.

Usage (dossier gimaly, GIMALY ferme) :  .\.venv\Scripts\python.exe patch_tendance.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_tendance. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_tendance_evalue"

A1 = '        "ecart_tp_r": float(lire("trading_ecart_tp_r", 1.0)),\n    }\n'
B1 = '''        "ecart_tp_r": float(lire("trading_ecart_tp_r", 1.0)),
        # 2e moteur « tendance_m5 » (suiveur de tendance, trades prives)
        "tendance_actif": bool(lire("trading_tendance_actif", True)),
        "tendance_risque_facteur": float(lire("trading_tendance_risque_facteur", 1.0)),
        "tendance_max_jour": int(lire("trading_tendance_max_jour", 2)),
        "tendance_eff_min": float(lire("trading_tendance_eff_min", 0.16)),
        "tendance_tp_r": float(lire("trading_tendance_tp_r", 2.0)),
        "tendance_sl_atr": float(lire("trading_tendance_sl_atr", 1.5)),
        "tendance_cassure_barres": int(lire("trading_tendance_cassure_barres", 6)),
        "tendance_pause_min": float(lire("trading_tendance_pause_min", 30)),
        "tendance_heures": [int(x) for x in (lire("trading_tendance_heures", None) or [9, 21])][:2],
    }
'''
A2 = '''    def volume(self, distance_sl):
'''
B2 = '''    def volume(self, distance_sl, facteur=1.0):
'''
A3 = '        risque = self.reglages["risque"] / 100 * self.capital()\n'
B3 = '        risque = self.reglages["risque"] / 100 * self.capital() * max(0.0, float(facteur or 1.0))\n'
A4 = '        lots = min(self.volume(distance), self.reglages["lots_max"])\n'
B4 = '''        lots = min(self.volume(distance, float((contexte or {}).get("risque_facteur") or 1.0)),
                   self.reglages["lots_max"])
'''
A5 = "        strict = not ecarts\n        mt5 = self._mt5()\n"
B5 = '        strict = not ecarts and not (contexte or {}).get("prive")     # trade prive : jamais publie ni signale\n        mt5 = self._mt5()\n'
A6 = "                self.traiter_signaux()\n                self.surveiller()\n"
B6 = A6 + "                self._tendance_evalue()\n"
A7 = "    def _charger_fantomes(self) -> list:\n"
B7 = '''    def _tendance_evalue(self):
        """2e moteur « tendance_m5 » : cassure d'un extreme M5 dans un marche directionnel. Ne leve jamais."""
        try:
            r = self.reglages
            if not r.get("tendance_actif", True) or not r["actif"]:
                return
            t = time.time()
            if t - getattr(self, "_tend_t", 0) < 20:
                return
            self._tend_t = t
            mt5 = self._mt5()
            m5 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M5, 0, 40)
            if m5 is None or len(m5) < 30:
                return
            barre = int(m5[-2]["time"])
            if barre == getattr(self, "_tend_barre", None):
                return                              # une seule evaluation par bougie M5 close
            self._tend_barre = barre
            jour = datetime.now().strftime("%d/%m/%Y")
            debut_h, fin_h = (list(r.get("tendance_heures") or [9, 21]) + [21])[:2]
            if not (debut_h <= datetime.now().hour < fin_h):
                return                              # hors horaires (heure du PC) : pas de filtre d'annonces ici, on reste en journee
            deja = getattr(self, "_tend_jour", (jour, 0))
            if deja[0] != jour:
                deja = (jour, 0)
            self._tend_jour = deja
            if deja[1] >= r["tendance_max_jour"]:
                return
            if t - getattr(self, "_tend_dernier", 0) < r["tendance_pause_min"] * 60:
                return
            faits, _ = self.journee()
            if faits >= r["max_jour"] - 1:
                return                              # on laisse toujours une place au scalp
            if self.positions():
                return                              # jamais en meme temps qu'une autre position
            # --- regime : marche directionnel (M1) et tendance H1
            m1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M1, 0, 260)
            h1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_H1, 1, 80)
            if m1 is None or h1 is None or len(m1) < 250 or len(h1) < 60:
                return
            c = [float(b["close"]) for b in m1]
            chemin = sum(abs(c[i] - c[i - 1]) for i in range(len(c) - 60, len(c)))
            n60, n240 = c[-1] - c[-61], c[-1] - c[-241]
            eff60 = abs(n60) / chemin if chemin else 0.0
            if eff60 < r["tendance_eff_min"] or n60 * n240 <= 0:
                return
            ch = [float(b["close"]) for b in h1]

            def ema(valeurs, periode):
                k, e, sortie = 2.0 / (periode + 1), valeurs[0], []
                for v in valeurs:
                    e = v * k + e * (1 - k)
                    sortie.append(e)
                return sortie

            e20, e50 = ema(ch, 20), ema(ch, 50)
            baisse = n60 < 0
            if baisse and not (e20[-1] < e50[-1] and e20[-1] < e20[-4]):
                return
            if not baisse and not (e20[-1] > e50[-1] and e20[-1] > e20[-4]):
                return
            # --- declencheur : cassure de l'extreme des N bougies M5 precedentes
            fermees = [(float(b["high"]), float(b["low"]), float(b["close"])) for b in m5[:-1]]
            n = max(2, int(r["tendance_cassure_barres"]))
            derniere, avant = fermees[-1], fermees[-1 - n:-1]
            if baisse and not derniere[2] < min(x[1] for x in avant):
                return
            if not baisse and not derniere[2] > max(x[0] for x in avant):
                return
            vrais = [max(fermees[i][0] - fermees[i][1], abs(fermees[i][0] - fermees[i - 1][2]),
                         abs(fermees[i][1] - fermees[i - 1][2])) for i in range(len(fermees) - 14, len(fermees))]
            atr = sum(vrais) / len(vrais)
            plancher = max(2.5, (r.get("sl_refus_sous_pips", 0) or 0) / PIPS_PAR_DOLLAR + 0.1)
            distance = min(max(r["tendance_sl_atr"] * atr, plancher), 7.0)
            tick = mt5.symbol_info_tick(SYMBOLE)
            if tick is None:
                return
            prix = float(tick.bid if baisse else tick.ask)
            if abs(prix - derniere[2]) > 0.5 * distance:
                return                              # le prix a deja trop couru depuis la cassure
            sens = "vente" if baisse else "achat"
            contexte = {"prive": True, "risque_facteur": r["tendance_risque_facteur"], "tp_r": r["tendance_tp_r"],
                        "duree_max_min": 240, "prix_xau": prix}
            raison = (f"tendance M5 : cassure {'basse' if baisse else 'haute'} des {n} bougies, efficacite 60 min "
                      f"{eff60:.2f}, mouvement 60 min {n60:+.1f} $, stop {distance:.1f} $")
            trade, message = self.ouvrir(sens, genre="tendance_m5", raison=raison, contexte=contexte,
                                         distant=True, distance_ref=distance)
            journal(f"{sens} (tendance_m5) : {message}")
            if trade is not None:
                self._tend_jour = (jour, self._tend_jour[1] + 1)
                self._tend_dernier = t
        except Exception as exc:
            journal(f"tendance_m5 : {exc!r}")

    def _charger_fantomes(self) -> list:
'''

CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3), (A4, B4), (A5, B5), (A6, B6), (A7, B7)]


def appliquer(txt):
    """Renvoie (nouveau texte, repere manquant)."""
    for ancien, _ in CHANGEMENTS:
        if txt.count(ancien) != 1:
            return None, ancien.strip()[:90]
    for ancien, nouveau in CHANGEMENTS:
        txt = txt.replace(ancien, nouveau)
    return txt, None


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    txt = brut.decode("utf-8-sig")
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
    shutil.copy2(F, F.with_name(F.name + ".avant_tendance"))
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + nouveau.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_tendance). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
