# -*- coding: utf-8 -*-
"""Prepare une MISE A JOUR signee pour les amis (a lancer sur TON PC, depuis le dossier gimaly).

  .\\.venv\\Scripts\\python.exe publier_maj.py --notes "ce qui change" [--quand week-end|demarrage|immediat]

  * regenere le paquet a partir de TON code actuel (creer_installateur_v7.py) ;
  * fabrique  maj-7.N.zip  (sans config.local.yaml, sans cle, sans VERSION.json) et  version.json  SIGNE
    avec ta cle privee (~/GIMALY/trading/cle_signature.priv, qui ne quitte jamais ton PC) ;
  * se controle comme le fera le PC d'un ami (signature, empreinte, chemins, compilation) ;
  * met les deux fichiers dans  C:\\Users\\<toi>\\GIMALY-publication  et ouvre la page GitHub pour les deposer.

Quand : "week-end" (defaut) = installee marche de l'or ferme ou au prochain demarrage ; "demarrage" = au
prochain demarrage du lanceur seulement ; "immediat" = tout de suite, bot redemarre (correctif urgent).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "gimaly" / "trading"))
import maj_auto  # noqa: E402
import sig25519  # noqa: E402

DOSSIER_GIMALY = Path.home() / "GIMALY"
CLE_PRIVEE = DOSSIER_GIMALY / "trading" / "cle_signature.priv"
CLE_PUBLIQUE = DOSSIER_GIMALY / "cle_publique.txt"
ETAT = DOSSIER_GIMALY / "publication_etat.json"
SORTIE = Path.home() / "GIMALY-publication"
DEPOT = "davidgiroud10-pixel/gimaly-maj"
TEMP = "GIMALY-Maj-temp"


def canon(p):
    return json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--notes", default="", help="ce qui change (visible dans le journal des amis)")
    a.add_argument("--quand", default="week-end", choices=["week-end", "demarrage", "immediat"])
    a.add_argument("--sans-ouvrir", action="store_true", help="n'ouvre ni l'Explorateur ni le navigateur")
    a = a.parse_args()

    try:
        graine = bytes.fromhex(CLE_PRIVEE.read_text(encoding="utf-8").strip())
        pub = CLE_PUBLIQUE.read_text(encoding="utf-8-sig").strip()
        assert len(graine) == 32 and sig25519.cle_publique(graine).hex() == pub
    except Exception:
        raise SystemExit("cle de signature introuvable ou incoherente : lance d'abord outils_v7\\installer_v7.py")
    try:
        numero = int(json.loads(ETAT.read_text(encoding="utf-8")).get("numero", 0)) + 1
    except (OSError, ValueError):
        numero = 1
    version = f"7.{numero}"

    print(f"1/4  Regeneration du paquet a partir de ton code actuel (version {version})...")
    r = subprocess.run([sys.executable, str(RACINE / "creer_installateur_v7.py"), "--nom", TEMP, "--ecraser"],
                       cwd=str(RACINE), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit("la generation du paquet a echoue : rien n'est publie")
    paquet = Path.home() / TEMP

    print("2/4  Fabrication de la mise a jour signee...")
    SORTIE.mkdir(exist_ok=True)
    for ancien in SORTIE.glob("*"):
        ancien.unlink()
    nom_zip = f"maj-{version}.zip"
    n = 0
    with zipfile.ZipFile(SORTIE / nom_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(paquet.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(paquet).as_posix()
            if rel.lower() in {j.lower() for j in maj_auto.JAMAIS} or "__pycache__" in rel or rel.startswith(".venv"):
                continue
            if not maj_auto.AUTORISES.match(rel):
                continue
            z.write(f, rel)
            n += 1
    contenu = (SORTIE / nom_zip).read_bytes()
    manifeste = {"numero": numero, "version": version, "fichier": nom_zip, "quand": a.quand,
                 "sha256": hashlib.sha256(contenu).hexdigest(), "notes": a.notes.strip()[:300],
                 "date": time.strftime("%Y-%m-%d %H:%M")}
    enveloppe = {"p": manifeste, "e": sig25519.signer(graine, canon(manifeste).encode("utf-8")).hex()}
    (SORTIE / "version.json").write_text(json.dumps(enveloppe, ensure_ascii=False, indent=1), encoding="utf-8")

    print("3/4  Controle comme le fera un ami...")
    env = json.loads((SORTIE / "version.json").read_text(encoding="utf-8"))
    assert sig25519.verifier_hex(pub, canon(env["p"]).encode("utf-8"), env["e"]), "signature invalide"
    assert hashlib.sha256((SORTIE / nom_zip).read_bytes()).hexdigest() == env["p"]["sha256"]
    with tempfile.TemporaryDirectory() as tmp:
        fichiers = maj_auto._extraire((SORTIE / nom_zip).read_bytes(), Path(tmp))
        for p in Path(tmp).rglob("*.py"):
            compile(p.read_bytes(), str(p), "exec")
    secret = [x for x in (RACINE / "config.local.yaml").read_text(encoding="utf-8").splitlines()
              if x.startswith("trading_signaux_secret:")]
    if secret and secret[0].split(":", 1)[1].strip() in (SORTIE / nom_zip).read_bytes().decode("latin-1", "ignore"):
        raise SystemExit("ALERTE : le secret des signaux est dans la mise a jour : rien n'est publie")
    if graine.hex().encode() in (SORTIE / nom_zip).read_bytes() or b"cle_signature" in (SORTIE / nom_zip).read_bytes():
        raise SystemExit("ALERTE : la cle privee est dans la mise a jour : rien n'est publie")
    print(f"     signature OK ; {len(fichiers)} fichiers ; compilation OK ; aucun secret ni cle privee dedans")

    ETAT.write_text(json.dumps({"numero": numero, "version": version, "date": manifeste["date"]}), encoding="utf-8")
    shutil.rmtree(paquet, ignore_errors=True)
    try:
        (Path.home() / f"{TEMP}.zip").unlink()
    except OSError:
        pass

    print(f"""
4/4  A TOI DE JOUER (2 minutes) :
     Les deux fichiers sont dans :  {SORTIE}
        - {nom_zip}
        - version.json
     1. Ouvre   https://github.com/{DEPOT}/upload/main
     2. Glisse les DEUX fichiers dans la page, puis clique sur le bouton vert "Commit changes".
     Les amis recevront la version {version} ({a.quand}) automatiquement.
""")
    if not a.sans_ouvrir:
        try:
            if sys.platform.startswith("win"):
                import os
                os.startfile(str(SORTIE))  # noqa: S606
            webbrowser.open(f"https://github.com/{DEPOT}/upload/main")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
