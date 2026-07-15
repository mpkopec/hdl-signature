"""VHDL entity-declaration adapter: tree-sitter CST to hdl_signature.ir.Signature.

Internal module - callers go through hdl_signature.parser.parse_string /
parse_file, which dispatch here for Language.VHDL. The tree-sitter CST shape
this module assumes, and the algorithm that walks it, are documented in
_vhdl.md alongside this file, not here - the docstrings below state each
function's contract only (arguments, return value, edge cases).
"""

from typing import NamedTuple

import tree_sitter
import tree_sitter_vhdl

from hdl_signature._cst import first_child_of_type, node_text
from hdl_signature.ir import Direction, Generic, Language, PurePort, Signature

_LANGUAGE = tree_sitter.Language(tree_sitter_vhdl.language())
_PARSER = tree_sitter.Parser(_LANGUAGE)

_DIRECTION_BY_MODE = {
    "in": Direction.IN,
    "out": Direction.OUT,
    "inout": Direction.INOUT,
    "buffer": Direction.BUFFER,
    "linkage": Direction.LINKAGE,
}


def parse(source_text: str) -> list[Signature]:
    """Parses every entity declaration in source_text into a Signature.

    source_text may contain multiple design units (entities, architecture
    bodies, package declarations, ...); only entity declarations produce a
    Signature, in the order they appear, and everything else is skipped. An
    entity with no generics or ports still produces a Signature, with empty
    generics/ports tuples rather than being omitted.
    """
    source_bytes = source_text.encode()
    tree = _PARSER.parse(source_bytes)

    signatures = []
    for design_unit in tree.root_node.children:
        # A design_file's design_units aren't all entities - architecture
        # bodies and package declarations are siblings at this same level,
        # and carry no interface information the IR models, so anything
        # without an entity_declaration child is skipped.
        entity_decl = first_child_of_type(design_unit, "entity_declaration")
        if entity_decl is None:
            continue

        identifier_node = first_child_of_type(entity_decl, "identifier")
        name = node_text(identifier_node, source_bytes)

        # entity_head is a required child of entity_declaration - always
        # present, even for an entity with neither generics nor ports (it
        # then holds only the "is" keyword) - confirmed empirically, so
        # unlike generic_clause/port_clause just below, no None-check here.
        entity_head = first_child_of_type(entity_decl, "entity_head")

        generic_clause = first_child_of_type(entity_head, "generic_clause")
        generics = _parse_generic_clause(generic_clause, source_bytes)

        port_clause = first_child_of_type(entity_head, "port_clause")
        ports = _parse_port_clause(port_clause, source_bytes)

        signatures.append(
            Signature(name=name, language=Language.VHDL, generics=generics, ports=ports)
        )
    return signatures


def _parse_generic_clause(
    generic_clause: tree_sitter.Node | None, source: bytes
) -> tuple[Generic, ...]:
    """Returns the Generics declared in generic_clause, or () if it is None.

    generic_clause, when given, must be a generic_clause node. One Generic is
    produced per declared name; a single declaration naming several generics
    at once (e.g. `A, B : integer := 0`) expands into that many Generics,
    each sharing the same type and default.
    """
    if generic_clause is None:
        return ()

    interface_list = first_child_of_type(generic_clause, "interface_list")
    generics = []
    for decl in interface_list.named_children:
        parsed = _parse_interface_declaration(decl, source)
        # One interface_declaration can name several generics at once, all
        # sharing the same type/default - e.g. "A, B : integer := 0" - hence
        # a name-level loop nested inside the declaration-level one.
        for name in parsed.names:
            generics.append(
                Generic(name=name, type=parsed.type_text, default=parsed.default_text)
            )
    return tuple(generics)


def _parse_port_clause(
    port_clause: tree_sitter.Node | None, source: bytes
) -> tuple[PurePort, ...]:
    """Returns the PurePorts declared in port_clause, or () if it is None.

    port_clause, when given, must be a port_clause node. One PurePort is
    produced per declared name, expanded the same way as
    _parse_generic_clause. Every declaration is assumed to carry a valid
    VHDL mode keyword (in/out/inout/buffer/linkage); any other value raises
    KeyError.
    """
    if port_clause is None:
        return ()

    interface_list = first_child_of_type(port_clause, "interface_list")
    ports = []
    for decl in interface_list.named_children:
        parsed = _parse_interface_declaration(decl, source)
        direction = _DIRECTION_BY_MODE[parsed.mode_keyword]
        for name in parsed.names:
            ports.append(
                PurePort(
                    name=name,
                    direction=direction,
                    type=parsed.type_text,
                    default=parsed.default_text,
                )
            )
    return tuple(ports)


class _ParsedInterfaceDeclaration(NamedTuple):
    """The four pieces of one VHDL interface_declaration (a generic or a port).

    A plain 4-tuple would force every caller to remember positional order;
    this names each field instead. mode_keyword is None for generics (which
    have no mode at all) and for ports would never be None in valid VHDL, but
    the type stays Optional since this class describes one parsed
    declaration generically, before the caller has decided which case it is.
    """

    names: list[str]
    mode_keyword: str | None
    type_text: str | None
    default_text: str | None


def _parse_interface_declaration(
    decl: tree_sitter.Node, source: bytes
) -> _ParsedInterfaceDeclaration:
    """Parses one interface_declaration (one generic or port entry) node.

    decl must be an interface_declaration node. names holds every name the
    declaration declares (more than one when comma-separated, e.g. `A, B :
    ...`). mode_keyword is None for a generic, and for a port is a VHDL mode
    keyword (in/out/inout/buffer/linkage). type_text is None if decl has no
    type. default_text is None if decl has no `:= ...` initialiser.
    """
    identifier_list = first_child_of_type(decl, "identifier_list")
    # identifier_list's only named children are the declared names; the
    # separating "," tokens are anonymous grammar literals, so named_children
    # already excludes them without an explicit filter. Individual names can
    # still be misclassified as `library_type`/`library_function` instead of
    # `identifier` when they collide with a VHDL standard-library name
    # (jpt13653903/tree-sitter-vhdl#69) - confirmed this also misfires on
    # ordinary names with no such collision (e.g. a generic called WIDTH) -
    # so this takes every named child regardless of its specific type.
    names = [node_text(n, source) for n in identifier_list.named_children]

    mode_indication = first_child_of_type(decl, "simple_mode_indication")

    mode_node = first_child_of_type(mode_indication, "mode")
    if mode_node is None:
        # Generics have no mode keyword at all; only ports do.
        mode_keyword = None
    else:
        mode_keyword = node_text(mode_node, source)

    subtype_node = first_child_of_type(mode_indication, "subtype_indication")
    if subtype_node is None:
        type_text = None
    else:
        type_text = node_text(subtype_node, source)

    default_text = _default_text(mode_indication, source)

    return _ParsedInterfaceDeclaration(names, mode_keyword, type_text, default_text)


def _default_text(mode_indication: tree_sitter.Node, source: bytes) -> str | None:
    """Returns mode_indication's `:= <expr>` default-value text, or None.

    mode_indication must be a simple_mode_indication node. Returns None if it
    has no initialiser (no default value), otherwise the source text of the
    expression on the right-hand side of `:=`, verbatim.
    """
    initialiser = first_child_of_type(mode_indication, "initialiser")
    if initialiser is None:
        return None

    # initialiser's two named children are the ":=" operator token itself
    # (named "variable_assignment" in this grammar, despite being an
    # operator, not a variable) and the default-value expression - take
    # whichever child isn't the operator, rather than assuming a fixed
    # position.
    for child in initialiser.named_children:
        if child.type != "variable_assignment":
            return node_text(child, source)
    return None
