# Annotation guidelines for citations (version 3.1, 17 November 2026)

**Unit to annotate:** one person named in one paragraph. The name is marked with ⟦ ⟧. If the same person appears several times in the same paragraph, the unit is annotated once, according to the prevailing use.

**What to look at:** the paragraph, the title of the lecture and the year. If the paragraph alone is not enough, the neighbouring paragraphs in the file `testo/` may be read.

**Labels** are kept in Italian, as in the data files: CITAZIONE (citation), MENZIONE (mention), SOGGETTO (subject), ERRORE (error); GENEALOGIA (genealogy), RAPPRESENTAZIONE (representation), ALLINEAMENTO (alignment), CONTESTAZIONE (contestation), APPROPRIAZIONE (appropriation), ALTRO (other).

**What changes in version 3.1 (17 Nov):** level 2 is no longer used for citations only. **RAPPRESENTAZIONE** is used mostly with SOGGETTO (and sometimes with MENZIONE): it is a function of the discourse about a character, not only of a citation. For MENZIONE and SOGGETTO without a recognisable function, ALTRO is marked, which there means "no function". `finzione_annotato.xlsx` was annotated this way.

**Version 3 (13 Nov):** characters of myth and fiction are **no longer ERRORE**: they are classified by their use, like real persons, and "finzione" (fiction) is written in the note. New function: RAPPRESENTAZIONE. The decision came from annotating the women-only gold standard: fictional women are often used as models (genealogy) or to discuss how authors represented women.

**Version 2 (12 Nov):** secondary subject; spelling variants; titles and epithets used alone; Cornelia and Paul.

---

## Level 1: what role does the person play in the passage?

| Label | When to use it | Example |
|---|---|---|
| **ERRORE** (error) | The marked words do not designate a person or a character: OCR error, place, institution, family or dynasty ("Casa Savoia", "i Gracchi"), common word taken for a name ("Genio", "Amore" as a feeling); title, role, epithet or pronoun used alone ("Maestro", "Prof", "Ei", "Apostolo"); a name split or merged wrongly by the NER. | "Incominció", "Sac". |
| **SOGGETTO** (subject) | The person or character is the topic of the lecture, **or of the passage** (secondary subject: the passage narrates their life, character or deeds, or describes their work as an object of study). | Anita Garibaldi in the lecture by Cantoni Nascimbene, 1932; Ruggero in "Le donne dell'Ariosto"; Jacopo Ortis in the lecture on Foscolo. |
| **CITAZIONE** (citation) | The speaker draws on the words, ideas, works or example of the person or character to support, frame or contest her own argument: direct quotation (also in verse), paraphrase ("come insegna X", "as X teaches"), reference to a work, a figure proposed as a model (also from fiction or myth). | Montessori cites Nietzsche; Penelope proposed as a model of the industrious woman. |
| **MENZIONE** (mention) | The person or character is named but is neither used as an authority nor the topic: narrated facts, events, people present, dedicatees, contemporaries as actors, passing names ("a temple dedicated to Venus"). | "The Committee chaired by Count X promoted this evening." |

Borderline cases:
- **Characters of myth and fiction** (Penelope, Criseyde, Dante's Beatrice, Faust, Venus): classified by their use; "finzione" (or "mito", myth) is written in the `note` column, so that they can be counted separately.
- **Real persons:** Jesus; historical biblical figures (Mary, Paul the apostle, Peter); saints; historical persons used as models ("like Cornelia, mother of the Gracchi" = CITAZIONE).
- **Spelling variants and OCR errors of a real name** count as the person: "Göthe" = Goethe.
- **Subject cited as an authority.** If, in the lecture on Pascoli, the speaker quotes a line by Pascoli to support a general claim, CITAZIONE is used; if she analyses the line as an object of study, SOGGETTO.
- **Epigraphs and attributions** in the paratext are always CITAZIONE.
- **A male person in the women-only sheets:** the role is annotated as usual and "uomo" (man) is written in the note.
- **When in doubt between CITAZIONE and MENZIONE,** mark "ambiguo: sì" (ambiguous: yes) and write both labels in the note.

---

## Level 2: what function does the reference have?

For **CITAZIONE**, level 2 is required. For **SOGGETTO** and **MENZIONE** it is filled in only when the passage has a recognisable function, in practice RAPPRESENTAZIONE; otherwise ALTRO is marked, which for these labels means "no function".

| Label | Definition | Reference case |
|---|---|---|
| **GENEALOGIA** (genealogy) | The person or character is presented as a precursor, ancestor, illustrious example or member of a tradition in which the speaker places herself, women or her cause. Often in lists of predecessors. Includes fictional characters proposed as female models. | Santangeli, 1914, goes from Socrates and Christ to Leopardi; Beatrice in "La Beatrice dell'età nostra". |
| **RAPPRESENTAZIONE** (representation) | The speaker discusses characters (mostly female) created by an author to examine how men, or literature, have represented women. The character is usually the SOGGETTO of the passage; it can also be a CITAZIONE, when the author is invoked as the creator of female figures. | Angelica and Bradamante in "Le donne dell'Ariosto"; Molière's Agnès, "il tipo immortale della… cosiddetta buona fanciulla di casa". |
| **ALLINEAMENTO** (alignment) | Citations only: adherence to the dominant or official ideology (State, monarchy, nation, war, regime, religious orthodoxy). | Cantoni Nascimbene, 1932, uses Carducci to link the Garibaldis to the fascist present. |
| **CONTESTAZIONE** (contestation) | Citations only: the speaker rejects, corrects or disputes the cited authority. | Ferruggia, 1894, rejects Madame de Staël's saying that "genius has no sex". |
| **APPROPRIAZIONE** (appropriation) | Citations only: an authority clearly distant from or hostile to the speaker's cause is borrowed and turned to support her claim. | Montessori, 1907, uses Nietzsche for the equality of the sexes. |
| **ALTRO** (other) | For citations: none of the functions above (ornamental verse, scientific authority cited for a fact), described in one word in the `note` column. For SOGGETTO and MENZIONE: no function. | |

- **AMBIGUO** (ambiguous): yes/no. "Yes" when hesitating between two labels; the two labels in doubt go in the note.

---

## Procedure

1. Annotate **without looking** at the LLM's labels: the files to annotate do not contain them.
2. Indicative time: about one minute per case.
3. Annotated files:
   - main gold standard `gold_annotato_v23_r3.xlsx` (201 units, random sample; the 15 units with fictional characters were revised with version 3);
   - women-only gold standard `gold_donne_annotato.xlsx` (110 units with female persons, stratified by Mistral's label);
   - `finzione_annotato.xlsx` (183 units with characters of myth and fiction: 168 from the random sample and 15 from the main gold standard; version 3.1).
4. Mistral's prompt v3 still follows the version-2 rule for fiction (ERRORE): for this reason all fictional characters were annotated by hand, and the author's labels replace Mistral's.
