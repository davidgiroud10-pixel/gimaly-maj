# -*- coding: utf-8 -*-
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
<p class="note" style="text-align:center">Resultats theoriques tires des messages du canal, hors spread et commission. Le trading comporte un risque de perte en capital.</p>
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
