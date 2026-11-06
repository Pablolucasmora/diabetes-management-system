#!/usr/bin/env python3
"""Builds the file that fills `ciqual_food` from the Ciqual XML files
(measurement_conventions.md §12.3). Standard library only.

Spanish names: overrides_es.csv (whole names) first, then glossary_es.csv
(phrases and words), with the noun placed first and adjectives agreeing with it.
A word the glossary lacks stays in English, and its stretch of the name keeps the
English order; correct a name by adding it to overrides_es.csv and running this again.

Usage:
    python clean_ciqual.py <folder with the XML files> ciqual_foods.csv.gz --export-date 2025-11-03
"""

from __future__ import annotations

import argparse
import csv
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

VERSION = "2025_11_03"
BABY_FOOD_GROUP = "11"
SUBTYPE_MAX_LENGTH = 100
KCAL_MAX = 900
HERE = Path(__file__).resolve().parent
COMPONENTS = {
    "kcal": lambda n: "kcal/100" in n and "1169" in n,
    "carbs": lambda n: n.startswith("carbohydrate"),
    "sugars": lambda n: n.startswith("sugars"),
    "fat": lambda n: n.startswith("fat ("),
    "saturated": lambda n: n.startswith("fa saturated"),
    "proteins": lambda n: n.startswith("protein (g"),
    "fiber": lambda n: n.startswith("fibres"),
    "alcohol": lambda n: n.startswith("alcohol"),
}
ADJECTIVES = frozenset(
    """
    alcohol-free all aromatic asian atlantic averagely baked black blue boiled bottled braised breaded
    brewed brined brown candied canned caramelized carbonated chinese chocolate-coated choice coated
    cold common concentrated cooked covered crunchy cultivated cured curly dairy dark decaffeinated
    defatted dehydrated diced diluted drained dried dry durum european farmed fermented filled filtered
    firm flaked flavoured fluid fortified french fresh fried frozen gluten-free golden grated green grey
    grilled half half-salted hard home-made homemade instant japanese large lean light lightly low
    marinated mashed mature matured mediterranean minced mineral mineralized mixed multivitamin oriental
    pan-fried partially pasteurised peeled pickled pink pitted plain plant-based popped powder pre-
    cooked pre-fried prepacked processed puffed pure raw ready-to-drink reconstituted red reduced
    refrigerated reheated rich roasted salted salty sampled sautéed savoury seasoned seasonned semi-
    preserved semi-skimmed semi-thick skimmed small smoked soft soft-ripened sparkling spicy split
    spreadable sprouted standard steamed stewed still stir-fried strongly stuffed superior swedish sweet
    sweetened swiss takeaway textured thick thin toasted topped tropical unknown unsalted vegan vegetal
    vegetarian very viennese warm whipped white whole wholegrain wholemeal wholewheat wild yellow
    """.split()
) | {
    "gluten free", "low fat", "reduced fat", "low sugar", "low salt", "all types", "added", "greek-style",
    "country-style", "washed-rind", "rind less",
}
# Feminine nouns that do not end in a, -ción, -sión or -dad.
FEMININE = frozenset({"leche", "carne", "sal", "miel", "piel", "col", "coliflor", "nuez", "ave", "levadura", "salmuera"})
CONNECTOR = re.compile(r"(?<![\w'-])(and/or|with|without|from|in|of|for|on|and|or|to|not)(?![\w'-])(?![^()]*\))", re.IGNORECASE)
PARENTHESES = re.compile(r"(\s\([^()]*\))")
TOP_LEVEL_COMMA = re.compile(r",(?![^()]*\))")
NOTE_LABELS = (
    ("kcal", "kcal"), ("carbs", "carbs"), ("sugars", "sugars"), ("fat", "fat"), ("saturated", "saturated"),
    ("proteins", "protein"), ("fiber", "fiber"), ("alcohol", "alcohol"),
)
COLUMNS = [
    "code", "name_es", "name_en", "name_fr", "category_hint", "subtype", "calories_100g", "carbs_100g",
    "sugars_100g", "fats_100g", "saturated_100g", "proteins_100g", "fiber_100g", "alcohol",
    "carbs_confidence", "fats_confidence", "proteins_confidence", "value_notes", "export_date",
]


def rows(folder: Path, name: str, tag: str):
    for element in ET.parse(folder / f"{name}_{VERSION}.xml").getroot().findall(tag):
        yield {child.tag: (child.text or "").strip() for child in element}


def parse_value(raw: str):
    """(number, note). Missing is None, never zero. Traces are 0 and "< x" is half of
    x, the substitution Anses uses for these values; the note keeps the original."""
    text = (raw or "").strip()
    if not text or text == "-":
        return None, None
    if text.lower() == "traces":
        return 0.0, text
    if text.startswith("<"):
        return float(text[1:].strip().replace(",", ".")) / 2, text
    return float(text.replace(",", ".")), None


def agree(adjective: str, head: str | None) -> str:
    """The adjective in the gender and number of the noun; only regular endings change."""
    if not head or " " in adjective or adjective.endswith("mente") or adjective == "muy":
        return adjective
    noun = head.split()[0]
    plural = noun.endswith("s")
    singular = noun.rstrip("s")
    feminine = singular in FEMININE or singular.endswith(("a", "ción", "sión", "dad"))
    if adjective.endswith("o"):
        adjective = adjective[:-1] + ("a" if feminine else "o")
    elif adjective.endswith("és") and feminine:
        adjective = adjective[:-2] + "esa"
    if plural:
        adjective += "s" if adjective[-1] in "aeiou" else "es"
    return adjective


class Translator:
    def __init__(self):
        with open(HERE / "overrides_es.csv", encoding="utf-8", newline="") as handle:
            self.overrides = {row["name_en"]: row["name_es"] for row in csv.DictReader(handle)}
        with open(HERE / "glossary_es.csv", encoding="utf-8", newline="") as handle:
            pairs = [(row["en"].lower(), row["es"]) for row in csv.DictReader(handle)]
        terms = sorted(pairs, key=lambda pair: -len(pair[0]))
        self.glossary = dict(terms)
        pattern = "|".join(re.escape(term) for term, _ in terms)
        self.pattern = re.compile(rf"(?<![\w'-])({pattern})(?![\w'-])", re.IGNORECASE)

    def _plain(self, text: str) -> str:
        return self.pattern.sub(lambda match: self.glossary[match.group(1).lower()], text)

    def _words(self, chunk: str, head: str | None) -> tuple[str, str | None]:
        """English puts the noun last and Spanish first, so a chunk made only of
        known words is rebuilt; any other word (a proper name) keeps the order."""
        terms = [match.lower() for match in self.pattern.findall(chunk)]
        if not terms or self.pattern.sub("", chunk).strip():
            return self._plain(chunk), head
        nouns = [self.glossary[t] for t in terms if t not in ADJECTIVES and self.glossary[t]]
        adjectives = [self.glossary[t] for t in terms if t in ADJECTIVES]
        if nouns:
            head = nouns[-1]
        agreed = [agree(adjective, head) for adjective in adjectives]
        return " ".join([*nouns[-1:], *(f"de {noun}" for noun in reversed(nouns[:-1])), *agreed]), head

    def _chunk(self, chunk: str, head: str | None) -> tuple[str, str | None]:
        """Parentheses are translated as they are; "a/b" are two alternatives."""
        pieces = []
        for index, piece in enumerate(PARENTHESES.split(chunk)):
            if index % 2:
                pieces.append(self._plain(piece))
                continue
            if chunk.strip().lower() in self.glossary:
                alternatives = [piece]
            else:
                alternatives = piece.split("/")
            done = []
            for alternative in alternatives:
                text, head = self._words(alternative, head)
                done.append(text)
            pieces.append("/".join(done))
        return " ".join(piece.strip() for piece in pieces if piece.strip()), head

    def __call__(self, name_en: str) -> str:
        if name_en in self.overrides:
            return self.overrides[name_en]
        head = None
        segments = []
        for position, segment in enumerate(TOP_LEVEL_COMMA.split(name_en)):
            parts = CONNECTOR.split(segment.strip())
            # After the first segment, "flesh and skin" or "with x" do not name what the
            # adjectives describe; only a segment that is a single noun does.
            for index in range(0, len(parts), 2):
                parts[index], new_head = self._chunk(parts[index], head)
                if index == 0 and (position == 0 or len(parts) == 1):
                    head = new_head
            for index in range(1, len(parts), 2):
                parts[index] = self.glossary.get(parts[index].lower(), parts[index])
            segments.append(" ".join(part.strip() for part in parts if part.strip()))
        text = re.sub(r"\s+", " ", ", ".join(segment for segment in segments if segment))
        text = re.sub(r"\s+,", ",", text).strip(" ,")
        return text[:1].upper() + text[1:]


def component_codes(folder: Path) -> dict:
    """Ciqual's component code -> our key."""
    codes = {}
    for row in rows(folder, "const", "CONST"):
        name = row["const_nom_eng"].lower()
        for key, matches in COMPONENTS.items():
            if key not in codes and matches(name):
                codes[key] = row["const_code"]
    missing = set(COMPONENTS) - set(codes)
    if missing:
        raise SystemExit(f"Components not found: {missing}")
    return {code: key for key, code in codes.items()}


def food_values(folder: Path, by_code: dict) -> dict:
    """Food code -> our key -> (raw value, confidence)."""
    values = {}
    for row in rows(folder, "compo", "COMPO"):
        key = by_code.get(row["const_code"])
        if key:
            values.setdefault(row["alim_code"], {})[key] = (row["teneur"], row.get("code_confiance") or None)
    return values


def check_limits(code: str, number: dict) -> None:
    """A value outside its physical range means the source changed: stop, never load it."""
    for key, value in number.items():
        if value is not None and not 0 <= value <= (KCAL_MAX if key == "kcal" else 100):
            raise SystemExit(f"Food {code}: {key} = {value} is outside its range.")


def build_row(food: dict, raw_values: dict, hint: str, translate, export_date: date) -> list | None:
    """The CSV row of a food, or None if it does not enter the copy (§12.3)."""
    parsed = {key: parse_value(raw_values.get(key, ("",))[0]) for key in COMPONENTS}
    if food["alim_grp_code"] == BABY_FOOD_GROUP or any(parsed[key][0] is None for key in ("carbs", "fat", "proteins")):
        return None
    number = {key: parsed[key][0] for key in COMPONENTS}
    check_limits(food["alim_code"], number)
    # The catalog rejects sugars above carbs and saturated above fat.
    if number["sugars"] is not None:
        number["sugars"] = min(number["sugars"], number["carbs"])
    if number["saturated"] is not None:
        number["saturated"] = min(number["saturated"], number["fat"])
    notes = "; ".join(
        f"{label} {parsed[key][1]}"
        for key, label in NOTE_LABELS
        if parsed[key][1]
    )
    subtype = translate(hint).lower()
    return [
        food["alim_code"], translate(food["alim_nom_eng"]), food["alim_nom_eng"], food["alim_nom_fr"],
        hint, subtype if len(subtype) <= SUBTYPE_MAX_LENGTH else None, number["kcal"], number["carbs"],
        number["sugars"], number["fat"], number["saturated"], number["proteins"], number["fiber"], number["alcohol"],
        raw_values["carbs"][1], raw_values["fat"][1], raw_values["proteins"][1],
        notes or None, export_date.isoformat(),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--export-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()

    by_code = component_codes(args.folder)
    subgroups = {row["alim_ssgrp_code"]: row.get("alim_ssgrp_nom_eng", "") for row in rows(args.folder, "alim_grp", "ALIM_GRP")}
    values = food_values(args.folder, by_code)
    translate = Translator()
    written = skipped = 0
    with gzip.open(args.output, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for food in rows(args.folder, "alim", "ALIM"):
            hint = subgroups.get(food["alim_ssgrp_code"], "")
            row = build_row(food, values.get(food["alim_code"], {}), hint, translate, args.export_date)
            if row is None:
                skipped += 1
                continue
            writer.writerow(row)
            written += 1
    print(f"written: {written}, skipped: {skipped}")


if __name__ == "__main__":
    main()
