# -*- coding: utf-8 -*-
r"""Patch : la page PERFORMANCE ne montre plus l'argent, seulement R, facteur de profit et RR (tant que le bot n'est pas en reel).

  * web.py : carte « Argent cumule » -> carte « RR moyen » (gain moyen / perte moyenne, avec le taux de gagnants minimum pour etre
    rentable) ; carte « Facteur de profit » plus lisible (au-dessus de 1 = gagnant) ; bouton « en argent » et colonne « argent »
    retires ; note de bas de page mise a jour.
  * previews.py : l'apercu du dock affiche le facteur de profit au lieu du gain en euros.
Prerequis : patch_performance_gimaly + patch_performance_v2 + patch_performance_live. Les donnees ne sont pas touchees.
Usage (dossier gimaly) : .\.venv\Scripts\python.exe patch_performance_sans_argent.py   puis redemarrer GIMALY (fenetre principale).
Sauvegardes : *.avant_perf_sans_argent. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

F_WEB = Path.cwd() / "gimaly" / "bridges" / "web.py"
F_PV = Path.cwd() / "gimaly" / "v2" / "core" / "services" / "previews.py"

CH_WEB = [
    ("  ['Argent cumule', eur(cumE), cls(cumE), 'selon les lots reels'],\n",
     "  ['RR moyen (gain / perte)', (gagn.length && perd.length) ? (mean(gagn.map((t) => t[4])) / Math.abs(mean(perd.map((t) => t[4])))).toFixed(2).replace('.', ',') : '–', '',\n"
     "    (gagn.length && perd.length) ? 'gain moyen ' + fmt(mean(gagn.map((t) => t[4]))) + ' R · perte moyenne ' + fmt(mean(perd.map((t) => t[4]))) + ' R · rentable a partir de ' + (100 / (1 + mean(gagn.map((t) => t[4])) / Math.abs(mean(perd.map((t) => t[4]))))).toFixed(0) + ' % de gagnants' : ''],\n"),
    ("  ['Facteur de profit', pertes ? (gains / pertes).toFixed(2).replace('.', ',') : '–', '', 'gains / pertes en R'],\n",
     "  ['Facteur de profit', pertes ? (gains / pertes).toFixed(2).replace('.', ',') : '–', pertes ? (gains / pertes >= 1 ? 'pos' : 'neg') : '', 'gains / pertes en R · au-dessus de 1 = gagnant'],\n"),
    ('<div class="bascule"><button id="b-r" class="on">en R</button><button id="b-e">en argent</button></div>',
     '<div class="bascule" style="display:none"><button id="b-r" class="on">en R</button><button id="b-e">en argent</button></div>'),
    ("""<td class="n ' + cls(e) + '">' + eur(e) + '</td>""", ""),
    ("""<th class="n">argent</th>""", ""),
    (""" « Argent » suit les lots reels du compte (plafond de lot) et peut s'ecarter du R. Rien n'est modifie par cette page.""",
     """ L'argent n'est pas affiche tant que le bot n'est pas en reel : seuls R, facteur de profit et RR comptent. Rien n'est modifie par cette page."""),
]
CH_PV = [
    ("        euros = sum(g for _, _, g in lignes)\n",
     "        gains = sum(r for _, r, _ in lignes if r > 0.05)\n"
     "        pertes = -sum(r for _, r, _ in lignes if r < -0.05)\n"
     "        pf = f\"{gains / pertes:.2f}\" if pertes else \"-\"\n"),
    ('detail = (f"Gain cumule : {_euros(euros)}", ', 'detail = (f"Facteur de profit : {pf}", '),
]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def main():
    jeu = ((F_WEB, "RR moyen (gain / perte)", CH_WEB), (F_PV, "Facteur de profit : {pf}", CH_PV))
    for f, _, _ in jeu:
        if not f.exists():
            print(f"{f} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    ecritures = []
    for f, marque, chs in jeu:
        txt, bom, crlf = lire(f)
        if marque in txt:
            print(f"{f.name} : deja corrige (rien a faire).")
            continue
        manquants = [a.strip()[:90] for a, _ in chs if txt.count(a) != 1]
        if manquants:
            print(f"REPERE INTROUVABLE (ou en double) dans {f.name} : rien n'est modifie. Envoie-moi cette erreur :")
            print("\n".join(manquants))
            return 2
        for a, b in chs:
            txt = txt.replace(a, b)
        try:
            compile(txt, str(f), "exec")
        except SyntaxError as exc:
            print(f"Erreur de syntaxe apres modification de {f.name} : {exc}. Rien n'est ecrit.")
            return 3
        ecritures.append((f, txt, bom, crlf))
    for f, txt, bom, crlf in ecritures:
        shutil.copy2(f, f.with_name(f.name + ".avant_perf_sans_argent"))
        sortie = txt.replace("\n", "\r\n") if crlf else txt
        f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
        print(f"{f.name} : corrige (sauvegarde {f.name}.avant_perf_sans_argent).")
    if ecritures:
        print("Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
