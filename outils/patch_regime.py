# -*- coding: utf-8 -*-
r"""Patch 7.20, PHASE 1 « le bot apprend a reconnaitre le regime du marche » : ENREGISTREMENT SEUL, aucune decision n'en depend.
Nouveau fichier regime_marche.csv (trades_bot.csv et trades_refuses.csv ne changent pas) :
  - une mesure toutes les 5 minutes (evenement = mesure) : le marche est-il en « dents de scie », « moyen » ou « directionnel » ?
  - une ligne a chaque trade OUVERT (evenement = ouvert) et a chaque signal REFUSE suivi en fantome (evenement = fantome),
    avec le regime au moment du signal et l'accord du trade avec le mouvement des 60 dernieres minutes et la tendance H1.
Mesures (bougies M1/H1 de MetaTrader) : efficacite du mouvement sur 60 min et 4 h (0 = dents de scie, 1 = ligne droite ; seuils 0,07 et
0,16 = les tiers observes sur octobre), mouvement en $, volatilite des 60 dernieres minutes rapportee a celle des ~24 h, tendance H1
(EMA 20/50, meme regle que le detecteur). Cle de jointure avec les autres fichiers : date + heure (+ genre, sens, pe).
Toute erreur est avalee (jamais bloquant). Prerequis : patch_couts_ia et patch_fantomes_contexte deja appliques.

Usage (dossier gimaly, GIMALY ferme) :  .\.venv\Scripts\python.exe patch_regime.py   puis relancer le bot / publier_maj.py.
Sauvegarde trading.py.avant_regime. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "trading" / "trading.py"
MARQUE = "_regime_mesure"

A1 = '''                    journal(f"suivi des trades refuses : {exc!r}")
                self._ecrire_etat()
'''
B1 = '''                    journal(f"suivi des trades refuses : {exc!r}")
                self._regime_mesure()
                self._ecrire_etat()
'''
A2 = "        self._couts_et_avis(trade, tick, pe, achat, contexte)\n"
B2 = A2 + '        self._regime_mesure("ouvert", genre, achat, pe, "")\n'
A3 = "            self._contexte_fantome(maintenant, genre, achat, pe, motif, contexte)\n"
B3 = A3 + '            self._regime_mesure("fantome", genre, achat, pe, motif)\n'
A4 = "    def _charger_fantomes(self) -> list:\n"
B4 = '''    COLONNES_REGIME = ["date", "heure", "evenement", "genre", "sens", "pe", "motif", "regime", "eff_60", "mouv_60", "eff_240",
                       "mouv_240", "volat_rel", "tendance_h1", "accord_60", "accord_h1", "prix"]

    def _regime_mesure(self, evenement="mesure", genre="", achat=None, pe="", motif=""):
        """Regime du marche -> regime_marche.csv. ENREGISTREMENT SEUL, ne leve jamais."""
        t = time.time()
        try:
            if evenement == "mesure":
                if t - getattr(self, "_regime_t", 0) < 300:
                    return
                self._regime_t = t              # meme en cas d'echec : une tentative toutes les 5 minutes au plus
            mt5 = self._mt5()
            m1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_M1, 0, 1500)
            h1 = mt5.copy_rates_from_pos(SYMBOLE, mt5.TIMEFRAME_H1, 1, 80)
            if m1 is None or h1 is None or len(m1) < 250 or len(h1) < 60:
                return
            barre = int(m1[-1]["time"])
            if evenement == "mesure":
                if barre == getattr(self, "_regime_barre", None):
                    return                      # marche ferme : pas de nouvelle bougie, pas de nouvelle ligne
                self._regime_barre = barre
            c = [float(b["close"]) for b in m1]
            hi = [float(b["high"]) for b in m1]
            lo = [float(b["low"]) for b in m1]

            def efficacite(n):
                chemin = sum(abs(c[i] - c[i - 1]) for i in range(len(c) - n, len(c)))
                net = c[-1] - c[-1 - n]
                return (abs(net) / chemin if chemin else 0.0), net

            e60, n60 = efficacite(60)
            e240, n240 = efficacite(240)
            vrai = [max(hi[i] - lo[i], abs(hi[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]
            volat = (sum(vrai[-60:]) / 60) / (sum(vrai) / len(vrai)) if sum(vrai) else 0.0

            def ema(valeurs, periode):
                k, e, sortie = 2.0 / (periode + 1), valeurs[0], []
                for v in valeurs:
                    e = v * k + e * (1 - k)
                    sortie.append(e)
                return sortie

            ch = [float(b["close"]) for b in h1]
            e20, e50 = ema(ch, 20), ema(ch, 50)
            if e20[-1] > e50[-1] and e20[-1] > e20[-4]:
                tendance = "haussier"
            elif e20[-1] < e50[-1] and e20[-1] < e20[-4]:
                tendance = "baissier"
            else:
                tendance = "mixte"
            regime = "dents_de_scie" if e60 < 0.07 else "moyen" if e60 < 0.16 else "directionnel"
            if regime == "directionnel":
                regime += "_hausse" if n60 > 0 else "_baisse"
            accord_60 = accord_h1 = ""
            if achat is not None:
                accord_60 = "avec" if (n60 > 0) == bool(achat) else "contre"
                if tendance != "mixte":
                    accord_h1 = "avec" if (tendance == "haussier") == bool(achat) else "contre"
                else:
                    accord_h1 = "mixte"
            debut = datetime.fromtimestamp(t)
            ligne = {"date": debut.strftime("%d/%m/%Y"), "heure": debut.strftime("%H:%M:%S"), "evenement": evenement,
                     "genre": genre, "sens": "" if achat is None else ("achat" if achat else "vente"), "pe": pe,
                     "motif": str(motif)[:160], "regime": regime, "eff_60": round(e60, 3), "mouv_60": round(n60, 2),
                     "eff_240": round(e240, 3), "mouv_240": round(n240, 2), "volat_rel": round(volat, 2),
                     "tendance_h1": tendance, "accord_60": accord_60, "accord_h1": accord_h1, "prix": round(c[-1], 2)}
            fichier = DOSSIER / "regime_marche.csv"
            DOSSIER.mkdir(parents=True, exist_ok=True)
            neuf = not fichier.exists()
            with open(fichier, "a", newline="", encoding="utf-8-sig") as f:
                e = csv.DictWriter(f, fieldnames=self.COLONNES_REGIME, delimiter=";", extrasaction="ignore")
                if neuf:
                    e.writeheader()
                e.writerow(ligne)
        except Exception as exc:
            journal(f"regime du marche non enregistre : {exc!r}")

    def _charger_fantomes(self) -> list:
'''

CHANGEMENTS = [(A1, B1), (A2, B2), (A3, B3), (A4, B4)]


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
    shutil.copy2(F, F.with_name(F.name + ".avant_regime"))
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + nouveau.encode("utf-8"))
    print("trading.py : corrige (sauvegarde trading.py.avant_regime). Redemarre le bot, puis publier_maj.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
