# -*- coding: utf-8 -*-
r"""Patch : TRACK RECORD « Le Coin Trader VIP » dans GIMALY (comme PERFORMANCE) : page, dock, envoi Telegram mensuel et a la demande.

  * gimaly/core/track_vip.py (nouveau) : lit les signaux du canal dans trades.db (lecture seule), calcule R, % du capital, facteur de
    profit, reculs, mois par mois ; page autonome ; message Telegram. Le 1er du mois (a partir de 9 h), envoi automatique dans tes
    messages enregistres, une seule fois. A la premiere mise en route rien n'est renvoye pour le passe.
  * web.py : page /track-vip (jeton principal), bouton « Envoyer sur Telegram » (a la demande), demarrage du calendrier.
  * v2 : module « TRACK VIP » dans le dock (groupe TRADING, sans raccourci F) + apercu au survol ; hud.py : methode ouvrir_track_vip.
Facultatif : ~\GIMALY\trading\track_vip_reglages.json  ->  {"depuis": "13/04/2026", "destinataire": "@pseudo_du_trader", "auto_trader": "mensuel"}
(date de lancement ; contact Telegram qui recoit le track record via le bouton « Envoyer au trader » ; auto_trader : « mensuel »
(le 1er) ou « hebdo » (le lundi) pour qu'il le recoive tout seul).
Prerequis : patch_performance_gimaly + patch_performance_v2. Rien n'est modifie dans le bot ni dans les donnees.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_track_vip.py   puis redemarrer GIMALY (fenetre principale).
Sauvegardes : *.avant_track_vip. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd() / "gimaly"
F_WEB = RACINE / "bridges" / "web.py"
F_HUD = RACINE / "ui" / "hud.py"
F_MOD = RACINE / "core" / "track_vip.py"
F_MW = RACINE / "v2" / "ui" / "main_window.py"
F_IN = RACINE / "v2" / "app" / "integre.py"
F_PV = RACINE / "v2" / "core" / "services" / "previews.py"

MODULE = r'''# -*- coding: utf-8 -*-
r"""Track record du canal Le Coin Trader VIP depuis son lancement (LECTURE SEULE).

Lit la base locale de GIMALY (~\GIMALY\trades.db) : les signaux du canal tels que GIMALY les a lus sur Telegram (coches des TP, stop).
Aucun acces a Telegram, rien n'est modifie. Produit une page autonome (aucun script) :
    ~\GIMALY\trading\track_record_coin_trader.html
a ouvrir dans le navigateur, a imprimer ou a envoyer.

Deux mesures, expliquees dans la page :
  * R : le R du TP le plus loin atteint, comme les bilans du canal ;
  * % du capital : 1 % de risque par signal reparti entre les TP, stop remonte au point mort apres TP1 (regle du canal), plus proche
    d'un suivi reel.
Resultats THEORIQUES : hors spread, commission et glissement. Les signaux « non declenches » et « clos sans chiffre » ne sont pas comptes
(leur nombre est affiche). Les ajustements manuels (trades_manuels.json) sont exclus par defaut (--avec-manuels pour les inclure).

Usage (dossier gimaly) :
  .\.venv\Scripts\python.exe track_record_vip.py                         tout l'historique du canal « coin trader »
  .\.venv\Scripts\python.exe track_record_vip.py --depuis 13/04/2026     premiere date a retenir (lancement)
  .\.venv\Scripts\python.exe track_record_vip.py --canal "coin trader" --avec-manuels"""
import html as _h
import json
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path.home() / "GIMALY"
SORTIE = DATA / "trading" / "track_record_coin_trader.html"
IGNORES = ("en cours", "non déclenché", "clos sans chiffre")
MOIS = ["janv.", "fevr.", "mars", "avril", "mai", "juin", "juil.", "aout", "sept.", "oct.", "nov.", "dec."]


def lire(canal, depuis, avec_manuels):
    base = sqlite3.connect(f"file:{DATA / 'trades.db'}?mode=ro", uri=True)
    base.row_factory = sqlite3.Row
    req = """SELECT t.date, t.sens, t.symbole,
                    COALESCE(c.statut, t.statut) AS statut, COALESCE(c.r, t.r) AS r,
                    COALESCE(c.pips, t.pips) AS pips, COALESCE(c.pourcentage, t.pourcentage) AS pct,
                    COALESCE(c.annule, t.annule) AS annule
             FROM trades t LEFT JOIN corrections c ON c.canal = t.canal AND c.message_id = t.message_id
             WHERE t.canal = ? ORDER BY t.date"""
    lignes = [dict(l) for l in base.execute(req, (canal,))]
    base.close()
    clos, ignores = [], {"non déclenché": 0, "clos sans chiffre": 0, "en cours": 0}
    for l in lignes:
        if l["annule"]:
            continue
        try:
            t = datetime.fromisoformat(l["date"]).astimezone().replace(tzinfo=None)
        except ValueError:
            continue
        if depuis and t < depuis:
            continue
        if l["statut"] in IGNORES:
            ignores[l["statut"]] += 1
            continue
        if l["r"] is None:
            continue
        clos.append({"t": t, "jour": t.date(), "sens": (l["sens"] or "?").upper(), "symbole": l["symbole"] or "?",
                     "statut": l["statut"], "r": float(l["r"]), "pct": float(l["pct"] or 0.0), "pips": float(l["pips"] or 0.0)})
    # % illisibles : un % tres superieur a ce que le R permet (1 % de risque) est une erreur de lecture du message.
    rap = sorted(t["pct"] / t["r"] for t in clos if abs(t["r"]) > 0.3 and t["pct"] / t["r"] > 0)
    med = rap[len(rap) // 2] if rap else 0.5
    for t in clos:
        t["suspect"] = abs(t["pct"]) > 2.0 and abs(t["pct"]) > 3 * med * abs(t["r"])
        if t["suspect"]:
            t["pct_lu"], t["pct"] = t["pct"], 0.0
    manuels = []
    try:
        for m in json.loads((DATA / "trades_manuels.json").read_text(encoding="utf-8")):
            if (m.get("canal") or "").lower() == canal:
                manuels.append(m)
    except (OSError, ValueError):
        pass
    return clos, ignores, manuels


def groupe(trades):
    r = [t["r"] for t in trades]
    gains = sum(x for x in r if x > 0.05)
    pertes = -sum(x for x in r if x < -0.05)
    gagn = [x for x in r if x > 0.05]
    perd = [x for x in r if x < -0.05]
    return {"n": len(r), "gagn": len(gagn), "perd": len(perd), "nul": len(r) - len(gagn) - len(perd),
            "reussite": 100 * len(gagn) / len(r) if r else 0.0, "r": sum(r), "pct": sum(t["pct"] for t in trades),
            "pf": gains / pertes if pertes else None,
            "rr": (statistics.fmean(gagn) / abs(statistics.fmean(perd))) if gagn and perd else None}


def recul(valeurs):
    cum = som = pire = 0.0
    serie = []
    for v in valeurs:
        cum += v
        som = max(som, cum)
        pire = max(pire, som - cum)
        serie.append((cum, som - cum))
    return pire, serie


def fr(x, d=1, signe=True):
    s = f"{abs(x):.{d}f}".replace(".", ",")
    return (("+" if x >= 0 else "-") if signe else ("-" if x < 0 else "")) + s


def nfr(x, d=2):
    return "–" if x is None else f"{x:.{d}f}".replace(".", ",")


def svg_temps(points, titre, largeur=860, hauteur=260, aire=True, couleur_classe="courbe", suffixe=""):
    """points : [(datetime, valeur)]. Axe X = temps reel, graduations par mois."""
    if len(points) < 2:
        return ""
    xs = [p[0].timestamp() for p in points]
    vs = [p[1] for p in points]
    lo, hi = min(min(vs), 0.0), max(max(vs), 0.0)
    if hi - lo < 1e-9:
        hi += 1
    g, d, h, b = 54, 14, 14, 26
    w, ht = largeur - g - d, hauteur - h - b
    x0, x1 = xs[0], xs[-1]
    X = lambda t: g + w * (t - x0) / ((x1 - x0) or 1)
    Y = lambda v: h + ht * (hi - v) / (hi - lo)
    ligne = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in zip(xs, vs))
    poly = f"{X(xs[0]):.1f},{Y(0):.1f} " + ligne + f" {X(xs[-1]):.1f},{Y(0):.1f}"
    pas = max(1, round((hi - lo) / 4))
    graduations = []
    v = (int(lo // pas)) * pas
    while v <= hi + 1e-9:
        if lo - 1e-9 <= v:
            graduations.append(f"<line x1='{g}' x2='{g + w}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' class='gr'/>"
                               f"<text x='{g - 6}' y='{Y(v) + 4:.1f}' text-anchor='end'>{v:+.0f}{suffixe}</text>")
        v += pas
    mois = []
    t = points[0][0].replace(day=1) + timedelta(days=32)
    t = t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while t.timestamp() < x1:
        mois.append(f"<line x1='{X(t.timestamp()):.1f}' x2='{X(t.timestamp()):.1f}' y1='{h}' y2='{h + ht}' class='mois'/>"
                    f"<text x='{X(t.timestamp()):.1f}' y='{hauteur - 8}' text-anchor='middle'>{MOIS[t.month - 1]}</text>")
        t = (t + timedelta(days=32)).replace(day=1)
    return (f"<svg viewBox='0 0 {largeur} {hauteur}' role='img' aria-label='{_h.escape(titre)}'>{''.join(graduations)}{''.join(mois)}"
            f"<line x1='{g}' x2='{g + w}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' class='zero'/>"
            + (f"<polygon points='{poly}' class='aire'/>" if aire else "")
            + f"<polyline points='{ligne}' class='{couleur_classe}' fill='none'/></svg>")


def svg_mois(mois_stats, cle, largeur=860, hauteur=220, suffixe=""):
    if not mois_stats:
        return ""
    vals = [m[cle] for _, m in mois_stats]
    mx = max(max(abs(v) for v in vals), 1.0)
    g, d, h, b = 54, 14, 16, 26
    w, ht = largeur - g - d, hauteur - h - b
    z = h + ht / 2
    pas = w / len(mois_stats)
    lp = min(56.0, pas * 0.6)
    out = [f"<line x1='{g}' x2='{g + w}' y1='{z:.1f}' y2='{z:.1f}' class='zero'/>",
           f"<text x='{g - 6}' y='{h + 8}' text-anchor='end'>{mx:+.0f}{suffixe}</text><text x='{g - 6}' y='{h + ht}' text-anchor='end'>{-mx:+.0f}{suffixe}</text>"]
    for i, (lib, m) in enumerate(mois_stats):
        v = m[cle]
        x = g + pas * i + (pas - lp) / 2
        hh = abs(v) / mx * ht / 2
        y = z - hh if v >= 0 else z
        out.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{lp:.1f}' height='{max(hh, .8):.1f}' class='{'pos' if v >= 0 else 'neg'}'>"
                   f"<title>{lib} : {v:+.1f}{suffixe}</title></rect>"
                   f"<text x='{x + lp / 2:.1f}' y='{(y - 4) if v >= 0 else (y + hh + 11):.1f}' text-anchor='middle' class='val'>{v:+.0f}</text>"
                   f"<text x='{x + lp / 2:.1f}' y='{hauteur - 8}' text-anchor='middle'>{lib}</text>")
    return f"<svg viewBox='0 0 {largeur} {hauteur}'>{''.join(out)}</svg>"


def tableau(titre, lignes):
    if not lignes:
        return ""
    corps = "".join(
        f"<tr><td>{_h.escape(str(nom))}</td><td class='n'>{m['n']}</td><td class='n'>{m['reussite']:.0f} %</td>"
        f"<td class='n {'pos' if m['r'] >= 0 else 'neg'}'>{fr(m['r'])}</td><td class='n {'pos' if m['pct'] >= 0 else 'neg'}'>{fr(m['pct'])} %</td>"
        f"<td class='n'>{nfr(m['pf'])}</td><td class='n'>{nfr(m['rr'])}</td></tr>" for nom, m in lignes)
    return (f"<section><h2>{titre}</h2><div class='tw'><table><thead><tr><th></th><th class='n'>signaux</th><th class='n'>reussite</th>"
            f"<th class='n'>R</th><th class='n'>% capital</th><th class='n'>fact. profit</th><th class='n'>RR</th></tr></thead>"
            f"<tbody>{corps}</tbody></table></div></section>")


def construire(canal, clos, ignores, manuels, avec_manuels, depuis_lib):
    g = groupe(clos)
    pire_r, serie_r = recul([t["r"] for t in clos])
    pire_p, serie_p = recul([t["pct"] for t in clos])
    mois = {}
    for t in clos:
        mois.setdefault(t["jour"].strftime("%Y-%m"), []).append(t)
    mois_stats = [(f"{MOIS[int(k[5:]) - 1]} {k[2:4]}", groupe(v)) for k, v in sorted(mois.items())]
    mois_pos = sum(1 for _, m in mois_stats if m["r"] > 0)
    sens = [(k, groupe([t for t in clos if t["sens"] == k])) for k in sorted({t["sens"] for t in clos})]
    symb = [(k, groupe([t for t in clos if t["symbole"] == k])) for k in sorted({t["symbole"] for t in clos})]
    c = ser = 0
    for t in clos:
        c = c + 1 if t["statut"] == "perdu" else 0
        ser = max(ser, c)
    jours = {}
    for t in clos:
        jours.setdefault(t["jour"], 0.0)
        jours[t["jour"]] += t["r"]
    jours_pos = sum(1 for v in jours.values() if v > 0)
    cum_r, cum_p, cum = 0.0, 0.0, []
    for t in clos:
        cum_r += t["r"]
        cum_p += t["pct"]
        cum.append((t["t"], cum_r, cum_p))
    susp = [t for t in clos if t.get("suspect")]
    susp_txt = (f"{len(susp)} signal(aux) au % illisible dans le canal (ex. {susp[0]['pct_lu']:+.0f} % pour {susp[0]['r']:+.1f} R) "
                f"comptes a 0 % dans la mesure en % capital (R {fr(sum(t['r'] for t in susp))} conserve dans la mesure en R) : mesure en % prudente. ") if susp else ""
    manuel_txt = ""
    if manuels:
        tot = sum(float(m.get("r") or 0) for m in manuels)
        manuel_txt = (f"{len(manuels)} ajustement(s) manuel(s) de {fr(tot)} R au total "
                      + ("INCLUS" if avec_manuels else "non inclus dans les chiffres ci-dessus") + ".")
    def carte(titre, valeur, sous="", cls=""):
        return f"<div class='carte'><span>{titre}</span><b class='{cls}'>{valeur}</b><small>{sous}</small></div>"
    cartes = "".join([
        carte("R cumule", fr(g["r"]), f"sur {g['n']} signaux clos · R moyen {fr(g['r'] / g['n'], 2)}", "pos" if g["r"] >= 0 else "neg"),
        carte("% du capital", fr(g["pct"]) + " %", "1 % de risque par signal, reparti entre les TP", "pos" if g["pct"] >= 0 else "neg"),
        carte("Reussite", f"{g['reussite']:.0f} %", f"{g['gagn']} gagnants · {g['perd']} perdants · {g['nul']} a plat"),
        carte("Facteur de profit", nfr(g["pf"]), "gains / pertes en R", "" if g["pf"] is None else ("pos" if g["pf"] >= 1 else "neg")),
        carte("RR moyen", nfr(g["rr"]), "gain moyen / perte moyenne"),
        carte("Pire recul", fr(-pire_r) + " R", f"soit {fr(-pire_p)} % du capital · depuis un sommet", "neg"),
        carte("Mois positifs", f"{mois_pos} / {len(mois_stats)}", "en R"),
        carte("Plus longue serie de stops", str(ser), "signaux perdants de suite")])
    pf_txt = (f"PF {nfr(g['pf'])} · RR {nfr(g['rr'])}")
    debut, fin = clos[0]["t"], clos[-1]["t"]
    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track record {_h.escape(canal)}</title>
<style>
:root{{--bg:#f4f6f9;--panel:#fff;--fg:#14181f;--mute:#5b6573;--line:#dfe3ea;--pos:#0b6e4f;--neg:#b3261e;--acc:#2f5bd8;--acc2:#b3590f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#070b10;--panel:#0d141c;--fg:#d6e4f0;--mute:#8aa0b3;--line:#1b2f40;--pos:#4ade80;--neg:#ff6b6b;--acc:#35d6ff;--acc2:#ffb547}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif;padding:20px 16px 48px}}
main{{max-width:960px;margin:0 auto;display:flex;flex-direction:column;gap:18px}}
h1{{font-size:24px;margin:0}}h2{{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}}
.sub{{color:var(--mute);margin:4px 0 0}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}}
section.cartes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;background:none;border:none;padding:0}}
.carte{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}.carte span{{display:block;font-size:12px;color:var(--mute)}}
.carte b{{display:block;font-size:22px;font-variant-numeric:tabular-nums}}.carte small{{color:var(--mute);font-size:11px}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}svg{{width:100%;height:auto;display:block}}svg text{{fill:var(--mute);font-size:11px}}svg text.val{{fill:var(--fg);font-size:10px}}
.gr{{stroke:var(--line)}}.mois{{stroke:var(--line);stroke-dasharray:2 4}}.zero{{stroke:var(--mute);stroke-dasharray:3 3}}.aire{{fill:var(--acc);opacity:.12}}
.courbe{{stroke:var(--acc);stroke-width:2}}.courbe2{{stroke:var(--acc2);stroke-width:2}}.recul{{stroke:var(--neg);stroke-width:1.6}}
rect.pos{{fill:var(--pos)}}rect.neg{{fill:var(--neg)}}
.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th{{text-align:left;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mute);padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}.n{{text-align:right}}.note{{color:var(--mute);font-size:12px}}
.avert{{border-left:3px solid var(--acc2)}}
@media print{{body{{background:#fff}}}}
</style></head><body><main>
<header><h1>Le Coin Trader VIP · track record</h1>
<p class="sub">Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} · {g['n']} signaux clos · {pf_txt} · genere le {datetime.now():%d/%m/%Y %H:%M}</p></header>
<section class="cartes">{cartes}</section>
<section><h2>Courbe en R cumule</h2>{svg_temps([(t, r) for t, r, _ in cum], "R cumule", suffixe="")}</section>
<section><h2>Courbe en % du capital (1 % de risque par signal)</h2>{svg_temps([(t, p) for t, _, p in cum], "% cumule", couleur_classe="courbe2", aire=False, suffixe=" %")}</section>
<section><h2>Recul depuis le sommet (R)</h2>{svg_temps([(t, v[1]) for t, v in zip([t for t, _, _ in cum], serie_r)], "Recul", couleur_classe="recul", aire=False)}</section>
<section><h2>R par mois</h2>{svg_mois(mois_stats, "r")}</section>
{tableau("Mois par mois", mois_stats)}{tableau("Par sens", sens)}{tableau("Par instrument", symb) if len(symb) > 1 else ""}
<section class="avert"><h2>Comment lire ces chiffres</h2>
<p class="note"><b>Source :</b> les signaux publies dans le canal, lus par GIMALY ; le resultat vient des coches de TP et du stop annonces dans les messages. Ce ne sont pas les releves d'un compte.</p>
<p class="note"><b>R :</b> le gain du TP le plus loin atteint, en multiples du risque (convention des bilans du canal). <b>% du capital :</b> 1 % de risque par signal reparti entre les TP, stop au point mort apres TP1 : plus proche de ce que vit quelqu'un qui suit les signaux.</p>
<p class="note"><b>Theorique :</b> hors spread, commission et glissement, avec une execution supposee parfaite aux prix publies. Les resultats reels d'un suiveur peuvent etre plus faibles.</p>
<p class="note"><b>Non comptes :</b> {ignores['non déclenché']} ordres jamais declenches, {ignores['clos sans chiffre']} signaux clos sans chiffre, {ignores['en cours']} en cours. {_h.escape(susp_txt + manuel_txt)}</p>
<p class="note">Les performances passees ne garantissent pas les performances futures. Le trading comporte un risque de perte en capital. Ce document n'est pas un conseil en investissement.</p></section>
</main></body></html>"""
    return page, g, pire_r, pire_p, mois_stats


def main(argv):
    argv = list(argv)
    canal, depuis, avec_manuels = "coin trader", None, False
    if "--canal" in argv:
        i = argv.index("--canal")
        canal = argv[i + 1].strip().lower()
        del argv[i:i + 2]
    if "--depuis" in argv:
        i = argv.index("--depuis")
        try:
            depuis = datetime.strptime(argv[i + 1], "%d/%m/%Y")
        except (ValueError, IndexError):
            print("Date attendue : jj/mm/aaaa")
            return 1
        del argv[i:i + 2]
    if "--avec-manuels" in argv:
        avec_manuels = True
    clos, ignores, manuels = lire(canal, depuis, avec_manuels)
    if not clos:
        print("Aucun signal clos pour ce canal.")
        return 0
    if avec_manuels and manuels:
        for m in manuels:
            try:
                t = datetime.fromisoformat(m["date"])
            except (KeyError, ValueError):
                continue
            clos.append({"t": t, "jour": t.date(), "sens": "MANUEL", "symbole": "manuel", "statut": "gagne" if float(m.get("r") or 0) > 0 else "perdu",
                         "r": float(m.get("r") or 0), "pct": float(m.get("r") or 0), "pips": float(m.get("pips") or 0)})
        clos.sort(key=lambda x: x["t"])
    page, g, pire_r, pire_p, mois_stats = construire(canal, clos, ignores, manuels, avec_manuels, depuis)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(page, encoding="utf-8")
    print(f"{g['n']} signaux clos du {clos[0]['t']:%d/%m/%Y} au {clos[-1]['t']:%d/%m/%Y} | "
          f"R {fr(g['r'])} | % capital {fr(g['pct'])} | reussite {g['reussite']:.0f} % | facteur de profit {nfr(g['pf'])} | RR {nfr(g['rr'])}")
    ns = sum(1 for t in clos if t.get("suspect"))
    if ns:
        print(f"{ns} signaux au % illisible mis a 0 % (R conserve)")
    print(f"pire recul : {fr(-pire_r)} R / {fr(-pire_p)} % | non comptes : {ignores['non déclenché']} non declenches, "
          f"{ignores['clos sans chiffre']} clos sans chiffre, {ignores['en cours']} en cours")
    for lib, m in mois_stats:
        print(f"  {lib:<9}{m['n']:>4} signaux  {m['reussite']:>3.0f} %  R {fr(m['r']):>8}  {fr(m['pct']):>7} %")
    print(f"\nPage : {SORTIE}")
    return 0




# ======================================================================= integration GIMALY (page, Telegram, calendrier)
import threading
import time

ETAT = DATA / "trading" / "track_vip_envoye.json"
REGLAGES = DATA / "trading" / "track_vip_reglages.json"
CANAL = "coin trader"
_verrou = threading.Lock()


def _depuis():
    """Date de depart facultative (fichier track_vip_reglages.json, cle depuis, format jj/mm/aaaa)."""
    try:
        return datetime.strptime(json.loads(REGLAGES.read_text(encoding="utf-8")).get("depuis", ""), "%d/%m/%Y")
    except (OSError, ValueError, AttributeError):
        return None


def _reglage(cle):
    try:
        return (json.loads(REGLAGES.read_text(encoding="utf-8")).get(cle) or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def _calcul():
    clos, ignores, manuels = lire(CANAL, _depuis(), False)
    if not clos:
        return None
    return construire(CANAL, clos, ignores, manuels, False, None), clos, ignores


BARRE = """<div id="act" style="max-width:960px;margin:0 auto 10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
<button id="env" style="font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--fg);cursor:pointer">Envoyer sur Telegram</button>
__TRADER__<span id="msg" class="note"></span></div>
<script>document.getElementById('env').onclick=function(){var m=document.getElementById('msg');m.textContent='Envoi...';
envoi('')};
function envoi(a){var m=document.getElementById('msg');m.textContent='Envoi...';
fetch('/api/track-vip/envoyer?k=__JETON__&a='+a).then(function(r){return r.json()}).then(function(j){m.textContent=j.message}).catch(function(){m.textContent='Envoi impossible'})};</script>"""


def html(jeton="", actions=False):
    res = _calcul()
    if res is None:
        return "<!DOCTYPE html><meta charset='utf-8'><p>Aucun signal clos pour le canal.</p>"
    (page, *_), _, _ = res
    if actions:
        bouton = ""
        if _reglage("destinataire"):
            bouton = ('<button id="trd" onclick="envoi(\'trader\')" style="font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);'
                      'background:var(--panel);color:var(--fg);cursor:pointer">Envoyer au trader</button>')
        page = page.replace("<main>", BARRE.replace("__TRADER__", bouton).replace("__JETON__", _h.escape(jeton, quote=True)) + "<main>", 1)
    return page


def texte():
    res = _calcul()
    if res is None:
        return None
    (page, g, pire_r, pire_p, mois_stats), clos, ignores = res
    dernier = mois_stats[-1][1] if mois_stats else None
    lignes = [f"Track record Le Coin Trader VIP au {clos[-1]['t']:%d/%m/%Y}",
              f"Depuis le {clos[0]['t']:%d/%m/%Y} : {g['n']} signaux clos",
              f"R cumule {fr(g['r'])} | % capital {fr(g['pct'])} % | reussite {g['reussite']:.0f} %",
              f"Facteur de profit {nfr(g['pf'])} | RR {nfr(g['rr'])} | pire recul {fr(-pire_r)} R"]
    if dernier:
        lignes.append(f"Dernier mois ({mois_stats[-1][0]}) : {dernier['n']} signaux, R {fr(dernier['r'])}, {fr(dernier['pct'])} %")
    lignes.append("Resultats theoriques tires des messages du canal (hors spread et commission).")
    return "\n".join(lignes)


def fichier_rapport():
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(html(), encoding="utf-8")
    return SORTIE


def _envoyer_telegram(config, message, chemin, cible="me"):
    from ..bridges import telegram_lecture as tl

    @tl.exclusif
    def tache(cfg):
        client = tl._client(cfg)
        client.send_message(cible, message)
        client.send_file(cible, str(chemin), caption="Track record detaille (a ouvrir dans le navigateur)")

    tache(config)


def envoyer(config, destinataire=False):
    """destinataire=True : envoie au contact du reglage « destinataire » (ex. @pseudo ou numero) ; sinon a toi (messages enregistres)."""
    with _verrou:
        message = texte()
        if message is None:
            return "Aucun signal clos : rien envoye."
        cible = "me"
        if destinataire:
            cible = _reglage("destinataire")
            if not cible:
                return "Aucun destinataire : ajoute-le dans track_vip_reglages.json (cle destinataire)."
            if cible.lstrip("-").isdigit():
                cible = int(cible)
        _envoyer_telegram(config, message, fichier_rapport(), cible)
        return ("Track record envoye a ton trader." if destinataire else "Track record envoye sur ton Telegram (messages enregistres).")


def _etat():
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire_etat(d):
    try:
        ETAT.write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def verifier(config):
    """A toi : le 1er du mois (9 h). Au trader (si « destinataire » et « auto_trader » : mensuel ou hebdo sont regles) :
    le 1er du mois, ou le lundi, a partir de 9 h. Une seule fois par periode ; premiere mise en route : rien d'envoye pour le passe."""
    maintenant = datetime.now()
    mois = maintenant.strftime("%Y-%m")
    semaine = maintenant.strftime("%G-%V")
    etat = _etat()
    if "dernier" not in etat:
        _ecrire_etat({"dernier": mois})
        return None
    message = None
    if maintenant.hour < 9:
        return None
    if etat["dernier"] != mois and maintenant.day == 1:
        message = envoyer(config)
        etat["dernier"] = mois
        _ecrire_etat(etat)
    frequence = _reglage("auto_trader").lower()
    if _reglage("destinataire") and frequence in ("mensuel", "hebdo"):
        periode, jour_ok = (mois, maintenant.day == 1) if frequence == "mensuel" else (semaine, maintenant.weekday() == 0)
        champ = "trader_" + frequence
        if etat.get(champ) != periode and jour_ok:
            message = envoyer(config, True)
            etat[champ] = periode
            _ecrire_etat(etat)
    return message


def demarrer(assistant):
    if getattr(demarrer, "_lance", False):
        return
    demarrer._lance = True

    def boucle():
        time.sleep(120)
        while True:
            try:
                verifier(assistant.config)
            except Exception as exc:  # noqa: BLE001 - ne jamais gener GIMALY
                print(f"[track vip] {exc!r}")
            time.sleep(900)

    threading.Thread(target=boucle, name="track-vip", daemon=True).start()


def apercu():
    """Pour l'apercu du dock : (titre ligne 1, ligne 2, ligne 3, alerte)."""
    res = _calcul()
    if res is None:
        return None
    (page, g, pire_r, pire_p, mois_stats), clos, ignores = res
    dern = mois_stats[-1]
    return (f"{fr(g['r'])} R depuis le {clos[0]['t']:%d/%m/%Y} · {g['n']} signaux", f"Reussite {g['reussite']:.0f} % · PF {nfr(g['pf'])}",
            f"{dern[0]} : {fr(dern[1]['r'])} R", g["r"] < 0)
'''

ROUTE = """            elif chemin in ("/track-vip", "/api/track-vip/envoyer"):
                if not self._autorise():          # jeton principal uniquement
                    self._repondre(403, b'{"erreur":"jeton"}', "application/json")
                    return
                from ..core import track_vip as _tv
                if chemin == "/track-vip":
                    page = _tv.html(jeton=self._jeton_recu(), actions=True)
                    self._repondre(200, page.encode("utf-8"), "text/html; charset=utf-8")
                else:
                    try:
                        message = _tv.envoyer(pont.assistant.config, (parse_qs(urlparse(self.path).query).get("a") or [""])[0] == "trader")
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
     "        from ..core.track_vip import demarrer as _demarrer_vip\n"
     "        _demarrer_vip(assistant)\n"
     "    except Exception as exc:\n"
     "        print(f\"[track vip] non demarre : {exc!r}\")\n"),
]
CH_HUD = [(
    "    def ouvrir_performance(self) -> None:\n",
    '''    def ouvrir_track_vip(self) -> None:
        """Ouvre la page du track record du canal Le Coin Trader VIP."""
        if self.ouvrir_page("/track-vip"):
            return
        self._signaler("Pour le track record, mets web_mobile: true dans config.local.yaml.")

    def ouvrir_performance(self) -> None:
''')]
CH_MW = [(
    '    ModuleDescriptor("performance", "PERFORMANCE", "TRADING"),\n',
    '    ModuleDescriptor("performance", "PERFORMANCE", "TRADING"),\n'
    '    ModuleDescriptor("track_vip", "TRACK VIP", "TRADING"),\n')]
CH_IN = [(
    '                table["performance"] = signaux.ouvrir_performance\n',
    '                table["performance"] = signaux.ouvrir_performance\n'
    '            if hasattr(signaux, "ouvrir_track_vip"):\n'
    '                table["track_vip"] = signaux.ouvrir_track_vip\n')]
METHODE = '''    def _track_vip(self) -> PreviewData:
        """Track record du canal Le Coin Trader VIP (signaux lus dans trades.db)."""
        try:
            from ....core import track_vip as tv
            a = tv.apercu()
        except Exception:  # noqa: BLE001
            return PreviewData("TRACK VIP", ("Indisponible",))
        if a is None:
            return PreviewData("TRACK VIP", ("Aucun signal clos",))
        return PreviewData("TRACK VIP", (a[0], a[1], a[2]), ("Page complete : clic sur TRACK VIP",), alerte=a[3])

'''
CH_PV = [
    ('"performance": self._performance,\n        }',
     '"performance": self._performance,\n            "track_vip": self._track_vip,\n        }'),
    ("    def _performance(self) -> PreviewData:\n", METHODE + "    def _performance(self) -> PreviewData:\n"),
]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def main():
    jeu = ((F_WEB, '"/track-vip"', CH_WEB), (F_HUD, "def ouvrir_track_vip", CH_HUD), (F_MW, 'ModuleDescriptor("track_vip"', CH_MW),
           (F_IN, 'table["track_vip"]', CH_IN), (F_PV, "def _track_vip", CH_PV))
    for f, _, _ in jeu:
        if not f.exists():
            print(f"{f} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    if not F_MOD.parent.exists():
        print("gimaly\\core introuvable.")
        return 1
    try:
        compile(MODULE, "track_vip.py", "exec")
    except SyntaxError as exc:
        print(f"Module invalide : {exc}. Rien n'est ecrit.")
        return 3
    ecritures = []
    for f, marque, changements in jeu:
        txt, bom, crlf = lire(f)
        if marque in txt:
            continue
        if f in (F_MW, F_IN, F_PV) and "performance" not in txt:
            print("Applique d'abord patch_performance_gimaly puis patch_performance_v2. Rien n'est modifie.")
            return 2
        manquants = [a.strip()[:90] for a, _ in changements if txt.count(a) != 1]
        if manquants:
            print(f"REPERE INTROUVABLE (ou en double) dans {f.name} : rien n'est modifie. Envoie-moi cette erreur :")
            print("\n".join(manquants))
            return 2
        for ancien, nouveau in changements:
            txt = txt.replace(ancien, nouveau)
        try:
            compile(txt, str(f), "exec")
        except SyntaxError as exc:
            print(f"Erreur de syntaxe apres modification de {f.name} : {exc}. Rien n'est ecrit.")
            return 3
        ecritures.append((f, txt, bom, crlf))
    maj_module = not F_MOD.exists() or F_MOD.read_text(encoding="utf-8") != MODULE
    if not ecritures and not maj_module:
        print("Deja installe (rien a faire).")
        return 0
    if maj_module:
        if F_MOD.exists():
            shutil.copy2(F_MOD, F_MOD.with_name(F_MOD.name + ".avant_track_vip"))
        F_MOD.write_text(MODULE, encoding="utf-8")
        print("core\\track_vip.py : ecrit.")
    for f, txt, bom, crlf in ecritures:
        shutil.copy2(f, f.with_name(f.name + ".avant_track_vip"))
        sortie = txt.replace("\n", "\r\n") if crlf else txt
        f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
        print(f"{f.name} : corrige (sauvegarde {f.name}.avant_track_vip).")
    print("Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
