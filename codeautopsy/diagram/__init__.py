"""
diagram/__init__.py — Phase 6 Architecture Diagram Engine

Converts Phase 2 output to interactive Mermaid.js diagrams.
"""

from .mermaid_generator import generate_mermaid_diagram

__all__ = ["generate_mermaid_diagram"]
