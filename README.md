# Building Authority: Citation as a Strategy of Public Intellectual Legitimation in Italian Women's Conferences, 1870–1936

Code, prompts, annotation guidelines and data for the short paper *Building Authority: Citation as a Strategy of Public Intellectual Legitimation in Italian Women’s Conferences, 1870–1936* (Computational Humanities Research 2027).

- **Code, data and annotations:** this repository, https://github.com/DaniV1t/chr2027-women-citations
- **Paper:** forthcoming in the proceedings of CHR 2027 (the reference will be added after publication)

## Overview

We find the persons named in a corpus of lectures by Italian women and link them to Wikidata. We then assign each person a gender and classify how the person is used in each paragraph: cited, mentioned or subject of the passage. Finally, we estimate the share of women in each role, corrected for the classifier's errors.

**All numbers in the paper come from corpus version 23** (319 texts). The analyses exclude texts 10b and 372.

## Repository layout

```
README.md
LICENSE                        MIT (code)
pipeline/
  ner_corpus.py                named-entity recognition
  filtri_pilota.py             NER filters from the pilot study, read by ner_corpus.py
  link_wikidata.py             candidate links to Wikidata
  genere_dai_nomi.py           gender from titles and first names, plus manual gender
  classifica_mistral_v2.py     classification with Mistral (contains the prompts)
  valuta.py                    agreement with the main gold standard
  valuta_gold_donne.py         precision and recall on citations of women
  stima_combinata.py           share of women per role, corrected for classifier error
  analizza.py                  all other statistics, with bootstrap by lecture
annotation/
  annotation_guidelines.md     annotation guidelines, version 3.1
data/                          data and annotations (CC BY 4.0, see data/LICENSE)
```

The repository contains the code of the methodological steps (NER, linking, classification) and the code that produces the numbers in the paper. Intermediate steps such as the filtering of links, the manual verification and the sampling are described below, and their outputs are in `data/`.

## Requirements

| Component | Version |
|---|---|
| Python | 3.14.7 |
| spaCy | 3.8.13 |
| spaCy model | `it_core_news_lg` 3.8.0 |
| Classifier | `mistral-large-2512`, temperature 0, top_p 1 (queried 12 November 2026) |
| OCR | `mistral-ocr-latest` |
| Other packages | pandas, numpy, openpyxl, requests, scikit-learn, gender-guesser |

```bash
pip install spacy==3.8.13 pandas numpy openpyxl requests scikit-learn gender-guesser
python -m spacy download it_core_news_lg-3.8.0 --direct
```

The Mistral API key is read from the environment variable `MISTRAL_API_KEY` and is never stored in the code. For Wikidata queries, set `WIKIDATA_CONTACT` to your e-mail address: Wikimedia asks for a contact in the User-Agent.

## Data

The folder `data/` contains:

- **Corpus metadata:** `metadati.tsv`, `correzioni_ocr.tsv`
- **Units of analysis:** `unita.csv` (all person × paragraph units, with the text of each paragraph), `unita_campione_v3.csv` (the units sent to the classifier, with the Wikidata hint given in the prompt)
- **Mentions and entities:** `menzioni_finali_v5.csv` (all mentions, with Wikidata link, gender and a `finzione` flag for fictional characters), `entita_verificate.csv` (the verified links of the most frequent name groups), `verifica_wikidata.xlsx` (the manual verification sheet, with the author's corrections in the column *conferma*)
- **Sample and predictions:** `campione_casuale_ids.csv` (the 3,499 units of the random sample), `predizioni_v3.jsonl` (raw output of Mistral, prompt v3), `predizioni_v3_finzione.jsonl` (labels used in the paper: Mistral's, with the author's labels for the 183 units with fictional characters), `campione_classificato.csv` (the 3,465 analysed units with labels, gender and Wikidata link)
- **Gold standards and manual annotations:** `gold_annotato_v23_r3.xlsx` (main gold standard, 201 units), `gold_donne_annotato.xlsx` (women-only gold standard, 110 units, 102 valid), `finzione_annotato.xlsx` (fictional characters, 183 units), `genere_manuale.xlsx` (manual gender)

File, script and column names are in Italian, as in the original project. Main terms: *menzioni* = mentions, *unità* = units, *campione* = sample, *predizioni* = predictions, *finzione* = fiction, *genere* = gender, *verifica* = verification, *correzioni* = corrections, *metadati* = metadata, *donne* = women, *annotato* = annotated, *conferenza* = lecture, *autrice* = author (speaker), *paragrafo* = paragraph, *forma* = surface form.

The lectures are in the public domain. The full texts will be deposited at a later stage; the files in `data/` already contain the text of the paragraphs they refer to.

## Method and reproduction

### 1. Named-entity recognition

```bash
python pipeline/ner_corpus.py CORPUS_FOLDER menzioni.csv
```

`CORPUS_FOLDER` contains `testo/`, `paratesto/` and `metadati.tsv`. The script applies `it_core_news_lg` with the filters of the pilot study, read unchanged from `filtri_pilota.py` (keep the two files in the same folder). Appendices are excluded. Result on corpus v23: 21,008 person mentions in 314 texts (6,845 distinct forms).

### 2. Linking to Wikidata

```bash
python pipeline/link_wikidata.py menzioni.csv
```

Only human beings (P31 = Q5) born before the lecture are accepted. The 419 name groups found in at least five lectures (48% of mentions) were verified by hand (`verifica_wikidata.xlsx`, results in `entita_verificate.csv`). The other links were filtered automatically: we dropped links found only by full-text search, links without a birth date or born less than ten years before the lecture, a lone first name linked to a person with that first name, mismatching surnames, and female titles linked to a man. Result: 53.6% of mentions linked, 1,922 persons. Wikidata changes over time, so a new query will not return exactly the same candidates; the verified links are in `menzioni_finali_v5.csv`.

### 3. Gender

```bash
python pipeline/genere_dai_nomi.py MENTIONS_LINKED.csv menzioni_finali_v5.csv --manuale data/genere_manuale.xlsx
```

Gender comes from Wikidata for linked persons. For the others, it comes from titles (*contessa*, *madame*, *suor*) and Italian first names; on linked names this rule agrees with Wikidata in 98.3% of cases. The remaining 292 names of the classified sample were assigned by hand (`genere_manuale.xlsx`). Fictional and mythological characters keep their gender and are flagged `finzione`.

### 4. Units, sample and gold standards

A unit is one person in one paragraph: 18,541 units. We classified a stratified random sample of 3,499 units (19%, seed 2027; `campione_casuale_ids.csv`). There are three gold standards:
- **main:** 201 units;
- **women-only:** 110 units, stratified by the classifier's label and reweighted to the sample;
- **fictional characters:** all 183 units with a fictional character, annotated by hand.

### 5. Classification with Mistral

```bash
python pipeline/classifica_mistral_v2.py data/unita_campione_v3.csv predizioni_v3.jsonl --prompt v3 \
    --model mistral-large-2512 --workers 3 --pause 2
```

The prompts v1, v2 and v3 are in the script; the paper uses **v3**, which was tuned on the main gold standard. Labels: level 1 (CITAZIONE, MENZIONE, SOGGETTO, ERRORE) and level 2 (GENEALOGIA, CONTESTAZIONE, ALLINEAMENTO, APPROPRIAZIONE, ALTRO). Prompt v3 still labels fictional characters as ERRORE, so for the 183 units with fictional characters the hand labels replace the model's (`predizioni_v3_finzione.jsonl`). Even at temperature 0, a hosted model may not return identical outputs on a new run: to reproduce the paper, use the deposited predictions.

### 6. Evaluation and corrected share of women

```bash
python pipeline/valuta.py data/gold_annotato_v23_r3.xlsx data/predizioni_v3.jsonl \
    --escludi-unita data/finzione_annotato.xlsx
python pipeline/valuta_gold_donne.py --gold-donne data/gold_donne_annotato.xlsx \
    --gold data/gold_annotato_v23_r3.xlsx --predizioni data/predizioni_v3.jsonl \
    --unita data/unita.csv --menzioni data/menzioni_finali_v5.csv \
    --campione-classificato data/campione_classificato.csv
python pipeline/stima_combinata.py --gold-donne data/gold_donne_annotato.xlsx \
    --gold data/gold_annotato_v23_r3.xlsx --predizioni data/predizioni_v3.jsonl \
    --unita data/unita.csv --menzioni data/menzioni_finali_v5.csv \
    --campione-classificato data/campione_classificato.csv \
    --finzione data/finzione_annotato.xlsx --campione data/campione_casuale_ids.csv
```

These three scripts measure the classifier, so they read Mistral's raw output (`predizioni_v3.jsonl`); `valuta.py` leaves out the units with fictional characters, which were annotated by hand. `analizza.py` uses the final labels (`predizioni_v3_finzione.jsonl`). `valuta_gold_donne.py` and `stima_combinata.py` must stay in the same folder as `analizza.py`, whose functions they use. Agreement with the main gold standard on the 186 units with real persons is 65.1% (κ = 0.53). The classifier finds only 22% of the citations of women (weighted recall). `stima_combinata.py` combines the confusion matrices of the two gold standards to correct the share of women in each role: 13.7% of cited persons, 22.4% of mentioned persons and 31.1% of subjects.

### 7. Statistics

```bash
python pipeline/analizza.py --menzioni data/menzioni_finali_v5.csv --unita data/unita.csv \
    --predizioni data/predizioni_v3_finzione.jsonl --gold data/gold_annotato_v23_r3.xlsx \
    --metadati data/metadati.tsv --campione data/campione_casuale_ids.csv --out risultati
```

Writes `risultati/risultati.md` and `campione_classificato.csv`. Persons are identified by their Wikidata QID. Confidence intervals come from a bootstrap that resamples whole lectures (2,000 replicates, seed 2027).

## Annotation guidelines

The guidelines are in `annotation/annotation_guidelines.md` (version 3.1).

The main gold standard was annotated with version 1 of the guidelines and revised according to version 2; its 15 fictional characters were re-annotated with version 3. The women-only gold standard follows version 2 with the version-3 rule for fictional characters; the fictional-character set follows version 3.1. The Mistral prompt v3 still treats fictional characters as ERRORE, so all fictional characters were annotated by hand and the author's labels replace the model's.

## Licences

- **Code:** MIT (see `LICENSE`)
- **Data, annotations and guidelines:** CC BY 4.0 (see `data/LICENSE`)

## Citation

If you use this code or these data, please cite the paper (full reference to be added after publication) and this repository: https://github.com/DaniV1t/chr2027-women-citations, release v1.0.
