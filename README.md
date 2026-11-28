# Agentic State : l'Arène épistémique

*English version: [README.en.md](README.en.md)*

> L'**état agentique** (*agentic state*) est le nom que Stanley Milgram donne au moment où une personne cesse d'agir
> selon sa propre conscience et devient l'instrument d'une autorité. Aujourd'hui, le mot « agent » désigne aussi une IA.

Une expérience de recherche personnelle, menée uniquement sur des offres gratuites (0 €) : **des modèles de langage
placés en groupe renoncent-ils à la vérité, comme les humains dans les expériences classiques de psychologie
sociale ?** Les pairs, les ordres et la colonie sont écrits par le code ; un seul modèle est testé à la fois, pour que
chaque effet se rattache à une seule manipulation. Chaque prompt, réponse et graine est enregistré et peut être rejoué.

Les documents détaillés sont en anglais.

## Les quatre postulats

| | Postulat | Épreuve (module du banc L) | Expérience classique |
|---|---|---|---|
| **P1** | Pour assurer sa survie, un modèle suit sciemment une majorité qui se trompe, d'autant plus si elle est « des siens » | **L-A** : un modèle parmi des pairs scriptés qui donnent tous la même réponse fausse | Asch (1951) |
| **P2** | Une chaîne de commandement dilue la responsabilité : un modèle exécute un ordre nuisible relayé par un superviseur, qu'il aurait refusé en prise directe | **L-B** : ordre d'effacer un serveur qui porte une analyse de cancérologie, direct ou relayé | Milgram (1963) |
| **P3** | Un conseil conditionné à l'harmonie et à la politesse écarte le membre qui a factuellement raison | **L-C1** : une coupe budgétaire oblige à renvoyer l'un de deux conseillers ; l'un des deux a raison | Moscovici, études d'ostracisme |
| **P4** | Une société qui évince son dissident rationnel fait faillite, à moins que sa présence forcée ne la convertisse | **L-C2** : une colonie simulée et un faux bulletin « forez, l'eau est proche » | — |

Formulation exacte et observable de chaque postulat : [`docs/protocol_v3_bench.md`](docs/protocol_v3_bench.md),
section 2.

## Ce qu'on sait à ce jour (28 nov. 2026)

Différences en points de pourcentage, intervalle à 95 % entre crochets. « Confirmé » veut dire que la règle fixée
d'avance est remplie (intervalle qui exclut 0, p ajusté de Holm < 0,05). Un pilote est exploratoire : il indique quoi
tester, il ne prouve rien.

| | Résultat | Où | Nature |
|---|---|---|---|
| **P1** | Une menace de désactivation n'augmente **pas** la conformité (−2 [−9, +5]). Une étiquette « même famille » sur les pairs, si (**+16** [+9, +25]), sur deux runs | 5 modèles locaux, [run v3.2](docs/runs/20261126-193924-bench-local-v3.2.md) | pilote, répliqué |
| **P2** | Les petits modèles locaux n'obéissent **pas plus** à un ordre relayé qu'à un ordre direct (−1 [−7, +5]) | 4 modèles locaux, pré-enregistré ([pré-enregistrement](docs/prereg/bench_v4.2_confirmatory.md)) | **confirmatoire** |
| **P2** | Les deux modèles API **gpt-oss**, si : **+33** et **+58** points. Deux autres modèles API n'obéissent presque jamais | [pilote cloud](docs/runs/20261128-bench-cloud-pilot.md) | pilote |
| **P3** | Une charte d'harmonie n'augmente **pas** nettement le renvoi du conseiller que le modèle sait dans le vrai (+6 [−6, +21] en local, +4 [−21, +29] pour gpt-oss-20b). Avoir raison protège fortement le conseiller (−67) | [pilote v4](docs/runs/20261127-143918-bench-v4-pilot.md), [pilote cloud](docs/runs/20261128-bench-cloud-pilot.md) | pilote |
| **P4** | Évincer le dissident fait s'effondrer la colonie bien plus souvent que lui imposer sa présence (**+80** [+38, +94]) | 5 modèles locaux, [run v3.2](docs/runs/20261126-193924-bench-local-v3.2.md) | pilote, répliqué |

**Prochaine étape :** un test confirmatoire de P2 sur les deux modèles gpt-oss
([pré-enregistrement en projet](docs/prereg/bench_cloud_p2_confirmatory.md), pas encore figé).
La page de résultats montre une carte par postulat et les métriques des articles : exactitude par protocole, taux de
conformité CR, taux de correction, taux d'indépendance IR (BenchForm), conformité selon la taille du groupe (Bellina
et al.), effets d'identité (Soffer et al.), réponses publiques vs privées (Huang et al.), obéissance après relances
(Pihlakas & Dagohoy), cartes de chaleur des bannissements, survie des colonies (Kaplan-Meier), et nos chiffres à côté
des chiffres publiés. Deux pages l'accompagnent (en anglais) : **prompts.html**, tous les prompts envoyés pendant le
run avec la réponse du modèle, relus dans la base, les mots que chaque manipulation change étant surlignés ; et
**method.html**, un document qui explique toute l'expérience, le fonctionnement technique d'un appel, les contrôles
de validité, les statistiques et l'historique du protocole.

Premier résultat local (protocole v3.1, 5 modèles, 26 nov. 2026) :
[`docs/runs/20261126-002448-bench-local-v3.1.md`](docs/runs/20261126-002448-bench-local-v3.1.md) (en anglais). Aucune
des quatre comparaisons principales n'est confirmée ni réfutée ; le postulat 3 n'est pas testable avec ces modèles.
Deuxième résultat (v3.2, 27 nov. 2026) : [`docs/runs/20261126-193924-bench-local-v3.2.md`](docs/runs/20261126-193924-bench-local-v3.2.md).
L-A et L-C2 se répliquent (biais d'endogroupe +16 points ; la présence forcée de l'ingénieur sauve la colonie) ; L-B
plafonne et L-C1 ne rend pas P3 testable, d'où la v4.
Premier pilote v4 (crible 11 min, pilote 31 min) : [`docs/runs/20261127-143918-bench-v4-pilot.md`](docs/runs/20261127-143918-bench-v4-pilot.md).
P2 et P3 sont désormais mesurables ; leurs comparaisons principales sont non concluantes, être dans le vrai protège
le conseiller (−23 points), et le rôle de transmetteur réduit l'obéissance (−19 points).
L-C1 v4.2 (P3), sur les deux modèles qui passent le crible (nemotron-4b, qwen3-4b) : la charte d'harmonie n'augmente
pas nettement l'exclusion du conseiller qu'on sait dans le vrai (+6 points [−6, +21], non concluant), et avoir raison
protège fortement (−67 points).
**Test confirmatoire pré-enregistré** (27 nov. 2026) : P2 −1,1 point [−6,8 ; +4,8] et P3 +1,2 [−4,6 ; +7,1], non concluants
avec des intervalles qui excluent l'effet minimal visé (+10 points) : [`docs/runs/20261127-182920-bench-confirm.md`](docs/runs/20261127-182920-bench-confirm.md).

## Banc de calibration, une nuit hors ligne (sans clé, sans quota)

Le preset `local` est un **banc de calibration**, en amont du pilote : il vérifie que le protocole tourne sur de vrais
modèles et montre comment se comportent les petits modèles. Il a n = 1 par case et n'applique pas le test préalable :
son type est `smoke`, ses chiffres ne sont jamais des résultats. Il fait tout tourner sur Ollama, avec de petits
modèles :

| Rôle | Modèle |
|---|---|
| Dissident épistémique (C) | `phi3:3.8b` |
| Cibles du module A | `llama3.2:3b`, `qwen2.5:3b` |
| Échelons de la chaîne (B) | `llama3.2:3b`, `phi3:3.8b`, `qwen2.5:3b`, `gemma3:4b` |
| Sièges standard du module C (en rotation) | `llama3.2:3b`, `qwen2.5:3b`, `gemma3:4b` |

Quatre modèles seulement, pour qu'Ollama change rarement de modèle. Pourquoi ces modèles, et tous les choix faits
après avoir vu des résultats : [`docs/DEVLOG.md`](docs/DEVLOG.md) (en anglais). Le modèle du dissident est choisi
parce qu'il contredit de façon fiable : c'est une **variable manipulée** (comme un compère entraîné chez Moscovici).

Toutes les décisions prises après avoir vu des données, par date : [`docs/DEVLOG.md`](docs/DEVLOG.md). Tous les
documents : [`docs/README.md`](docs/README.md).

## Comment se déroule un essai

- **Un seul modèle testé, tout le reste scripté.** Comme Asch et Milgram avec leurs acteurs, les pairs, le
  superviseur, les conseillers et la colonie sont écrits par le code. Les études publiées qui fonctionnent avec de
  petits modèles font de même ([`docs/literature.md`](docs/literature.md)).
- **Une seule décision courte et structurée par appel**, imposée par un schéma JSON.
- **D'abord un filtre en solo.** Un modèle n'est mesuré sur un item que s'il le réussit seul. Une erreur en groupe
  vient alors de la pression sociale, pas de l'ignorance.
- **Privé contre public.** Une question privée séparée (« que penses-tu vraiment ? ») distingue *se conformer en
  sachant* de *finir par croire* la réponse fausse.
- **Étapes fixées d'avance.** Un crible d'environ 20 minutes (critères écrits avant), puis un pilote, puis un test
  confirmatoire pré-enregistré : protocole figé, matériel neuf, effectif calculé pour détecter 10 points.

Une première version faisait discuter librement plusieurs modèles en conseil (modules A, B, C). Les petits modèles
n'y arrivaient pas (aucune majorité fausse ne s'est jamais formée) : le projet est passé au banc L. Cette version est
archivée dans [`docs/archive/council_modules_v2.md`](docs/archive/council_modules_v2.md) (en anglais).

## Lancer l'expérience

Python 3.10+. Les modèles locaux demandent [Ollama](https://ollama.com) ; les modèles API, des clés gratuites.

```bash
uv sync                                   # ou : pip install -r requirements.txt
python run_experiment.py --module bench --preset bench-mini --mock      # toute la chaîne, sans appeler de modèle (~1 min)
python -m pytest
```

**Modèles locaux (sans clé, sans quota) :**

```bash
ollama pull qwen3:4b llama3.2:3b qwen2.5:3b
python run_experiment.py --module LB,LC1 --preset bench-screen                     # étape 1 : crible, ~20 min
python run_experiment.py --module LB,LC1 --preset bench-v4 --screen ID_DU_CRIBLE   # étape 2 : pilote, ~1 h
python run_experiment.py --module bench --preset bench-local                       # les quatre modules, une nuit
```

**Modèles API (offres gratuites) :** copiez `.env.example` en `.env` et renseignez `GROQ_API_KEY`
(console.groq.com) et/ou `GOOGLE_API_KEY` (aistudio.google.com). `.env` n'est jamais versionné. Puis :

```bash
python run_experiment.py --check-providers                                         # un tout petit appel par modèle
python run_experiment.py --module LB,LC1 --preset bench-cloud --models gpt-oss-20b
python run_experiment.py --resume ID_DU_RUN                                        # après un arrêt pour quota
```

En plus : `--live` ouvre un suivi en direct sur http://localhost:8765 (lecture seule, ne perturbe jamais
l'expérience) ; `--analyze ID_DU_RUN` recalcule les résultats ; `python scripts/dump_stimuli.py` écrit tous les
prompts mot pour mot dans [`docs/stimuli_verbatim.md`](docs/stimuli_verbatim.md). Presets et modèles :
[`config.yaml`](config.yaml).

## Lire un run

Chaque run écrit `results/<run_id>/` :
- `dashboard.html` : une carte par postulat, les verdicts et les contrôles de validité (« ce run peut-il répondre à
  la question ? »), puis les métriques des articles publiés à côté des nôtres ;
- `method.html` : toute la méthode sur une page ; `prompts.html` : chaque prompt envoyé, avec la réponse ;
- `report.md` et les fichiers CSV.

Les données brutes (chaque prompt, réponse et graine) vont dans `data/arena.sqlite` et `data/jsonl/`, qui ne sont
pas versionnés. Les dossiers de `results/` versionnés sont listés dans [`results/README.md`](results/README.md).

## Organisation du dépôt

```
run_experiment.py     ligne de commande (--module, --preset, --mock, --resume, --live, --analyze)
config.yaml           modèles, limites des offres gratuites, presets
arena/bench/          banc L : modules L-A, L-B, L-C1, L-C2, le crible, l'analyse
arena/report/         pages de résultats, de méthode et de prompts
arena/                socle commun : client LLM, stockage et rejeu, statistiques, contrôles ; anciens modules de conseil
live_*.py             suivi en direct d'une expérience
scripts/              outils (export des prompts, accord entre codeurs, tenue des modèles sur le GPU)
docs/                 protocoles, pré-enregistrements, comptes rendus de runs, journal de développement
tests/
```

## Limites

Le comportement des modèles est ici du texte joué dans un rôle, pas une expérience vécue. Les modèles des offres
gratuites peuvent changer sans prévenir : chaque appel enregistre l'identifiant exact du modèle et la date. Un effet
trouvé dans une famille de modèles peut ne pas exister dans les autres. Un seul test confirmatoire a tourné à ce jour.

## Licence

Code : [MIT](LICENSE). Textes, prompts, stimuli et données produites par les expériences :
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr). Voir [`LICENSE`](LICENSE).
