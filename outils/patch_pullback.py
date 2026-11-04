# -*- coding: utf-8 -*-
r"""Patch 7.22 : 3e MOTEUR « tendance_pullback » (achat des replis dans la tendance), EN REEL, a cote du scalp et du moteur de cassure.
Idee d'un trader : tendance de fond haussiere, on n'achete pas le haut, on attend un repli vers la moyenne puis la reprise (miroir en baisse).
  1. contexte : tendance H1 (EMA 20/50) dans un sens ET mouvement des 4 dernieres heures dans le meme sens, d'au moins 4 x l'ATR M5
     (pas d'exigence d'« efficacite » sur 60 min : un repli la fait baisser par nature) ;
  2. repli : sur les 12 dernieres bougies M5, le prix s'etait ecarte d'au moins 1 x l'ATR de sa moyenne EMA 20 M5, puis la derniere
     bougie M5 close a touche la zone de la moyenne (a 0,25 x ATR) ;
  3. confirmation : cette bougie cloture dans le sens de la tendance ET du bon cote de la moyenne (haussiere au-dessus pour un achat) ;
  4. stop : sous le plus bas des 6 dernieres bougies - 0,2 x ATR (miroir en vente), entre 25 et 70 pips ; au-dela de 70 pips : pas de trade ;
     objectif 2 R ; sortie au temps 4 h ; une evaluation par bougie M5.
Memes garde-fous que tendance_m5 : securites du bot, risque trading_tendance_risque_facteur (1.0 = 1 %), 2 trades/jour (a part),
30 min entre deux trades de l'un ou l'autre moteur, jamais en meme temps qu'une autre position, une place du quota du jour laissee
au scalp, horaires trading_tendance_heures (9-21), annonce dans la ligue (trading_tendance_ligue), envoye aux amis seulement apres patch_tendance_amis.
Etiquette genre = tendance_pullback (analyses : --genre tendance_pullback). Interrupteur : trading_pullback_actif: false.
Reglages (tous facultatifs) : trading_pullback_actif (true), _max_jour (2), _mouv_atr (4.0), _ext_atr (1.0), _touche_atr (0.25), _barres (12).
ATTENTION : logique NON validee sur historique avant mise en service (a la demande de Dav) ; pas de filtre d'annonces economiques.
Prerequis : patch_tendance (et patch_tendance_ligue) deja appliques.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_pullback.py   puis redemarrer le bot.
Sauvegarde trading.py.avant_pullback. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_pullback_evalue"

A1 = '        "tendance_ligue": bool(lire("trading_tendance_ligue", True)),   # true = annonce dans la ligue (jamais aux amis)\n'
B1 = A1 + '''        # 3e moteur « tendance_pullback » (achat des replis dans la tendance)
        "pullback_actif": bool(lire("trading_pullback_actif", True)),
        "pullback_max_jour": int(lire("trading_pullback_max_jour", 2)),
        "pullback_mouv_atr": float(lire("trading_pullback_mouv_atr", 4.0)),
        "pullback_ext_atr": float(lire("trading_pullback_ext_atr", 1.0)),
        "pullback_touche_atr": float(lire("trading_pullback_touche_atr", 0.25)),
        "pullback_barres": int(lire("trading_pullback_barres", 12)),
'''
A2 = "                self._tendance_evalue()\n"
B2 = A2 + "                self._pullback_evalue()\n"
A3 = "    def _charger_fantomes(self) -> list:\n"
B3 = '''    def _pullback_evalue(self):
        """3e moteur « tendance_pullback » : achat des replis (vente des rebonds) dans la tendance. Ne leve jamais."""
        try:
            r = self.reglages
            if not r.get("pullback_actif", True) or not r.get("tendance_actif", True) or not r["actif"]:
                return
            t = time.time()
            if t - getattr(self, "_pb_t", 0) < 20:
                return
            self._pb_t = t
            mt5 = self._mt5()
            m5 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M5, 0, 90)
            if m5 is None or len(m5) < 60:
                return
            barre = int(m5[-2]["time"])
            if barre == getattr(self, "_pb_barre", None):
                return                              # une seule evaluation par bougie M5 close
            self._pb_barre = barre
            jour = datetime.now().strftime("%d/%m/%Y")
            debut_h, fin_h = (list(r.get("tendance_heures") or [9, 21]) + [21])[:2]
            if not (debut_h <= datetime.now().hour < fin_h):
                return
            deja = getattr(self, "_pb_jour", (jour, 0))
            if deja[0] != jour:
                deja = (jour, 0)
            self._pb_jour = deja
            if deja[1] >= r.get("pullback_max_jour", 2):
                return
            if t - getattr(self, "_tend_dernier", 0) < r["tendance_pause_min"] * 60:
                return                              # 30 min entre deux trades, tous moteurs tendance confondus
            faits, _ = self.journee()
            if faits >= r["max_jour"] - 1:
                return                              # on laisse toujours une place au scalp
            if self.positions():
                return                              # jamais en meme temps qu'une autre position
            h1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_H1, 1, 80)
            m1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M1, 0, 260)
            if m1 is None or h1 is None or len(m1) < 250 or len(h1) < 60:
                return

            def ema(valeurs, periode):
                k, e, sortie = 2.0 / (periode + 1), valeurs[0], []
                for v in valeurs:
                    e = v * k + e * (1 - k)
                    sortie.append(e)
                return sortie

            ch = [float(b["close"]) for b in h1]
            e20, e50 = ema(ch, 20), ema(ch, 50)
            if e20[-1] > e50[-1] and e20[-1] > e20[-4]:
                hausse = True
            elif e20[-1] < e50[-1] and e20[-1] < e20[-4]:
                hausse = False
            else:
                return                              # tendance H1 mixte : on ne joue pas de repli
            c1 = [float(b["close"]) for b in m1]
            n240 = c1[-1] - c1[-241]
            if (n240 > 0) != hausse:
                return
            fermees = [(float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])) for b in m5[:-1]]
            vrais = [max(fermees[i][1] - fermees[i][2], abs(fermees[i][1] - fermees[i - 1][3]),
                         abs(fermees[i][2] - fermees[i - 1][3])) for i in range(len(fermees) - 14, len(fermees))]
            atr = sum(vrais) / len(vrais)
            if atr <= 0 or abs(n240) < r["pullback_mouv_atr"] * atr:
                return
            cl = [x[3] for x in fermees]
            em = ema(cl, 20)
            sens = 1 if hausse else -1
            n = max(3, int(r["pullback_barres"]))
            ecart = max(sens * (cl[i] - em[i]) for i in range(len(cl) - n, len(cl) - 1))
            if ecart < r["pullback_ext_atr"] * atr:
                return                              # pas d'elan avant : ce n'est pas un repli
            o, h, l, c = fermees[-1]
            marge = r["pullback_touche_atr"] * atr
            touche = (l <= em[-1] + marge) if hausse else (h >= em[-1] - marge)
            confirme = (c > o and c > em[-1]) if hausse else (c < o and c < em[-1])
            if not (touche and confirme):
                return
            tick = mt5.symbol_info_tick(SYMBOLE)
            if tick is None:
                return
            prix = float(tick.ask if hausse else tick.bid)
            recent = fermees[-6:]
            if hausse:
                distance = prix - (min(x[2] for x in recent) - 0.2 * atr)
            else:
                distance = (max(x[1] for x in recent) + 0.2 * atr) - prix
            plancher = max(2.5, (r.get("sl_refus_sous_pips", 0) or 0) / PIPS_PAR_DOLLAR + 0.1)
            if distance > 7.0:
                return                              # le repli est trop profond : stop au-dela de 70 pips
            distance = max(distance, plancher)
            if abs(prix - c) > 0.5 * distance:
                return                              # le prix a deja trop couru depuis la bougie de confirmation
            ordre = "achat" if hausse else "vente"
            contexte = {"prive": not r.get("tendance_ligue", True), "risque_facteur": r["tendance_risque_facteur"],
                        "tp_r": r["tendance_tp_r"], "duree_max_min": 240, "prix_xau": prix}
            raison = (f"repli M5 dans la tendance H1 {'haussiere' if hausse else 'baissiere'} : retour sur la moyenne 20, "
                      f"bougie de reprise, mouvement 4 h {n240:+.1f} $, stop {distance:.1f} $")
            trade, message = self.ouvrir(ordre, genre="tendance_pullback", raison=raison, contexte=contexte,
                                         distant=True, distance_ref=distance)
            journal(f"{ordre} (tendance_pullback) : {message}")
            if trade is not None:
                self._pb_jour = (jour, self._pb_jour[1] + 1)
                self._tend_dernier = t
                envoyer = getattr(self, "_tendance_signal_amis", None)      # present apres patch_tendance_amis
                if envoyer:
                    envoyer(ordre, "tendance_pullback", raison, contexte, trade, t)
        except Exception as exc:
            journal(f"tendance_pullback : {exc!r}")

    def _charger_fantomes(self) -> list:
'''
CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3)]


def appliquer(txt):
    """Renvoie (nouveau texte, reperes manquants)."""
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
    crlf = brut.count(b"\r\n") > brut.count(b"\n") / 2          # fichier Windows : on rend les memes fins de ligne
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
    shutil.copy2(F, F.with_name(F.name + ".avant_pullback"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_pullback). Redemarre le bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
