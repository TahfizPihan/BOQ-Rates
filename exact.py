"""Exact matching of a BOQ line against the rate schedules. No guessing.

A rate is used only when
  1. the BOQ description equals a schedule description (ignoring upper/lower case, spaces and punctuation), or
  2. the BOQ gives a schedule item code that exists in the schedule AND the description agrees with that item.
Anything else is left blank and reported, never filled with a "similar" item.
"""
import re

from rapidfuzz import fuzz

from db import norm_code

AGENCY_PRIORITY = {"PWD": 0, "LGED": 1, "RHD": 2}


def desc_key(s):
    """Text reduced to letters and digits (ratios such as 1:2:4 and decimals such as 1.5 are kept intact)."""
    s = str(s or "").lower().replace("&", "and")
    s = re.sub(r"(?<!\d)[.:]|[.:](?!\d)", "", s)
    return re.sub(r"[^a-z0-9.:]+", "", s)


def _words(s):
    return re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower())


def is_distinct_code(tok):
    """Item codes look like 4.1.2 or A-12. Plain serial numbers (1, 2, 3 ...) are NOT codes."""
    tok = tok.strip(" .,;:()[]")
    if not tok or not re.search(r"\d", tok) or re.fullmatch(r"\d+", tok) or re.fullmatch(r"\d+\.0+", tok):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-/]*", tok)) and bool(re.search(r"[.\-/A-Za-z]", tok))


def description_codes(desc):
    """Codes written inside the description: a leading one ('4.1.2 Brick work...') or tagged ('SOR 4.1.2', 'Item: 4.1.2')."""
    desc = str(desc or "").strip()
    found = []
    m = re.match(r"^\(?\[?([A-Za-z0-9][A-Za-z0-9.\-/]*)[\])]?[\s:.\-]+\S", desc)
    if m and is_distinct_code(m[1]):
        found.append(m[1])
    for m in re.finditer(r"(?:item|code|sor|ref)\.?\s*(?:no\.?)?\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9.\-/]*\d)", desc, re.I):
        if is_distinct_code(m[1]):
            found.append(m[1])
    return found


def strip_leading_code(desc):
    m = re.match(r"^\(?\[?([A-Za-z0-9][A-Za-z0-9.\-/]*)[\])]?[\s:.\-]+(\S.*)$", str(desc or "").strip(), re.S)
    return m[2] if m and is_distinct_code(m[1]) else desc


class ExactMatcher:
    def __init__(self, items):
        # best source first: PWD, LGED, RHD, others; newest edition first within an agency
        ranked = sorted(sorted(items, key=lambda i: i["edition"], reverse=True),
                        key=lambda i: AGENCY_PRIORITY.get(i["agency"].upper(), 9))
        self.by_key, self.by_code = {}, {}
        for it in ranked:
            self.by_key.setdefault(desc_key(it["description"]), []).append(it)
            if it["code"]:
                self.by_code.setdefault(it["code"], []).append(it)

    @staticmethod
    def _pick(cands):
        best = cands[0]
        return best, any(abs(c["rate"] - best["rate"]) > 0.005 for c in cands[1:])

    def match(self, codes, desc):
        """Returns (kind, item, conflict, info). kind: DESC | CODE | MISMATCH | NONE."""
        keys = [desc_key(desc)]
        stripped = desc_key(strip_leading_code(desc))
        if stripped not in keys:
            keys.append(stripped)
        for k in keys:
            if k and k in self.by_key:
                it, conflict = self._pick(self.by_key[k])
                return "DESC", it, conflict, ""
        tried = []
        for code in list(codes) + description_codes(desc):
            cands = self.by_code.get(norm_code(code))
            if not cands:
                continue
            tried.append(code)
            scored = sorted(cands, key=lambda c: -fuzz.token_set_ratio(_words(desc), _words(c["description"])))
            if fuzz.token_set_ratio(_words(desc), _words(scored[0]["description"])) >= 60:
                ok = [c for c in cands if fuzz.token_set_ratio(_words(desc), _words(c["description"])) >= 60]
                it, conflict = self._pick(ok)
                return "CODE", it, conflict, ""
        if tried:
            return "MISMATCH", None, False, tried[0]
        return "NONE", None, False, ""
