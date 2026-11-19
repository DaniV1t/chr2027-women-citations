"""
Classify each (paragraph, person) unit by citation role and rhetorical function
using the Mistral API.

Input: unita.csv (produced by prepara_unita.py), columns:
    unit_id, doc_id, anno, titolo, autrice, persona, paragrafo_marcato, contesto_wd

Output: predizioni.jsonl, one JSON object per unit. The script can be stopped
and restarted: units already in the output are skipped.

Usage:
    set MISTRAL_API_KEY=...            (Windows)   /   export MISTRAL_API_KEY=...
    python classifica_mistral_v2.py unita_gold_v2.csv predizioni_v2.jsonl --workers 3 --pause 2      # 1) gold only
    python classifica_mistral_v2.py unita_campione_v2.csv predizioni_v2.jsonl --workers 3 --pause 2  # 2) sample, only if v2 is better
"""
import argparse
import csv
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API_URL = "https://api.mistral.ai/v1/chat/completions"
PROMPTS = {"v1": "v1-2026-11-11", "v2": "v2-2026-11-12", "v3": "v3-2026-11-12"}

L1 = ["CITAZIONE", "MENZIONE", "SOGGETTO", "ERRORE"]
L2 = ["CONTESTAZIONE", "GENEALOGIA", "APPROPRIAZIONE", "ALLINEAMENTO", "ALTRO"]

SYSTEM = """You are an expert in Italian cultural history (1870-1936) annotating public lectures ("conferenze") delivered by Italian women. You classify how ONE named person, marked with ⟦ ⟧ in a paragraph, is used by the speaker.

The marked name was found automatically, so it can be wrong. You also receive an automatic indication from Wikidata (checked by hand for frequent names). Use it as a hint: it can be wrong, and the paragraph always decides.

LEVEL 1 - role of the marked person in this paragraph. Decide in this order:

1. ERRORE: the marked words do not designate a real historical person. This includes:
   - OCR errors, places, institutions, families or dynasties ("Casa Savoia", "Borboni"), common words taken for names ("Genio", "Amore", "Sole");
   - a title, role, epithet or pronoun used alone instead of a name ("Maestro", "Prof", "Confessore", "Pontefice", "Ei", "Colui", "Principessa");
   - characters of fiction, literature or myth, and gods: Faust, Criseide, Enea, Achille, Venere, Minerva, Doralice, Bradamante. They are ERRORE EVEN WHEN the speaker uses them as a model or example.
   Exceptions, which are real persons: Jesus; historical biblical figures (Mary, Paul the apostle, Peter); historical persons used as models (Cornelia mother of the Gracchi); spelling variants of a real person's name ("Göthe" = Goethe, "Michelangiolo").
2. SOGGETTO: the person is the topic of the lecture, OR the topic of this passage (a secondary subject): the passage narrates their life, describes their character or deeds, or describes their work as an object of discussion. If instead the speaker takes the person's words or ideas to support a general claim of her own, choose CITAZIONE.
3. CITAZIONE: the speaker draws on the person's words, ideas, works or example as an AUTHORITY to support, frame or contest her own argument: direct quotation, verse, paraphrase ("come insegna X", "X ha detto"), reference to a work, an exemplary figure explicitly proposed as a model.
   Choose CITAZIONE only if you can say which words, idea, work or example is being used to support the argument.
4. MENZIONE: everything else. The person is named but their authority is not used: narrated facts, historical events, people present in the room, organisers, dedicatees, acknowledgements, contemporaries as actors, names in a list of facts, praise without argumentative use.
   When you hesitate between CITAZIONE and MENZIONE, choose MENZIONE and set "ambiguo" to true.

LEVEL 2 - only if LEVEL 1 is CITAZIONE, the rhetorical function:
- GENEALOGIA: the person is presented as a precursor, ancestor, illustrious example or member of a tradition that the speaker claims for herself, for women or for her cause: lists of great predecessors, illustrious women, poets and thinkers of the Italian or Christian tradition, Risorgimento heroes evoked as models. This is the most frequent function: when the person is evoked positively as part of a tradition the speaker identifies with, choose GENEALOGIA.
- ALLINEAMENTO: the citation expresses adherence to the dominant or official ideology: State, monarchy, nation, war, regime, religious orthodoxy.
- CONTESTAZIONE: the speaker rejects, corrects or disputes the cited authority.
- APPROPRIAZIONE: use it only when the authority is clearly distant from or hostile to the speaker's cause (for example a misogynist philosopher, an opponent) and the speaker turns it to support her claim. An authority that simply agrees with her is not APPROPRIAZIONE.
- ALTRO: only if none of the above applies, for example an ornamental verse or a scientific authority cited for a fact. Describe it in one word in "altro_descrizione".

Set "ambiguo" to true when two labels are plausible, and give the second one in "alternativa".
Answer ONLY with a JSON object with keys:
"livello1", "livello2" (null if not CITAZIONE), "ambiguo" (true/false), "alternativa" (label or null), "altro_descrizione" (string or null), "confidenza" ("alta"|"media"|"bassa"), "motivazione" (max 25 words, in Italian)."""

SYSTEM_V3 = """You are an expert in Italian cultural history (1870-1936) annotating public lectures ("conferenze") delivered by Italian women. You classify how ONE named person, marked with ⟦ ⟧ in a paragraph, is used by the speaker.

The marked name was found automatically, so it can be wrong. You also receive an automatic indication from Wikidata (checked by hand for frequent names). Use it as a hint: it can be wrong, and the paragraph always decides.

LEVEL 1 - role of the marked person in this paragraph. Decide in this order:

1. ERRORE: choose it ONLY when you have positive evidence that the marked words are not the name of a person:
   - OCR errors, places, institutions, families or dynasties ("Casa Savoia", "Borboni", "i Gracchi"), common words taken for names ("Genio", "Amore", "Sole");
   - a title, role, epithet or pronoun used alone instead of a name ("Maestro", "Prof", "Confessore", "Pontefice", "Ei", "Colui", "Principessa");
   - gods, and characters of fiction or myth (Faust, Criseide, Enea, Venere, Minerva, Doralice) when the speaker uses them as a model, example or authority: they cannot be authorities.
   NOT ERRORE:
   - a plausible personal name that is simply unknown or not found on Wikidata: many real people (local figures, contemporaries, minor writers) are missing there. Treat them as persons;
   - Jesus; historical biblical figures (Mary, Paul the apostle, Peter, Solomon); saints; historical persons used as models (Cornelia mother of the Gracchi); spelling variants of a real person's name ("Göthe" = Goethe);
   - a fictional or literary character who is the topic of the lecture or of the passage (Beatrice in a lecture on Dante, Ruggero in a lecture on Ariosto): choose SOGGETTO.
2. SOGGETTO: the person is the topic of the lecture, OR the topic of this passage (a secondary subject): the passage narrates their life, describes their character or deeds, or describes their work as an object of discussion. If instead the speaker takes the person's words or ideas to support a general claim of her own, choose CITAZIONE.
3. CITAZIONE: the speaker draws on the person's words, ideas, works or example as an AUTHORITY to support, frame or contest her own argument: direct quotation, verse, paraphrase ("come insegna X", "X ha detto"), reference to a work, an exemplary figure explicitly proposed as a model.
   Choose CITAZIONE only if you can say which words, idea, work or example is being used to support the argument.
4. MENZIONE: everything else. The person is named but their authority is not used: narrated facts, historical events, people present in the room, organisers, dedicatees, acknowledgements, contemporaries as actors, names in a list of facts, praise without argumentative use.
   When you hesitate between CITAZIONE and MENZIONE, choose MENZIONE and set "ambiguo" to true.

LEVEL 2 - only if LEVEL 1 is CITAZIONE, the rhetorical function:
- GENEALOGIA: the person is presented as a precursor, ancestor, illustrious example or member of a tradition that the speaker claims for herself, for women or for her cause: lists of great predecessors, illustrious women, poets and thinkers of the Italian or Christian tradition, Risorgimento heroes evoked as models. This is the most frequent function: when the person is evoked positively as part of a tradition the speaker identifies with, choose GENEALOGIA.
- ALLINEAMENTO: the citation expresses adherence to the dominant or official ideology: State, monarchy, nation, war, regime, religious orthodoxy.
- CONTESTAZIONE: the speaker rejects, corrects or disputes the cited authority.
- APPROPRIAZIONE: use it only when the authority is clearly distant from or hostile to the speaker's cause (for example a misogynist philosopher, an opponent) and the speaker turns it to support her claim. An authority that simply agrees with her is not APPROPRIAZIONE.
- ALTRO: only if none of the above applies, for example an ornamental verse or a scientific authority cited for a fact. Describe it in one word in "altro_descrizione".

Set "ambiguo" to true when two labels are plausible, and give the second one in "alternativa".
Answer ONLY with a JSON object with keys:
"livello1", "livello2" (null if not CITAZIONE), "ambiguo" (true/false), "alternativa" (label or null), "altro_descrizione" (string or null), "confidenza" ("alta"|"media"|"bassa"), "motivazione" (max 25 words, in Italian)."""

USER_TMPL = """Lecture: "{titolo}" ({anno}), speaker: {autrice}
Marked person: {persona}
Wikidata indication: {contesto_wd}

Paragraph:
{paragrafo_marcato}"""

USER_TMPL_V3 = USER_TMPL



SYSTEM_V1 = """You are an expert in Italian cultural history (1870-1936) annotating public lectures ("conferenze") delivered by Italian women. You classify how ONE named person, marked with ⟦ ⟧ in a paragraph, is used by the speaker.

LEVEL 1 - role of the marked person in this paragraph:
- CITAZIONE: the speaker draws on the person's words, ideas, works or example as an authority to support, frame or contest her own argument (direct quotation, verse, paraphrase, "come insegna X", reference to a work, an exemplary figure used as a model).
- MENZIONE: the person is named without drawing on their authority (narrated facts, historical events, people present, organisers, dedicatees, acknowledgements, contemporaries as actors).
- SOGGETTO: the person is the topic of the lecture (commemoration, biography, study of an author) and the passage narrates their life or describes their work as an object of study. If the speaker uses the topic-person's words to support a general claim, choose CITAZIONE instead.
- ERRORE: not a real person (OCR error, place, institution, common word, purely fictional name).

LEVEL 2 - only if LEVEL 1 is CITAZIONE, the rhetorical function:
- CONTESTAZIONE: the speaker rejects, corrects or disputes the cited authority.
- GENEALOGIA: the person is presented as a precursor or ancestor in a tradition in which the speaker places herself or her cause (often lists of predecessors).
- APPROPRIAZIONE: an authority external to the speaker's cause or field, or ideologically distant from it, is borrowed and redirected to support her claim.
- ALLINEAMENTO: the citation expresses adherence to the dominant or official ideology (State, monarchy, nation, regime, religious orthodoxy).
- ALTRO: none of the above (e.g. ornamental verse, scientific authority cited for a fact); describe it in one word in "altro_descrizione".

Set "ambiguo" to true when two labels are plausible, and give the second one in "alternativa".
Answer ONLY with a JSON object with keys:
"livello1", "livello2" (null if not CITAZIONE), "ambiguo" (true/false), "alternativa" (label or null), "altro_descrizione" (string or null), "confidenza" ("alta"|"media"|"bassa"), "motivazione" (max 25 words, in Italian)."""

USER_TMPL_V1 = """Lecture: "{titolo}" ({anno}), speaker: {autrice}
Marked person: {persona}

Paragraph:
{paragrafo_marcato}"""

TEXTS = {"v1": (SYSTEM_V1, USER_TMPL_V1), "v2": (SYSTEM, USER_TMPL), "v3": (SYSTEM_V3, USER_TMPL_V3)}


class Refused(Exception):
    pass


def call(api_key, model, unit, prompt="v2", max_retries=6):
    system, user_tmpl = TEXTS[prompt]
    body = {
        "model": model,
        "temperature": 0,
        "top_p": 1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_tmpl.format(**unit)},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    wait = 2
    for attempt in range(max_retries):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(wait)
                wait = min(wait * 2, 60)
                continue
            if r.status_code >= 400:
                # 4xx = request refused: no retry, show Mistral's explanation
                raise Refused(f"{r.status_code}: {r.text[:400]}")
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            usage = dict(data.get("usage", {}), model_version=data.get("model"))
            return json.loads(content), usage
        except Refused:
            raise
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(wait)
            wait = min(wait * 2, 60)
    raise RuntimeError("too many retries")


def validate(out):
    """Normalise labels; mark invalid output instead of dropping it."""
    l1 = str(out.get("livello1", "")).upper().strip()
    l2 = out.get("livello2")
    l2 = str(l2).upper().strip() if l2 else None
    ok = l1 in L1 and (l1 != "CITAZIONE" or l2 in L2)
    if l1 != "CITAZIONE":
        l2 = None
    out["livello1"], out["livello2"], out["valido"] = l1, l2, ok
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("unita_csv")
    ap.add_argument("out_jsonl")
    ap.add_argument("--model", default="mistral-large-latest")
    ap.add_argument("--prompt", choices=["v1", "v2", "v3"], default="v3", help="prompt version")
    ap.add_argument("--limit", type=int, default=None, help="classify only N new units (for testing)")
    ap.add_argument("--pause", type=float, default=1.1, help="seconds between requests (per worker)")
    ap.add_argument("--workers", type=int, default=1, help="parallel requests (check your Mistral rate limit)")
    args = ap.parse_args()

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("MISTRAL_API_KEY is not set")

    done = set()
    if os.path.exists(args.out_jsonl):
        with open(args.out_jsonl, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    done.add(json.loads(line)["unit_id"])

    with open(args.unita_csv, encoding="utf-8", newline="") as f:
        units = [u for u in csv.DictReader(f) if u["unit_id"] not in done]
    if args.limit:
        units = units[: args.limit]
    print(f"{len(done)} already done, {len(units)} to classify with {args.model}, prompt {PROMPTS[args.prompt]}")

    tok = {"in": 0, "out": 0, "n": 0}
    lock = threading.Lock()

    def work(u):
        try:
            out, usage = call(api_key, args.model, u, args.prompt)
            out = validate(out)
        except Exception as e:  # keep going; the unit is retried on the next run
            print(f"  ! {u['unit_id']}: {e}")
            time.sleep(args.pause)
            return
        out.update(unit_id=u["unit_id"], modello=args.model, versione_modello=usage.get("model_version"), prompt=PROMPTS[args.prompt])
        with lock:
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            fout.flush()
            tok["in"] += usage.get("prompt_tokens", 0)
            tok["out"] += usage.get("completion_tokens", 0)
            tok["n"] += 1
            if tok["n"] % 50 == 0:
                print(f"  {tok['n']}/{len(units)}  tokens in={tok['in']} out={tok['out']}")
        time.sleep(args.pause)

    with open(args.out_jsonl, "a", encoding="utf-8") as fout:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for _ in as_completed([ex.submit(work, u) for u in units]):
                pass
    tok_in, tok_out = tok["in"], tok["out"]
    print(f"done. tokens in={tok_in} out={tok_out}")


if __name__ == "__main__":
    main()
