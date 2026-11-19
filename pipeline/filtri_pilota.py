"""
NER filters from the pilot study (August 2026).

This file is an exact copy of lines 35-151 of the pilot script
extraction_authors_complete.py: the exclusion list, the checks for verb
forms, -mente adverbs and OCR noise, the royal titles, extract_people()
and extract_year(). Nothing has been changed.

ner_corpus.py does not import this file: it looks for a .py file in its own
folder (or the parent folder) containing the filter block, copies the block
up to the line that defines extract_year, and executes it. Keep this file
in the same folder as ner_corpus.py, and do not edit the block, so that the
filters stay identical to those used for the paper.
"""
import re

NER_EXCLUSIONS = {
    "Signore", "Signori", "Voi", "Cielo", "Iddio", "Chissà",
    "Avrete", "Pensate", "Provate", "Leggete", "Riuscirà",
    "Finchè", "Madonna", "Re", "Poeta", "Babbo", "Dio", "Cristo", "Perchè",
    "Grandesalle", "Sbarcai", "Mercèla", "lasoia", "Pugnaste",
    # Batch-added: OCR/tokenization noise identified in the 957-group run
    "Eliso", "Lilia", "Giaccio", "Kaespair", "Vôlto", "Cielosentisti",
    "Neppur", "Laonde", "Làsulla", "Scannaveno", "riconforta", "Perchèla",
    "Uocoli", "Pontofice", "strozzasseli", "Morosinicadono", "esclusivamenle",
    "narreràun", "Squajateve", "Eriuscl", "lontanid'esiglio", "tutfi",
    "Discendere", "stamio", "sontitela", "buoua", "Scorren", "Menolti",
    "Victorium Emanuelem", "Coritybanos", "Pintensa", "Alsace.-Parigi,1916",
    "F. Petrarca-Canzone", "Specchiati", "V'Eco", "Cumpidoglio",
    "Sconfessava", "Carleggio", "martiio", "assalirvi", "Novepoesie",
    "Volgevano", "B. Franceвco", "Anelanti", "Ietterarie",
    "Emilio Zola-Forza", "Poechio", "del-1'uccel", "presuntuosità",
    "Sbucata", "Nonuo", "esiglio", "Èproprio", "L＇abbiam", "Arissomija",
    "colazionc", "Eroismi", "Perchèessa",
}

VERB_SUFFIXES = (
    "iamo", "iamoci", "iamola", "atela", "etela", "atevi", "etevi",
    "ate", "ete", "isci", "iscono", "irono", "arono", "erono", "ando", "endo",
    # Imperfetto indicativo
    "ava", "eva", "iva", "avano", "evano", "ivano",
    # Congiuntivo imperfetto
    "asse", "esse", "isse", "assero", "essero", "issero",
)

ADVERB_SUFFIX = "mente"


def fix_ocr_spacing(text):
    """Fix missing whitespace after punctuation (common OCR artifact)."""
    return re.sub(r'([.!?;,])([A-Za-zÀ-ÿ])', r'\1 \2', text)


def looks_like_a_verb(word):
    """Detects Italian verb forms mistakenly tagged as proper nouns."""
    w = word.lower()
    return len(w) > 5 and any(w.endswith(suf) for suf in VERB_SUFFIXES)


def looks_like_common_word(word):
    """
    Check for single-token 'names' that are actually ordinary Italian
    vocabulary: verb forms or '-mente' adverbs.

    NOTE: an earlier version also rejected tokens whose lowercase form had a
    static word vector in the language model (on the theory that common
    words are more likely in-vocabulary than surnames). This was removed:
    many genuine Italian given names double as ordinary common nouns
    (e.g. 'Omero' / 'omero' = humerus bone; and disproportionately common
    among female names — 'Fede', 'Speranza', 'Vittoria', 'Aurora', 'Stella',
    'Grazia', 'Rosa', 'Viola', 'Costanza'...), so that check was silently
    dropping real names — and doing so asymmetrically by gender, which is
    exactly the kind of artifact this project needs to avoid introducing
    into its own data.
    """
    w = word.lower()
    if len(w) <= 5:
        return False
    if looks_like_a_verb(word):
        return True
    if w.endswith(ADVERB_SUFFIX):
        return True
    return False


def looks_like_ocr_garbage(word):
    """
    Flags character patterns typical of OCR corruption rather than genuine
    names: stray digits/fullwidth punctuation, 3+ repeated letters, or an
    unusually low vowel ratio for the token's length.
    """
    if re.search(r'[0-9＇]', word):
        return True
    if re.search(r'(.)\1\1', word):  # same character 3+ times in a row
        return True
    letters = re.sub(r'[^A-Za-zÀ-ÿ]', '', word)
    if len(letters) >= 6:
        vowels = sum(1 for c in letters.lower() if c in "aeiouàèéìòù")
        if vowels / len(letters) < 0.25:
            return True
    return False


TRAILING_ROYAL_TITLES = {"Re", "Regina", "Papa", "Duca", "Santo", "Santa", "Gran"}


def extract_people(doc):
    """Extract plausible PERSON entities from a spaCy-parsed document."""
    people = []
    for ent in doc.ents:
        if ent.label_ != "PER":
            continue
        if not all(token.pos_ == "PROPN" for token in ent):
            continue
        text = ent.text.strip()
        if text in NER_EXCLUSIONS:
            continue
        if looks_like_ocr_garbage(text.replace(" ", "")):
            continue
        if len(text.split()) == 1 and looks_like_common_word(text):
            continue
        tokens = text.split()
        if tokens[0] in TRAILING_ROYAL_TITLES or tokens[-1] in TRAILING_ROYAL_TITLES:
            continue
        people.append(text)
    return people


def extract_year(filename):
    """Extracts a 4-digit year at the end of a filename (before the extension)."""
    stem = re.sub(r'\.\w+$', '', filename)
    match = re.search(r'(\d{4})$', stem)
    return int(match.group(1)) if match else None
