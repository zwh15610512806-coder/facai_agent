"""Generic persistent synchronization primitives.

Provider-specific connectors deliberately live outside this package.  The queue
contains identifiers and sanitized work descriptions only; it performs no
network I/O.
"""
