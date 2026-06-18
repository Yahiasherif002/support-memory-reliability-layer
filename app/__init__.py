"""Support Memory Reliability Layer.

An event-sourced memory layer for an AI support assistant. Raw events are
immutable; structured facts are extracted and linked to evidence; current
beliefs are *derived* (never authored); contradictions, stale facts, identity
ambiguity, and idempotency conflicts are surfaced rather than silently resolved.
"""

__version__ = "0.1.0"
