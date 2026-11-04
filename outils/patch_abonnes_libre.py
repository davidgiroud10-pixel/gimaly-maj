# -*- coding: utf-8 -*-
r"""Patch : page « Abonnements VIP » plus simple et plus libre.

  * Par ligne : prix par mois LIBRE, nombre de MOIS pris d'un coup LIBRE, et le TOTAL (prix x mois), la FIN et le RESTE se calculent.
    Changer les mois ou le debut recalcule la fin (meme regle que le PC : meme quantieme le mois suivant).
  * Colonnes « au renouv. » et « depot » : le prix au renouvellement reste visible sous le prix (avec la case « fige »), broker et
    depot n'apparaissent plus que pour les membres broker.
  * A l'ajout : prix, mois pris, debut ; la fin se calcule, et le paiement (prix x mois) est note dans « encaisse ce mois-ci ».
  * Seule la PAGE change (PAGE_ABOS dans gimaly/bridges/web.py). abonnements.py, abonnements.json, les rappels, le bilan et
    l'envoi sur Telegram ne sont pas touches.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_abonnes_libre.py   puis redemarrer GIMALY (ou relancer le serveur web).
Sauvegarde : web.py.avant_abos. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "gimaly" / "bridges" / "web.py"
MARQUE = "<!-- abonnes_libre -->"
DEBUT = 'PAGE_ABOS = """<!DOCTYPE html>'
SUITE = '\n"""\n\n\nPAGE_ICEBERGS'
NOUVELLE = r'''
<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#05080d">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Abonnements VIP</title>
<!-- abonnes_libre -->
<style>
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{margin:0;background:#05080d;color:#9fb4c7;font-family:"SF Mono",Consolas,monospace;
       min-height:100dvh;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
  header{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid #14293a}
  h1{font-size:16px;letter-spacing:.5px;color:#2a9cc2;margin:0}
  header a{margin-left:auto;color:#35d6ff;text-decoration:none;font-size:12px}
  .bilan{display:flex;gap:10px;flex-wrap:wrap;padding:12px 14px}
  .bloc{flex:1 1 140px;background:#0a111acc;border:1px solid #14293a;border-radius:6px;padding:9px 12px}
  .bloc span{display:block;font-size:12px;letter-spacing:.5px;color:#2a9cc2}
  .bloc b{font-size:17px;color:#d6e4f0;font-weight:700}
  .bloc small{display:block;font-size:11px;color:#7d93a6;margin-top:2px}
  .zone{overflow-x:auto;padding:0 14px 14px}
  table{width:100%;border-collapse:collapse;font-size:12px;min-width:1040px}
  th{text-align:left;font-size:12px;letter-spacing:.5px;color:#2a9cc2;padding:8px 6px;
     border-bottom:1px solid #14293a;white-space:nowrap}
  td{padding:7px 6px;border-bottom:1px solid #0e1d2a;vertical-align:middle}
  tr.urgent td{background:#2a0f1580}
  tr.bientot td{background:#2a220f80}
  tr.inactif{opacity:.45}
  input,select{background:#0a111a;border:1px solid #14293a;border-radius:4px;color:#d6e4f0;
     font-family:inherit;font-size:13px;padding:6px}
  input:focus,select:focus{outline:none;border-color:#35d6ff}
  input.pseudo{width:130px}input.prix{width:80px}input.mois{width:64px}input.date{width:132px}
  input.broker{width:92px}input.depot{width:78px}
  input.note{width:100%;min-width:120px}
  .calc{white-space:nowrap;color:#d6e4f0;font-size:13px}
  .petit{font-size:11px;color:#7d93a6;white-space:nowrap}
  .reste{white-space:nowrap;font-size:12px}
  .reste.rouge{color:#ff6b6b}.reste.orange{color:#ffb547}.reste.vert{color:#6ee7a8}
  button{background:#0f2a3a;border:1px solid #1e4a63;color:#9fb4c7;border-radius:4px;
     padding:6px 10px;font-family:inherit;font-size:12px;cursor:pointer}
  button:hover{border-color:#35d6ff;color:#35d6ff}
  button.sup:hover{border-color:#ff6b6b;color:#ff6b6b}
  .ajout{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;padding:12px 14px;
     border-top:1px solid #14293a}
  .ajout label{display:flex;flex-direction:column;gap:3px;font-size:11px;color:#7d93a6}
  .etat{padding:0 14px 14px;font-size:12px;color:#7d93a6;min-height:16px}
</style></head><body>
<header><h1>ABONNEMENTS · LE COIN TRADER VIP</h1><a href="/" id="retour">← assistant</a></header>

<div class="bilan">
  <div class="bloc"><span>MEMBRES</span><b id="b-membres">–</b><small id="b-detail"></small></div>
  <div class="bloc"><span>PAR MOIS</span><b id="b-total">–</b></div>
  <div class="bloc"><span>APRÈS RENOUV.</span><b id="b-futur">–</b></div>
  <div class="bloc"><span>ENCAISSÉ CE MOIS</span><b id="b-encaisse">–</b></div>
  <div class="bloc"><span>DÉPÔTS BROKER</span><b id="b-depots">–</b></div>
</div>

<div class="zone">
<table><thead><tr>
  <th>PSEUDO</th><th>STATUT</th><th>PRIX / MOIS €</th><th>MOIS PRIS</th><th>TOTAL</th>
  <th>DÉBUT</th><th>FIN</th><th>RESTE</th><th>BROKER · DÉPÔT</th><th>NOTE</th><th></th>
</tr></thead><tbody id="corps"></tbody></table>
</div>

<div class="ajout">
  <label>pseudo<input class="pseudo" id="n-pseudo" placeholder="pseudo"></label>
  <label>statut<select id="n-statut"><option value="payant">payant</option><option value="formation">formation</option><option value="broker">broker</option></select></label>
  <label>prix par mois €<input class="prix" id="n-prix" placeholder="89" inputmode="decimal"></label>
  <label>mois pris d'un coup<input class="mois" id="n-mois" placeholder="1" inputmode="numeric"></label>
  <label>début<input class="date" id="n-debut" type="date"></label>
  <label>fin (formation)<input class="date" id="n-fin" type="date"></label>
  <label>broker<input class="broker" id="n-broker" placeholder="broker" list="brokers"></label>
  <label>dépôt €<input class="depot" id="n-depot" placeholder="0" inputmode="decimal"></label>
  <datalist id="brokers"><option value="PU Prime"><option value="Vantage"></datalist>
  <button onclick="ajouter()">+ ajouter</button>
  <button onclick="charger()">↻</button>
  <button onclick="bilan(false)">📊 bilan</button>
  <button onclick="bilan(true)">➤ sur Telegram</button>
</div>
<pre id="resume" style="display:none;margin:0;padding:12px 14px;white-space:pre-wrap;
     font-size:12px;line-height:1.5;color:#6ee7a8;border-top:1px solid #14293a"></pre>
<div class="etat" id="etat">Le prix, les mois et le début se règlent librement : le total et la fin se calculent. Tout est enregistré dès que tu quittes une case. Pour une formation, mets la date de fin dans la colonne FIN.</div>

<script>
const params = new URLSearchParams(location.search);
let JETON = params.get('k') || localStorage.getItem('gimaly_k') || '';
if (JETON) {
  localStorage.setItem('gimaly_k', JETON);
  if (!params.get('k')) history.replaceState({}, '', location.pathname + '?k=' + JETON);
  document.getElementById('retour').href = '/?k=' + JETON;
}

let STANDARD = 150;
function etat(texte) { document.getElementById('etat').textContent = texte; }
function ech(t) { return String(t ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }
function eur(n) { return (Math.round(n * 100) / 100).toFixed(2).replace('.', ',').replace(',00', '') + ' €'; }
function nombre(t) { const x = parseFloat(String(t ?? '').replace(',', '.')); return isFinite(x) ? x : 0; }

async function api(corps) {
  const r = await fetch('/api/abonnements', {
    method: corps ? 'POST' : 'GET',
    headers: {'Content-Type':'application/json','X-Jeton':JETON},
    body: corps ? JSON.stringify(corps) : undefined});
  if (r.status === 403) { etat("jeton invalide : rouvre la page avec ?k=…"); return null; }
  return await r.json();
}

// Dates : même règle que le PC (même quantième le mois suivant, ramené à la fin du mois).
function lireJour(s) { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ''); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
function iso(d) { const p = (n) => (n < 10 ? '0' : '') + n; return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }
function moisSuivant(d) {
  const annee = d.getFullYear() + (d.getMonth() === 11 ? 1 : 0), mois = (d.getMonth() + 1) % 12;
  const dernier = new Date(annee, mois + 1, 0).getDate();
  return new Date(annee, mois, Math.min(d.getDate(), dernier));
}
function ajoutMois(d, n) { let r = d; for (let i = 0; i < n; i++) r = moisSuivant(r); return r; }
function nbMois(debut, fin) {            // combien de mois entre le début et la fin ; null si illisible
  const a = lireJour(debut), b = lireJour(fin);
  if (!a || !b || b <= a) return null;
  let d = a, n = 0;
  while (d < b && n < 600) { d = moisSuivant(d); n++; }
  return {n: n, exact: iso(d) === iso(b)};
}

function classeReste(j) {
  if (j === null) return ['', '–'];
  if (j < 0) return ['rouge', 'en retard de ' + (-j) + ' j'];
  if (j === 0) return ['rouge', "aujourd'hui"];
  if (j <= 3) return ['orange', 'dans ' + j + ' j'];
  return ['vert', 'dans ' + j + ' j'];
}
function classeLigne(m) {
  return !m.actif ? 'inactif' : (m.reste !== null && m.reste <= 0 ? 'urgent'
         : (m.reste !== null && m.reste <= 3 ? 'bientot' : ''));
}

function compteurs(d) {
  const actifs = d.membres.filter((m) => m.actif !== false).length;
  document.getElementById('b-membres').textContent = actifs;
  document.getElementById('b-detail').textContent =
    d.payants + ' payants · ' + d.formation + ' formation · ' + d.broker + ' broker';
  document.getElementById('b-total').textContent = eur(d.total);
  document.getElementById('b-futur').textContent = eur(d.futur);
  document.getElementById('b-depots').textContent = eur(d.depots);
  document.getElementById('b-encaisse').textContent = eur(d.encaisse);
  STANDARD = d.standard || 150;
}

async function charger() {
  const d = await api(null);
  if (!d) return;
  compteurs(d);
  const corps = document.getElementById('corps');
  corps.innerHTML = '';
  for (const m of d.membres) {
    const payant = m.statut === 'payant', broker = m.statut === 'broker';
    const [cl, txt] = classeReste(m.reste);
    const nm = payant ? nbMois(m.debut, m.renouvellement) : null;
    const tr = document.createElement('tr');
    tr.dataset.id = m.id;
    tr.className = classeLigne(m);
    tr.innerHTML =
      '<td><input class="pseudo" value="' + ech(m.pseudo) + '" data-c="pseudo"></td>' +
      '<td><select data-c="statut"><option value="payant"' + (payant ? ' selected' : '') +
        '>payant</option><option value="formation"' + (m.statut === 'formation' ? ' selected' : '') +
        '>formation</option><option value="broker"' + (broker ? ' selected' : '') +
        '>broker</option></select></td>' +
      '<td>' + (payant
          ? '<input class="prix" value="' + (m.prix || 0) + '" data-c="prix" inputmode="decimal">' +
            '<div class="petit" data-du>→ ' + eur(m.du || 0) + ' au renouv. ' +
            '<label><input type="checkbox" data-c="tarif_fige"' + (m.tarif_fige ? ' checked' : '') + '> figé</label></div>'
          : (m.statut === 'formation' ? '<span class="petit">' + eur(STANDARD) + ' à la fin</span>'
                                      : '<span class="petit">offert</span>')) + '</td>' +
      '<td>' + (payant
          ? '<input class="mois" value="' + (nm ? nm.n : '') + '" data-c="mois" inputmode="numeric"' +
            (nm && !nm.exact ? ' title="la fin n\'est pas un nombre rond de mois"' : '') + '>'
          : '–') + '</td>' +
      '<td class="calc" data-total>–</td>' +
      '<td><input class="date" type="date" value="' + ech(m.debut) + '" data-c="debut"></td>' +
      '<td><input class="date" type="date" value="' + ech(m.renouvellement) + '" data-c="renouvellement"></td>' +
      '<td class="reste ' + cl + '" data-r>' + txt + '</td>' +
      '<td>' + (broker
          ? '<input class="broker" value="' + ech(m.broker) + '" data-c="broker" list="brokers"> ' +
            '<input class="depot" value="' + (m.depot || 0) + '" data-c="depot" inputmode="decimal">'
          : '–') + '</td>' +
      '<td><input class="note" value="' + ech(m.note) + '" data-c="note"></td>' +
      // Les boutons reçoivent leur action plus bas : un onclick écrit dans le
      // HTML obligerait à échapper les apostrophes des pseudos.
      '<td style="white-space:nowrap">' +
        '<button data-a="un" title="paiement d un mois">+1</button> ' +
        '<button data-a="n" title="paiement de plusieurs mois">+N</button> ' +
        '<button data-a="h" title="paiements reçus">≡</button> ' +
        '<button data-a="sup" class="sup">✕</button>' +
      '</td>';
    const actions = {
      un: () => renouveler(m.id, 1, m.du),
      n: () => renouveler(m.id, 0),
      h: () => historique(m.id),
      sup: () => supprimer(m.id, m.pseudo),
    };
    for (const bouton of tr.querySelectorAll('[data-a]')) {
      bouton.addEventListener('click', actions[bouton.dataset.a]);
    }
    for (const champ of tr.querySelectorAll('[data-c]')) {
      champ.addEventListener('change', () => surChamp(m.id, tr, champ));
    }
    corps.appendChild(tr);
    totalLigne(tr);
  }
  etat(d.membres.length ? 'À jour.' : "Aucun abonné : ajoute le premier ci-dessous.");
}

function champ(tr, nom) { return tr.querySelector('[data-c="' + nom + '"]'); }

// Total = prix par mois × nombre de mois, recalculé à chaque saisie.
function totalLigne(tr) {
  const cellule = tr.querySelector('[data-total]');
  const prix = champ(tr, 'prix'), mois = champ(tr, 'mois');
  cellule.textContent = (prix && mois && nombre(mois.value) > 0)
    ? eur(nombre(prix.value) * Math.round(nombre(mois.value))) : '–';
}

async function ecrire(id, nom, valeur) {
  // Une date en cours de frappe passe par des valeurs vides : on ne les
  // enregistre pas, sinon l'année à moitié tapée effacerait la date.
  if ((nom === 'debut' || nom === 'renouvellement') && !valeur) return false;
  const d = await api({action: 'modifier', id, champ: nom, valeur});
  if (d && d.erreur) { etat('Erreur : ' + d.erreur); charger(); return false; }
  return !!d;
}

async function surChamp(id, tr, el) {
  const nom = el.dataset.c;
  const valeur = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
  const fin = champ(tr, 'renouvellement'), moisEl = champ(tr, 'mois');
  const payant = champ(tr, 'statut').value === 'payant';
  if (nom === 'statut') {
    if (await ecrire(id, nom, valeur)) { etat('Enregistré.'); charger(); }
    return;
  }
  if (nom === 'mois') {                       // « mois pris » : la fin = début + ces mois
    const n = Math.max(1, Math.round(nombre(valeur)));
    const debut = lireJour(champ(tr, 'debut').value);
    if (!debut) { etat("Mets d'abord la date de début."); return; }
    moisEl.value = n;
    const nouvelle = iso(ajoutMois(debut, n));
    if (!(await ecrire(id, 'renouvellement', nouvelle))) return;
    fin.value = nouvelle;
  } else if (nom === 'debut' && payant && moisEl && nombre(moisEl.value) > 0) {
    if (!(await ecrire(id, 'debut', valeur))) return;
    const d = lireJour(valeur);
    if (d) {                                  // le début bouge : la fin suit, avec les mêmes mois
      const nouvelle = iso(ajoutMois(d, Math.round(nombre(moisEl.value))));
      if (!(await ecrire(id, 'renouvellement', nouvelle))) return;
      fin.value = nouvelle;
    }
  } else {
    if (!(await ecrire(id, nom, valeur))) return;
    if ((nom === 'renouvellement' || nom === 'debut') && moisEl) {
      const nm = nbMois(champ(tr, 'debut').value, fin.value);
      if (nm) moisEl.value = nm.n;
    }
  }
  totalLigne(tr);
  etat('Enregistré.');
  majTotaux();                 // on ne redessine pas le tableau : le curseur reste où il est
}

// Rafraîchit seulement les compteurs du haut et la colonne « reste ».
async function majTotaux() {
  const d = await api(null);
  if (!d) return;
  compteurs(d);
  for (const m of d.membres) {
    const tr = document.querySelector('tr[data-id="' + m.id + '"]');
    if (!tr) continue;
    const cellule = tr.querySelector('[data-r]');
    const [cl, txt] = classeReste(m.reste);
    if (cellule) { cellule.className = 'reste ' + cl; cellule.textContent = txt; }
    tr.className = classeLigne(m);
    const du = tr.querySelector('[data-du]');
    if (du && du.firstChild) du.firstChild.textContent = '→ ' + eur(m.du || 0) + ' au renouv. ';
  }
}

async function ajouter() {
  const pseudo = document.getElementById('n-pseudo').value.trim();
  if (!pseudo) { etat('Il manque le pseudo.'); return; }
  const statut = document.getElementById('n-statut').value;
  const prix = nombre(document.getElementById('n-prix').value);
  const mois = Math.max(1, Math.round(nombre(document.getElementById('n-mois').value)) || 1);
  const debut = document.getElementById('n-debut').value || iso(new Date());
  let fin = document.getElementById('n-fin').value;
  if (!fin && statut === 'payant') fin = iso(ajoutMois(lireJour(debut), mois));
  const d = await api({action: 'ajouter', pseudo, statut, prix,
    broker: document.getElementById('n-broker').value,
    depot: document.getElementById('n-depot').value || 0,
    debut, renouvellement: fin});
  if (d && d.erreur) { etat('Erreur : ' + d.erreur); return; }
  if (statut === 'payant' && prix > 0) {      // les mois pris comptent dans « encaissé »
    const p = await api({action: 'paiement', pseudo, montant: prix * mois, mois, date: debut});
    if (p && p.erreur) etat('Ajouté, mais paiement non noté : ' + p.erreur);
  }
  for (const id of ['n-pseudo', 'n-prix', 'n-mois', 'n-fin', 'n-broker', 'n-depot']) {
    document.getElementById(id).value = '';
  }
  etat('Ajouté.'); charger();
}

async function renouveler(id, mois, du) {
  let montant = null;
  if (mois === 1) {
    // 01/10 : le +1 encaissait 150 € d'office ; on confirme toujours le montant
    const saisi = prompt("Montant encaissé pour 1 mois (en euros) :", String(du || ''));
    if (saisi === null) return;
    if (saisi.trim()) montant = saisi.replace(',', '.');
  }
  if (!mois) {
    mois = parseInt(prompt("Combien de mois payés d'avance ?", "3") || 0, 10);
    if (!mois || mois < 1) return;
    const saisi = prompt("Montant encaissé en euros (vide = prix × " + mois + ") :", "");
    if (saisi !== null && saisi.trim()) montant = saisi.replace(',', '.');
  }
  const d = await api({action: 'renouveler', id, mois, montant});
  if (d && d.erreur) { etat('Erreur : ' + d.erreur); return; }
  etat('Échéance décalée de ' + mois + ' mois.'); charger();
}

async function historique(id) {
  const d = await api({action: 'historique', id});
  if (!d) return;
  const zone = document.getElementById('resume');
  zone.style.display = 'block';
  if (!d.paiements || !d.paiements.length) { zone.textContent = d.texte || d.erreur; return; }
  zone.innerHTML = '<b>' + ech(d.pseudo) + ' — paiements</b> (n°1 = le plus récent)<br>' +
    d.paiements.map((p, i) =>
      'n°' + (i + 1) + ' · ' + ech(p.date) + ' · ' + Number(p.montant || 0).toFixed(2) + ' € · ' +
      (p.mois || 1) + ' mois ' +
      '<button data-p="' + (i + 1) + '" data-op="modifier">corriger</button> ' +
      '<button data-p="' + (i + 1) + '" data-op="supprimer">supprimer</button>').join('<br>');
  zone.querySelectorAll('button[data-p]').forEach((b) => b.onclick = async () => {
    const numero = parseInt(b.dataset.p, 10), p = d.paiements[numero - 1];
    if (b.dataset.op === 'modifier') {
      const montant = prompt('Montant correct (euros) :', String(p.montant));
      if (montant === null) return;
      const quand = prompt('Date (jj/mm/aaaa) :', p.date.split('-').reverse().join('/'));
      if (quand === null) return;
      const r = await api({action: 'modifier_paiement', id, numero, montant: montant.replace(',', '.'), date: quand});
      etat(r && r.erreur ? 'Erreur : ' + r.erreur : 'Paiement corrigé.');
    } else {
      if (!confirm('Supprimer le paiement n°' + numero + ' (' + p.montant + ' €) ?')) return;
      const reculer = confirm("Reculer aussi l'échéance de " + (p.mois || 1) + " mois ?\n(OK = oui, Annuler = garder la date)");
      const r = await api({action: 'supprimer_paiement', id, numero, reculer});
      etat(r && r.erreur ? 'Erreur : ' + r.erreur : 'Paiement supprimé.');
    }
    charger(); historique(id);
  });
}

async function supprimer(id, pseudo) {
  if (!confirm('Supprimer ' + pseudo + ' ?')) return;
  await api({action: 'supprimer', id});
  etat('Supprimé.'); charger();
}

async function bilan(surTelegram) {
  etat(surTelegram ? 'Envoi…' : 'Calcul…');
  const d = await api({action: surTelegram ? 'bilan_telegram' : 'bilan'});
  if (!d) return;
  if (d.erreur) { etat('Erreur : ' + d.erreur); return; }
  const zone = document.getElementById('resume');
  zone.style.display = 'block';
  zone.textContent = d.texte;
  etat(surTelegram ? 'Bilan envoyé sur Telegram.' : 'Bilan du jour.');
}

charger();
// On ne redessine plus le tableau tout seul : une saisie en cours serait perdue.
setInterval(majTotaux, 300000);
</script></body></html>
'''


def main():
    if not F.exists():
        print(f"{F} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    brut = F.read_bytes()
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), brut.count(b"\r\n") > brut.count(b"\n") / 2
    txt = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if MARQUE in txt:
        print("web.py : page des abonnes deja remplacee (rien a faire).")
        return 0
    a = txt.find(DEBUT)
    if a < 0 or txt.count(DEBUT) != 1:
        print("REPERE INTROUVABLE : debut de PAGE_ABOS. Rien n'est modifie. Envoie-moi cette erreur.")
        return 2
    b = txt.find(SUITE, a)
    if b < 0:
        print("REPERE INTROUVABLE : fin de PAGE_ABOS (avant PAGE_ICEBERGS). Rien n'est modifie. Envoie-moi cette erreur.")
        return 2
    nouveau = txt[:a] + 'PAGE_ABOS = r"""' + NOUVELLE.lstrip("\n").rstrip("\n") + txt[b:]
    try:
        compile(nouveau, str(F), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F, F.with_name(F.name + ".avant_abos"))
    sortie = nouveau.replace("\n", "\r\n") if crlf else nouveau
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("web.py : page des abonnes remplacee (sauvegarde web.py.avant_abos). Redemarre GIMALY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
