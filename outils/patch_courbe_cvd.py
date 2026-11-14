# -*- coding: utf-8 -*-
"""Fenetre BOT : ajoute la courbe CVD M3 + EMA 5/9/14 (et les croisements du bot CVD) entre le graphique et le tableau des trades.
Modifie UNIQUEMENT gimaly\\ui\\icebergs_panneau.py (affichage). Aucun ordre, aucun moteur, aucun redemarrage du bot : fermer puis rouvrir la fenetre GIMALY suffit.
Lit en lecture seule cvd_m3_independant\\cvd_m3_flux.csv (5 s), les journaux des 3 EMA, cvd_m3_etat.json, sinon GIMALY\\trading\\flux_minute.csv.
Erreur dans le bloc = bloc absent, le panneau s'affiche comme avant. Sauvegarde *.avant_courbe_cvd. Retour arriere : --annuler. Idempotent.
Usage (dossier gimaly) : .\\.venv\\Scripts\\python.exe patch_courbe_cvd.py [--annuler]"""
import shutil
import sys
from pathlib import Path

U = Path.cwd() / "gimaly" / "ui" / "icebergs_panneau.py"
MARQUE = "_bloc_cvd"
ANCRE_DEF = "def _texte_bot() -> str:\n"
ANCRE_SPLIT = (
    "        gauche.addWidget(cadre_graph)\n"
    "        gauche.addWidget(self.table)\n"
    "        gauche.setStretchFactor(0, 5)\n"
    "        gauche.setStretchFactor(1, 1)\n"
    "        self.table.setMinimumHeight(110)\n"
)
NOUV_SPLIT = (
    "        gauche.addWidget(cadre_graph)\n"
    "        try:\n"
    "            _bloc_cvd(self, gauche)\n"
    "        except Exception:\n"
    "            pass\n"
    "        gauche.addWidget(self.table)\n"
    "        if gauche.count() == 3:\n"
    "            gauche.setStretchFactor(0, 5)\n"
    "            gauche.setStretchFactor(1, 2)\n"
    "            gauche.setStretchFactor(2, 1)\n"
    "        else:\n"
    "            gauche.setStretchFactor(0, 5)\n"
    "            gauche.setStretchFactor(1, 1)\n"
    "        self.table.setMinimumHeight(110)\n"
)
BLOC = '# ---------------------------------------------------------------- 14/11 : courbe CVD M3 + EMA 5/9/14 (bot CVD) dans la fenetre BOT. Lecture seule de fichiers.\n_CVD_EMAS = (5, 9, 14)\n_CVD_COULEURS = {5: "#2dd4bf", 9: "#f5b942", 14: "#a78bfa"}\n\n\ndef _cvd_fin_de_fichier(chemin, octets=500_000):\n    import os\n    with open(chemin, "rb") as f:\n        f.seek(0, os.SEEK_END)\n        taille = f.tell()\n        f.seek(max(0, taille - octets))\n        brut = f.read()\n    lignes = brut.decode("utf-8-sig", errors="ignore").splitlines()\n    return lignes[1:] if taille > octets else lignes\n\n\ndef _cvd_points(dossier_cvd, dossier_flux):\n    """(points [(ts, cvd, session)], source, fichier). Journal du bot CVD (5 s) sinon flux_minute.csv de GIMALY (1 min)."""\n    from pathlib import Path\n    p = Path(dossier_cvd) / "cvd_m3_flux.csv"\n    if p.exists():\n        pts = []\n        for l in _cvd_fin_de_fichier(p):\n            c = l.split(";")\n            try:\n                pts.append((float(c[1]), float(c[3]), int(c[2])))\n            except (ValueError, IndexError):\n                continue\n        if pts:\n            return pts, "journal du bot CVD (5 s)", p\n    p = Path(dossier_flux) / "flux_minute.csv"\n    if p.exists():\n        with open(p, "r", encoding="utf-8-sig") as f:\n            entete = f.readline().strip().split(";")\n        if "ts" in entete and "cvd" in entete and "session" in entete:\n            i_ts, i_cvd, i_s = entete.index("ts"), entete.index("cvd"), entete.index("session")\n            pts = []\n            for l in _cvd_fin_de_fichier(p, 300_000):\n                c = l.split(";")\n                try:\n                    pts.append((float(c[i_ts]), float(c[i_cvd]), int(float(c[i_s]))))\n                except (ValueError, IndexError):\n                    continue\n            if pts:\n                return pts, "flux_minute.csv (1 point par minute)", p\n    return [], "", None\n\n\ndef _cvd_lignes(pts):\n    """Lignes EMA 5/9/14 du CVD, calculees comme le bot : EMA des clotures M3 precedentes, ligne intrabougie = a*CVD + (1-a)*EMA."""\n    etats = {n: {"a": 2.0 / (n + 1), "ema": None, "seau": None, "dern": None, "barres": 0} for n in _CVD_EMAS}\n    sortie = {n: [] for n in _CVD_EMAS}\n    prec_t = prec_s = None\n    for ts, cvd, sess in pts:\n        if prec_s is not None and (sess != prec_s or ts - prec_t > 300):\n            for e in etats.values():\n                e.update(ema=None, seau=None, dern=None, barres=0)\n        prec_t, prec_s = ts, sess\n        seau = int(ts // 180)\n        for n, e in etats.items():\n            if e["seau"] is None:\n                e["seau"], e["ema"] = seau, cvd\n            elif seau != e["seau"]:\n                cl = e["dern"] if e["dern"] is not None else cvd\n                for _ in range(min(seau - e["seau"], 500)):\n                    e["ema"] = e["a"] * cl + (1 - e["a"]) * e["ema"]\n                    e["barres"] += 1\n                e["seau"] = seau\n            e["dern"] = cvd\n            sortie[n].append((ts, e["a"] * cvd + (1 - e["a"]) * e["ema"] if e["barres"] >= 1 else None))\n    return sortie\n\n\ndef _cvd_marqueurs(dossier_cvd, depuis):\n    """Croisements reellement detectes par le bot CVD (journaux des 3 EMA + positions encore ouvertes)."""\n    import json\n    from pathlib import Path\n    d = Path(dossier_cvd)\n    out = []\n    for n in _CVD_EMAS:\n        p = d / f"cvd_m3_ema{n}_trades.csv"\n        if p.exists():\n            try:\n                for l in _cvd_fin_de_fichier(p, 300_000):\n                    c = l.split(";")\n                    try:\n                        ts = float(c[4])\n                    except (ValueError, IndexError):\n                        continue\n                    if ts >= depuis and c[2] in ("BUY", "SELL"):\n                        out.append((ts, n, c[2]))\n            except OSError:\n                pass\n    try:\n        et = json.loads((d / "cvd_m3_etat.json").read_text(encoding="utf-8"))\n        for n, liste in et.get("ouvertes", {}).items():\n            for q in liste:\n                if float(q["ts"]) >= depuis and int(n) in _CVD_EMAS:\n                    out.append((float(q["ts"]), int(n), q["sens"]))\n    except (OSError, ValueError, KeyError, TypeError):\n        pass\n    return sorted(set(out))\n\n\ndef _cvd_lire(dossier_cvd, dossier_flux, maintenant=None, fenetre_s=3 * 3600):\n    """Donnees de la courbe, ou None s\'il n\'y en a pas. Ne touche a aucun fichier (lecture seule)."""\n    import time\n    pts, source, _ = _cvd_points(dossier_cvd, dossier_flux)\n    if not pts:\n        return None\n    pts.sort()\n    derniere = pts[-1][2]\n    pts = [p for p in pts if p[2] == derniere]            # session en cours seulement\n    lignes = _cvd_lignes(pts)\n    t_fin = pts[-1][0]\n    t_deb = t_fin - fenetre_s\n    pts_f = [(t, v) for t, v, _ in pts if t >= t_deb]\n    pas = max(1, len(pts_f) // 1500)\n    pts_f = pts_f[::pas] + ([pts_f[-1]] if pts_f and (len(pts_f) - 1) % pas else [])\n    lg = {n: [(t, v) for (t, v) in lignes[n] if t >= t_deb and v is not None][::pas] for n in _CVD_EMAS}\n    return {"points": pts_f, "lignes": lg, "marqueurs": [m for m in _cvd_marqueurs(dossier_cvd, t_deb) if m[0] <= t_fin + 60],\n            "source": source, "age": (maintenant or time.time()) - t_fin, "t_deb": t_deb, "t_fin": t_fin, "dernier": pts[-1][1]}\n\n\ndef _bloc_cvd(panneau, gauche, dossier_cvd=None, dossier_flux=None):\n    """Ajoute dans le separateur `gauche` un bloc « CVD M3 · EMA 5/9/14 ». Echec silencieux : le panneau continue sans."""\n    from pathlib import Path\n    try:\n        from PySide6.QtCore import QPointF, Qt, QTimer\n        from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF\n        from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget\n    except ImportError:\n        from PyQt6.QtCore import QPointF, Qt, QTimer\n        from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF\n        from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget\n    import time\n    d_cvd = Path(dossier_cvd) if dossier_cvd else Path(__file__).resolve().parents[2] / "cvd_m3_independant"\n    d_flux = Path(dossier_flux) if dossier_flux else Path.home() / "GIMALY" / "trading"\n\n    class _Courbe(QWidget):\n        def __init__(self):\n            super().__init__()\n            self.setMinimumHeight(150)\n            self.donnees = None\n            self.message = "lecture..."\n            self._cle = None\n            self._minuteur = QTimer(self)\n            self._minuteur.timeout.connect(self.rafraichir)\n            self._minuteur.start(5000)\n            self.rafraichir()\n\n        def rafraichir(self):\n            try:\n                if not self.isVisible() and self.donnees is not None:\n                    return\n                cle = []\n                for p in (d_cvd / "cvd_m3_flux.csv", d_flux / "flux_minute.csv", d_cvd / "cvd_m3_etat.json"):\n                    try:\n                        s = p.stat()\n                        cle.append((s.st_mtime, s.st_size))\n                    except OSError:\n                        cle.append(None)\n                if cle != self._cle or self.donnees is None:\n                    self._cle = cle\n                    self.donnees = _cvd_lire(d_cvd, d_flux)\n                    self.message = "" if self.donnees else "pas de donnees CVD (bot CVD jamais lance ?)"\n            except Exception as e:                      # jamais d\'erreur vers le panneau\n                self.message = "courbe CVD indisponible : " + repr(e)[:60]\n            self.update()\n\n        def paintEvent(self, ev):  # noqa: N802\n            p = QPainter(self)\n            try:\n                self._dessiner(p)\n            except Exception:\n                pass\n            finally:\n                p.end()\n\n        def _dessiner(self, p):\n            w, h = self.width(), self.height()\n            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)\n            p.fillRect(0, 0, w, h, QColor("#070d16"))\n            f = p.font()\n            f.setPointSize(8)\n            p.setFont(f)\n            gris = QColor("#6f8aa3")\n            p.setPen(QColor("#1a7a99"))\n            p.drawText(12, 16, "CVD M3 · EMA 5 / 9 / 14")\n            x = 190\n            for n in _CVD_EMAS:\n                p.setPen(QPen(QColor(_CVD_COULEURS[n]), 3))\n                p.drawLine(x, 12, x + 16, 12)\n                p.setPen(gris)\n                p.drawText(x + 20, 16, f"EMA {n}")\n                x += 74\n            p.setPen(gris)\n            p.drawText(x + 4, 16, "▲ achat  ▼ vente")\n            dd = self.donnees\n            if not dd:\n                p.setPen(gris)\n                p.drawText(12, h // 2, self.message)\n                return\n            L, R, T, B = 52, 70, 26, 20\n            pts = dd["points"]\n            ys = [v for _, v in pts] + [v for n in _CVD_EMAS for _, v in dd["lignes"][n]]\n            y0, y1 = min(ys + [0]), max(ys + [0])\n            if y1 - y0 < 2:\n                y0, y1 = y0 - 1, y1 + 1\n            marge = (y1 - y0) * 0.08\n            y0, y1 = y0 - marge, y1 + marge\n            t0, t1 = dd["t_deb"], max(dd["t_fin"], dd["t_deb"] + 60)\n            X = lambda t: L + (t - t0) / (t1 - t0) * (w - L - R)\n            Y = lambda v: T + (1 - (v - y0) / (y1 - y0)) * (h - T - B)\n            p.setPen(QPen(QColor(255, 255, 255, 18), 1))\n            for i in range(5):\n                v = y0 + (y1 - y0) * i / 4\n                p.drawLine(L, int(Y(v)), w - R, int(Y(v)))\n                p.setPen(gris)\n                p.drawText(2, int(Y(v)) + 4, f"{v:+.0f}")\n                p.setPen(QPen(QColor(255, 255, 255, 18), 1))\n            pen0 = QPen(QColor("#4a5d7a"), 1)\n            pen0.setStyle(Qt.PenStyle.DashLine)\n            p.setPen(pen0)\n            p.drawLine(L, int(Y(0)), w - R, int(Y(0)))\n            p.setPen(gris)\n            for k in range(4):\n                t = t0 + (t1 - t0) * k / 3\n                heure = time.strftime("%H:%M", time.localtime(t))\n                p.drawText(int(X(t)) - (0 if k == 0 else 28 if k == 3 else 14), h - 5, heure)\n\n            def courbe(serie, couleur, ep):\n                if len(serie) < 2:\n                    return\n                p.setPen(QPen(QColor(couleur), ep))\n                prec = None\n                for t, v in serie:\n                    pt = QPointF(X(t), Y(v))\n                    if prec is not None and t - prec[0] < 600:           # pas de trait au travers d\'un trou de donnees\n                        p.drawLine(prec[1], pt)\n                    prec = (t, pt)\n            for n in _CVD_EMAS:\n                courbe(dd["lignes"][n], _CVD_COULEURS[n], 1.3)\n            courbe(pts, "#35d6ff", 1.9)\n            for t, n, sens in dd["marqueurs"]:\n                if t < t0 or not pts:\n                    continue\n                v = min(pts, key=lambda q: abs(q[0] - t))[1]\n                cx, cy = X(t), Y(v)\n                tri = QPolygonF([QPointF(cx, cy - 7), QPointF(cx - 5, cy + 2), QPointF(cx + 5, cy + 2)]) if sens == "BUY" else \\\n                    QPolygonF([QPointF(cx, cy + 7), QPointF(cx - 5, cy - 2), QPointF(cx + 5, cy - 2)])\n                p.setPen(QPen(QColor("#05080f"), 1))\n                p.setBrush(QColor(_CVD_COULEURS[n]))\n                p.drawPolygon(tri)\n                p.setBrush(Qt.BrushStyle.NoBrush)\n            dernier = dd["dernier"]\n            p.setPen(QColor("#35d6ff"))\n            p.drawText(w - R + 6, int(Y(dernier)) + 4, f"{dernier:+.0f}")\n            age = dd["age"]\n            etat = ("à jour" if age < 20 else f"figé depuis {age / 60:.0f} min" if age < 7200 else f"figé depuis {age / 3600:.0f} h (marché fermé ?)")\n            p.setPen(gris if age < 20 else QColor("#f5b942"))\n            p.drawText(w - 330, 16, f"{dd[\'source\'].split(\' (\')[0]} · {etat}".rjust(48))\n\n    cadre = QFrame()\n    cadre.setStyleSheet("QFrame{background:#070d16;border:1px solid rgba(255,255,255,0.06);border-radius:14px;}")\n    pile = QVBoxLayout(cadre)\n    pile.setContentsMargins(8, 4, 8, 4)\n    pile.addWidget(_Courbe())\n    gauche.addWidget(cadre)\n\n\n'


def sauv(p):
    return p.with_name(p.name + ".avant_courbe_cvd")


def main(chemin=None):
    u = Path(chemin) if chemin else U
    if "--annuler" in sys.argv:
        if not sauv(u).exists():
            print("Pas de sauvegarde : rien a annuler.")
            return 1
        shutil.copy2(sauv(u), u)
        print("Restaure : " + u.name + ". Ferme puis rouvre la fenetre GIMALY.")
        return 0
    if not u.exists():
        print(f"{u} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = u.read_bytes()
    bom = brut.startswith(b"\xef\xbb\xbf")
    src = brut.decode("utf-8-sig")
    crlf = "\r\n" in src
    src = src.replace("\r\n", "\n")
    if MARQUE in src:
        print("Deja installe.")
        return 0
    if src.count(ANCRE_DEF) != 1 or src.count(ANCRE_SPLIT) != 1:
        print("Repere introuvable ou ambigu : ton fichier differe de celui que j'ai teste. RIEN n'est modifie.")
        return 1
    nouveau = src.replace(ANCRE_SPLIT, NOUV_SPLIT).replace(ANCRE_DEF, BLOC + ANCRE_DEF)
    try:
        compile(nouveau, str(u), "exec")
    except SyntaxError as e:
        print(f"Le fichier modifie ne compile pas ({e}). RIEN n'est modifie.")
        return 1
    shutil.copy2(u, sauv(u))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    u.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("Installe. Ferme puis rouvre la fenetre GIMALY (pas besoin de redemarrer le bot).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
