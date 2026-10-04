"""Natural-language query parsing into structured filters plus semantic intent.

Rule- and vocabulary-based, deterministic and fast (well under 5 ms). Every
vocabulary term, label and synonym is a phrase the parser recognises, so
admins extend the parser by extending the vocabularies. Technical constraints
and negations become hard filters; vocabulary terms become *preferences* by
default (strong ranking boosts that the UI shows as chips and can promote to
hard filters), because machine labels carry uncertainty.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..vocab import norm, registry

# Vocabularies the parser maps phrases into (others such as usage/channel are rights).
SEARCH_VOCABS = ("camera_movement", "shot_size", "camera_angle", "shot_role", "setting", "time_of_day", "weather", "season", "mood", "pace",
                 "speed_effect", "audio_class", "edit_type")
RIGHTS_VOCABS = ("usage", "channel")

STOP = {"a", "an", "the", "of", "with", "and", "or", "in", "on", "at", "for", "to", "from", "shot", "shots", "footage", "clip", "clips",
        "video", "videos", "some", "me", "find", "show", "give", "get", "that", "which", "are", "is", "we", "have", "do", "what", "any",
        "please", "like", "under", "this", "these", "those", "b", "roll", "i", "need", "want", "looking", "where", "s", "it", "its",
        "least", "more", "than", "would", "could", "work", "works", "actually", "use", "used", "good", "nice", "great",
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "few", "couple", "several", "longer", "shorter", "over", "about", "around", "seconds", "second", "sec", "secs"}

# Extra phrase -> (vocab, term) mappings the vocabularies do not carry.
EXTRA = {
    "drone": ("camera_movement", "aerial"), "drone shot": ("camera_movement", "aerial"), "aerial": ("camera_movement", "aerial"),
    "wide": ("shot_size", "long_shot"), "wide shot": ("shot_size", "long_shot"), "wides": ("shot_size", "long_shot"),
    "close up": ("shot_size", "close_up"), "close ups": ("shot_size", "close_up"), "closeup": ("shot_size", "close_up"),
    "closeups": ("shot_size", "close_up"), "cu": ("shot_size", "close_up"), "ecu": ("shot_size", "extreme_close_up"),
    "coastline": ("setting", "coast"), "coast": ("setting", "coast"), "beach": ("setting", "coast"), "seaside": ("setting", "coast"),
    "street": ("setting", "street"), "city": ("setting", "urban"), "indoors": ("setting", "interior"), "outdoors": ("setting", "exterior"),
    "night": ("time_of_day", "night"), "nighttime": ("time_of_day", "night"), "sunset": ("time_of_day", "sunset"),
    "slow": ("pace", "slow"), "calm": ("pace", "slow"), "fast": ("pace", "fast"), "busy": ("pace", "fast"),
    "interview": ("shot_role", "interview"), "interviews": ("shot_role", "interview"), "cutaway": ("shot_role", "cutaway"),
    "cutaways": ("shot_role", "cutaway"), "b roll": ("shot_role", "b_roll"), "broll": ("shot_role", "b_roll"),
    "establishing": ("shot_role", "establishing"), "piece to camera": ("shot_role", "piece_to_camera"), "ptc": ("shot_role", "piece_to_camera"),
    "raw": ("edit_type", "raw"), "raw footage": ("edit_type", "raw"), "rushes": ("edit_type", "raw"), "selects": ("edit_type", "selects"),
    "finished": ("edit_type", "finished"), "finished edit": ("edit_type", "finished"), "final edit": ("edit_type", "finished"),
    "slow motion": ("speed_effect", "slow_motion"), "slowmo": ("speed_effect", "slow_motion"), "slo mo": ("speed_effect", "slow_motion"),
    "timelapse": ("speed_effect", "time_lapse"), "time lapse": ("speed_effect", "time_lapse"), "hyperlapse": ("speed_effect", "hyperlapse"),
    "golden hour": ("time_of_day", "golden_hour"),
}
# Words that only make sense as a preference within these vocabularies when the
# vocabulary's own synonym list would otherwise claim a common word.
AMBIGUOUS_SKIP = {"footage", "files", "file", "still", "day", "light", "clear", "warm", "open", "neutral", "cut", "set", "master", "insert", "real time", "sky", "studio"}


@dataclass
class Parsed:
    text: str
    semantic: str = ""
    keywords: list[str] = field(default_factory=list)
    prefer: dict[str, list[str]] = field(default_factory=dict)   # vocab -> terms (soft)
    require: dict[str, list[str]] = field(default_factory=dict)  # vocab -> terms (hard)
    exclude: dict[str, list[str]] = field(default_factory=dict)  # vocab -> terms (hard negative)
    filters: dict[str, Any] = field(default_factory=dict)        # typed hard filters
    rights: dict[str, Any] = field(default_factory=dict)         # intended use
    place: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limit: int | None = None                                     # "three cutaways" -> 3
    prefer_people: int | None = None                             # soft: at least this many people
    context: str = ""                                            # e.g. the interview line B-roll should cover

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


NUM = r"(\d+(?:\.\d+)?)"
DURATION_PATTERNS = [
    (re.compile(rf"\b(?:at least|min(?:imum)?|longer than|more than|over|>=?)\s*{NUM}\s*(?:s|sec|secs|seconds?)\b"), "min"),
    (re.compile(rf"\b{NUM}\s*(?:s|sec|secs|seconds?)\s*(?:\+|or (?:more|longer)|plus)"), "min"),
    (re.compile(rf"\b(?:at most|max(?:imum)?|shorter than|less than|under|<=?)\s*{NUM}\s*(?:s|sec|secs|seconds?)\b"), "max"),
    (re.compile(rf"\b{NUM}\s*(?:-|to)\s*{NUM}\s*(?:s|sec|secs|seconds?)\b"), "range"),
]
RES = [(re.compile(r"\b(8k|4320p)\b"), 4320), (re.compile(r"\b(6k)\b"), 3160), (re.compile(r"\b(4k|uhd|2160p)\b"), 2160),
       (re.compile(r"\b(2\.7k|1440p|qhd)\b"), 1440), (re.compile(r"\b(1080p?|full hd|fhd)\b"), 1080), (re.compile(r"\b(720p|hd)\b"), 720)]
FPS = re.compile(rf"\b{NUM}\s*(?:fps|p(?=\b)|frames per second)")
PEOPLE_NONE = re.compile(r"\b(no|without|zero|empty of) (people|person|persons|humans|crowds?)\b|\b(nobody|no one|empty|deserted|unpeopled)\b")
PEOPLE_ONE = re.compile(r"\b(one|single|a single|1|lone|solo) (person|man|woman|people|presenter|subject)\b")
PEOPLE_SOME = re.compile(r"\b(people|person|crowd|crowds|busy|man|woman|men|women|kids|children|family|families|couple)\b")
PEOPLE_MANY = re.compile(r"\b(crowd|crowds|crowded|busy|packed|lots of people|many people)\b")
NEG = re.compile(r"\b(?:no|not|without|exclude|excluding|except)\s+([a-z][a-z ]{1,30}?)(?=,|\.|$| and | or | but | with )")
CLEARED = re.compile(r"\b(?:cleared|licensed|allowed|ok|approved|safe|usable|can use|able to use|we can use|permitted)\b.*?\b(?:for|on|in)\b\s+([a-z][a-z ]{2,40})")
FROM_PLACE = re.compile(r"\b(?:from|in|at|of)\s+([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,2})")
COVER = re.compile(r"\b(?:under|over|for|to cover|covering|to go with|with)\s+(?:this|an|the|a|that|our)\s+(?:interview\s+|vo\s+|voice[- ]?over\s+)?(?:line|soundbite|quote|interview|voice[- ]?over|vo|sentence|answer)\s+(?:about|on|saying|that says|where .{0,20}? says|discussing)\s+(.+)$")
FILLER = re.compile(r"\b(what do we have|do we have|that we are actually|that we're actually|that we are|we are|actually|that would work|would work|which of these|of these)\b")
TECH = [(re.compile(r"\b(vertical|portrait|9[:x]16)\b"), ("orientation", "vertical")), (re.compile(r"\b(horizontal|landscape|16[:x]9)\b"), ("orientation", "horizontal")),
        (re.compile(r"\b(log|flat profile|s-?log|v-?log|c-?log|apple log|ungraded)\b"), ("log", True)), (re.compile(r"\bhdr\b"), ("hdr", True)),
        (re.compile(r"\b(usable|good quality|sharp)\b"), ("usable", True)), (re.compile(r"\b(with speech|talking|dialogue|speaking)\b"), ("speech", True)),
        (re.compile(r"\b(no speech|without speech|no dialogue|no talking|silent)\b"), ("speech", False)),
        (re.compile(r"\b(no music|without music)\b"), ("music", False)), (re.compile(r"\b(with music)\b"), ("music", True))]


def _phrase_map() -> list[tuple[str, str, str]]:
    reg = registry()
    out = [(p, v, t) for p, v, t in reg.phrase_index() if v in SEARCH_VOCABS + RIGHTS_VOCABS and p not in AMBIGUOUS_SKIP]
    out += [(norm(k), v, t) for k, (v, t) in EXTRA.items()]
    out.sort(key=lambda x: -len(x[0]))
    return out


_PM: list[tuple[str, str, str]] | None = None


def phrase_map() -> list[tuple[str, str, str]]:
    global _PM
    if _PM is None:
        _PM = _phrase_map()
    return _PM


def parse(q: str) -> Parsed:
    raw = q.strip()
    p = Parsed(text=raw)
    low = " " + raw.lower().replace("’", "'") + " "
    # Places: capitalised words after from/in/at (before lower-casing).
    for m in FROM_PLACE.finditer(raw):
        place = m.group(1).strip()
        if norm(place) not in {norm(x[0]) for x in phrase_map()[:0]} and place.lower() not in STOP and len(place) > 2:
            p.place.append(place)
    mm = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+(?:[a-z-]+\s+){0,3}?(shots|clips|cutaways|options|takes|b-?roll|inserts|wides|close-?ups)\b", low)
    if mm:
        words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        p.limit = words.index(mm.group(1)) + 1 if mm.group(1) in words else int(mm.group(1))
    # "B-roll under this interview line about X": X is what the footage must show.
    m = COVER.search(low)
    if m:
        p.context = m.group(1).strip(" .?!")
        low = low[:m.start()] + " " + low[m.end():]
    # Rights intent.
    m = CLEARED.search(low)
    if m:
        target = norm(m.group(1))
        for phrase, vocab, term in phrase_map():
            if vocab in RIGHTS_VOCABS and re.search(rf"\b{re.escape(phrase)}\b", target):
                p.rights.setdefault("channel" if vocab == "channel" else "use", term)
        if not p.rights:
            p.notes.append(f"Could not map '{m.group(1).strip()}' to a usage or channel term.")
        low = low[:m.start()] + " " + low[m.end():]
    # Durations.
    for rx, kind in DURATION_PATTERNS:
        for mm in rx.finditer(low):
            if kind == "min":
                p.filters["min_duration"] = float(mm.group(1))
            elif kind == "max":
                p.filters["max_duration"] = float(mm.group(1))
            else:
                p.filters["min_duration"], p.filters["max_duration"] = float(mm.group(1)), float(mm.group(2))
            low = low.replace(mm.group(0), " ")
    for rx, h in RES:
        if rx.search(low):
            p.filters["min_height"] = h
            low = rx.sub(" ", low)
            break
    if (mm := FPS.search(low)):
        fps = float(mm.group(1))
        if fps >= 15:
            p.filters["min_fps"] = fps - 0.5
            low = low.replace(mm.group(0), " ")
    for rx, (k, v) in TECH:
        if rx.search(low):
            p.filters[k] = v
            low = rx.sub(" ", low)
    # People.
    if PEOPLE_NONE.search(low):
        p.filters["max_people"] = 0
        low = PEOPLE_NONE.sub(" ", low)
    elif (mm := PEOPLE_ONE.search(low)):
        p.filters["min_people"], p.filters["max_people"] = 1, 1
        low = low.replace(mm.group(0), " ")
    elif re.search(r"\b(with|including|showing) (people|a person|someone|crowds?)\b|\bpeople in (shot|frame)\b", low):
        p.filters["min_people"] = 1
    elif PEOPLE_MANY.search(low):
        p.prefer_people = 4
    elif PEOPLE_SOME.search(low):
        p.prefer_people = 1
    # Negated vocabulary terms ("not at night", "without text").
    for mm in NEG.finditer(low):
        frag = " " + norm(mm.group(1)) + " "
        for phrase, vocab, term in phrase_map():
            if vocab in SEARCH_VOCABS and f" {phrase} " in frag:
                p.exclude.setdefault(vocab, []).append(term)
                low = low.replace(mm.group(0), " ")
                break
    # Vocabulary phrases, longest first.
    work = " " + norm(low) + " "
    for phrase, vocab, term in phrase_map():
        if vocab not in SEARCH_VOCABS:
            continue
        pat = f" {phrase} "
        if pat in work:
            lst = p.prefer.setdefault(vocab, [])
            if term not in lst:
                lst.append(term)
            work = work.replace(pat, " | ")
    # "slow motion" also implies slow pace preference only if "slow" was not separately used.
    rest = [w for w in work.replace("|", " ").split() if w not in STOP and len(w) > 1 and not w.isdigit()]
    p.keywords = rest
    # Semantic intent: the original phrase minus purely technical constraints.
    sem = raw
    for rx, _ in DURATION_PATTERNS:
        sem = rx.sub(" ", sem.lower())
    for rx, _h in RES:
        sem = rx.sub(" ", sem)
    sem = PEOPLE_NONE.sub(" ", sem)
    sem = CLEARED.sub(" ", sem)
    sem = COVER.sub(" ", sem)
    sem = FILLER.sub(" ", sem)
    if p.context:
        sem = p.context
    sem = re.sub(r"\b(find|show me|give me|get me|i need|we need|looking for|what do we have|which of these)\b", " ", sem)
    p.semantic = re.sub(r"\s+", " ", re.sub(r"[,.;]+", " ", sem)).strip()
    return p
