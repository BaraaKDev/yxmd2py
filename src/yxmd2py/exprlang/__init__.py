"""Alteryx expression language -> vectorized pandas code.

The one public entry point:

    translate_expression(text, df_var) -> python code string

It either returns working code or raises ExprUnsupported — callers keep the verbatim
expression in a TODO, so nothing is ever silently guessed.
"""

from .emit import translate_expression

__all__ = ["translate_expression"]
