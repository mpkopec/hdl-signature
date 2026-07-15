"""Grammar-agnostic tree-sitter node helpers, shared across per-language adapters.

Neither function below assumes anything about a specific grammar - both operate
purely on tree-sitter's generic Node API (children, type, start_byte/end_byte),
so every per-language adapter in this package (currently _vhdl.py; future
Verilog/SystemVerilog adapters the same way) uses them unchanged. See
_vhdl.md, section 3, for the algorithm walkthrough and worked examples.
"""

import tree_sitter


def first_child_of_type(
    node: tree_sitter.Node, type_name: str
) -> tree_sitter.Node | None:
    """Returns node's first direct child whose grammar type is type_name, or None."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Returns the exact source text spanned by node.

    source must be the same bytes the tree containing node was parsed from.
    """
    return source[node.start_byte : node.end_byte].decode()
