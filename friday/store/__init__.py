"""Persistence layer (G4): the single-writer SQLite store, preferences,
audit, and retention. Nothing here touches CUDA and nothing binds a socket
(T6/ADR-018); it is local disk state only.
"""
