# -*- coding: utf-8 -*-
"""Le lanceur des amis cherche une mise a jour toutes les 30 min au lieu de 6 h (une publication « immediat » arrive vite).
Dossier gimaly :  .\\.venv\\Scripts\\python.exe patch_maj_30min.py   puis publier_maj.py. Sauvegarde *.avant_30min. Idempotent."""
import shutil
import sys
from pathlib import Path

F = Path.cwd() / "outils_v7" / "lancer.py"
ANCIEN = 'PERIODE_MAJ = float(os.environ.get("GIMALY_MAJ_PERIODE") or 6 * 3600)    # secondes entre deux verifications'
NOUVEAU = 'PERIODE_MAJ = float(os.environ.get("GIMALY_MAJ_PERIODE") or 30 * 60)    # secondes entre deux verifications'
ENTETE = "toutes les 6 h"


def main():
    if not F.exists():
        raise SystemExit(f"{F} introuvable : lance ce script depuis le dossier gimaly")
    brut = F.read_bytes()
    bom, crlf = brut.startswith(b"\xef\xbb\xbf"), b"\r\n" in brut
    t = brut.decode("utf-8-sig").replace("\r\n", "\n")
    if NOUVEAU in t:
        print("outils_v7/lancer.py : deja a jour")
        return 0
    if t.count(ANCIEN) != 1:
        raise SystemExit("repere PERIODE_MAJ introuvable : RIEN ecrit. Envoie-moi outils_v7/lancer.py")
    t = t.replace(ANCIEN, NOUVEAU).replace(ENTETE, "toutes les 30 min")
    compile(t, "lancer.py", "exec")
    copie = F.with_name(F.name + ".avant_30min")
    if not copie.exists():
        shutil.copy2(F, copie)
    F.write_bytes((b"\xef\xbb\xbf" if bom else b"") + (t.replace("\n", "\r\n") if crlf else t).encode("utf-8"))
    print("outils_v7/lancer.py : corrige (sauvegarde lancer.py.avant_30min). Prochaine etape : publier_maj.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
