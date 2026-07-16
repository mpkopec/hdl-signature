"""VHDL-specific declaration-block rendering.

Lays out a full entity or component declaration (header, generic clause,
port clause, end) with a Jinja2 template. Unlike _vhdl_instantiate.py, none
of _snippet.py's tabstop/prefill machinery is involved here: a declaration's
generic and port lines are a verbatim restatement of the entity's own
interface, not a map entry with a caller-chosen right-hand side, so there is
nothing for a snippet-engine tabstop to stand in for.
"""

import jinja2

from hdl_signature.ir import Generic, PurePort, Signature

_TEMPLATE = jinja2.Template(
    "{{ keyword }} {{ name }} is\n"
    "{% if generics %}"
    "  generic (\n"
    "{% for g in generics %}"
    '    {{ g.name }} : {{ g.rest }}{{ ";" if not loop.last }}\n'
    "{% endfor %}"
    "  );\n"
    "{% endif %}"
    "{% if ports %}"
    "  port (\n"
    "{% for p in ports %}"
    '    {{ p.name }} : {{ p.rest }}{{ ";" if not loop.last }}\n'
    "{% endfor %}"
    "  );\n"
    "{% endif %}"
    "end {{ keyword }} {{ name }};\n",
    trim_blocks=True,
    lstrip_blocks=True,
)


def _generic_rows(generics: tuple[Generic, ...]) -> list[dict[str, str]]:
    """Builds one templated row per generic: its name and its type/default.

    name is padded to the width of the longest generic name, so every ":"
    lines up in a column - the same alignment render_instantiation offers
    behind an `align` flag, but unconditional here since a declaration has
    no other style to weigh it against.
    """
    width = max((len(g.name) for g in generics), default=0)
    rows = []
    for g in generics:
        rest = g.type or ""
        if g.default:
            rest += f" := {g.default}"
        rows.append({"name": g.name.ljust(width), "rest": rest})
    return rows


def _port_rows(ports: tuple[PurePort, ...]) -> list[dict[str, str]]:
    """Builds one templated row per port: its name and its direction/type/default.

    Both name and direction are padded independently to their own longest
    value, so the ":" column and the type column each line up - a port row
    has two alignable fields where a generic row only has one, since a
    generic has no direction.
    """
    name_width = max((len(p.name) for p in ports), default=0)
    dir_width = max((len(p.direction.value) for p in ports), default=0)
    rows = []
    for p in ports:
        rest = f"{p.direction.value.ljust(dir_width)} {p.type or ''}"
        if p.default:
            rest += f" := {p.default}"
        rows.append({"name": p.name.ljust(name_width), "rest": rest})
    return rows


def render_vhdl_declaration(signature: Signature, keyword: str) -> str:
    """Renders signature as a full VHDL declaration block (no tabstops).

    signature.language must be Language.VHDL. keyword is "entity" or
    "component" - selects the opening/closing keyword pair; the generic/port
    clause bodies are identical either way, since both restate the same
    interface. Every generic/port line is committed plain text - there is
    no caller-supplied value anywhere in a declaration, unlike a map entry's
    right-hand side in render_instantiation.
    """
    return _TEMPLATE.render(
        keyword=keyword,
        name=signature.name,
        generics=_generic_rows(signature.generics),
        ports=_port_rows(signature.ports),
    )
