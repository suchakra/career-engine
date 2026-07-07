"""FastAPI transport layer for CareerEngine.

Thin, resource-oriented HTTP surface over the existing async stores and the
identity boundary. No business logic lives here — handlers verify the caller,
then delegate to the domain. See ARCHITECTURE.md §16 (AD-16.1 … AD-16.4).
"""

from __future__ import annotations
