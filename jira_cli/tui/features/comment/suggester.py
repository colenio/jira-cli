"""Mention completion for comment input."""

from textual.suggester import Suggester


class MentionSuggester(Suggester):
    """Complete the final @mention while preserving the rest of the comment."""

    def __init__(self, candidates: list[str], aliases: dict[str, str] | None = None):
        super().__init__(use_cache=False, case_sensitive=False)
        self.candidates = candidates
        self.aliases = aliases or {}

    async def get_suggestion(self, value: str) -> str | None:
        token_start = value.rfind("@")
        if token_start < 0:
            return None

        token = value[token_start + 1 :]
        if any(char.isspace() for char in token):
            return None

        token_lower = token.casefold()
        for candidate in self.candidates:
            if candidate.casefold().startswith(token_lower) and candidate.casefold() != token_lower:
                replacement = self.aliases.get(candidate, candidate)
                return f"{value[:token_start]}@{replacement}"
        return None
