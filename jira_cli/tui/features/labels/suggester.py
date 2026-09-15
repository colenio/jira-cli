"""Label completion for comma-separated label inputs."""

from textual.suggester import Suggester


class LabelSuggester(Suggester):
    """Complete the label token after the final comma."""

    def __init__(self, labels: list[str]):
        super().__init__(use_cache=False, case_sensitive=False)
        self.labels = labels

    async def get_suggestion(self, value: str) -> str | None:
        prefix, separator, token = value.rpartition(",")
        query = token.strip()
        if not query:
            return None

        query_lower = query.casefold()
        for label in self.labels:
            if label.casefold().startswith(query_lower) and label.casefold() != query_lower:
                completed_prefix = f"{prefix}, " if separator else ""
                return f"{completed_prefix}{label}"
        return None
