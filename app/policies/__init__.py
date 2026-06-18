"""Tunable decision policies.

Isolating these constants (source authority, freshness TTLs, salience weights,
resolution rule order) from the algorithms makes the system's *judgment* legible
and adjustable without touching control flow — exactly what a reviewer wants to
inspect and what an operator would tune in production.
"""
