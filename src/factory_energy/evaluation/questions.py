"""The evaluation question set (eval/questions.yaml), validated with pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from factory_energy.rag.settings import REPO_ROOT

EVAL_DIR = REPO_ROOT / "eval"
QUESTIONS = EVAL_DIR / "questions.yaml"
HARD_QUESTIONS = EVAL_DIR / "hard" / "questions.yaml"  # the X set, scored and reported apart
CORE_CATEGORIES = ("numeric", "knowledge", "multi_tool", "refusal")
HARD_CATEGORIES = ("chain", "scope", "limits", "ambiguous", "citation")
Category = Literal["numeric", "knowledge", "multi_tool", "refusal",
                   "chain", "scope", "limits", "ambiguous", "citation"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NumberSpec(_Strict):
    golden: str
    tolerance: float = Field(ge=0)
    also_fraction: bool = False


class Alternative(_Strict):
    """One acceptable way to answer: its numbers and phrase groups must all match."""

    numbers: tuple[NumberSpec, ...] = ()
    phrases: tuple[tuple[str, ...], ...] = ()


class Expectation(_Strict):
    numbers: tuple[NumberSpec, ...] = ()
    phrases: tuple[tuple[str, ...], ...] = ()
    refusal: bool = False
    forbidden: tuple[str, ...] = ()
    any_of: tuple[Alternative, ...] = ()  # at least one alternative must match
    clarify: bool = False  # the answer asks for clarification or states its assumption


class Question(_Strict):
    id: str = Field(pattern=r"^[NKMRX]\d{2}$")
    category: Category
    question: str = Field(min_length=10)
    expect: Expectation
    tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    strict_citations: bool = False  # any citation to something not retrieved fails the answer
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def checkable(self) -> Question:
        e = self.expect
        if not (e.numbers or e.phrases or e.refusal or e.any_of or e.clarify):
            raise ValueError(f"{self.id}: nothing to check")
        return self

    @property
    def smoke(self) -> bool:
        return "smoke" in self.tags


def load_questions(path: Path = QUESTIONS) -> list[Question]:
    with path.open(encoding="utf-8") as handle:
        rows = yaml.safe_load(handle)
    questions = [Question.model_validate(row) for row in rows]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question id")
    return questions
