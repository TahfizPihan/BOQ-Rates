"""Exact and conservative fuzzy matching against loaded rate schedules."""
import re

from rapidfuzz import fuzz, process

from db import norm_code, norm_unit

AGENCY_PRIORITY = {"PWD": 0, "LGED": 1, "RHD": 2}


def desc_key(s):
    """Text reduced to letters and digits (ratios and decimals are retained)."""
    s = str(s or "").lower().replace("&", "and")
    s = re.sub(r"(?<!\d)[.:]|[.:](?!\d)", "", s)
    return re.sub(r"[^a-z0-9.:]+", "", s)


def _words(s):
    return re.sub(r"[^a-z0-9 ]+", " ", str(s or "").lower())


def _specs(s):
    s = str(s or "").lower().replace(" ", "")
    ratios = set(re.findall(r"\d+(?:\.\d+)?(?:[:/]\d+(?:\.\d+)?)+", s))
    dimensions = set(re.findall(r"\d+(?:\.\d+)?(?:mm|cm|mpa|psi|kg|m3|m2)", s))
    return ratios, dimensions


def is_distinct_code(tok):
    """Item codes look like 4.1.2 or A-12. Plain serial numbers are not codes."""
    tok = tok.strip(" .,;:()[]")
    if not tok or not re.search(r"\d", tok) or re.fullmatch(r"\d+", tok) or re.fullmatch(r"\d+\.0+", tok):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-/]*", tok)) and bool(re.search(r"[.\-/A-Za-z]", tok))


def description_codes(desc):
    desc = str(desc or "").strip()
    found = []
    m = re.match(r"^\(?\[?([A-Za-z0-9][A-Za-z0-9.\-/]*)[\])]?\s*[.:\-]+\s*\S", desc)
    if m and is_distinct_code(m[1]):
        found.append(m[1])
    for m in re.finditer(r"(?:item|code|sor|ref)\.?\s*(?:no\.?)?\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9.\-/]*\d)", desc, re.I):
        if is_distinct_code(m[1]):
            found.append(m[1])
    return found


def strip_leading_code(desc):
    m = re.match(r"^\(?\[?([A-Za-z0-9][A-Za-z0-9.\-/]*)[\])]?\s*[.:\-]+\s*(\S.*)$", str(desc or "").strip(), re.S)
    return m[2] if m and is_distinct_code(m[1]) else desc


class ExactMatcher:
    def __init__(self, items):
        ranked = sorted(sorted(items, key=lambda i: str(i["edition"]), reverse=True),
                        key=lambda i: AGENCY_PRIORITY.get(i["agency"].upper(), 9))
        self.items = ranked
        self.by_key, self.by_code = {}, {}
        for it in ranked:
            self.by_key.setdefault(desc_key(it["description"]), []).append(it)
            if it.get("code"):
                self.by_code.setdefault(norm_code(it["code"]), []).append(it)

    @staticmethod
    def _pick(cands):
        best = cands[0]
        return best, any(abs(c["rate"] - best["rate"]) > 0.005 for c in cands[1:])

    def suggest(self, desc, unit=None, limit=3):
        """Return ranked suggestions for human review; suggestions never auto-fill a price."""
        query = _words(strip_leading_code(desc))
        if not query:
            return []
        candidates = process.extract(query, [_words(i["description"]) for i in self.items],
                                     scorer=fuzz.WRatio, limit=min(12, len(self.items)))
        ranked, seen = [], set()
        query_unit = norm_unit(unit)
        query_ratios, query_dims = _specs(desc)
        for _, score, index in candidates:
            item = self.items[index]
            item_unit = norm_unit(item.get("unit"))
            ratios, dimensions = _specs(item["description"])
            # Avoid suggesting different concrete mix ratios, sizes, or known units as equivalent.
            if query_ratios and ratios and query_ratios != ratios:
                continue
            if query_dims and dimensions and query_dims != dimensions:
                continue
            if query_unit and item_unit and query_unit != item_unit:
                continue
            identity = (item["agency"], item["edition"], item.get("code"), item["description"])
            if identity in seen:
                continue
            seen.add(identity)
            ranked.append({"agency": item["agency"], "edition": item["edition"], "code": item.get("code") or "",
                           "description": item["description"], "unit": item.get("unit") or "",
                           "rate": item["rate"], "score": int(score)})
            if len(ranked) >= limit:
                break
        return ranked

    def match(self, codes, desc):
        """Return kind/item/conflict/info; fuzzy suggestions are deliberately not auto-selected."""
        keys = [desc_key(desc)]
        stripped = desc_key(strip_leading_code(desc))
        if stripped not in keys:
            keys.append(stripped)
        for key in keys:
            if key and key in self.by_key:
                item, conflict = self._pick(self.by_key[key])
                return "DESC", item, conflict, ""
        tried = []
        for code in list(codes) + description_codes(desc):
            candidates = self.by_code.get(norm_code(code))
            if not candidates:
                continue
            tried.append(code)
            scored = sorted(candidates, key=lambda c: -fuzz.token_set_ratio(_words(desc), _words(c["description"])))
            if fuzz.token_set_ratio(_words(desc), _words(scored[0]["description"])) >= 60:
                ok = [c for c in candidates if fuzz.token_set_ratio(_words(desc), _words(c["description"])) >= 60]
                item, conflict = self._pick(ok)
                return "CODE", item, conflict, ""
        if tried:
            return "MISMATCH", None, False, tried[0]
        return "NONE", None, False, ""
