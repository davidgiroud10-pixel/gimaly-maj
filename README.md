# gimaly-maj

Dépôt de mises à jour de GIMALY Trading.

- `version.json` : manifeste de la dernière version, **signé** (signature Ed25519). Un PC qui ne reconnaît pas la signature ignore la mise à jour.
- `maj-7.N.zip` : le contenu de la version N. Son empreinte SHA-256 figure dans le manifeste signé.
- `outils/` : scripts de l'éditeur (génération des clés, du paquet et des mises à jour).

Aucun secret n'est stocké ici : la clé qui signe reste sur le PC de l'éditeur.
