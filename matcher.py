"""Match a BOQ line to a rate-schedule item: by item code first, then by description similarity."""
import re
from rapidfuzz import fuzz, process
from db import norm_text, norm_code, norm_unit

CODE_RE = re.compile(r"[A-Za-z]{0,6}[-\s]?\d+(?:\.\d+){1,4}[A-Za-z]?|[A-Za-z]{1,6}[-/]\d+(?:[-./]\d+)*")


class Matcher:
    def __init__(self, items):
        self.items = items
        self.by_code = {}
        for it in items:
            if it["code"]:
                self.by_code.setdefault(it["code"], []).append(it)
        self.texts = [it["norm_desc"] for it in items]

    def code_candidates(self, *cells):
        found = []
        for cell in cells:
            s = str(cell or "").strip()
            if not s:
                continue
            if norm_code(s) in self.by_code:
                found.append(norm_code(s))
            for m in CODE_RE.findall(s):
                c = norm_code(m)
                if c in self.by_code and c not in found:
                    found.append(c)
        return found

    @staticmethod
    def _specs(s):
        ratios = set(re.findall(r"\d+(?:\.\d+)?(?:_\d+(?:\.\d+)?)+", s))
        dims = set(re.findall(r"\d+(?:\.\d+)?(?:mm|cm|mpa|psi|kg)", s))
        return ratios, dims

    def _spec_adjust(self, a, b):
        """Mix ratios (1:2:4) and sizes (12mm) must agree - they change the rate a lot."""
        ra, da = self._specs(a)
        rb, db_ = self._specs(b)
        adj = 0
        if ra and rb:
            adj += 6 if ra == rb else -25
        if da and db_:
            adj += 0 if da == db_ else -15
        return adj

    def _desc_score(self, a, b):
        return max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)) + self._spec_adjust(a, b)

    def match(self, item_cell, desc, unit=None, threshold=85, code_floor=45):
        """Returns dict: status (CODE / DESC / REVIEW / NONE), item, score, alternatives."""
        nd = norm_text(desc)
        nu = norm_unit(unit)

        # 1) code match, confirmed by at least a loose description similarity
        for code in self.code_candidates(item_cell, desc):
            cands = self.by_code[code]
            scored = sorted(((self._desc_score(nd, c["norm_desc"]), c) for c in cands), key=lambda x: -x[0])
            s, best = scored[0]
            if s >= code_floor:
                return {"status": "CODE" if s >= 60 else "REVIEW", "item": best, "score": round(s),
                        "note": "code match" + ("" if s >= 60 else " (description differs - check)"),
                        "alts": [c for _, c in scored[1:3]]}

        if not nd or not self.items:
            return {"status": "NONE", "item": None, "score": 0, "note": "no description", "alts": []}

        # 2) description similarity (unit-aware)
        res = process.extract(nd, self.texts, scorer=fuzz.token_set_ratio, limit=15)
        res2 = process.extract(nd, self.texts, scorer=fuzz.WRatio, limit=15)
        pool = {}
        for _, s, i in res + res2:
            pool[i] = max(pool.get(i, 0), s)
        ranked = []
        for i, s in pool.items():
            it = self.items[i]
            adj = s + self._spec_adjust(nd, it["norm_desc"])
            if nu and it["unit"]:
                adj += 4 if it["unit"] == nu else -12   # same unit boosts, different unit penalises
            ranked.append((min(adj, 100), it))
        ranked.sort(key=lambda x: -x[0])
        s, best = ranked[0]
        alts = [c for _, c in ranked[1:3]]
        if s >= threshold:
            return {"status": "DESC", "item": best, "score": round(s), "note": "description match", "alts": alts}
        if s >= 60:
            return {"status": "REVIEW", "item": best, "score": round(s), "note": "low confidence - check", "alts": alts}
        return {"status": "NONE", "item": None, "score": round(s), "note": "no similar item", "alts": ranked and [c for _, c in ranked[:3]] or []}

    def search(self, text, limit=15):
        nd = norm_text(text)
        res = process.extract(nd, self.texts, scorer=fuzz.WRatio, limit=limit)
        return [(round(s), self.items[i]) for _, s, i in res]
