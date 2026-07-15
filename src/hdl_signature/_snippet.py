"""Shared machinery for building snippet-placeholder text.

None of this assumes which HDL an instantiation template is being rendered
for - every per-language renderer (currently _vhdl_instantiate.py; future
Verilog/SystemVerilog renderers the same way) builds on it: _Style carries
the three formatting choices render_instantiation exposes, _rhs renders one
map entry's right-hand side under that style, and _build_map_entries turns
a (name, prefill) list into the rows of a generic map or port map.
"""

from typing import Iterator, NamedTuple


class _Style(NamedTuple):
    """The three independent formatting choices for one rendered map entry.

    Bundled once, at the top of render_instantiation, so a per-language
    renderer and its helpers can pass one value instead of three -
    render_instantiation itself still takes prefill/tabstop/align as flat
    keyword arguments, since callers only ever set all three at once and
    constructing this type has no benefit for them.
    """

    prefill: bool
    tabstop: bool
    align: bool


def _rhs(
    tabstop_counter: Iterator[int], prefill_text: str | None, style: _Style
) -> str:
    """Renders one map entry's right-hand side under style.

    prefill_text is None when there's nothing to offer (e.g. a generic with
    no declared default) - style.prefill then has no effect, since there is
    no text to prefill with.
    """
    if style.tabstop:
        n = next(tabstop_counter)
        if style.prefill and prefill_text:
            return f"${{{n}:{prefill_text}}}"
        return f"${{{n}}}"
    return prefill_text if (style.prefill and prefill_text) else ""


def _build_map_entries(
    names_and_prefill: list[tuple[str, str | None]],
    style: _Style,
    tabstop_counter: Iterator[int],
) -> list[dict[str, str]]:
    """Builds one map_entry per (name, prefill_text) pair.

    A map_entry is one row of a generic map or port map: {"name": ...,
    "rhs": ...}, with name padded to the width of the longest name in
    names_and_prefill when style.align is set. prefill_text is the
    candidate right-hand-side text for that entry - a port's own name, or a
    generic's default expression - or None if there is none to offer.
    names_and_prefill may be empty, in which case so is the result.
    """
    width = max((len(name) for name, _ in names_and_prefill), default=0)
    width = width if style.align else 0

    return [
        {"name": name.ljust(width), "rhs": _rhs(tabstop_counter, prefill_text, style)}
        for name, prefill_text in names_and_prefill
    ]
