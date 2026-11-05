# -*- coding: utf-8 -*-
r"""Patch : BILAN MENSUEL du bot (R, RR, facteur de profit, sans argent) : page + envoi automatique sur Telegram.

  * gimaly/core/bilan_mensuel.py (nouveau) : calcule le bilan d'un mois a partir de trades_bot.csv (trades REELS termines), produit une
    page autonome (courbe, resultat par jour, par moteur, par sens, par semaine, comparaison avec le mois precedent) et un message Telegram.
    Le 1er du mois (a partir de 9 h), GIMALY envoie tout seul le bilan du mois ecoule dans tes messages enregistres, une seule fois.
    A la premiere mise en route, rien n'est renvoye pour le passe ; il reste disponible a la demande (bouton « Envoyer sur Telegram »).
  * web.py : page /bilan-mensuel?mois=AAAA-MM (jeton principal), envoi a la demande, lien « Bilan mensuel » dans la page PERFORMANCE,
    demarrage de la surveillance du calendrier.
Prerequis : patch_performance_gimaly + patch_performance_live. Rien n'est modifie dans le bot ni dans les donnees.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_bilan_mensuel.py   puis redemarrer GIMALY (fenetre principale).
Sauvegardes : web.py.avant_bilan_mensuel (et bilan_mensuel.py.avant si mise a jour). Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd() / "gimaly"
F_WEB = RACINE / "bridges" / "web.py"
F_MOD = RACINE / "core" / "bilan_mensuel.py"
MARQUE = '"/bilan-mensuel"'

MODULE = r'''# -*- coding: utf-8 -*-
"""Bilan mensuel du bot : trades REELS termines (trades_bot.csv), en R, sans argent.

* html(mois) : page autonome (aucun script, SVG integre) : se lit dans un navigateur, sur telephone, ou s'imprime.
* envoyer(config, mois) : message Telegram (dans tes messages enregistres) + fichier de rapport.
* demarrer(assistant) : surveille le calendrier ; le 1er du mois (a partir de 9 h), envoie le bilan du mois ecoule.
Lecture seule sur les donnees du bot.
"""
from __future__ import annotations

import csv
import html as _h
import json
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
ETAT = DOSSIER / "bilan_mensuel_envoye.json"
MOIS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]
SEUIL_GROUPE = 30            # en dessous : « trop peu de trades » pour un groupe
_verrou = threading.Lock()


def libelle(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{MOIS_FR[m - 1]} {a}"


def mois_avant(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def mois_apres(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a + 1}-01" if m == 12 else f"{a}-{m + 1:02d}"


def mois_courant() -> str:
    return date.today().strftime("%Y-%m")


def _nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def lire_trades() -> list[dict]:
    """Trades termines, tries par date/heure. Les trades « ouvert » sont ignores."""
    sortie = []
    try:
        with open(DOSSIER / "trades_bot.csv", newline="", encoding="utf-8-sig") as f:
            for l in csv.DictReader(f, delimiter=";"):
                if (l.get("resultat") or "").strip() in ("", "ouvert"):
                    continue
                try:
                    jour = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
                except ValueError:
                    continue
                r = _nombre(l.get("R"))
                if r is None:
                    continue
                h = (l.get("heure") or "").strip()
                try:
                    jour = jour.replace(hour=int(h[:2]), minute=int(h[3:5]))
                except ValueError:
                    pass
                sortie.append({"t": jour, "jour": jour.date(), "genre": (l.get("genre") or "?").strip() or "?",
                               "sens": (l.get("sens") or "?").strip().lower(), "r": r})
    except OSError:
        return []
    sortie.sort(key=lambda x: x["t"])
    return sortie


def _groupe(rs: list[float]) -> dict:
    gagn = [r for r in rs if r > 0.05]
    perd = [r for r in rs if r < -0.05]
    gains, pertes = sum(gagn), -sum(perd)
    return {"n": len(rs), "r": sum(rs), "moy": statistics.fmean(rs) if rs else 0.0,
            "reussite": 100 * len(gagn) / len(rs) if rs else 0.0, "nb_gagn": len(gagn), "nb_perd": len(perd),
            "pf": (gains / pertes) if pertes else None,
            "rr": (statistics.fmean(gagn) / abs(statistics.fmean(perd))) if gagn and perd else None}


def calculer(mois: str, trades: list[dict] | None = None) -> dict:
    trades = lire_trades() if trades is None else trades
    du_mois = [t for t in trades if t["jour"].strftime("%Y-%m") == mois]
    prec = [t for t in trades if t["jour"].strftime("%Y-%m") == mois_avant(mois)]
    s = _groupe([t["r"] for t in du_mois])
    s["mois"], s["libelle"] = mois, libelle(mois)
    cumul = sommet = recul = 0.0
    courbe = []
    for t in du_mois:
        cumul += t["r"]
        sommet = max(sommet, cumul)
        recul = max(recul, sommet - cumul)
        courbe.append(cumul)
    s["courbe"], s["recul"] = courbe, recul
    jours: dict = {}
    for t in du_mois:
        jours.setdefault(t["jour"], []).append(t["r"])
    s["jours"] = [(j, sum(v), len(v)) for j, v in sorted(jours.items())]
    s["jours_pos"] = sum(1 for _, r, _ in s["jours"] if r > 0)
    serie = c = 0
    for t in du_mois:
        c = c + 1 if t["r"] < -0.5 else 0
        serie = max(serie, c)
    s["serie_stops"] = serie
    s["seuil_reussite"] = (100 / (1 + s["rr"])) if s["rr"] else None
    moteurs: dict = {}
    for t in du_mois:
        moteurs.setdefault(t["genre"], []).append(t["r"])
    s["moteurs"] = sorted(((g, _groupe(v)) for g, v in moteurs.items()), key=lambda x: -x[1]["r"])
    sens: dict = {}
    for t in du_mois:
        sens.setdefault(t["sens"], []).append(t["r"])
    s["sens"] = [(k, _groupe(v)) for k, v in sorted(sens.items())]
    semaines: dict = {}
    for t in du_mois:
        lundi = t["jour"] - timedelta(days=t["jour"].weekday())
        semaines.setdefault(lundi, []).append(t["r"])
    s["semaines"] = [(d, _groupe(v)) for d, v in sorted(semaines.items())]
    s["prec"] = _groupe([t["r"] for t in prec]) if prec else None
    s["prec_libelle"] = libelle(mois_avant(mois))
    s["meilleur"] = max(s["jours"], key=lambda x: x[1]) if s["jours"] else None
    s["pire"] = min(s["jours"], key=lambda x: x[1]) if s["jours"] else None
    return s


def _f(x, d=2):
    return ("+" if x >= 0 else "-") + f"{abs(x):.{d}f}".replace(".", ",")


def _n(x, d=2):
    return "–" if x is None else f"{x:.{d}f}".replace(".", ",")


def _jj(d: date) -> str:
    return d.strftime("%d/%m")


def texte(s: dict) -> str:
    """Message Telegram (sans argent)."""
    if not s["n"]:
        return f"Bilan du bot, {s['libelle']} : aucun trade termine."
    lignes = [f"BILAN DU BOT, {s['libelle'].upper()}", "",
              f"{_f(s['r'], 1)} R sur {s['n']} trades (R moyen {_f(s['moy'], 3)})",
              f"Reussite {s['reussite']:.0f} % ({s['nb_gagn']} gagnants, {s['nb_perd']} perdants)",
              f"Facteur de profit {_n(s['pf'])} · RR moyen {_n(s['rr'])}"
              + (f" (rentable a partir de {s['seuil_reussite']:.0f} % de gagnants)" if s["seuil_reussite"] else ""),
              f"Pire recul {_f(-s['recul'], 1)} R · plus longue serie de stops {s['serie_stops']}",
              f"Jours positifs {s['jours_pos']} / {len(s['jours'])}"]
    if s["meilleur"]:
        lignes.append(f"Meilleur jour {_jj(s['meilleur'][0])} {_f(s['meilleur'][1], 1)} R · pire {_jj(s['pire'][0])} {_f(s['pire'][1], 1)} R")
    if s["prec"]:
        lignes.append(f"Mois precedent ({s['prec_libelle']}) : {_f(s['prec']['r'], 1)} R sur {s['prec']['n']} trades, "
                      f"facteur de profit {_n(s['prec']['pf'])}")
    if s["moteurs"]:
        lignes += ["", "Par moteur :"] + [
            f"- {g} : {_f(m['r'], 1)} R sur {m['n']} trades" + (" (trop peu de trades pour conclure)" if m["n"] < SEUIL_GROUPE else "")
            for g, m in s["moteurs"]]
    lignes += ["", "Lecture : sur un seul mois et quelques dizaines de trades, ces chiffres restent fragiles (R, sans argent)."]
    return "\n".join(lignes)


# --------------------------------------------------------------------------- HTML
def _svg_courbe(courbe: list[float], largeur=720, hauteur=240) -> str:
    if len(courbe) < 2:
        return "<p class='note'>Pas assez de trades pour tracer une courbe.</p>"
    pts = [0.0] + courbe
    lo, hi = min(pts), max(pts)
    if hi - lo < 1e-9:
        hi, lo = hi + 1, lo - 1
    g, d, h, b = 46, 12, 12, 24
    w, ht = largeur - g - d, hauteur - h - b
    X = lambda i: g + w * i / (len(pts) - 1)
    Y = lambda v: h + ht * (hi - v) / (hi - lo)
    ligne = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(pts))
    aire = f"{X(0):.1f},{Y(0):.1f} " + ligne + f" {X(len(pts) - 1):.1f},{Y(0):.1f}"
    graduations = "".join(
        f"<line x1='{g}' x2='{g + w}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' class='gr'/><text x='{g - 6}' y='{Y(v) + 4:.1f}' text-anchor='end'>{('%+d' % v) if v else '0'}</text>"
        for v in sorted({round(lo), round((lo + hi) / 2), round(hi), 0}) if lo - 0.01 <= v <= hi + 0.01)
    return (f"<svg viewBox='0 0 {largeur} {hauteur}' role='img' aria-label='Courbe du mois en R'>{graduations}"
            f"<line x1='{g}' x2='{g + w}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' class='zero'/>"
            f"<polygon points='{aire}' class='aire'/><polyline points='{ligne}' class='courbe' fill='none'/>"
            f"<text x='{g}' y='{hauteur - 6}'>1er trade</text><text x='{g + w}' y='{hauteur - 6}' text-anchor='end'>{len(courbe)} trades</text></svg>")


def _svg_jours(jours, largeur=720, hauteur=200) -> str:
    if not jours:
        return ""
    vals = [r for _, r, _ in jours]
    m = max(max(abs(v) for v in vals), 1.0)
    g, d, h, b = 46, 12, 12, 26
    w, ht = largeur - g - d, hauteur - h - b
    z = h + ht / 2
    pas = w / len(jours)
    lp = min(24.0, pas * 0.7)
    barres = []
    for i, (j, r, n) in enumerate(jours):
        x = g + pas * i + (pas - lp) / 2
        hh = abs(r) / m * ht / 2
        y = z - hh if r >= 0 else z
        barres.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{lp:.1f}' height='{max(hh, 0.8):.1f}' class='{'pos' if r >= 0 else 'neg'}'><title>{_jj(j)} : {_f(r, 1)} R sur {n} trades</title></rect>")
        if len(jours) <= 16 or i % 2 == 0:
            barres.append(f"<text x='{x + lp / 2:.1f}' y='{hauteur - 8}' text-anchor='middle' class='j'>{_jj(j)}</text>")
    return (f"<svg viewBox='0 0 {largeur} {hauteur}' role='img' aria-label='Resultat par jour en R'>"
            f"<line x1='{g}' x2='{g + w}' y1='{z:.1f}' y2='{z:.1f}' class='zero'/>"
            f"<text x='{g - 6}' y='{h + 8}' text-anchor='end'>{m:+.0f}</text><text x='{g - 6}' y='{h + ht}' text-anchor='end'>{-m:+.0f}</text>"
            + "".join(barres) + "</svg>")


def _tableau(titre: str, lignes: list[tuple[str, dict]]) -> str:
    if not lignes:
        return ""
    corps = "".join(
        f"<tr><td>{_h.escape(str(nom))}</td><td class='n'>{m['n']}</td><td class='n'>{m['reussite']:.0f} %</td>"
        f"<td class='n {'pos' if m['r'] >= 0 else 'neg'}'>{_f(m['r'], 1)}</td><td class='n'>{_n(m['pf'])}</td><td class='n'>{_n(m['rr'])}</td>"
        f"<td class='note'>{'trop peu de trades' if m['n'] < SEUIL_GROUPE else ''}</td></tr>" for nom, m in lignes)
    return (f"<section><h2>{titre}</h2><div class='tw'><table><thead><tr><th></th><th class='n'>trades</th><th class='n'>reussite</th>"
            f"<th class='n'>R</th><th class='n'>fact. profit</th><th class='n'>RR</th><th></th></tr></thead><tbody>{corps}</tbody></table></div></section>")


def html(mois: str, trades=None, jeton: str = "", actions: bool = False) -> str:
    s = calculer(mois, trades)
    nav = ""
    if actions:
        k = f"&k={jeton}" if jeton else ""
        nav = (f"<nav><a href='/bilan-mensuel?mois={mois_avant(mois)}{k}'>&larr; {_h.escape(libelle(mois_avant(mois)))}</a>"
               f"<a href='/bilan-mensuel?mois={mois_apres(mois)}{k}'>{_h.escape(libelle(mois_apres(mois)))} &rarr;</a>"
               f"<a href='/performance{('?k=' + jeton) if jeton else ''}'>Track record</a>"
               f"<button id='envoi' data-mois='{mois}'>Envoyer sur Telegram</button><span id='etat'></span></nav>")
    if not s["n"]:
        corps = f"<p class='note'>Aucun trade termine en {_h.escape(s['libelle'])}.</p>"
    else:
        def carte(titre, valeur, sous="", cls=""):
            return f"<div class='carte'><span>{titre}</span><b class='{cls}'>{valeur}</b><small>{sous}</small></div>"
        p = s["prec"]
        cartes = "".join([
            carte("R du mois", _f(s["r"], 1), f"sur {s['n']} trades · R moyen {_f(s['moy'], 3)}", "pos" if s["r"] >= 0 else "neg"),
            carte("Facteur de profit", _n(s["pf"]), "gains / pertes en R · au-dessus de 1 = gagnant",
                  "" if s["pf"] is None else ("pos" if s["pf"] >= 1 else "neg")),
            carte("RR moyen", _n(s["rr"]), (f"rentable a partir de {s['seuil_reussite']:.0f} % de gagnants" if s["seuil_reussite"] else "")),
            carte("Reussite", f"{s['reussite']:.0f} %", f"{s['nb_gagn']} gagnants · {s['nb_perd']} perdants"),
            carte("Pire recul", _f(-s["recul"], 1) + " R", "depuis un sommet, dans le mois", "neg" if s["recul"] > 0 else ""),
            carte("Jours positifs", f"{s['jours_pos']} / {len(s['jours'])}",
                  (f"meilleur {_jj(s['meilleur'][0])} {_f(s['meilleur'][1], 1)} R · pire {_jj(s['pire'][0])} {_f(s['pire'][1], 1)} R" if s["meilleur"] else "")),
            carte("Plus longue serie de stops", str(s["serie_stops"]), "trades de suite"),
            carte("Mois precedent", (_f(p["r"], 1) + " R") if p else "–",
                  (f"{_h.escape(s['prec_libelle'])} · {p['n']} trades · fact. profit {_n(p['pf'])}" if p else "pas de trades"),
                  "" if not p else ("pos" if p["r"] >= 0 else "neg"))])
        corps = (f"<section class='cartes'>{cartes}</section>"
                 f"<section><h2>Courbe du mois (R cumule)</h2>{_svg_courbe(s['courbe'])}</section>"
                 f"<section><h2>Resultat par jour (R)</h2>{_svg_jours(s['jours'])}</section>"
                 + _tableau("Par moteur", s["moteurs"]) + _tableau("Par sens", s["sens"])
                 + _tableau("Par semaine", [(f"semaine du {_jj(d)}", m) for d, m in s["semaines"]]))
    titre = f"Bilan du bot, {s['libelle']}"
    script = ""
    if actions:
        script = ("<script>const b=document.getElementById('envoi');if(b){b.onclick=async()=>{const e=document.getElementById('etat');"
                  "e.textContent='envoi...';try{const k=new URLSearchParams(location.search).get('k')||'';"
                  "const r=await fetch('/api/bilan-mensuel/envoyer?mois='+b.dataset.mois,{headers:{'X-Jeton':k}});"
                  "const d=await r.json();e.textContent=d.message||d.erreur||'';}catch(x){e.textContent='echec : '+x;}};}</script>")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h.escape(titre)}</title>
<style>
:root{{--bg:#f4f6f9;--panel:#fff;--fg:#14181f;--mute:#5b6573;--line:#dfe3ea;--pos:#0b6e4f;--neg:#b3261e;--acc:#2f5bd8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#070b10;--panel:#0d141c;--fg:#d6e4f0;--mute:#8aa0b3;--line:#1b2f40;--pos:#4ade80;--neg:#ff6b6b;--acc:#35d6ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif;padding:20px 16px 48px}}
main{{max-width:900px;margin:0 auto;display:flex;flex-direction:column;gap:18px}}
h1{{font-size:22px;margin:0}}h2{{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}}
.sub{{color:var(--mute);margin:4px 0 0}}nav{{display:flex;gap:14px;flex-wrap:wrap;align-items:center}}nav a{{color:var(--acc);text-decoration:none}}
button{{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px;padding:5px 10px;cursor:pointer}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}}
section.cartes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;background:none;border:none;padding:0}}
.carte{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}.carte span{{display:block;font-size:12px;color:var(--mute)}}
.carte b{{display:block;font-size:22px;font-variant-numeric:tabular-nums}}.carte small{{color:var(--mute);font-size:11px}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}svg{{width:100%;height:auto;display:block}}svg text{{fill:var(--mute);font-size:11px}}
.gr{{stroke:var(--line)}}.zero{{stroke:var(--mute);stroke-dasharray:3 3}}.aire{{fill:var(--acc);opacity:.12}}.courbe{{stroke:var(--acc);stroke-width:2}}
rect.pos{{fill:var(--pos)}}rect.neg{{fill:var(--neg)}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th{{text-align:left;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mute);padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}.n{{text-align:right}}.note{{color:var(--mute);font-size:12px}}
@media print{{body{{background:#fff}}nav{{display:none}}}}
</style></head><body><main>
<header><h1>{_h.escape(titre)}</h1><p class="sub">Trades reels termines, resultats en R (sans argent) · genere le {datetime.now():%d/%m/%Y %H:%M}</p></header>
{nav}{corps}
<p class="note">Lecture : le R mesure le gain en multiples du risque pris. Sur un mois, les groupes de moins de {SEUIL_GROUPE} trades ne permettent pas de conclure ; le facteur de profit et le RR n'ont de sens que sur la duree. Ce document decrit le passe, il ne garantit rien.</p>
</main>{script}</body></html>"""


# --------------------------------------------------------------------------- envoi
def fichier_rapport(mois: str) -> Path:
    chemin = DOSSIER / f"bilan_bot_{mois}.html"
    chemin.write_text(html(mois), encoding="utf-8")
    return chemin


def _envoyer_telegram(config, message: str, chemin: Path) -> None:
    from ..bridges import telegram_lecture as tl

    @tl.exclusif
    def tache(cfg):
        client = tl._client(cfg)
        client.send_message("me", message)
        client.send_file("me", str(chemin), caption="Bilan detaille (a ouvrir dans le navigateur)")

    tache(config)


def envoyer(config, mois: str) -> str:
    with _verrou:
        s = calculer(mois)
        if not s["n"]:
            return f"Aucun trade termine en {s['libelle']} : rien envoye."
        _envoyer_telegram(config, texte(s), fichier_rapport(mois))
        return f"Bilan de {s['libelle']} envoye sur ton Telegram (messages enregistres)."


def _etat() -> dict:
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire_etat(d: dict) -> None:
    try:
        ETAT.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def verifier(config) -> str | None:
    """A appeler regulierement : envoie le bilan du mois ecoule une seule fois, a partir de 9 h le 1er jour du mois."""
    maintenant = datetime.now()
    precedent = mois_avant(mois_courant())
    etat = _etat()
    if "dernier" not in etat:
        # premiere mise en route : on ne renvoie pas le passe, il reste disponible a la demande
        _ecrire_etat({"dernier": precedent})
        return None
    if etat["dernier"] == precedent or maintenant.hour < 9:
        return None
    if not any(t["jour"].strftime("%Y-%m") == precedent for t in lire_trades()):
        _ecrire_etat({"dernier": precedent})
        return None
    message = envoyer(config, precedent)
    _ecrire_etat({"dernier": precedent})
    return message


def demarrer(assistant) -> None:
    """Fil d'arriere-plan : controle toutes les 15 minutes ; en cas d'echec, reessaie au tour suivant."""
    if getattr(demarrer, "_lance", False):
        return
    demarrer._lance = True

    def boucle():
        time.sleep(90)
        while True:
            try:
                verifier(assistant.config)
            except Exception as exc:  # noqa: BLE001 - ne jamais gener GIMALY
                print(f"[bilan mensuel] {exc!r}")
            time.sleep(900)

    threading.Thread(target=boucle, name="bilan-mensuel", daemon=True).start()
'''

ROUTE = """            elif chemin in ("/bilan-mensuel", "/api/bilan-mensuel/envoyer"):
                if not self._autorise():          # jeton principal uniquement
                    self._repondre(403, b'{"erreur":"jeton"}', "application/json")
                    return
                from ..core import bilan_mensuel as _bm
                mois = (parse_qs(urlparse(self.path).query).get("mois") or [_bm.mois_courant()])[0]
                if len(mois) != 7 or mois[4] != "-" or not (mois[:4] + mois[5:]).isdigit() or not 1 <= int(mois[5:]) <= 12:
                    self._repondre(400, b'{"erreur":"mois"}', "application/json")
                    return
                if chemin == "/bilan-mensuel":
                    page = _bm.html(mois, jeton=self._jeton_recu(), actions=True)
                    self._repondre(200, page.encode("utf-8"), "text/html; charset=utf-8")
                else:
                    try:
                        message = _bm.envoyer(pont.assistant.config, mois)
                    except Exception as exc:
                        message = f"Envoi impossible : {exc}"
                    self._repondre(200, json.dumps({"message": message}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
"""
ANCRE_ROUTE = '            elif chemin in ("/tableau", "/tableau.html"):\n'
CH_WEB = [
    (ANCRE_ROUTE, ROUTE + ANCRE_ROUTE),
    ("    pont = Pont(assistant, jeton, partage)\n",
     "    pont = Pont(assistant, jeton, partage)\n"
     "    try:\n"
     "        from ..core.bilan_mensuel import demarrer as _demarrer_bilan\n"
     "        _demarrer_bilan(assistant)\n"
     "    except Exception as exc:\n"
     "        print(f\"[bilan mensuel] non demarre : {exc!r}\")\n"),
    ('<header><h1>Track record du bot</h1><p class="sub" id="sous"></p></header>',
     '<header><h1>Track record du bot</h1><p class="sub" id="sous"></p><p class="sub"><a id="lm" href="/bilan-mensuel">Bilan mensuel</a></p></header>'),
    ("charger(true);\nsetInterval",
     "charger(true);\n$('lm').href = '/bilan-mensuel?k=' + encodeURIComponent(JETON);\nsetInterval"),
]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def main():
    if not F_WEB.exists() or not F_MOD.parent.exists():
        print("gimaly\\bridges\\web.py ou gimaly\\core introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt, bom, crlf = lire(F_WEB)
    ecrire_web = MARQUE not in txt
    if ecrire_web:
        if "def lire_performance" not in txt or "charger(true);" not in txt:
            print("Applique d'abord patch_performance_gimaly puis patch_performance_live. Rien n'est modifie.")
            return 2
        manquants = [a.strip()[:90] for a, _ in CH_WEB if txt.count(a) != 1]
        if manquants:
            print("REPERE INTROUVABLE (ou en double) dans web.py : rien n'est modifie. Envoie-moi cette erreur :")
            print("\n".join(manquants))
            return 2
        for a, b in CH_WEB:
            txt = txt.replace(a, b)
        try:
            compile(txt, str(F_WEB), "exec")
        except SyntaxError as exc:
            print(f"Erreur de syntaxe apres modification de web.py : {exc}. Rien n'est ecrit.")
            return 3
    try:
        compile(MODULE, "bilan_mensuel.py", "exec")
    except SyntaxError as exc:
        print(f"Module invalide : {exc}. Rien n'est ecrit.")
        return 3
    maj_module = not F_MOD.exists() or F_MOD.read_text(encoding="utf-8") != MODULE
    if not ecrire_web and not maj_module:
        print("Deja installe (rien a faire).")
        return 0
    if maj_module:
        if F_MOD.exists():
            shutil.copy2(F_MOD, F_MOD.with_name(F_MOD.name + ".avant"))
        F_MOD.write_text(MODULE, encoding="utf-8")
        print("core\\bilan_mensuel.py : ecrit.")
    if ecrire_web:
        shutil.copy2(F_WEB, F_WEB.with_name("web.py.avant_bilan_mensuel"))
        sortie = txt.replace("\n", "\r\n") if crlf else txt
        F_WEB.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
        print("web.py : corrige (sauvegarde web.py.avant_bilan_mensuel).")
    print("Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
