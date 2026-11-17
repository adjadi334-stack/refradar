<p align="center">
  <img src="assets/logo.svg" alt="RefRadar" width="300">
</p>

<h1 align="center">RefRadar — le détecteur de références hallucinées par l'IA</h1>

<p align="center">
  <em>ChatGPT, Claude, Gemini et consorts inventent des références.<br/>
  RefRadar les démasque avant qu'elles ne t'embarrassent.</em>
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>Français</strong>
</p>

---

## Le problème que tu connais déjà

Demande une bibliographie à un LLM : tu obtiendras des articles d'apparence plausible qui
n'existent pas — des DOI réalistes qui ne pointent vers rien, des identifiants arXiv sortis
d'un univers parallèle, des URLs en 404, des ISBN dont la somme de contrôle est fausse.
Si tu publies, rends ou cites un travail assisté par IA, **tu** es responsable de chaque
référence qu'il contient — et vérifier à la main 40 citations sur Crossref, arXiv, NCBI et
Open Library, c'est un après-midi misérable.

Les solutions existantes sont des plateformes de fact-checking commerciales ou des scripts
académiques bricolés. Il n'existait pas de petit outil open source, gratuit, local, qui lit
un document et te dit simplement : *« ces 5 références sont fausses ou mortes, voici la preuve. »*

C'est ça, RefRadar.

## Ce que ça fait

| | |
|---|---|
| **Extrait** | URLs, DOI, identifiants arXiv, identifiants PubMed, ISBN (texte brut, liens Markdown, stdin) |
| **Vérifie** | Le DOI existe-t-il chez Crossref ? L'article est-il sur arXiv ? Le PMID dans PubMed ? L'ISBN est-il valide *et* enregistré ? L'URL répond-elle ? |
| **Compare les titres** | Confronte le titre annoncé par l'IA (texte du lien Markdown) au titre réellement enregistré — attrape le « bon identifiant, mauvais article » |
| **Note** | Un **Trust Score** /100 avec un verdict par référence : `Verified · Exists · Weak match · Mismatch · Not found · Dead link · Invalid ISBN · Unreachable` |
| **Rapporte** | Affichage terminal lisible, codes de sortie compatibles CI (`--fail-under`), JSON pour les scripts, rapport HTML autonome hors-ligne |
| **Interfaces** | CLI (`refradar check`) **et** app web locale (`refradar web`) — même moteur, zéro dépendance |

Uniquement la bibliothèque standard Python. `pip install .` et c'est parti. Ni clés API,
ni comptes, ni télémétrie, ni cloud.

## Démo

```console
$ python -m refradar demo

RefRadar scan of demo/example-ai-output.md
============================================================
[OK]   L3     ARXIV 1706.03762 — “Attention Is All You Need”
        → Found on arXiv
[MISS] L4     ARXIV 9999.99999 — “A later replication”
        → No arXiv paper with this identifier
[OK?]  L7     DOI   10.1038/nature14539
        → DOI resolved via Crossref — Deep learning
[MISS] L8     DOI   10.1234/refradar.fake.9.9.9
        → DOI not registered at Crossref
[DEAD] L12    URL   https://example.com/definitely-not-a-real-study-refradar
        → HTTP 404
[BAD ] L16    ISBN  9782070000000
        → ISBN checksum is invalid — cannot exist as printed
------------------------------------------------------------
Trust score: 43/100 — Mixed — review the flagged references
```

## Installation

Python ≥ 3.10 requis. Zéro dépendance d'exécution.

```bash
git clone https://github.com/adjadi334-stack/refradar.git   # ou dézippe l'archive
cd refradar
pip install .            # installe la commande `refradar`
```

Sans pip, directement depuis les sources :

```bash
PYTHONPATH=src python -m refradar demo
```

## Utilisation

### En ligne de commande

```bash
refradar check rapport.md                    # scanne un fichier
refradar check ch1.md ch2.md                 # plusieurs fichiers
cat reponse.txt | refradar check             # stdin (parfait en pipe)
refradar check --text "DOI 10.1038/nature14539"
refradar check rapport.md --html rapport.html  # + rapport HTML autonome
refradar check rapport.md --json               # pour les scripts
refradar check rapport.md --no-net             # extraction seule, aucun appel réseau
refradar check rapport.md --fail-under 80      # sortie 1 si score < 80 → gate CI
```

Codes de sortie : `0` ok · `1` sous le seuil `--fail-under` · `3` rien à scanner.

### App web locale

```bash
refradar web            # http://127.0.0.1:8787
```

Tu colles ton texte → **Verify references** → verdicts, Trust Score et rapport HTML
téléchargeable. Tout se passe sur ta machine ; seuls partent les appels de vérification
(Crossref / arXiv / NCBI / Open Library / les sites que tu cites).

### En intégration continue

```yaml
- run: refradar check docs/**/*.md --fail-under 80
```

### Validation d'ISBN hors-ligne

Même sans réseau, RefRadar valide les sommes de contrôle ISBN-10/13 localement et signale
instantanément les identifiants structurellement impossibles.

## Fonctionnement

1. **Extraction** — passe regex + conscience du Markdown (hors-ligne).
2. **Classification & déduplication** — `https://doi.org/10.1038/x`, `10.1038/x` et `doi:10.1038/x` fusionnent en une seule référence DOI canonique. Numéros de ligne et contexte conservés.
3. **Vérification** — chaque référence est interrogée auprès de son registre de référence :
   Crossref (DOI) · API arXiv · NCBI E-utilities (PMID) · Open Library (ISBN) · requête HTTP (URLs).
4. **Similarité de titres** — quand la citation donne un titre supposé (texte du lien), il est comparé
   au titre enregistré (Jaccard + taux de recouvrement) : `≥ 0,45` Verified · `0,22–0,45` Weak match · `< 0,22` Mismatch.
5. **Score** — `verified=100 · exists=85 · partial=55 · mismatch=15 · dead/not_found/invalid=0` ;
   les références injoignables (réseau) sont exclues de la moyenne, jamais comptées comme fausses.

## Limites — à lire avant de t'y fier

- RefRadar **signale la suspicion ; il ne prouve pas la vérité.** Un vrai article peut soutenir une affirmation fausse.
- Le contrôle d'URL dit que la page *a répondu*, pas qu'elle correspond à ce que l'IA en dit — privilégie les DOI/PMID.
- Le matching de titres est heuristique (langue, sous-titres, translittération). Un `Weak match` = « regarde de plus près », pas un verdict.
- Couverture : les DOI hors Crossref peuvent remonter comme injoignables ; les ISBN dépendent d'Open Library.
- Limites de débit : les gros scans de DOI puisent dans le pool public de Crossref ; utilise `--timeout` et relance si besoin.

## Feuille de route

- [ ] DataCite + OpenAlex en registres DOI
- [ ] Ancrage des citations textuelles (le passage cité est-il vraiment dans la source ?)
- [ ] Export BibTeX/EndNote des références vérifiées
- [ ] Extension navigateur
- [ ] `--format sarif` pour GitHub code scanning
- [ ] Citations juridiques françaises (Légifrance / EUR-Lex)

## Publier ce dépôt sur GitHub

```bash
cd refradar
git init && git add . && git commit -m "RefRadar 1.0.0"
gh repo create refradar --public --source=. --push   # GitHub CLI
# …ou crée un dépôt vide sur github.com, puis :
git remote add origin git@github.com:adjadi334-stack/refradar.git
git branch -M main && git push -u origin main
```

Avant de pousser : vérifie que `pyproject.toml` et les README pointent vers ton compte GitHub,
et remplace `assets/logo.svg` si tu veux ta propre identité visuelle.

## Contribuer & licence

PR bienvenues — voir [CONTRIBUTING.md](CONTRIBUTING.md). Licence MIT ; voir [LICENSE](LICENSE).

*RefRadar est un détecteur de fumée, pas le chef des pompiers.*
