"""
Step 1 of the revised pipeline: person-name extraction over the layered corpus.

Differences from the pilot (extraction_authors_complete.py):
- runs paragraph by paragraph on testo/NN_..._clean.txt, so every mention keeps
  its paragraph index (needed for context and citation-function classification);
- also runs on epigraphs and attributions from paratesto/ (citations by definition);
- the speaker is taken from metadati.tsv (exact file id), not from fuzzy title matching;
- the speaker filter removes only names whose surname matches the speaker's
  surname(s): the pilot removed any name sharing ANY token with the speaker
  (e.g. every "Maria ..." in a lecture by Maria Bobba);
- same rule-based filters as the pilot (PROPN, verb/adverb endings, OCR garbage,
  exclusion list, royal titles). They are read UNCHANGED from filtri_pilota.py,
  a copy of the filter block of the pilot script (keep it in the same folder).

Usage:
    python ner_corpus.py CORPUS_FOLDER OUTPUT.csv [PILOT_SCRIPT.py]

    CORPUS_FOLDER  folder with testo/, paratesto/ and metadati.tsv (corpus v23)
    PILOT_SCRIPT   optional: path of the file with the filters. If omitted, the
                   script finds filtri_pilota.py in its own folder.

Output: OUTPUT.csv (one row per mention) and ner_stats.json
"""
import csv
import glob
import json
import os
import re
import sys
from collections import Counter

import spacy

CORPUS = sys.argv[1] if len(sys.argv) > 1 else "corpus"
OUT = sys.argv[2] if len(sys.argv) > 2 else "menzioni.csv"
PILOT = sys.argv[3] if len(sys.argv) > 3 else None

START, END = "NER_EXCLUSIONS = {", "def extract_year(filename)"


def find_pilot():
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (here, os.path.dirname(here), os.getcwd(), os.path.dirname(os.getcwd())):
        for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            try:
                src = open(path, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            if START in src and END in src:
                return path
    sys.exit("Pilot script not found: pass its path as third argument, e.g.\n"
             '  python ner_corpus.py corpus_v23 menzioni_mia.csv "..\\extraction_authors_complete.py"')


PILOT = PILOT or find_pilot()
src = open(PILOT, encoding="utf-8").read()
if START not in src or END not in src:
    sys.exit(f"{PILOT} does not contain the NER filter block ({START!r} ... {END!r})")
filters = {"re": re}
exec(src[src.index(START):src.index(END)], filters)
extract_people, fix_ocr_spacing = filters["extract_people"], filters["fix_ocr_spacing"]
print(f"NER filters read from: {PILOT}")

nlp = spacy.load("it_core_news_lg", disable=["parser", "lemmatizer"])
nlp.max_length = 2_000_000
print(f"spaCy {spacy.__version__}, model it_core_news_lg {nlp.meta.get('version')}")

meta = {}
with open(os.path.join(CORPUS, "metadati.tsv"), encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        meta[row["file"]] = row


def speaker_surnames(autrice):
    toks = [t for t in re.split(r"[\s\-]+", autrice or "") if len(t) > 1 and t[0].isupper()]
    return {t.lower() for t in toks[1:]} if len(toks) > 1 else {t.lower() for t in toks}


def is_speaker(name, surnames):
    last = name.split()[-1].strip(".,;:").lower()
    return last in surnames


units = []  # (file, source, paragraph_idx, text)
for path in sorted(glob.glob(os.path.join(CORPUS, "testo", "*_clean.txt"))):
    file = os.path.basename(path)[: -len("_clean.txt")]
    with open(path, encoding="utf-8") as f:
        lines = [l.strip() for l in f]
    paras = [l for l in lines[1:] if l]
    for i, p in enumerate(paras):
        units.append((file, "testo", i, p))
    pt = os.path.join(CORPUS, "paratesto", f"{file}_paratesto.tsv")
    if os.path.exists(pt):
        with open(pt, encoding="utf-8", newline="") as f:
            for j, row in enumerate(csv.DictReader(f, delimiter="\t")):
                if row["tipo"] in ("epigrafe", "attribuzione"):
                    # names in epigraphs are often in capitals: title-case them for the tagger
                    txt = re.sub(r"\b([A-ZÀ-Ý]{2,})\b", lambda m: m.group(1).title(), row["testo"])
                    units.append((file, row["tipo"], j, txt))

if not units:
    sys.exit(f"No texts found in {os.path.join(CORPUS, 'testo')}: check the corpus folder")
print(f"{len(units)} paragraphs/paratext items in {len(meta)} files; running spaCy (this takes a while)...")

rows, removed_speaker = [], Counter()
texts = (fix_ocr_spacing(u[3]) for u in units)
for n, ((file, source, idx, _), doc) in enumerate(zip(units, nlp.pipe(texts, batch_size=64)), 1):
    if n % 5000 == 0:
        print(f"  {n}/{len(units)}")
    m = meta.get(file)
    if m is None or m.get("lingua", "it") != "it":  # appendices (not in metadata) and non-Italian texts
        continue
    surn = speaker_surnames(m.get("autrice", ""))
    for name in extract_people(doc):
        if surn and is_speaker(name, surn):
            removed_speaker[file] += 1
            continue
        rows.append([m.get("id", file.split("_")[0]), file, m.get("anno", ""), source, idx, name])

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["doc_id", "file", "anno", "fonte", "paragrafo_idx", "forma"])
    w.writerows(rows)

stats = {
    "files": len({r[1] for r in rows}),
    "mentions": len(rows),
    "distinct_forms": len({r[5] for r in rows}),
    "speaker_mentions_removed": sum(removed_speaker.values()),
    "mentions_in_paratext": sum(r[3] != "testo" for r in rows),
    "spacy": spacy.__version__,
    "model": f"it_core_news_lg {nlp.meta.get('version')}",
}
json.dump(stats, open("ner_stats.json", "w"), indent=2)
print(stats)
