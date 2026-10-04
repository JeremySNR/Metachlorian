"""Controlled vocabularies.

Built-in vocabularies are versioned YAML files in ``vocab/v<N>/``. Admins can
add terms at runtime (stored in the ``vocab_terms`` table); built-in ids are
never changed or removed, only deprecated, so stored labels stay valid.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

VOCAB_DIR = Path(__file__).parent
DEFAULT_VERSION = "v1"


@dataclass
class Term:
    id: str
    label: str
    definition: str = ""
    synonyms: list[str] = field(default_factory=list)
    broader: str | None = None
    mappings: dict[str, Any] = field(default_factory=dict)
    custom: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "definition": self.definition, "synonyms": self.synonyms,
                "broader": self.broader, "mappings": self.mappings, "custom": self.custom}


@dataclass
class Vocabulary:
    name: str
    version: str
    description: str
    multi: bool
    terms: dict[str, Term]
    ordered: bool = False

    def narrower(self, term_id: str) -> set[str]:
        """The term and every descendant (search for 'pan' matches 'pan_left')."""
        out = {term_id}
        changed = True
        while changed:
            changed = False
            for t in self.terms.values():
                if t.broader in out and t.id not in out:
                    out.add(t.id)
                    changed = True
        return out

    def ancestors(self, term_id: str) -> list[str]:
        out = []
        cur = self.terms.get(term_id)
        while cur and cur.broader and cur.broader not in out:
            out.append(cur.broader)
            cur = self.terms.get(cur.broader)
        return out

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "multi": self.multi,
                "ordered": self.ordered, "terms": [t.as_dict() for t in self.terms.values()]}


class VocabRegistry:
    def __init__(self, version: str = DEFAULT_VERSION):
        self.version = version
        self._lock = threading.Lock()
        self.vocabs: dict[str, Vocabulary] = {}
        self._load_builtin()

    def _load_builtin(self) -> None:
        for f in sorted((VOCAB_DIR / self.version).glob("*.yaml")):
            d = yaml.safe_load(f.read_text())
            terms = {}
            for t in d.get("terms", []):
                terms[t["id"]] = Term(
                    id=t["id"], label=t.get("label", t["id"]), definition=t.get("definition", "") or "",
                    synonyms=[str(s) for s in (t.get("synonyms") or [])], broader=t.get("broader"),
                    mappings=t.get("mappings") or {},
                    extra={k: v for k, v in t.items() if k not in ("id", "label", "definition", "synonyms", "broader", "mappings")})
            self.vocabs[d["vocabulary"]] = Vocabulary(d["vocabulary"], str(d.get("version", "1.0.0")), (d.get("description") or "").strip(),
                                                      bool(d.get("multi", True)), terms, bool(d.get("ordered", False)))

    def load_custom(self, db) -> None:
        with self._lock:
            for r in db.q("SELECT * FROM vocab_terms"):
                v = self.vocabs.get(r["vocab"])
                if not v:
                    continue
                import json

                v.terms[r["term"]] = Term(r["term"], r["label"], r["definition"], json.loads(r["synonyms"]), r["broader"], {}, True)
            _phrase_index.cache_clear()

    def get(self, name: str) -> Vocabulary:
        return self.vocabs[name]

    def valid(self, vocab: str, term: str) -> bool:
        v = self.vocabs.get(vocab)
        return bool(v and term in v.terms)

    def label(self, vocab: str, term: str) -> str:
        v = self.vocabs.get(vocab)
        return v.terms[term].label if v and term in v.terms else term

    def summary(self) -> dict[str, str]:
        return {n: v.version for n, v in sorted(self.vocabs.items())}

    def phrase_index(self) -> list[tuple[str, str, str]]:
        """(normalised phrase, vocab, term) sorted longest first, for query parsing."""
        return _phrase_index(self)


def norm(s: str) -> str:
    s = s.lower().replace("-", " ").replace("_", " ").replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^\w' ]", " ", s)).strip()


@lru_cache(maxsize=4)
def _phrase_index(reg: VocabRegistry) -> list[tuple[str, str, str]]:
    out: dict[tuple[str, str], str] = {}
    for vname, v in reg.vocabs.items():
        for t in v.terms.values():
            for phrase in [t.id, t.label, *t.synonyms]:
                p = norm(phrase)
                if len(p) >= 2:
                    out.setdefault((p, vname), t.id)
    items = [(p, vn, tid) for (p, vn), tid in out.items()]
    items.sort(key=lambda x: (-len(x[0]), x[0]))
    return items


_registry: VocabRegistry | None = None


def registry() -> VocabRegistry:
    global _registry
    if _registry is None:
        _registry = VocabRegistry()
    return _registry
