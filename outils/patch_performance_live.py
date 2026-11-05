# -*- coding: utf-8 -*-
r"""Patch : page /performance en direct (rafraichie toutes les 30 s + trades ouverts affiches).

  * web.py : lire_performance ajoute « ouverts » (lu dans trading_etat.json, lecture seule) ;
    la page se recharge seule toutes les 30 s (onglet visible) en gardant la periode choisie ;
    bandeau « En ce moment » : sens, genre, entree, SL, TP et R flottant SI le fichier d'etat contient un prix courant.
Prerequis : patch_performance_gimaly applique. Rien dans le bot.
Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_performance_live.py   puis redemarrer GIMALY (fenetre principale).
Sauvegarde : web.py.avant_perf_live. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F_WEB = Path.cwd() / "gimaly" / "bridges" / "web.py"
MARQUE = "def _ouverts_perf"

HELPER = '''    def _ouverts_perf(self) -> list:
        """Trades ouverts du bot (trading_etat.json, lecture seule) ; R flottant seulement si un prix courant est fourni."""
        import json
        from pathlib import Path as _P

        def nombre(x):
            try:
                return float(str(x).replace(",", ".").strip())
            except (TypeError, ValueError):
                return None

        try:
            etat = json.loads((_P.home() / "GIMALY" / "trading" / "trading_etat.json").read_text(encoding="utf-8-sig"))
        except Exception:
            return []
        sortie = []
        for t in (etat.get("en_cours") or []):
            if not isinstance(t, dict):
                continue
            pe, sl = nombre(t.get("pe")), nombre(t.get("sl"))
            prix = None
            for cle in ("prix", "prix_actuel", "cours", "bid", "last"):
                prix = nombre(t.get(cle)) if prix is None else prix
            for cle in ("prix", "prix_actuel", "cours", "bid", "last"):
                prix = nombre(etat.get(cle)) if prix is None else prix
            sens = str(t.get("sens") or "?").lower()
            r = None
            if prix and pe and sl and abs(pe - sl) > 0:
                r = round((prix - pe) / abs(pe - sl) * (-1 if sens.startswith("s") or sens.startswith("v") else 1), 2)
            sortie.append({"genre": str(t.get("genre") or "?"), "sens": sens, "pe": pe, "sl": sl,
                           "tp": [x for x in (t.get("tp") or []) if isinstance(x, (int, float))] if isinstance(t.get("tp"), list) else [],
                           "prix": prix, "r": r})
        return sortie

'''
CH = [
    ("    def lire_performance(self) -> dict:\n", HELPER + "    def lire_performance(self) -> dict:\n"),
    ('"periodes": PERIODES_PERF, "evenements": EVENEMENTS_PERF}',
     '"periodes": PERIODES_PERF, "evenements": EVENEMENTS_PERF, "ouverts": self._ouverts_perf()}'),
    ('<div class="bascule" id="periodes"></div>',
     '<section class="bloc" id="live"></section>\n<div class="bascule" id="periodes"></div>'),
    ("function periode(i) { const d =", "let PI = 0; let OUV = [];\nfunction periode(i) { PI = i; const d ="),
    ("""fetch('/api/performance', {headers: {'X-Jeton': JETON}}).then((r) => r.status === 403 ? Promise.reject('jeton') : r.json())
  .then((d) => { TOUT = d.trades; EVT = d.evenements; PERIODES = d.periodes; MAJ = d.maj; boutons(); periode(0); })
  .catch((e) => { $('sous').textContent = e === 'jeton' ? 'Jeton invalide : rouvre cette page depuis GIMALY.' : 'Erreur : ' + e; });
""",
     """function live(ok) {
  const h = new Date().toLocaleTimeString('fr-FR');
  const lignes = OUV.map((t) => {
    const buy = !(t.sens.startsWith('s') || t.sens.startsWith('v'));
    const r = t.r === null || t.r === undefined ? 'R flottant : non disponible' : 'R flottant ' + fmt(t.r);
    return '<div><b>' + (buy ? 'ACHAT' : 'VENTE') + '</b> ' + t.genre + ' · entree ' + t.pe + ' · SL ' + t.sl +
      (t.tp.length ? ' · TP ' + t.tp.join(' / ') : '') + (t.prix ? ' · prix ' + t.prix : '') +
      ' · <span class="' + (t.r === null || t.r === undefined ? '' : cls(t.r)) + '">' + r + '</span></div>';
  }).join('');
  $('live').innerHTML = '<h2>En ce moment</h2>' + (lignes || '<div class="note">Aucun trade ouvert.</div>') +
    '<div class="note">' + (ok ? 'Mis a jour a ' + h + ' · rafraichi toutes les 30 s' : 'Connexion perdue : derniere mise a jour affichee') + '</div>';
}
function charger(premier) {
  fetch('/api/performance', {headers: {'X-Jeton': JETON}}).then((r) => r.status === 403 ? Promise.reject('jeton') : r.json())
    .then((d) => { TOUT = d.trades; EVT = d.evenements; PERIODES = d.periodes; MAJ = d.maj; OUV = d.ouverts || []; boutons(); periode(Math.min(PI, PERIODES.length - 1)); live(true); })
    .catch((e) => { if (premier) { $('sous').textContent = e === 'jeton' ? 'Jeton invalide : rouvre cette page depuis GIMALY.' : 'Erreur : ' + e; } else { live(false); } });
}
charger(true);
setInterval(() => { if (!document.hidden) charger(false); }, 30000);
"""),
]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def main():
    if not F_WEB.exists():
        print(f"{F_WEB} introuvable : lance ce script depuis le dossier gimaly.")
        return 1
    txt, bom, crlf = lire(F_WEB)
    if MARQUE in txt:
        print("web.py : deja corrige (rien a faire).")
        return 0
    if "def lire_performance" not in txt:
        print("Applique d'abord patch_performance_gimaly. Rien n'est modifie.")
        return 2
    manquants = [a.strip()[:90] for a, _ in CH if txt.count(a) != 1]
    if manquants:
        print("REPERE INTROUVABLE (ou en double) dans web.py : rien n'est modifie. Envoie-moi cette erreur :")
        print("\n".join(manquants))
        return 2
    for ancien, nouveau in CH:
        txt = txt.replace(ancien, nouveau)
    try:
        compile(txt, str(F_WEB), "exec")
    except SyntaxError as exc:
        print(f"Erreur de syntaxe apres modification : {exc}. Rien n'est ecrit.")
        return 3
    shutil.copy2(F_WEB, F_WEB.with_name("web.py.avant_perf_live"))
    sortie = txt.replace("\n", "\r\n") if crlf else txt
    F_WEB.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
    print("web.py : corrige (sauvegarde web.py.avant_perf_live). Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
