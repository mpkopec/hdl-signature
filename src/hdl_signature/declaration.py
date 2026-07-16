"""Renders a parsed Signature as a full entity or component declaration block.

The output is a complete header, generic clause, and port clause, ending in
"end entity name;" or "end component name;" - unlike instantiate.py's
output, every line is committed plain text, since a declaration restates the
entity's own interface verbatim rather than prompting for per-instance
values. Intended uses include pasting a component declaration into an
architecture's declarative part, or reproducing an entity's own header
elsewhere.
"""

from typing import Callable

from hdl_signature.ir import Language, Signature

from . import _vhdl_declaration


def render_declaration(signature: Signature, *, keyword: str = "entity") -> str:
    """Renders signature as a full declaration block: header, generic clause,
    port clause, end - with no tabstop placeholders.

    keyword: "entity" (the default) to reproduce the entity's own
    declaration verbatim, or "component" to produce a component declaration
    for an architecture's declarative part. The two forms share an
    identical body; only the opening/closing keyword differs, so this is
    one function rather than a render_component/render_entity pair.

    Unlike render_instantiation, there is no prefill/tabstop/align style to
    choose - a declaration has no per-instance values to prompt for, so the
    output is always fully-formed, static text. Column alignment (padding
    generic/port names to the widest in their own clause) is unconditional,
    not a flag, for the same reason: there is no "unaligned" mode a caller
    would ever want here.

    Raises NotImplementedError if signature.language has no renderer yet.
    Raises ValueError if keyword is not "entity" or "component".
    """
    if keyword not in ("entity", "component"):
        raise ValueError(f'keyword must be "entity" or "component", got {keyword!r}')
    try:
        renderer = _RENDERERS[signature.language]
    except KeyError:
        language = signature.language.value
        raise NotImplementedError(
            f"declaration rendering for {language} is not implemented yet"
        )
    return renderer(signature, keyword)


_RENDERERS: dict[Language, Callable[[Signature, str], str]] = {
    Language.VHDL: _vhdl_declaration.render_vhdl_declaration,
}
