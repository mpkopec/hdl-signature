"""VHDL-specific instantiation-template rendering.

Lays out a direct entity instantiation (`label : entity lib.name`) with a
Jinja2 template, on top of the shared tabstop/prefill machinery in
_snippet.py.
"""

import itertools

import jinja2

from hdl_signature._snippet import _Style, _build_map_entries
from hdl_signature.ir import Signature

_TEMPLATE = jinja2.Template(
    "{{ label }} : entity {{ library }}.{{ entity_name }}\n"
    "{% if generics %}"
    "  generic map (\n"
    "{% for entry in generics %}"
    '    {{ entry.name }} => {{ entry.rhs }}{{ "," if not loop.last }}\n'
    "{% endfor %}"
    "  )\n"
    "{% endif %}"
    "{% if ports %}"
    "  port map (\n"
    "{% for entry in ports %}"
    '    {{ entry.name }} => {{ entry.rhs }}{{ "," if not loop.last }}\n'
    "{% endfor %}"
    "  )\n"
    "{% endif %}",
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_vhdl_instantiation(signature: Signature, style: _Style) -> str:
    """Renders signature as a direct VHDL entity instantiation.

    signature.language must be Language.VHDL.
    """
    tabstop_counter = itertools.count(1)

    # The instance label and library name have no plain-text form - always a
    # tabstop, always pre-filled, unlike a map entry's right-hand side.
    n = next(tabstop_counter)
    label = f"${{{n}:{signature.name}_inst}}"
    n = next(tabstop_counter)
    library = f"${{{n}:work}}"

    generics = _build_map_entries(
        [(g.name, g.default) for g in signature.generics], style, tabstop_counter
    )
    ports = _build_map_entries(
        [(p.name, p.name) for p in signature.ports], style, tabstop_counter
    )

    body = _TEMPLATE.render(
        label=label,
        library=library,
        entity_name=signature.name,
        generics=generics,
        ports=ports,
    )
    # The template can't cleanly own the trailing ";" - which clause ends up
    # last (generic map, port map, or just the header) varies - so it's
    # appended here instead, the same boundary the hand-written version had.
    return body.rstrip() + ";\n$0"
