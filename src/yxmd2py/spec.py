"""The translator contract every tool module implements, plus shared helpers.

A translator is a function (Node, TranslationContext) -> Emission. It may raise
ConfigUnsupported; codegen catches that and downgrades the node to a passthrough stub.
It must never raise anything else on malformed config — read config only through the
cfg_* helpers, which turn missing pieces into ConfigUnsupported.

This lives at the top level (not in tools/) so that registry.py can import the
contract without triggering tools/__init__.py, whose register() calls need registry
to be fully initialized first — tools/ only ever imports downward.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .errors import ConfigUnsupported
from .model import Node

# ---------------------------------------------------------------------------
# Contract dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Emission:
    """One tool's contribution to the generated script."""

    lines: list[str]  # python source lines, unindented
    outputs: dict[str, str]  # out-port name -> DataFrame variable name
    status: Literal["ok", "partial", "stub"] = "ok"
    todos: list[str] = field(default_factory=list)  # human-readable, for the report


@dataclass
class TranslationContext:
    """Everything a translator may need beyond its own Node."""

    inputs: dict[str, str]  # in-port name -> upstream DataFrame variable
    ordered_inputs: list[tuple[str, str]]  # [(in-port, var), ...] in wire order (Union)
    consumed: set[str]  # out-port names read downstream
    var: Callable[[str], str]  # out-port name -> this node's variable name
    source_dir: Path  # directory containing the .yxmd (for relative paths)
    add_path_const: Callable[[str, str], str]  # (kind, path) -> hoisted constant name
    translate_expression: Callable[[str, str], str] | None = None  # (expr, df_var) -> code

    def sole_input(self) -> str:
        """The single input variable, for one-input tools."""
        if len(self.inputs) != 1:
            raise ConfigUnsupported(
                f"expected exactly 1 input connection, found {len(self.inputs)}"
            )
        return next(iter(self.inputs.values()))


@dataclass(frozen=True)
class ToolSpec:
    kind: str  # "select", "filter", ..., "ignore", "stub"
    in_ports: tuple[str, ...]
    out_ports: tuple[str, ...]
    translate: Callable[[Node, TranslationContext], Emission]
    label: str = ""  # human name for comments/report; defaults to kind.title()

    @property
    def display(self) -> str:
        return self.label or self.kind.title()


# ---------------------------------------------------------------------------
# Defensive config readers — the ONLY way translators touch node.config
# ---------------------------------------------------------------------------


def cfg_root(node: Node) -> ET.Element:
    if node.config is None:
        raise ConfigUnsupported("node has no <Configuration> element")
    return node.config


def cfg_find(node: Node, path: str) -> ET.Element:
    el = cfg_root(node).find(path)
    if el is None:
        raise ConfigUnsupported(f"missing <{path}> in configuration")
    return el


def cfg_findall(node: Node, path: str) -> list[ET.Element]:
    return cfg_root(node).findall(path)


def cfg_text(node: Node, path: str, default: str | None = None) -> str:
    """Text content of a config element; raises unless a default is supplied."""
    el = cfg_root(node).find(path)
    if el is None or el.text is None:
        if default is not None:
            return default
        raise ConfigUnsupported(f"missing <{path}> text in configuration")
    return el.text


def attr(el: ET.Element, name: str, default: str | None = None) -> str:
    val = el.get(name)
    if val is None:
        if default is not None:
            return default
        raise ConfigUnsupported(f"<{el.tag}> missing required attribute '{name}'")
    return val


# ---------------------------------------------------------------------------
# Emission helpers shared across tools
# ---------------------------------------------------------------------------


def pystr(value: str) -> str:
    """A safe python string literal for arbitrary field names / values."""
    return repr(value)


def col(df_var: str, field_name: str) -> str:
    return f"{df_var}[{pystr(field_name)}]"


def stub_emission(node: Node, ctx: TranslationContext, reason: str, display: str) -> Emission:
    """Passthrough placeholder: keeps downstream code runnable-ish, demands attention.

    Every consumed output port maps to the same variable so unknown port names on
    unknown tools still wire up.
    """
    var = f"df_{node.tool_id}"
    if len(ctx.inputs) == 1:
        src = next(iter(ctx.inputs.values()))
        line = f"{var} = {src}.copy()  # TODO(yxmd2py): passthrough placeholder"
    else:
        line = f"{var} = pd.DataFrame()  # TODO(yxmd2py): placeholder ({len(ctx.inputs)} inputs)"
    todo = f"{display} (ToolID {node.tool_id}): {reason}"
    lines = [
        f"# TODO(yxmd2py): NOT TRANSLATED - {reason}",
        f"# Plugin: {node.plugin or '(none)'}",
        line,
    ]
    ports = ctx.consumed or {"Output"}
    return Emission(
        lines=lines,
        outputs={port: var for port in ports},
        status="stub",
        todos=[todo],
    )
