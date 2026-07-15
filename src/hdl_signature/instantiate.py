"""Renders a parsed Signature as an instantiation-template snippet body.

The output is a complete instance label, generic map, and port map, with
tabstop placeholders (`$n` / `${n:default}`, the TextMate/UltiSnips
convention) already embedded. The caller - currently an nvim UltiSnips `!p`
block - passes the returned string straight to its snippet-expansion call;
no snippet-engine-specific logic is needed on that side.
"""

from typing import Callable

from hdl_signature._snippet import _Style
from hdl_signature.ir import Language, Signature

from . import _vhdl_instantiate


def render_instantiation(
    signature: Signature,
    *,
    prefill: bool = True,
    tabstop: bool = True,
    align: bool = True,
) -> str:
    """Renders signature as an instantiation-template snippet body.

    prefill: pre-fill each map entry's right-hand side - with the port's own
    name for a port, or the generic's declared default expression for a
    generic (left blank if it has none, regardless of this flag).
    tabstop: make each map entry's right-hand side a snippet tabstop
    (`$n`/`${n:...}`) rather than plain committed text.
    align: pad every map entry's left-hand name, within its own map, to the
    longest name in that map, so every `=>` lines up in a column.

    The instance label and library name are always tabstops, always
    pre-filled, regardless of these three flags - unlike a map entry's
    right-hand side, no plain-text form of them is offered.

    Raises NotImplementedError if signature.language has no renderer yet.
    """
    style = _Style(prefill=prefill, tabstop=tabstop, align=align)
    try:
        renderer = _RENDERERS[signature.language]
    except KeyError:
        language = signature.language.value
        raise NotImplementedError(
            f"instantiation rendering for {language} is not implemented yet"
        )
    return renderer(signature, style)


_RENDERERS: dict[Language, Callable[[Signature, _Style], str]] = {
    Language.VHDL: _vhdl_instantiate.render_vhdl_instantiation,
}
