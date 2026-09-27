"""Reclamation Evidence Ledger pipeline.

Stages: sites -> imagery -> indices -> change -> packet -> render.
Each stage reads the previous stage's output and writes self-describing
artifacts. Nothing is a black box: raw evidence is kept, transforms logged.
"""
