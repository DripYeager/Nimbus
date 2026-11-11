"""
Builds the large retrieval benchmark in tests/fixtures/eval_corpus_large: about 100 documents in
families of look-alikes, plus two labelled question sets, direct (codes, names, exact phrases)
and paraphrased (the same facts asked in other words). Seeded, so rebuilding gives identical
files. The output is committed; rerun this only after changing scripts/eval_corpus_data.py.

    python scripts/build_eval_corpus.py
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from eval_corpus_data import AGREEMENTS, APPOINTMENTS, GUIDES, INVOICES, PROJECTS, RECIPES, TRIPS  # noqa: E402

OUTPUT = ROOT / "tests" / "fixtures" / "eval_corpus_large"
SEED = 2026
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October"]
Case = dict[str, str]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def invoices(rng: random.Random) -> list[tuple[str, str, Case, Case]]:
    documents = []
    # Drawn together without repeats: two invoices sharing a number would share a file name.
    numbers = rng.sample(range(3000, 4000), len(INVOICES))
    for (vendor, item, quantity, price, paraphrase), raw_number in zip(INVOICES, numbers, strict=True):
        number = f"INV-{raw_number}"
        total = quantity * price
        text = (
            f"Invoice {number} from {vendor}. Bill to: Northwind Ltd. Item: {quantity} x {item} at "
            f"{price:,} USD each. Total due {total:,.2f} USD by {rng.randint(1, 28)} {rng.choice(MONTHS)}. "
            f"Pay by bank transfer, quoting {number}."
        )
        documents.append(
            (
                f"invoice_{number}.txt",
                text,
                _case(number, f"invoice_{number}.txt"),
                _case(f"how much did we pay for {paraphrase}", f"invoice_{number}.txt"),
            )
        )
    return documents


def projects() -> list[tuple[str, str, Case, Case]]:
    documents = []
    for codename, goal, paraphrase, owner, deadline in PROJECTS:
        name = f"meeting_project_{slug(codename)}.md"
        text = (
            f"Project {codename} weekly meeting. Goal: {goal}. Owner: {owner}. Target date: end of "
            f"{deadline}. Decisions: keep the scope fixed, review budget next week. Risks: vendor delays."
        )
        documents.append(
            (name, text, _case(f"project {codename} owner", name), _case(f"who is in charge of {paraphrase}", name))
        )
    return documents


def trips() -> list[tuple[str, str, Case, Case]]:
    documents = []
    for city, country, sights, food, paraphrase in TRIPS:
        name = f"trip_{slug(city)}.md"
        text = (
            f"Holiday notes, {city}, {country}. Day one we saw {sights}. In the evening we ate {food} "
            f"at a small place near the hotel. Day three was for shopping and packing."
        )
        documents.append((name, text, _case(f"{city} trip", name), _case(f"where did we eat {paraphrase}", name)))
    return documents


def recipes() -> list[tuple[str, str, Case, Case]]:
    documents = []
    for dish, ingredient, method, paraphrase in RECIPES:
        name = f"recipe_{slug(dish)}.md"
        text = f"Recipe: {dish}. You need {ingredient}, salt, pepper and oil. Method: {method}. Serves four."
        documents.append((name, text, _case(f"{dish} recipe", name), _case(f"how do I make {paraphrase}", name)))
    return documents


def agreements() -> list[tuple[str, str, Case, Case]]:
    documents = []
    for agreement, provider, notice, fee, paraphrase in AGREEMENTS:
        name = f"{slug(agreement)}_{slug(provider)}.txt"
        text = (
            f"{agreement.capitalize()} with {provider}. Price: {fee}. To cancel, give {notice} notice in "
            f"writing. Renews automatically each year unless cancelled."
        )
        documents.append(
            (
                name,
                text,
                _case(f"{provider} {agreement}", name),
                _case(f"how much notice to get out of {paraphrase}", name),
            )
        )
    return documents


def appointments() -> list[tuple[str, str, Case, Case]]:
    documents = []
    for who, specialty, place, when, paraphrase in APPOINTMENTS:
        name = f"appointment_{slug(specialty)}.txt"
        text = (
            f"Appointment confirmation: {who}, {specialty}, {place}, {when}. Please arrive ten minutes "
            f"early. To rearrange, call at least 24 hours before."
        )
        documents.append((name, text, _case(f"{who} {place}", name), _case(f"when is {paraphrase}", name)))
    return documents


def guides() -> list[tuple[str, str, Case, Case]]:
    return [
        (
            f"note_{slug(title)}.md",
            f"{title}. {body}",
            _case(direct, f"note_{slug(title)}.md"),
            _case(paraphrase, f"note_{slug(title)}.md"),
        )
        for title, body, direct, paraphrase in GUIDES
    ]


def _case(query: str, expected: str) -> Case:
    return {"query": query, "expected": expected}


def main() -> None:
    rng = random.Random(SEED)
    documents = [*invoices(rng), *projects(), *trips(), *recipes(), *agreements(), *appointments(), *guides()]
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    for name, text, _, _ in documents:
        (OUTPUT / name).write_text(text + "\n", encoding="utf-8")
    for file_name, index in (("queries.json", 2), ("queries_hard.json", 3)):
        cases = [document[index] for document in documents]
        (OUTPUT / file_name).write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(documents)} documents and {2 * len(documents)} questions to {OUTPUT}")


if __name__ == "__main__":
    main()
