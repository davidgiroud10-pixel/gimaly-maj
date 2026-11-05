# -*- coding: utf-8 -*-
r"""TRACK RECORD du bot depuis sa creation : une page web (fichier unique, hors ligne) avec courbes et chiffres. Lecture seule : rien n'est modifie.
Source : trades_bot.csv (trades REELS termines). Contenu : courbe cumulee en R et en argent avec les grandes decisions marquees, drawdown,
resultat par jour, moyenne glissante, courbe par moteur, chiffres cles (gagnants, R moyen, facteur de profit, serie de stops, meilleurs et pires jours),
tableaux par mois, moteur, sens et heure. Les intervalles et verdicts sont ceux du bilan_semaine : peu de trades = aucune conclusion.

Usage (dossier du programme) :
  .\.venv\Scripts\python.exe track_record.py                  cree track_record.html a cote du fichier de trades et l'ouvre
  .\.venv\Scripts\python.exe track_record.py 20/10/2026       depuis cette date seulement
  .\.venv\Scripts\python.exe track_record.py --sans-ouvrir    ne l'ouvre pas
Les decisions marquees sur la courbe sont dans EVENEMENTS (en haut du script) : corrige les dates si besoin."""
import csv
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

DOSSIER = Path.home() / "GIMALY" / "trading"
FICHIER = DOSSIER / "trades_bot.csv"
SORTIE = DOSSIER / "track_record.html"

# Grandes decisions (date AAAA-MM-JJ, texte). Reprises de nos echanges ; a verifier et a completer.
EVENEMENTS = [
    ("2026-09-30", "Mode strict (configuration definitive)"),
    ("2026-10-01", "Lancement dans la WinLeague"),
    ("2026-10-06", "Scalping en test (fantomes)"),
    ("2026-10-15", "Scalp VI M5 en reel ; sortie au temps (4 h) coupee"),
    ("2026-10-20", "Scalp Keltner large en reel"),
    ("2026-10-21", "Seul scalp_keltner_large en reel ; plusieurs trades ouverts"),
    ("2026-10-28", "Plafond de perte du jour a 3 %"),
    ("2026-11-04", "Moteurs de tendance en reel (tendance_m5, pullback)"),
]


def nombre(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def lire(chemin, depuis):
    out = []
    with open(chemin, newline="", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            if (l.get("resultat") or "").strip() in ("", "ouvert"):
                continue
            try:
                jour = datetime.strptime((l.get("date") or "").strip(), "%d/%m/%Y")
            except ValueError:
                continue
            if depuis and jour < depuis:
                continue
            r = nombre(l.get("R"))
            if r is None:
                continue
            h = (l.get("heure") or "").strip()
            try:
                hh, mm = int(h[:2]), int(h[3:5])
            except ValueError:
                hh, mm = 12, 0
            t = jour.replace(hour=hh, minute=mm)
            out.append([int(t.timestamp() * 1000), jour.strftime("%Y-%m-%d"), (l.get("genre") or "?").strip() or "?",
                        (l.get("sens") or "?").strip().lower(), round(r, 3), round(nombre(l.get("gain_devise")) or 0.0, 2),
                        (l.get("resultat") or "").strip()])
    out.sort(key=lambda x: x[0])
    return out


MODELE = r'''<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track record du bot</title>
<style>
:root{--bg:#f4f6f9;--panel:#fff;--fg:#14181f;--mute:#5b6573;--line:#dfe3ea;--accent:#0b6e4f;--bad:#b3261e;--c1:#0b6e4f;--c2:#2f5bd8;--c3:#b3590f;--c4:#7a3fb0;--c5:#a02060;--grid:#e6e9ef}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#070b10;--panel:#0d141c;--fg:#d6e4f0;--mute:#8aa0b3;--line:#1b2f40;--accent:#35d6ff;--bad:#ff6b6b;--c1:#35d6ff;--c2:#6ee7a8;--c3:#ffb547;--c4:#c39bff;--c5:#ff8fb8;--grid:#14212d;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#070b10;--panel:#0d141c;--fg:#d6e4f0;--mute:#8aa0b3;--line:#1b2f40;--accent:#35d6ff;--bad:#ff6b6b;--c1:#35d6ff;--c2:#6ee7a8;--c3:#ffb547;--c4:#c39bff;--c5:#ff8fb8;--grid:#14212d;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif;padding:20px max(16px,env(safe-area-inset-right,0px)) 48px max(16px,env(safe-area-inset-left,0px))}
main{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
h1{font-size:22px;margin:0}h2{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}
.sub{color:var(--mute);margin:4px 0 0}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.carte,.bloc{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}
.carte span{display:block;font-size:12px;color:var(--mute)}.carte b{display:block;font-size:20px;font-variant-numeric:tabular-nums;margin-top:2px}
.carte small{color:var(--mute);font-size:11px}
.pos{color:var(--accent)}.neg{color:var(--bad)}
svg{width:100%;height:auto;display:block;overflow:visible}
.axe text{fill:var(--mute);font-size:11px}.grille line{stroke:var(--grid)}
.bascule{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
button{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px;padding:5px 10px;cursor:pointer}
button.on{border-color:var(--accent);color:var(--accent)}
.legende{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--mute);margin-top:6px}.legende i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px #0003;display:none;z-index:5;max-width:260px}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mute);padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}td.n,th.n{text-align:right}
.deux{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(420px,100%),1fr));gap:18px}.deux>*{min-width:0}
.note{color:var(--mute);font-size:12px}
.evts li{margin:2px 0}.evts{margin:6px 0 0;padding-left:18px;color:var(--mute);font-size:12px}
</style></head><body><main>
<header><h1>Track record du bot</h1><p class="sub" id="sous"></p></header>
<section class="cartes" id="cartes"></section>
<section class="bloc"><h2>Courbe de performance</h2>
<div class="bascule"><button id="b-r" class="on">en R</button><button id="b-e">en argent</button></div>
<svg id="g-courbe" viewBox="0 0 1100 340" role="img" aria-label="Courbe cumulee"></svg>
<ol class="evts" id="evts"></ol></section>
<div class="deux">
<section class="bloc"><h2>Drawdown (recul depuis le sommet, en R)</h2><svg id="g-dd" viewBox="0 0 540 220"></svg></section>
<section class="bloc"><h2>R moyen sur les 30 derniers trades</h2><svg id="g-glis" viewBox="0 0 540 220"></svg></section>
</div>
<section class="bloc"><h2>Resultat par jour (R)</h2><svg id="g-jour" viewBox="0 0 1100 240"></svg></section>
<section class="bloc"><h2>Courbe par moteur (R cumule)</h2><svg id="g-moteurs" viewBox="0 0 1100 300"></svg><div class="legende" id="leg-m"></div></section>
<div class="deux">
<section class="bloc tablewrap"><h2>Par mois</h2><table id="t-mois"></table></section>
<section class="bloc tablewrap"><h2>Par moteur</h2><table id="t-moteur"></table></section>
<section class="bloc tablewrap"><h2>Par sens</h2><table id="t-sens"></table></section>
<section class="bloc tablewrap"><h2>Par heure (colonne « heure » du fichier)</h2><table id="t-heure"></table></section>
</div>
<p class="note">Lecture : la part de gagnants et le R moyen n'ont de sens qu'avec assez de trades (au moins une trentaine par groupe). « Argent » suit les lots reels du compte (plafond de lot) et peut s'ecarter du R. Rien n'est modifie par cette page.</p>
<div class="tip" id="tip"></div>
</main>
<script>
const T = __DONNEES__, EVT = __EVENEMENTS__, MAJ = "__MAJ__";
const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const fmt = (x, d = 2) => (x >= 0 ? '+' : '') + x.toFixed(d).replace('.', ',');
const eur = (x) => (x >= 0 ? '+' : '') + Math.round(x).toLocaleString('fr-FR') + ' €';
const cls = (x) => x > 0 ? 'pos' : (x < 0 ? 'neg' : '');
const COUL = ['--c1', '--c2', '--c3', '--c4', '--c5'];
const couleur = (i) => getComputedStyle(document.documentElement).getPropertyValue(COUL[i % 5]).trim() || '#35d6ff';
const jolie = (iso) => iso.split('-').reverse().join('/');

if (!T.length) { document.body.innerHTML = '<main><h1>Aucun trade termine dans le fichier.</h1></main>'; }
else {
const mean = (a) => a.reduce((s, x) => s + x, 0) / (a.length || 1);
const R = T.map((t) => t[4]), E = T.map((t) => t[5]);
let cumR = 0, cumE = 0, sommet = 0, ddMax = 0, ddCour = [];
const serieR = [], serieE = [];
T.forEach((t, i) => { cumR += t[4]; cumE += t[5]; sommet = Math.max(sommet, cumR); ddMax = Math.min(ddMax, cumR - sommet);
  serieR.push([t[0], cumR]); serieE.push([t[0], cumE]); ddCour.push([t[0], cumR - sommet]); });
const gagn = T.filter((t) => t[4] > 0.05), perd = T.filter((t) => t[4] < -0.05);
const gains = gagn.reduce((s, t) => s + t[4], 0), pertes = -perd.reduce((s, t) => s + t[4], 0);
let serieMax = 0, c = 0; T.forEach((t) => { c = t[4] < -0.5 ? c + 1 : 0; serieMax = Math.max(serieMax, c); });
const jours = {}; T.forEach((t) => { (jours[t[1]] = jours[t[1]] || []).push(t); });
const jr = Object.keys(jours).sort().map((j) => [j, jours[j].reduce((s, t) => s + t[4], 0), jours[j].reduce((s, t) => s + t[5], 0), jours[j].length]);
const meilleur = jr.reduce((a, b) => b[1] > a[1] ? b : a), pire = jr.reduce((a, b) => b[1] < a[1] ? b : a);
const nbJoursPos = jr.filter((j) => j[1] > 0).length;
$('sous').textContent = 'Du ' + jolie(jr[0][0]) + ' au ' + jolie(jr[jr.length - 1][0]) + ' · ' + T.length + ' trades reels termines · ' + jr.length + ' jours de trading · mis a jour le ' + MAJ;
const cartes = [
  ['R cumule', fmt(cumR), cls(cumR), 'sur ' + T.length + ' trades'],
  ['Argent cumule', eur(cumE), cls(cumE), 'selon les lots reels'],
  ['R moyen par trade', fmt(mean(R), 3), cls(mean(R)), 'esperance observee'],
  ['Gagnants', (100 * gagn.length / T.length).toFixed(0) + ' %', '', gagn.length + ' gagnants · ' + perd.length + ' perdants'],
  ['Facteur de profit', pertes ? (gains / pertes).toFixed(2).replace('.', ',') : '–', '', 'gains / pertes en R'],
  ['Pire recul (drawdown)', fmt(ddMax) + ' R', 'neg', 'depuis un sommet'],
  ['Plus longue serie de stops', serieMax, '', 'trades de suite'],
  ['Jours positifs', nbJoursPos + ' / ' + jr.length, '', 'meilleur ' + jolie(meilleur[0]).slice(0, 5) + ' ' + fmt(meilleur[1], 1) + ' R · pire ' + jolie(pire[0]).slice(0, 5) + ' ' + fmt(pire[1], 1) + ' R'],
];
$('cartes').innerHTML = cartes.map((c) => '<div class="carte"><span>' + c[0] + '</span><b class="' + c[2] + '">' + c[1] + '</b><small>' + c[3] + '</small></div>').join('');

const tip = $('tip');
function el(n, a, p) { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function chiffresRonds(min, max, n) { const pas0 = (max - min) / n || 1, e = Math.pow(10, Math.floor(Math.log10(pas0))); const pas = [1, 2, 5, 10].map((m) => m * e).find((p) => p >= pas0) || pas0; const out = []; for (let v = Math.ceil(min / pas) * pas; v <= max + 1e-9; v += pas) out.push(Math.round(v / pas) * pas); return out; }
function tracer(svg, W, H, series, o) {
  svg.innerHTML = ''; const m = {l: 54, r: 14, t: 10, b: 26}, w = W - m.l - m.r, h = H - m.t - m.b;
  const toutes = series.flatMap((s) => s.pts); if (!toutes.length) return;
  let x0 = Math.min(...toutes.map((p) => p[0])), x1 = Math.max(...toutes.map((p) => p[0]));
  if (o.xmin !== undefined) x0 = Math.min(x0, o.xmin); if (x1 === x0) x1 = x0 + 1;
  let y0 = Math.min(0, ...toutes.map((p) => p[1])), y1 = Math.max(0, ...toutes.map((p) => p[1])); if (y1 === y0) y1 = y0 + 1; const mg = (y1 - y0) * .06; y0 -= mg; y1 += mg;
  const X = (v) => m.l + (v - x0) / (x1 - x0) * w, Y = (v) => m.t + (y1 - v) / (y1 - y0) * h;
  const g = el('g', {class: 'grille'}, svg), a = el('g', {class: 'axe'}, svg);
  chiffresRonds(y0, y1, 5).forEach((v) => { el('line', {x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), 'stroke-width': v === 0 ? 1.4 : 1, opacity: v === 0 ? 1 : .8}, g); const t = el('text', {x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end'}, a); t.textContent = o.fy ? o.fy(v) : v; });
  const nT = 6; for (let i = 0; i <= nT; i++) { const v = x0 + (x1 - x0) * i / nT, t = el('text', {x: X(v), y: H - 6, 'text-anchor': i === 0 ? 'start' : (i === nT ? 'end' : 'middle')}, a); const d = new Date(v); t.textContent = String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0'); }
  (o.evts || []).forEach((e, i) => { if (e[0] < x0 || e[0] > x1) return; el('line', {x1: X(e[0]), x2: X(e[0]), y1: m.t, y2: m.t + h, stroke: couleur(4), 'stroke-dasharray': '3 4', 'stroke-width': 1, opacity: .7}, svg);
    const t = el('text', {x: X(e[0]) + 3, y: m.t + 10 + (i % 3) * 11, fill: couleur(4), 'font-size': 10}, svg); t.textContent = (i + 1); });
  series.forEach((s, k) => { const col = s.couleur || couleur(k);
    if (o.barres) { const bw = Math.max(1.5, w / s.pts.length * .7); s.pts.forEach((p) => el('rect', {x: X(p[0]) - bw / 2, y: Math.min(Y(p[1]), Y(0)), width: bw, height: Math.max(.8, Math.abs(Y(p[1]) - Y(0))), fill: p[1] >= 0 ? couleur(0) : getComputedStyle(document.documentElement).getPropertyValue('--bad').trim()}, svg)); return; }
    const d = s.pts.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('');
    if (o.aire) el('path', {d: d + 'L' + X(s.pts[s.pts.length - 1][0]) + ' ' + Y(0) + 'L' + X(s.pts[0][0]) + ' ' + Y(0) + 'Z', fill: col, opacity: .15}, svg);
    el('path', {d: d, fill: 'none', stroke: col, 'stroke-width': 2, 'stroke-linejoin': 'round'}, svg); });
  const cur = el('line', {y1: m.t, y2: m.t + h, stroke: couleur(0), 'stroke-width': 1, opacity: 0}, svg), zone = el('rect', {x: m.l, y: m.t, width: w, height: h, fill: 'transparent'}, svg);
  zone.addEventListener('mousemove', (ev) => { const r = svg.getBoundingClientRect(), vx = x0 + ((ev.clientX - r.left) / r.width * W - m.l) / w * (x1 - x0); let best = null;
    series.forEach((s, k) => s.pts.forEach((p) => { if (!best || Math.abs(p[0] - vx) < Math.abs(best.p[0] - vx)) best = {p, s, k}; }));
    if (!best) return; cur.setAttribute('x1', X(best.p[0])); cur.setAttribute('x2', X(best.p[0])); cur.setAttribute('opacity', .6);
    const d = new Date(best.p[0]); tip.style.display = 'block'; tip.style.left = Math.min(ev.clientX + 14, innerWidth - 270) + 'px'; tip.style.top = (ev.clientY + 14) + 'px';
    tip.innerHTML = '<b>' + d.toLocaleDateString('fr-FR') + (o.heure ? ' ' + d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'}) : '') + '</b><br>' + series.map((s2) => { const q = s2.pts.reduce((a, b) => Math.abs(b[0] - best.p[0]) < Math.abs(a[0] - best.p[0]) ? b : a); return (series.length > 1 ? s2.nom + ' : ' : '') + (o.fy ? o.fy(q[1]) : fmt(q[1])); }).join('<br>'); });
  zone.addEventListener('mouseleave', () => { tip.style.display = 'none'; cur.setAttribute('opacity', 0); });
}
const evts = EVT.map((e) => [new Date(e[0] + 'T00:00:00').getTime(), e[1]]).filter((e) => e[0] >= T[0][0] - 86400000 * 3);
$('evts').innerHTML = evts.map((e) => '<li>' + new Date(e[0]).toLocaleDateString('fr-FR') + ' — ' + e[1] + '</li>').join('');
const xmin = Math.min(T[0][0], evts.length ? evts[0][0] : T[0][0]);
function courbe(mode) { $('b-r').className = mode === 'r' ? 'on' : ''; $('b-e').className = mode === 'e' ? 'on' : '';
  tracer($('g-courbe'), 1100, 340, [{nom: mode === 'r' ? 'R cumule' : 'Argent cumule', pts: mode === 'r' ? serieR : serieE}], {aire: true, evts: evts, heure: true, xmin: xmin, fy: mode === 'r' ? (v) => fmt(v, 1) + ' R' : (v) => eur(v)}); }
$('b-r').onclick = () => courbe('r'); $('b-e').onclick = () => courbe('e'); courbe('r');
tracer($('g-dd'), 540, 220, [{nom: 'Drawdown', pts: ddCour, couleur: getComputedStyle(document.documentElement).getPropertyValue('--bad').trim()}], {aire: true, fy: (v) => fmt(v, 1) + ' R'});
const glis = []; for (let i = 29; i < T.length; i++) glis.push([T[i][0], mean(R.slice(i - 29, i + 1))]);
tracer($('g-glis'), 540, 220, [{nom: 'R moyen (30 trades)', pts: glis.length ? glis : [[T[0][0], 0], [T[T.length - 1][0], 0]]}], {fy: (v) => fmt(v, 2)});
tracer($('g-jour'), 1100, 240, [{nom: 'Jour', pts: jr.map((j) => [new Date(j[0] + 'T12:00:00').getTime(), j[1]])}], {barres: true, fy: (v) => fmt(v, 1) + ' R'});
const moteurs = [...new Set(T.map((t) => t[2]))]; const sm = []; const cums = {};
moteurs.forEach((m, k) => { let c2 = 0; const pts = [[T[0][0], 0]]; T.forEach((t) => { if (t[2] === m) { c2 += t[4]; pts.push([t[0], c2]); } }); pts.push([T[T.length - 1][0], c2]); cums[m] = c2; sm.push({nom: m, pts: pts, couleur: couleur(k)}); });
tracer($('g-moteurs'), 1100, 300, sm, {fy: (v) => fmt(v, 1) + ' R', heure: true});
$('leg-m').innerHTML = sm.map((s) => '<span><i style="background:' + s.couleur + '"></i>' + s.nom + ' ' + fmt(cums[s.nom], 1) + ' R</span>').join('');
function tableau(id, cleFn, ordre, titre) { const g = {}; T.forEach((t) => { const k = cleFn(t); (g[k] = g[k] || []).push(t); });
  const lignes = Object.keys(g).sort(ordre).map((k) => { const l = g[k], rs = l.map((t) => t[4]), e = l.reduce((s, t) => s + t[5], 0); const gg = rs.filter((r) => r > 0.05).length;
    return '<tr><td>' + k + '</td><td class="n">' + l.length + '</td><td class="n">' + (100 * gg / l.length).toFixed(0) + ' %</td><td class="n ' + cls(rs.reduce((a, b) => a + b, 0)) + '">' + fmt(rs.reduce((a, b) => a + b, 0)) + '</td><td class="n ' + cls(mean(rs)) + '">' + fmt(mean(rs), 3) + '</td><td class="n ' + cls(e) + '">' + eur(e) + '</td><td class="note">' + (l.length < 30 ? 'trop peu de trades' : '') + '</td></tr>'; });
  $(id).innerHTML = '<thead><tr><th>' + titre + '</th><th class="n">trades</th><th class="n">gagn.</th><th class="n">R cumule</th><th class="n">R moyen</th><th class="n">argent</th><th></th></tr></thead><tbody>' + lignes.join('') + '</tbody>'; }
const MOIS = ['janv.', 'fevr.', 'mars', 'avril', 'mai', 'juin', 'juil.', 'aout', 'sept.', 'oct.', 'nov.', 'dec.'];
tableau('t-mois', (t) => t[1].slice(0, 7), (a, b) => a < b ? -1 : 1, 'mois'); document.querySelectorAll('#t-mois tbody td:first-child').forEach((td) => { const [y, m] = td.textContent.split('-'); td.textContent = MOIS[+m - 1] + ' ' + y; });
tableau('t-moteur', (t) => t[2], (a, b) => a < b ? -1 : 1, 'moteur'); tableau('t-sens', (t) => t[3], (a, b) => a < b ? -1 : 1, 'sens');
tableau('t-heure', (t) => String(new Date(t[0]).getHours()).padStart(2, '0') + 'h', (a, b) => a < b ? -1 : 1, 'heure');
}
</script></body></html>
'''


def main(argv):
    ouvrir = "--sans-ouvrir" not in argv
    argv = [a for a in argv if not a.startswith("--")]
    try:
        depuis = datetime.strptime(argv[0], "%d/%m/%Y") if argv else None
    except ValueError:
        print("Date attendue : jj/mm/aaaa")
        return 1
    if not FICHIER.exists():
        print(f"{FICHIER} introuvable.")
        return 1
    trades = lire(FICHIER, depuis)
    if not trades:
        print("Aucun trade termine a afficher.")
        return 0
    html = (MODELE.replace("__DONNEES__", json.dumps(trades, ensure_ascii=False))
            .replace("__EVENEMENTS__", json.dumps(EVENEMENTS, ensure_ascii=False))
            .replace("__MAJ__", datetime.now().strftime("%d/%m/%Y %H:%M")))
    SORTIE.write_text(html, encoding="utf-8")
    print(f"{len(trades)} trades -> {SORTIE}")
    if ouvrir:
        webbrowser.open(SORTIE.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
