"""Tool translators. Importing this package registers every supported tool.

Registration lives here (not in each module) so the registry keys — the plugin-string
middle tokens — are visible in one place next to the specs they map to.
"""

from .. import registry
from . import filter_tool, formula, io_tools, join, sample, select, sort, summarize, textinput, union, unique

registry.register("TextInput", textinput.SPEC)
registry.register("DbFileInput", io_tools.INPUT_SPEC)
registry.register("DbFileOutput", io_tools.OUTPUT_SPEC)
registry.register("AlteryxSelect", select.SPEC)
registry.register("Filter", filter_tool.SPEC)
registry.register("Sort", sort.SPEC)
registry.register("Unique", unique.SPEC)
registry.register("Sample", sample.SPEC)
registry.register("Union", union.SPEC)
registry.register("Join", join.SPEC)
registry.register("Summarize", summarize.SPEC)
registry.register("Formula", formula.SPEC)
