"""DotEnv handling — robust loading from CWD/.env or local.env."""

import os
from pathlib import Path


class DotEnv:
    """Load environment variables from .env or local.env in CWD or parent directories."""

    def __init__(self, search_up: int = 3, verbose: bool = False):
        """
        Args:
            search_up: How many parent directories to search up for .env/local.env
            verbose: Print debug info when loading env files
        """
        self.search_up = search_up
        self.verbose = verbose
        self._loaded_from = None

    def load(self) -> dict[str, str]:
        """
        Load from .env or local.env in CWD or parent directories.
        Tries: CWD/local.env → CWD/.env → parent/local.env → parent/.env (up to search_up levels)
        
        Returns dict of loaded variables (also sets in os.environ).
        """
        cwd = Path.cwd()
        candidates = []

        # Build candidate list: current and parent dirs, prioritizing local.env
        for level in range(self.search_up + 1):
            target_dir = cwd
            for _ in range(level):
                target_dir = target_dir.parent
                if target_dir == target_dir.parent:  # Reached filesystem root
                    break

            # local.env first, then .env
            candidates.append(target_dir / "local.env")
            candidates.append(target_dir / ".env")

        loaded = {}
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                self._load_file(candidate)
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip()
                            loaded[key] = val
                            os.environ[key] = val
                
                self._loaded_from = candidate
                if self.verbose:
                    print(f"[dotenv] Loaded from {self._loaded_from}")
                return loaded

        if self.verbose:
            print("[dotenv] No .env/local.env found")

        return loaded

    def _load_file(self, path: Path) -> None:
        """Load single env file into os.environ."""
        if self.verbose:
            print(f"[dotenv] Reading {path}")

    def get(self, key: str, default: str = "") -> str:
        """Get env variable (from loaded or os.environ)."""
        return os.environ.get(key, default)

    def require(self, *keys: str) -> dict[str, str]:
        """Get multiple required env variables. Raise if any missing."""
        missing = [k for k in keys if not os.environ.get(k)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return {k: os.environ[k] for k in keys}
