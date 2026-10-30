# -*- coding: utf-8 -*-
"""CLASSEMENT A PARTAGER : ajoute deux boutons dans la fenetre « Classement par canal » de GIMALY.

  * COPIER LE TEXTE      : le classement de la periode choisie, au format du leaderboard de la ligue
                           (1️⃣ Nom +14.64R ...), pret a coller dans un message ;
  * EXPORTER EN IMAGE    : un tableau (rang, canal, barre, resultat) enregistre en PNG dans Images (ou dans
                           ton dossier utilisateur), et copie dans le presse-papiers (Ctrl+V pour le coller).

Attend la fin de la lecture des canaux avant d'exporter. Ne modifie ni les calculs ni l'affichage existant.
Retour en arriere : copie de gimaly/ui/classement.py.avant_partage sur gimaly/ui/classement.py.

A lancer sur TON PC, depuis le dossier gimaly, GIMALY FERME (sauvegarde, idempotent) :
  .\\.venv\\Scripts\\python.exe patch_classement_partage.py
"""
import shutil
import sys
from pathlib import Path

CIBLE = Path.cwd() / "gimaly" / "ui" / "classement.py"

BOUTONS_ANCIEN = "        entete.addWidget(self.periode)\n"
BOUTONS_NOUVEAU = '''        for texte_b, action_b in (("COPIER LE TEXTE", self._copier_texte),
                                  ("EXPORTER EN IMAGE", self._exporter_image)):
            bouton = QPushButton(texte_b)
            bouton.setFont(QFont("Consolas", 8))
            bouton.setStyleSheet(
                "QPushButton{background:#0f2a3a;border:1px solid #1e4a63;border-radius:3px;"
                "color:#9fb4c7;padding:3px 10px;} QPushButton:hover{border-color:#35d6ff;}")
            bouton.clicked.connect(action_b)
            entete.addWidget(bouton)
        self.retour_partage = QLabel("")
        self.retour_partage.setFont(QFont("Consolas", 8))
        self.retour_partage.setStyleSheet("color:#4ade80;")
        self.retour_partage.setWordWrap(True)
''' + BOUTONS_ANCIEN

LIGNE_ANCIEN = "        disposition.addWidget(self.progression)\n"
LIGNE_NOUVEAU = LIGNE_ANCIEN + "        disposition.addWidget(self.retour_partage)\n"

METHODES_ANCIEN = "    def closeEvent(self, evenement) -> None:  # noqa: N802 (API Qt)\n"
METHODES_NOUVEAU = '''    # ------------------------------------------------------------ partage
    def _classement_partage(self):
        """(libelle de periode, lignes triees [(canal, R)], nombre de canaux sans trade) ou None si la
        lecture n'est pas finie."""
        canaux = list(getattr(self.config, "signal_channels", None) or {})
        if not self.resultats or len(self.resultats) < len(canaux):
            self.retour_partage.setStyleSheet("color:#f0a030;")
            self.retour_partage.setText("Lecture des canaux en cours : attends la fin avant de partager.")
            return None
        lignes = sorted(((c, _r(s)) for c, s in self.resultats.items() if _r(s) is not None),
                        key=lambda p: -p[1])
        if not lignes:
            self.retour_partage.setStyleSheet("color:#f0a030;")
            self.retour_partage.setText("Aucun trade sur la période : rien à partager.")
            return None
        libelle = self.periode.currentText()
        try:
            depuis, jusqua, _ = self.assistant.registry._skills["signaux"].borne(self.periode.currentData() or "mois")
            libelle += f" ({depuis:%d/%m/%Y} au {jusqua:%d/%m/%Y})"
        except Exception:  # noqa: BLE001 (les dates sont un plus, pas une condition)
            pass
        return libelle, lignes, len(self.resultats) - len(lignes)

    @staticmethod
    def _rang(n: int) -> str:
        return "".join(c + "\\ufe0f\\u20e3" for c in str(n))

    @staticmethod
    def _nom(canal: str) -> str:
        return canal.strip().title()

    def _copier_texte(self) -> None:
        from PySide6.QtWidgets import QApplication

        donnees = self._classement_partage()
        if donnees is None:
            return
        libelle, lignes, muets = donnees
        texte = [f"⚡️CLASSEMENT WINLEAGUE⚡️ - {libelle}", ""]
        texte += [f"{self._rang(i)} {self._nom(c)} {r:+.2f}R" for i, (c, r) in enumerate(lignes, 1)]
        if muets:
            texte += ["", f"{muets} canaux sans trade sur la période"]
        QApplication.clipboard().setText("\\n".join(texte))
        self.retour_partage.setStyleSheet("color:#4ade80;")
        self.retour_partage.setText("Texte copié : colle-le dans ton message (Ctrl+V).")

    def _exporter_image(self) -> None:
        from datetime import datetime
        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        donnees = self._classement_partage()
        if donnees is None:
            return
        libelle, lignes, muets = donnees
        largeur, haut_ligne, haut_entete = 900, 34, 96
        hauteur = haut_entete + haut_ligne * len(lignes) + (30 if muets else 10) + 16
        image = QImage(largeur, hauteur, QImage.Format.Format_ARGB32)
        image.fill(QColor(10, 17, 23))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        police_titre = QFont("Segoe UI", 17)
        police_titre.setBold(True)
        p.setFont(police_titre)
        p.setPen(QColor(53, 214, 255))
        p.drawText(QRectF(28, 16, largeur - 56, 34), int(Qt.AlignmentFlag.AlignVCenter), "CLASSEMENT WINLEAGUE")
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor(150, 170, 186))
        p.drawText(QRectF(28, 52, largeur - 56, 24), int(Qt.AlignmentFlag.AlignVCenter),
                   f"{libelle} · résultat net en R")
        plus_grand = max((abs(r) for _, r in lignes), default=1.0) or 1.0
        x_nom, x_barre, l_valeur = 84, 330, 120
        piste = largeur - x_barre - l_valeur - 40
        for i, (canal, r) in enumerate(lignes, 1):
            y = haut_entete + (i - 1) * haut_ligne
            if i % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(14, 23, 32))
                p.drawRect(QRectF(16, y, largeur - 32, haut_ligne))
            couleur = VERT if r >= 0 else ROUGE
            p.setFont(QFont("Segoe UI", 11))
            p.setPen(QColor(110, 130, 148))
            p.drawText(QRectF(28, y, 48, haut_ligne), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(i))
            p.setPen(QColor(220, 232, 242))
            p.drawText(QRectF(x_nom, y, x_barre - x_nom - 10, haut_ligne), int(Qt.AlignmentFlag.AlignVCenter),
                       self._nom(canal))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(FOND_BARRE)
            p.drawRoundedRect(QRectF(x_barre, y + 11, piste, 12), 6, 6)
            p.setBrush(couleur)
            p.drawRoundedRect(QRectF(x_barre, y + 11, max(piste * min(abs(r) / plus_grand, 1.0), 6.0), 12), 6, 6)
            p.setPen(couleur)
            p.setFont(QFont("Consolas", 12))
            p.drawText(QRectF(largeur - l_valeur - 24, y, l_valeur, haut_ligne),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), f"{r:+.2f}R")
        if muets:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(90, 110, 128))
            p.drawText(QRectF(28, hauteur - 38, largeur - 56, 24), int(Qt.AlignmentFlag.AlignVCenter),
                       f"{muets} canaux sans trade sur la période")
        p.end()
        dossier = Path.home() / "Pictures"
        if not dossier.is_dir():
            dossier = Path.home()
        fichier = dossier / f"classement_winleague_{datetime.now():%Y%m%d_%H%M}.png"
        sauve = image.save(str(fichier), "PNG")
        QApplication.clipboard().setImage(image)
        self.retour_partage.setStyleSheet("color:#4ade80;")
        self.retour_partage.setText(
            "Image copiée (Ctrl+V pour la coller)" + (f" et enregistrée : {fichier}" if sauve else
                                                      " (enregistrement du fichier impossible)"))

''' + METHODES_ANCIEN


def une_fois(texte, ancien, nouveau, nom):
    n = texte.count(ancien)
    if n != 1:
        raise SystemExit(f"{nom} : repere trouve {n} fois (1 attendu) : rien n'a ete change")
    return texte.replace(ancien, nouveau)


def main():
    if not CIBLE.exists():
        raise SystemExit(f"{CIBLE} introuvable : lance ce script depuis le dossier gimaly")
    brut = CIBLE.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    texte = brut.decode("utf-8-sig")
    if "_exporter_image" in texte:
        print("Deja applique : rien a faire.")
        return
    crlf = "\r\n" in texte
    texte = texte.replace("\r\n", "\n")
    texte = une_fois(texte, BOUTONS_ANCIEN, BOUTONS_NOUVEAU, "boutons")
    texte = une_fois(texte, LIGNE_ANCIEN, LIGNE_NOUVEAU, "ligne de retour")
    texte = une_fois(texte, METHODES_ANCIEN, METHODES_NOUVEAU, "methodes")
    texte = une_fois(texte, "from PySide6.QtGui import QColor, QFont, QPainter\n",
                     "from PySide6.QtGui import QColor, QFont, QImage, QPainter\n", "import QImage")
    compile(texte, str(CIBLE), "exec")
    if crlf:
        texte = texte.replace("\n", "\r\n")
    sauvegarde = CIBLE.with_name("classement.py.avant_partage")
    if not sauvegarde.exists():
        shutil.copy2(CIBLE, sauvegarde)
    CIBLE.write_bytes((b"\xef\xbb\xbf" if bom else b"") + texte.encode("utf-8"))
    print(f"OK : boutons COPIER LE TEXTE et EXPORTER EN IMAGE ajoutes dans {CIBLE.name} (sauvegarde : {sauvegarde.name}).")
    print("Relance GIMALY pour les voir dans la fenetre du classement.")


if __name__ == "__main__":
    sys.exit(main())
