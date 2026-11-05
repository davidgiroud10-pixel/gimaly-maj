# -*- coding: utf-8 -*-
r"""Patch : module PERFORMANCE dans la nouvelle interface (dock, groupe TRADING, palette Ctrl+K).

  * v2/ui/main_window.py : ajoute le module « PERFORMANCE » (sans raccourci F, pour ne decaler aucune touche).
  * v2/app/integre.py : le clic ouvre la page /performance (meme action que le bouton « % » de l'ancien HUD).
  * v2/core/services/previews.py : apercu au survol (R cumule, trades, taux de reussite, 7 jours, creux max).
Prerequis : patch_performance_gimaly deja applique. Lecture seule sur les donnees, rien dans le bot.

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe patch_performance_v2.py   puis redemarrer GIMALY (fenetre principale).
Sauvegardes : *.avant_perf2. Idempotent. Rien n'est ecrit si un repere manque."""
import shutil
import sys
from pathlib import Path

RACINE = Path.cwd() / "gimaly" / "v2"
F_MW = RACINE / "ui" / "main_window.py"
F_IN = RACINE / "app" / "integre.py"
F_PV = RACINE / "core" / "services" / "previews.py"

CH_MW = [(
    '    ModuleDescriptor("fond", "FOND", "SYSTÈME"),\n)\n',
    '    ModuleDescriptor("fond", "FOND", "SYSTÈME"),\n'
    '    ModuleDescriptor("performance", "PERFORMANCE", "TRADING"),\n)\n')]

CH_IN = [(
    '                          "abonnes": signaux.ouvrir_abonnements})\n',
    '                          "abonnes": signaux.ouvrir_abonnements})\n'
    '            if hasattr(signaux, "ouvrir_performance"):\n'
    '                table["performance"] = signaux.ouvrir_performance\n')]

METHODE = '''    def _performance(self) -> PreviewData:
        """Trades REELS termines (trades_bot.csv) : R cumule, taux de reussite, 7 derniers jours, creux maximal."""
        def nombre(x: Any) -> float | None:
            try:
                return float(str(x).replace(",", ".").strip())
            except (TypeError, ValueError):
                return None

        lignes: list[tuple[date, float, float]] = []
        try:
            with open(self._trading / "trades_bot.csv", newline="", encoding="utf-8-sig") as f:
                for l in csv.DictReader(f, delimiter=";"):
                    if (l.get("resultat") or "").strip() in ("", "ouvert"):
                        continue
                    jour = _date(l.get("date"))
                    r = nombre(l.get("R"))
                    if jour is None or r is None:
                        continue
                    lignes.append((jour, r, nombre(l.get("gain_devise")) or 0.0))
        except OSError:
            return PreviewData("PERFORMANCE", ("Fichier des trades introuvable",))
        if not lignes:
            return PreviewData("PERFORMANCE", ("Aucun trade termine",))
        total = sum(r for _, r, _ in lignes)
        gagnes = sum(1 for _, r, _ in lignes if r > 0)
        cumul = sommet = creux = 0.0
        for _, r, _ in lignes:
            cumul += r
            sommet = max(sommet, cumul)
            creux = max(creux, sommet - cumul)
        limite = date.today() - timedelta(days=7)
        sept = sum(r for j, r, _ in lignes if j > limite)
        euros = sum(g for _, _, g in lignes)
        detail = (f"Gain cumule : {_euros(euros)}", f"Creux maximal : {creux:+.1f} R".replace("+", "-"),
                  "Page complete : clic sur PERFORMANCE")
        return PreviewData("PERFORMANCE", (f"{total:+.1f} R depuis le debut · {len(lignes)} trades",
                                           f"Reussite : {100 * gagnes / len(lignes):.0f} %",
                                           f"7 derniers jours : {sept:+.1f} R"), detail, alerte=total < 0)

'''
ANCRE_M = "    # ---------------------------------------------------------------- sources\n    def _bot(self) -> PreviewData:\n"
CH_PV = [
    ('"planning": self._planning, "agenda": self._agenda,\n        }',
     '"planning": self._planning, "agenda": self._agenda,\n            "performance": self._performance,\n        }'),
    (ANCRE_M, "    # ---------------------------------------------------------------- sources\n" + METHODE
     + "    def _bot(self) -> PreviewData:\n"),
]


def lire(f):
    brut = f.read_bytes()
    return (brut.decode("utf-8-sig").replace("\r\n", "\n"), brut.startswith(b"\xef\xbb\xbf"),
            brut.count(b"\r\n") > brut.count(b"\n") / 2)


def main():
    jeu = ((F_MW, 'ModuleDescriptor("performance"', CH_MW), (F_IN, 'table["performance"]', CH_IN),
           (F_PV, "def _performance", CH_PV))
    for f, _, _ in jeu:
        if not f.exists():
            print(f"{f} introuvable : lance ce script depuis le dossier gimaly.")
            return 1
    ecritures = []
    for f, marque, changements in jeu:
        txt, bom, crlf = lire(f)
        if marque in txt:
            print(f"{f.name} : deja corrige (rien a faire).")
            continue
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
    for f, txt, bom, crlf in ecritures:
        shutil.copy2(f, f.with_name(f.name + ".avant_perf2"))
        sortie = txt.replace("\n", "\r\n") if crlf else txt
        f.write_bytes((b"\xef\xbb\xbf" if bom else b"") + sortie.encode("utf-8"))
        print(f"{f.name} : corrige (sauvegarde {f.name}.avant_perf2).")
    if ecritures:
        print("Redemarre GIMALY (fenetre principale).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
