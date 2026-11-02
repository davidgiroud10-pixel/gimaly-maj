# -*- coding: utf-8 -*-
"""Affiche les trades POC EN SIMULATION sur le graphique du bot (gimaly\\ui\\graphique_bot.py).

Meme principe que les scalps en test, avec un ROND pour les distinguer du losange des scalps :
- en cours (poc_ouverts.json) : rond cyan vide a l'entree + SL (rouge) et TP (vert) en pointilles jusqu'au bord droit ;
- termines (poc_resultats.csv) : rond plein vert (gagne) ou rouge (perdu), relie en pointilles cyan au point de sortie ;
- survol : logique (retour, rebond, cassure), sens, PE, SL, TP, resultat en R ; legende « ○ POC test ».
Rien n'est trade. Prerequis : patch_poc.py (le module de simulation) et patch_graphique_scalps.py deja appliques.

Sauvegarde : gimaly\\ui\\graphique_bot.py.avant_poc. Idempotent. Rien n'est ecrit si un repere manque.
Usage (depuis C:\\Users\\Alycia\\gimaly) :
  .\\.venv\\Scripts\\python.exe patch_graphique_poc.py
Ensuite : ferme puis relance GIMALY.
"""
import shutil
import sys
from pathlib import Path

FICHIER = Path.cwd() / "gimaly" / "ui" / "graphique_bot.py"

LECTURE = '''    def _lire_poc(self, maintenant):
        """Trades POC EN SIMULATION (jamais trades) : en cours dans poc_ouverts.json, termines dans
        poc_resultats.csv. Relu au plus toutes les 20 s."""
        import csv
        import json
        import time as _time
        from pathlib import Path

        if _time.time() - getattr(self, "_t_poc", 0) < 20:
            return getattr(self, "poc_tests", [])
        self._t_poc = _time.time()
        dossier = Path.home() / "GIMALY" / "trading"
        tests = []
        try:
            for f in json.loads((dossier / "poc_ouverts.json").read_text(encoding="utf-8")):
                tests.append({"t": float(f["t"]), "genre": str(f.get("logique", "poc")), "achat": bool(f["achat"]),
                              "pe": float(f["pe"]), "sl": float(f["sl"]), "tp": _f(f.get("tp")),
                              "fin": None, "r": None, "issue": "en cours"})
        except Exception:
            pass
        try:
            with open(dossier / "poc_resultats.csv", encoding="utf-8-sig") as fh:
                lignes = list(csv.DictReader(fh, delimiter=";"))[-400:]
            for l in lignes:
                t = _horodatage(l.get("date"), l.get("heure"), maintenant)
                pe, sl = _f(l.get("pe")), _f(l.get("sl"))
                if t is None or pe is None or sl is None:
                    continue
                tests.append({"t": t, "genre": str(l.get("logique", "poc")), "achat": l.get("sens") == "achat",
                              "pe": pe, "sl": sl, "tp": _f(l.get("tp")), "r": _f(l.get("R")),
                              "fin": t + (_f(l.get("minutes")) or 0) * 60, "issue": l.get("issue", "")})
        except Exception:
            pass
        return tests

    def _cloture_a(self, t):
'''

DESSIN = '''        # trades POC EN SIMULATION (jamais trades) : rond cyan
        for s in getattr(self, "poc_tests", []):
            if s["t"] < debut or not dedans(s["pe"]):
                continue
            x, y = X(s["t"]), Y(s["pe"])
            if s["fin"] is None:
                for niveau, coul in ((s["sl"], ROUGE), (s["tp"], VERT)):
                    if niveau is not None and dedans(niveau):
                        stylo = QPen(coul, 1)
                        stylo.setStyle(Qt.PenStyle.DotLine)
                        p.setPen(stylo)
                        p.drawLine(QPointF(x, Y(niveau)), QPointF(cadre.right(), Y(niveau)))
                p.setPen(QPen(CYAN, 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                r = s["r"] or 0.0
                sortie = s["pe"] + r * (s["pe"] - s["sl"])
                if dedans(sortie):
                    stylo = QPen(CYAN, 1)
                    stylo.setStyle(Qt.PenStyle.DotLine)
                    p.setPen(stylo)
                    p.drawLine(QPointF(x, y), QPointF(X(s["fin"]), Y(sortie)))
                p.setPen(QPen(CYAN, 1.6))
                p.setBrush(VERT if r > 0 else ROUGE)
            p.drawEllipse(QPointF(x, y), 6, 6)
            resultat = ("en cours" if s["fin"] is None else
                        f"{s['issue']} : {s['r']:+.2f} R" if s["r"] is not None else str(s["issue"]))
            self._cibles.append((x, y, (
                f"POC TEST — {s['genre'].replace('poc_', '')} (jamais tradé)\\n"
                f"{'achat' if s['achat'] else 'vente'} · PE {s['pe']:.2f} · SL {s['sl']:.2f}"
                + (f" · TP {s['tp']:.2f}" if s["tp"] is not None else "") + f"\\n{resultat}")))

        # prix actuel
'''

MODIFS = [
    ("        self.scalps = self._lire_scalps(maintenant)\n",
     "        self.scalps = self._lire_scalps(maintenant)\n        self.poc_tests = self._lire_poc(maintenant)\n"),
    ("    def _cloture_a(self, t):\n", LECTURE),
    ("        # prix actuel\n", DESSIN),
    ("◇ scalp test", "◇ scalp test   ○ POC test"),
]


def main():
    if not FICHIER.exists():
        raise SystemExit(f"{FICHIER} introuvable : lance ce script depuis le dossier gimaly")
    brut = FICHIER.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    texte = brut.decode("utf-8-sig")
    crlf = "\r\n" in texte
    texte = texte.replace("\r\n", "\n")
    if "_lire_poc" in texte:
        print("graphique_bot.py : trades POC deja affiches, RIEN n'est modifie")
        return 0
    for nom in ("QColor", "QPen", "QPointF", "CYAN", "_horodatage"):
        if nom not in texte:
            raise SystemExit(f"graphique_bot.py : {nom} introuvable, RIEN n'est modifie (envoie-moi ce message)")
    for ancien, nouveau in MODIFS:
        n = texte.count(ancien)
        if n != 1:
            raise SystemExit(f"graphique_bot.py : passage trouve {n} fois au lieu d'une, RIEN n'est modifie "
                             f"(le patch des scalps est-il applique ?) :\n{ancien}")
        texte = texte.replace(ancien, nouveau)
    compile(texte, str(FICHIER), "exec")
    copie = FICHIER.with_name("graphique_bot.py.avant_poc")
    if not copie.exists():
        shutil.copy2(FICHIER, copie)
    if crlf:
        texte = texte.replace("\n", "\r\n")
    FICHIER.write_bytes((b"\xef\xbb\xbf" if bom else b"") + texte.encode("utf-8"))
    print("graphique_bot.py : trades POC en simulation affiches (4 modifications). Ferme puis relance GIMALY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
