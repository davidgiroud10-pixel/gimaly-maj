# -*- coding: utf-8 -*-
r"""Editeur : envoie a tes amis l'ordre SIGNE « mets-toi a jour maintenant ».

Usage (dossier gimaly) :  .\.venv\Scripts\python.exe forcer_maj.py
Publie d'abord ta mise a jour (publier_maj.py + zip et version.json sur GitHub), PUIS lance ce script. Le lanceur de chaque ami
qui a la version 7.15 ou plus cherche alors la mise a jour tout de suite, au lieu d'attendre jusqu'a 30 min, et l'installe des
qu'aucun trade n'est ouvert (au plus tard apres 4 h). L'ordre passe par un canal PRIVE a part, signe avec ta cle privee : un
ordre non signe est ignore. Les amis dont le lanceur est ferme ou le PC eteint ne le recoivent pas (ils se mettront a jour
a leur prochain contrôle ou demarrage). Rien n'est modifie chez toi."""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
from gimaly.trading import signaux_distants as sd  # noqa: E402


def secret_commun():
    try:
        texte = (RACINE / "config.local.yaml").read_text(encoding="utf-8-sig")
    except OSError:
        return None
    m = re.search(r"(?m)^trading_signaux_secret:[ \t]*['\"]?([^\s'\"#]+)", texte)
    return m.group(1) if m else None


def main():
    if sd._lire_cle_privee() is None:
        print("Cle de signature introuvable (cle_signature.priv) : impossible de signer l'ordre. Rien n'est envoye.")
        return 1
    amis, ancien = sd.lire_amis()
    cibles = {f"ami {nom}": a["secret"] for nom, a in amis.items()}
    commun = secret_commun()
    if (ancien or not amis) and commun:
        cibles["canal commun (amis pas encore migres)"] = commun
    if not cibles:
        print("Aucun ami actif dans amis.json : rien a envoyer.")
        return 1
    echecs = 0
    for nom, secret in cibles.items():
        ok, msg = sd.publier({"cmd": "maj"}, sd.canal_commande(secret), secret)
        print(f"{'envoye' if ok else 'ECHEC '} : {nom} ({msg})")
        echecs += 0 if ok else 1
    print("L'ordre est valable 90 secondes : les lanceurs ouverts le recoivent tout de suite." if not echecs
          else "Certains envois ont echoue : relance dans un instant.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
