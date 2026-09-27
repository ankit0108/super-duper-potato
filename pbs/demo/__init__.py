"""An offline 'world' (feeds + model replies) for tests and the desk demo.

`MockWeb` serves recorded-style RSS, Atom and JSON responses for the seed sources, so the real
pipeline can run end to end without network access: `pbs demo` uses it to build the desk demo data.
"""
