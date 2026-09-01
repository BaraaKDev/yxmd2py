"""Plugin-string -> ToolSpec resolution. THE single extension point.

Keyed by the middle token of the Plugin attribute
("AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect" -> "AlteryxSelect") because vendor
prefixes vary across Designer versions while the tool name is stable. When a real
workflow reveals a variant string, supporting it is one ALIASES line or one register()
call — nothing else changes.

resolve() never raises: unknown plugins get a stub ToolSpec so translation always
completes and the gap is reported instead of crashing.
"""

from __future__ import annotations

from .model import Node
from .spec import Emission, ToolSpec, TranslationContext, stub_emission

REGISTRY: dict[str, ToolSpec] = {}

# Known variant spellings -> canonical registry key.
ALIASES: dict[str, str] = {
    "BrowseV2": "Browse",
}

# Recognized, deliberately skipped, counted in the report — data no-ops.
# ToolContainer is organizational: its children are real nodes collected by the
# parser; the container itself produces no data.
IGNORED: set[str] = {"Browse", "ToolContainer"}


def register(key: str, spec: ToolSpec) -> None:
    REGISTRY[key] = spec


def plugin_token(plugin: str) -> str:
    """Middle token of the dotted plugin string; the whole string if not dotted."""
    parts = [p for p in plugin.split(".") if p]
    if len(parts) >= 2:
        return parts[1]
    return plugin.strip()


def _stub_translate(node: Node, ctx: TranslationContext) -> Emission:
    return stub_emission(
        node, ctx, reason=f"unsupported tool (plugin '{node.plugin or 'unknown'}')",
        display="Unknown tool",
    )


STUB_SPEC = ToolSpec(
    kind="stub", in_ports=("Input",), out_ports=("Output",),
    translate=_stub_translate, label="Unknown tool",
)

IGNORE_SPEC = ToolSpec(
    kind="ignore", in_ports=("Input",), out_ports=(),
    translate=_stub_translate,  # never called for ignored tools
    label="No-op",
)


def resolve(plugin: str) -> ToolSpec:
    # Everything under AlteryxGuiToolkit.* is canvas furniture, not a data tool:
    # Browse, Tool Containers, HtmlBox comment boxes, and the macro-interface
    # family (TextBox, Action, Questions.*, Error). None of them transforms the
    # data stream, and ignoring them also stops an Action tool's configuration
    # arrows from being counted as data inputs on the tool they point at.
    if plugin.startswith("AlteryxGuiToolkit."):
        return IGNORE_SPEC
    token = plugin_token(plugin)
    token = ALIASES.get(token, token)
    if token in IGNORED:
        return IGNORE_SPEC
    if token in REGISTRY:
        return REGISTRY[token]
    return STUB_SPEC
