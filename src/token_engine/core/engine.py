"""Main Token Engine facade."""

from __future__ import annotations

import json
from pathlib import Path

from token_engine.core.config import EngineConfig
from token_engine.core.types import ContentItem, ContentType, OptimizationResult
from token_engine.optimizer.context_optimizer import ContextOptimizer
from token_engine.tokenizer.tiktoken_tokenizer import create_tokenizer
from token_engine.compressor.detect import detect_content_type


class TokenEngine:
    """Unified entry point for token analysis and optimization."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self.tokenizer = create_tokenizer(self.config.encoding)
        self._optimizer = ContextOptimizer(self.config, self.tokenizer)

    def optimize(self, text: str, *, content_type: str = "") -> OptimizationResult:
        return self._optimizer.optimize_text(text, content_type=content_type)

    def optimize_context(self, items: list[ContentItem] | list[dict]) -> OptimizationResult:
        if items and isinstance(items[0], dict):
            items = [ContentItem(**self._normalize_item_dict(d)) for d in items]
        return self._optimizer.optimize_items(items)

    def optimize_context_file(self, path: str | Path) -> OptimizationResult:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_items = data if isinstance(data, list) else data.get("items", [])
        return self.optimize_context(raw_items)

    def analyze(self, text: str) -> OptimizationResult:
        item = ContentItem(id="input", content=text, token_count=self.tokenizer.count(text))
        report = self._optimizer.analyze([item])
        return OptimizationResult(content=text, analysis=report)

    def analyze_project(self, directory: str | Path, *, extensions: list[str] | None = None) -> OptimizationResult:
        directory = Path(directory)
        exts = extensions or [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md", ".json", ".yaml", ".yml"]
        files: dict[str, str] = {}

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in exts:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 500_000:
                    content = content[:500_000] + "\n... [truncated for analysis]"
                files[str(path.relative_to(directory))] = content
            except OSError:
                continue

        items = [
            ContentItem(
                id=path,
                content=content,
                source=path,
                content_type=detect_content_type(content),
                token_count=self.tokenizer.count(content),
                metadata={"path": path},
            )
            for path, content in files.items()
        ]

        report = self._optimizer.analyze(items)
        return OptimizationResult(content="", analysis=report, items=items)

    def count_tokens(self, text: str) -> int:
        return self.tokenizer.count(text)

    def compact_tool_schemas(self, tools: list[dict]) -> tuple[list[dict], dict]:
        return self._optimizer.compact_tool_schemas(tools)

    def retrieve_compressed(self, handle: str) -> str | None:
        return self._optimizer.retrieve_ccr(handle)

    def estimate_cost(self, input_tokens: int, output_tokens: int = 0) -> float:
        inp = input_tokens * self.config.input_cost_per_million / 1_000_000
        out = output_tokens * self.config.output_cost_per_million / 1_000_000
        return inp + out

    @staticmethod
    def _normalize_item_dict(d: dict) -> dict:
        out = dict(d)
        if "content_type" in out and isinstance(out["content_type"], str):
            out["content_type"] = ContentType(out["content_type"])
        return out

    @classmethod
    def from_config_file(cls, path: str | Path) -> TokenEngine:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(EngineConfig.from_dict(data))

    @classmethod
    def default(cls) -> TokenEngine:
        """Engine with full default stack enabled."""
        defaults_path = Path(__file__).resolve().parents[3] / "config" / "token-engine.defaults.json"
        if defaults_path.exists():
            return cls.from_config_file(defaults_path)
        return cls(EngineConfig.default())
