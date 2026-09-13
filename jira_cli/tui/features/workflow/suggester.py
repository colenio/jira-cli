"""Action suggester for transition and assign auto-completion in TUI."""

from textual.suggester import Suggester


class ActionSuggester(Suggester):
    """Prefix suggester for candidate strings (e.g. status names, user names/handles)."""

    def __init__(self, candidates: list[str]):
        super().__init__(use_cache=False, case_sensitive=False)
        self.candidates = candidates

    async def get_suggestion(self, value: str) -> str | None:
        val = value.strip()
        if not val:
            return None

        prefix = ""
        target_val = val
        if "|" in val:
            parts = val.split("|", 1)
            prefix = parts[0].strip() + " | "
            target_val = parts[1].strip()
            if not target_val:
                return None

        target_lower = target_val.casefold()

        # 1. First try exact prefix match
        for candidate in self.candidates:
            cand_lower = candidate.casefold()
            if cand_lower.startswith(target_lower) and cand_lower != target_lower:
                return f"{prefix}{candidate}" if prefix else candidate

        # 2. Try substring match if no prefix match
        for candidate in self.candidates:
            cand_lower = candidate.casefold()
            if target_lower in cand_lower and cand_lower != target_lower:
                return f"{prefix}{candidate}" if prefix else candidate

        return None
