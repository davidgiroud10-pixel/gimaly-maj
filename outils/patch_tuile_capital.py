# -*- coding: utf-8 -*-
"""Panneau BOT : nouvelle tuile CAPITAL a cote d'AUJOURD'HUI = solde du compte MT5 + mini-courbe de son evolution (derniers trades).
  * trading.py : le bot ecrit aussi `solde` et `equite` dans trading_etat.json (toutes les 5 s, comme le reste) ;
  * gimaly\\ui\\icebergs_panneau.py : la tuile lit ce fichier et trades_bot.csv (via trades_termines) toutes les 5 s ; la courbe reconstruit le solde apres chaque trade
    en remontant depuis le solde actuel (solde avant = solde apres - gain du trade). Verte si le solde est au-dessus du point de depart de la courbe, rouge sinon.
Infobulle : solde, equite, resultat du jour. Si le bot n'a pas encore ecrit le solde (pas redemarre), la tuile affiche un tiret.
Sauvegardes *.avant_tuile_capital. Retour arriere : --annuler. Idempotent. Rien n'est ecrit si un repere manque ou si un fichier ne compile plus.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_tuile_capital.py [--annuler]   puis REDEMARRER GIMALY (fenetre principale) ET le bot (redemarrer_bot.py)."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd()
T = RACINE / "gimaly" / "trading" / "trading.py"
U = RACINE / "gimaly" / "ui" / "icebergs_panneau.py"

CODE_TUILE = '''def _tuile_capital(panneau, ligne):
    """12/11 : tuile CAPITAL (solde du compte + mini-courbe de son evolution), ajoutee dans la tete du panneau BOT."""
    import json
    try:
        from PySide6.QtCore import QPointF, Qt, QTimer
        from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
    except ImportError:
        from PyQt6.QtCore import QPointF, Qt, QTimer
        from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
        from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
    from ..trading.trading import FICHIER_ETAT

    carte = QFrame()
    carte.setStyleSheet("QFrame{background:rgba(255,255,255,0.04);"
                        "border:1px solid rgba(255,255,255,0.08);border-radius:10px;}")
    pile = QVBoxLayout(carte)
    pile.setContentsMargins(12, 6, 12, 6)
    pile.setSpacing(0)
    haut = QLabel("CAPITAL")
    haut.setFont(panneau.police(7, False, 2))
    haut.setStyleSheet("color:#6f8aa3;background:transparent;border:none;")
    bas = QHBoxLayout()
    bas.setSpacing(10)
    valeur = QLabel("\\u2013")
    valeur.setFont(panneau.police(11, True))
    valeur.setStyleSheet("color:#e6f6ff;background:transparent;border:none;")
    courbe = QLabel()
    courbe.setFixedSize(96, 24)
    courbe.setStyleSheet("background:transparent;border:none;")
    bas.addWidget(valeur)
    bas.addWidget(courbe)
    pile.addWidget(haut)
    pile.addLayout(bas)
    ligne.insertWidget(5, carte)

    def dessiner(points):
        pm = QPixmap(96, 24)
        pm.fill(QColor(0, 0, 0, 0))
        if len(points) >= 2:
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            bas_v, haut_v = min(points), max(points)
            amp = (haut_v - bas_v) or 1.0
            n = len(points) - 1
            pos = [QPointF(2 + 92 * i / n, 22 - 20 * (v - bas_v) / amp) for i, v in enumerate(points)]
            couleur = QColor("#4ade80") if points[-1] >= points[0] else QColor("#ff6b6b")
            p.setPen(QPen(couleur, 1.6))
            for a, b in zip(pos, pos[1:]):
                p.drawLine(a, b)
            p.setBrush(couleur)
            p.drawEllipse(pos[-1], 2.2, 2.2)
            p.end()
        courbe.setPixmap(pm)

    def maj():
        try:
            etat = json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
            solde = etat.get("solde")
            if solde is None:
                valeur.setText("\\u2013")
                dessiner([])
                return
            solde = float(solde)
            valeur.setText(f"{solde:,.0f} \\u20ac".replace(",", "\\u202f"))
            gains = []
            try:
                from ..trading.trading import trades_termines
                for t in trades_termines()[-40:]:
                    try:
                        gains.append(float(str(t.get("gain_devise", "0")).replace(",", ".")))
                    except ValueError:
                        gains.append(0.0)
            except Exception:
                pass
            pts = [solde]
            for g in reversed(gains):
                pts.append(pts[-1] - g)
            pts.reverse()
            dessiner(pts)
            equite = etat.get("equite")
            jour = etat.get("resultat_du_jour", 0)
            carte.setToolTip(f"Solde {solde:,.2f} \\u20ac" + (f" \\u00b7 \\u00e9quit\\u00e9 {float(equite):,.2f} \\u20ac" if equite is not None else "")
                             + f"\\nR\\u00e9sultat du jour {float(jour):+,.2f} \\u20ac\\nCourbe : les {len(gains)} derniers trades")
        except Exception:
            pass

    minuterie = QTimer(carte)
    minuterie.timeout.connect(maj)
    minuterie.start(5000)
    panneau._minuterie_capital = minuterie
    maj()


'''

REMPL_T = [
    ("methode solde pour l'etat",
     "    def _ecrire_etat(self):\n",
     "    def _solde_etat(self):\n"
     "        \"\"\"12/11 : (solde, equite) du compte pour la tuile CAPITAL du panneau.\"\"\"\n"
     "        try:\n"
     "            c = self.compte()\n"
     "            return (round(c.balance, 2), round(c.equity, 2)) if c else (None, None)\n"
     "        except Exception:\n"
     "            return (None, None)\n"
     "\n"
     "    def _ecrire_etat(self):\n"),
    ("solde dans l'etat",
     "                \"resultat_du_jour\": round(resultat, 2),\n",
     "                \"resultat_du_jour\": round(resultat, 2),\n"
     "                \"solde\": self._solde_etat()[0], \"equite\": self._solde_etat()[1],\n"),
]
REMPL_U = [
    ("fonction tuile capital",
     "def _texte_bot() -> str:\n",
     CODE_TUILE + "def _texte_bot() -> str:\n"),
    ("appel dans la tete",
     "            self.pastilles[cle] = valeur\n        ligne.addStretch()\n",
     "            self.pastilles[cle] = valeur\n"
     "        try:\n"
     "            _tuile_capital(self, ligne)          # 12/11 : tuile CAPITAL\n"
     "        except Exception:\n"
     "            pass\n"
     "        ligne.addStretch()\n"),
]


def sauv(p):
    return p.with_name(p.name + ".avant_tuile_capital")


def lire_fichier(p):
    brut = p.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    return src.replace("\r\n", "\n"), bom, "\r\n" in src


def ecrire_fichier(p, texte, bom, crlf):
    sortie = texte.replace("\n", "\r\n") if crlf else texte
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))


def preparer(p, remplacements, marque):
    src, bom, crlf = lire_fichier(p)
    if marque in src:
        return None, bom, crlf, "deja"
    nouveau = src
    for nom, ancien, rempl in remplacements:
        if nouveau.count(ancien) != 1:
            return None, bom, crlf, f"Repere introuvable ou ambigu ({nom}) dans {p.name}"
        nouveau = nouveau.replace(ancien, rempl)
    try:
        compile(nouveau, str(p), "exec")
    except SyntaxError as e:
        return None, bom, crlf, f"{p.name} modifie ne compile pas ({e})"
    return nouveau, bom, crlf, "ok"


def main():
    if "--annuler" in sys.argv:
        fait = False
        for p in (T, U):
            if sauv(p).exists():
                shutil.copy2(sauv(p), p)
                print(f"Restaure : {p.name}")
                fait = True
        if not fait:
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        print("Redemarre GIMALY et le bot (redemarrer_bot.py).")
        return 0
    for p in (T, U):
        if not p.exists():
            print(f"{p} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    nt, bt, ct, et = preparer(T, REMPL_T, "_solde_etat")
    nu, bu, cu, eu = preparer(U, REMPL_U, "_tuile_capital")
    for e in (et, eu):
        if e not in ("ok", "deja"):
            print(e + " : ton fichier differe de celui que j'ai teste. RIEN n'est modifie.")
            return 1
    if et == "deja" and eu == "deja":
        print("Deja installe.")
        return 0
    if nt is not None:
        shutil.copy2(T, sauv(T))
        ecrire_fichier(T, nt, bt, ct)
    if nu is not None:
        shutil.copy2(U, sauv(U))
        ecrire_fichier(U, nu, bu, cu)
    print("Installe. Redemarre GIMALY (fenetre principale) ET le bot : .\\.venv\\Scripts\\python.exe redemarrer_bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
