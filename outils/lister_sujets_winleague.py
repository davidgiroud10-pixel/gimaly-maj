# -*- coding: utf-8 -*-
"""Liste les sujets de la winleague (pseudo et numero) qui ne sont PAS encore dans ton classement par canal.

A lancer sur TON PC, depuis le dossier gimaly, GIMALY FERME (lecture seule : rien n'est modifie) :
  .\\.venv\\Scripts\\python.exe lister_sujets_winleague.py            les sujets absents du classement
  .\\.venv\\Scripts\\python.exe lister_sujets_winleague.py --tout      tous les sujets, y compris ceux deja presents

Contrairement a la fonction de GIMALY (qui se rabat sur les 3000 derniers messages si la requete echoue),
ce script lit la liste des sujets PAGE PAR PAGE ; s'il doit se rabattre sur l'historique, il le lit en entier
(plus long) et le dit.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def lire(config, canal="WINLEAGUE"):
    from gimaly.bridges import telegram_lecture as tl

    @tl.exclusif
    def sujets_complets(config, canal):
        client = tl._client(config)
        try:
            correspondances = getattr(config, "signal_channels", None) or {}
            _, valeur = tl.resoudre_alias(correspondances, canal)
            cible, _ = tl._decoder_cible(valeur if valeur else canal)
            entite = tl._trouver_canal(client, cible)
            sujets, erreur = {}, None
            try:
                from telethon.tl.functions.channels import GetForumTopicsRequest
                offset_date, offset_id, offset_topic = 0, 0, 0
                for _ in range(50):
                    reponse = client(GetForumTopicsRequest(
                        channel=entite, offset_date=offset_date, offset_id=offset_id,
                        offset_topic=offset_topic, limit=100))
                    page = list(getattr(reponse, "topics", []))
                    nouveaux = 0
                    for s in page:
                        if getattr(s, "id", None) not in sujets and getattr(s, "title", None):
                            sujets[s.id] = s.title
                            nouveaux += 1
                    if len(page) < 100 or not nouveaux:
                        break
                    dernier = page[-1]
                    offset_topic = dernier.id
                    offset_id = getattr(dernier, "top_message", 0) or 0
                    offset_date = getattr(dernier, "date", 0) or 0
            except Exception as exc:  # noqa: BLE001
                erreur = repr(exc)
            methode = "requete des sujets"
            if erreur or not sujets:
                methode = "historique complet (long)"
                for message in client.iter_messages(entite, limit=None):
                    action = getattr(message, "action", None)
                    titre = getattr(action, "title", None)
                    if titre and type(action).__name__.startswith("MessageActionTopic"):
                        sujets.setdefault(message.id, titre)
            return cible, sujets, methode, erreur
        finally:
            tl._liberer(client)

    return sujets_complets(config, canal)


def main():
    tout = "--tout" in sys.argv
    try:
        from gimaly.config import Config
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Lance ce script depuis le dossier gimaly ({exc!r})")
    config = Config.load()
    present = set()
    for valeur in (getattr(config, "signal_channels", None) or {}).values():
        m = re.search(r"#(\d+)\s*$", str(valeur))
        if m:
            present.add(m.group(1))
    try:
        cible, sujets, methode, erreur = lire(config)
    except Exception as exc:  # noqa: BLE001
        texte = repr(exc)
        if "database is locked" in texte.lower():
            sys.exit("La session Telegram est utilisee par GIMALY (base verrouillee) : ferme GIMALY "
                     f"completement puis relance cette commande.\nErreur : {texte}")
        sys.exit(f"Lecture des sujets impossible : {texte}")
    if erreur:
        print(f"(la requete des sujets a echoue : {erreur})")
    print(f"{len(sujets)} sujet(s) trouves dans {cible} par {methode} ; {len(present)} deja dans ton classement.\n")
    montres = 0
    for numero, titre in sorted(sujets.items(), key=lambda x: str(x[1]).lower()):
        connu = str(numero) in present
        if connu and not tout:
            continue
        montres += 1
        print(("  [deja] " if connu else "  ") + f"{titre}  ->  {cible}#{numero}")
    if not montres:
        print("Tous les sujets sont deja dans ton classement.")


if __name__ == "__main__":
    main()
