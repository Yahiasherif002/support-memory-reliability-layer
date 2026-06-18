"""Layer 2 — deterministic fact extraction (payload + text), keyed by source."""

from app.services.extraction.rules import ExtractorRegistry, RuleExtractor, default_registry

__all__ = ["ExtractorRegistry", "RuleExtractor", "default_registry"]
