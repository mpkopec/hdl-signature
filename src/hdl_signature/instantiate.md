# Instantiation-Template Snippet Renderer: Design Walkthrough

Three modules turn a `hdl_signature.ir.Signature` into an instantiation
snippet body: `instantiate.py` (public entry point and per-language
dispatch), `_snippet.py` (language-agnostic tabstop/prefill/alignment
machinery), and `_vhdl_instantiate.py` (the one VHDL-specific renderer that
exists so far). This document explains how the three fit together, from the
public function down to the single Jinja2 template that produces the text,
and is written to be read start to finish with nothing else open.

## Target shape

The input is `hdl_signature.ir.Signature` — the same IR `_vhdl.py` produces
from parsed source (see `_vhdl.md`), not VHDL text. A renderer never touches
source text or a CST; it only reads `Signature.name`, `.generics` (each a
`name`/`type`/`default`), and `.ports` (each a `name`/`direction`/`type`/
`default`).

The output is a single string: an instance label, an optional generic map,
and an optional port map, with UltiSnips/TextMate tabstop placeholders
already embedded — ready to be handed straight to a snippet engine's expand
call (`snip.expand_anon(body)` on the nvim side), with no further templating
needed by the caller.

## 1. Concepts

### Tabstop syntax

`$n` and `${n:default text}` are the placeholder syntax shared by UltiSnips,
TextMate, VSCode, and LSP snippets alike — the same two forms across all
four, which is why this library can embed them directly instead of routing
through an editor-specific API. `$n` is an empty tabstop the user's cursor
lands on in numeric order; `${n:default text}` is the same tabstop
pre-loaded with `default text`, which stays selected so the first keystroke
replaces it outright. `$0` is a special case: the final cursor position
after every numbered tabstop has been visited, not an addressable
tabstop of its own — every template in this module ends the whole snippet
body with `$0` after the closing `;`, regardless of style.

Tabstop numbers must be contiguous starting at 1 (`$1`, `$2`, `$3`, ...) for
a snippet engine to visit them in the intended order; skipping a number or
reusing one is a correctness bug, not a stylistic choice. This is why every
renderer threads a single counter through label, library, generics, and
ports, rather than numbering each section independently (Section 6).

### The three style axes

`render_instantiation` exposes three independent boolean choices, bundled
into one `_Style` value once at the top of the call. Independent means each
can be set without constraining the others — all eight combinations are
valid and produce a different, well-formed rendering:

| Axis      | `True`                                             | `False`                              |
|-----------|-----------------------------------------------------|---------------------------------------|
| `prefill` | pre-load the right-hand side (port's own name, generic's declared default) | leave the right-hand side blank |
| `tabstop` | make the right-hand side a `$n`/`${n:...}` tabstop | commit the right-hand side as plain text |
| `align`   | pad every entry's name to the longest name in its own map, so every `=>` lines up | no padding |

`prefill` and `tabstop` compose: with both set, a port's own name becomes
the *default text inside* a tabstop (`${5:clk}`) rather than committed,
uneditable text. A generic with no declared default has nothing to prefill
regardless of the `prefill` flag — Section 4 covers this as a property of
the *data*, not an extra style choice.

### `map_entry`

One row of a rendered generic map or port map — one `name => rhs` line — is
called a **map_entry** throughout this module, echoing the VHDL syntax both
kinds of row appear under (`generic map (...)`, `port map (...)`) rather
than a term borrowed from either side of the arrow alone: a port's map_entry
connects a formal port to an actual net, a generic's connects a formal
generic to an actual value, and the shared machinery in Section 4 treats
both the same way structurally, differing only in what `prefill_text` is
computed from.

### Why three modules, not one

`instantiate.py` must import each per-language renderer (`_vhdl_instantiate.
render_vhdl_instantiation`, and eventually a Verilog counterpart) to build
its dispatch table. If `_Style` and the map_entry-building helpers lived in
`instantiate.py` itself, `_vhdl_instantiate.py` would need to import them
back from there — a circular import. `_snippet.py` breaks the cycle by
holding everything both sides need, one level below both: `instantiate.py`
never imports from `_vhdl_instantiate.py`'s helpers, and `_vhdl_instantiate.
py` never imports from `instantiate.py` at all. This mirrors the existing
`_cst.py` split in the parsing side of the package (see `_vhdl.md`, Section
3): a shared, language-agnostic layer beneath the per-language modules that
use it, not inside either one.

The same split also marks what a future Verilog/SystemVerilog renderer can
reuse outright versus what it must write itself: `_snippet.py`'s tabstop
counter, prefill decision, and alignment-width computation only ever touch
fields common to every `ir.Generic`/`ir.PurePort`, so a Verilog renderer
would import `_snippet.py` unchanged. The header/label construction in
`_vhdl_instantiate.py` would not transfer — VHDL's instantiation names a
*library* (`work`) that Verilog module instantiation has no equivalent
concept for at all, so that part is necessarily per-language.

## 2. The canonical example

One `Signature`, built directly as IR (no parsing step, since a renderer's
input is already parsed), used throughout this document:

```python
Signature(
    name="fifo",
    language=Language.VHDL,
    generics=(
        Generic(name="WIDTH", type="integer", default="8"),
        Generic(name="DEPTH", type="natural"),
    ),
    ports=(
        PurePort(name="clk", direction=Direction.IN, type="std_logic"),
        PurePort(name="rst", direction=Direction.IN, type="std_logic"),
        PurePort(name="sin", direction=Direction.IN, type="std_logic"),
        PurePort(name="write", direction=Direction.IN, type="std_logic"),
        PurePort(name="dout", direction=Direction.OUT, type="std_logic_vector(...)"),
        PurePort(name="dio", direction=Direction.INOUT, type="std_logic"),
    ),
)
```

`WIDTH` has a declared default (`"8"`); `DEPTH` does not (`default=None`) —
the one detail in this example that Section 4's prefill logic depends on.
A second, minimal signature — `Signature(name="bare", language=Language.
VHDL)`, no generics or ports at all — exercises the clause-omission
behaviour in Section 6.

## 3. `render_instantiation()`: the entry point

```python
def render_instantiation(
    signature: Signature,
    *,
    prefill: bool = True,
    tabstop: bool = True,
    align: bool = True,
) -> str:
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
```

The public signature takes `prefill`/`tabstop`/`align` as flat keyword
arguments rather than a `_Style` object, since every caller sets all three
at once — there is no ergonomic benefit to a bundled type at the call site,
only internally, once the value has to be threaded through several helper
functions. Bundling happens exactly once, here, immediately after the three
flags arrive.

Dispatch on `signature.language` mirrors `parser.py`'s own `_PARSERS` table
exactly: a plain `dict` keyed by `Language`, a `try`/`except KeyError` that
re-raises as `NotImplementedError` naming the missing language. `_RENDERERS`
currently has one entry; adding Verilog support later means adding one
dict entry and one new module, not touching this function's body.

## 4. `_Style` and `_rhs()`: one map_entry's right-hand side

```python
class _Style(NamedTuple):
    prefill: bool
    tabstop: bool
    align: bool


def _rhs(
    tabstop_counter: Iterator[int], prefill_text: str | None, style: _Style
) -> str:
    if style.tabstop:
        n = next(tabstop_counter)
        if style.prefill and prefill_text:
            return f"${{{n}:{prefill_text}}}"
        return f"${{{n}}}"
    return prefill_text if (style.prefill and prefill_text) else ""
```

`_Style` is a `NamedTuple` rather than a `@dataclass`, matching the existing
`_ParsedInterfaceDeclaration` convention on the parsing side (`_vhdl.md`,
Section 6) — a small, immutable, positional-or-keyword bundle with no
behaviour of its own.

`_rhs` renders exactly one map_entry's right-hand side, and is the only
place in either module that calls `next()` on the shared tabstop counter —
every other function receives already-rendered text. Its branching is
governed by two independent facts: `style.tabstop` (does this entry get a
number at all) and whether `prefill_text` exists (does this entry have
anything to prefill with). `prefill_text` is `None` for a generic with no
declared default (`DEPTH` in Section 2) — a property of the IR data, not a
style choice — so `style.prefill and prefill_text` reads as "the *style*
wants prefill, *and* there's something to prefill", short-circuiting to an
empty tabstop or empty string when there isn't:

| `style.tabstop` | `style.prefill` | `prefill_text` | Result            |
|------------------|-----------------|-----------------|--------------------|
| `True`           | `True`          | `"clk"`         | `${5:clk}`         |
| `True`           | `True`          | `None`          | `${5}`             |
| `True`           | `False`         | any             | `${5}`             |
| `False`          | `True`          | `"clk"`         | `clk`              |
| `False`          | `True`          | `None`          | `` (empty string)  |
| `False`          | `False`         | any             | `` (empty string)  |

Every branch that produces a tabstop consumes exactly one number from
`tabstop_counter` via `next()`; every branch that doesn't (the bottom three
rows) consumes none — which is exactly why the counter must be *shared*
across every `_rhs` call for one signature, and not reset per map: a
non-tabstop entry contributes no number, so the next tabstop-producing
entry, wherever it falls, still needs the next integer in sequence.

## 5. `_build_map_entries()`: one map, aligned

```python
def _build_map_entries(
    names_and_prefill: list[tuple[str, str | None]],
    style: _Style,
    tabstop_counter: Iterator[int],
) -> list[dict[str, str]]:
    width = max((len(name) for name, _ in names_and_prefill), default=0)
    width = width if style.align else 0

    return [
        {"name": name.ljust(width), "rhs": _rhs(tabstop_counter, prefill_text, style)}
        for name, prefill_text in names_and_prefill
    ]
```

Takes one map's worth of `(name, prefill_text)` pairs — the caller decides
what counts as prefill text for that map (Section 6: a port's own name, a
generic's declared default) — and returns one `map_entry` dict per pair, in
the same order. `width` is computed once per call, from every name in
*this* map only: the generic map and port map are aligned independently of
each other, each to its own longest name, never to a shared width across
both maps. `width` collapses to `0` when `style.align` is unset, which
makes `.ljust(0)` a no-op — `name` comes back unchanged, rather than a
separate unpadded code path being needed.

`names_and_prefill` can be empty (an entity with no generics, or no ports);
`max(..., default=0)` is why that case doesn't raise on an empty sequence,
and the list comprehension over an empty input simply yields `[]`.

## 6. `render_vhdl_instantiation()`: assembling one instantiation

```python
_TEMPLATE = jinja2.Template(
    "{{ label }} : {{ entity_kw }}{{ library }}{{ entity_name }}\n"
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
    tabstop_counter = itertools.count(1)

    n = next(tabstop_counter)
    label = f"${{{n}:{signature.name}_inst}}"
    n = next(tabstop_counter)
    entity_kw = f"${{{n}:entity }}"
    n = next(tabstop_counter)
    library = f"${{{n}:work.}}"
    n = next(tabstop_counter)
    entity_name = f"${{{n}:{signature.name}}}"

    generics = _build_map_entries(
        [(g.name, g.default) for g in signature.generics], style, tabstop_counter
    )
    ports = _build_map_entries(
        [(p.name, p.name) for p in signature.ports], style, tabstop_counter
    )

    body = _TEMPLATE.render(
        label=label,
        entity_kw=entity_kw,
        library=library,
        entity_name=entity_name,
        generics=generics,
        ports=ports,
    )
    return body.rstrip() + ";\n$0"
```

### The tabstop counter's lifetime

`itertools.count(1)` is created exactly once per call, at the top of
`render_vhdl_instantiation`, and threaded — the same `Iterator[int]` object,
never a fresh one — through the label, the `entity` keyword, the library,
the entity name, and both calls to `_build_map_entries` (which in turn
passes it on to every `_rhs` call). This is what keeps numbering contiguous
across sections that are otherwise built independently: the label always
claims `$1`, `entity ` always claims `$2`, the library always claims `$3`,
and the entity name always claims `$4` (all four unconditional, unaffected
by any style flag — Section 1 established these have no plain-text form at
all), with the first generic or port map_entry that produces a tabstop
picking up at `$5` and onward, whichever map it belongs to.

### Four tabstops, three instantiation styles

`entity `'s trailing space and `work.`'s trailing `.` are pre-filled *inside*
their own tabstop rather than left as literal characters in the template
between `{{ entity_kw }}` and `{{ library }}`. This is what lets either
tabstop be deleted outright, rather than deleting it leaving an orphaned
space or `.` behind for the user to clean up by hand. Three renderings are
reachable from the one snippet body, depending on which of `$2`
(`entity `)/`$3` (`work.`) the user clears while tabbing through:

| `$2` (`entity `) | `$3` (`work.`) | Result                          | VHDL form                          |
|-------------------|-----------------|----------------------------------|-------------------------------------|
| kept               | kept            | `label : entity work.fifo`      | direct entity instantiation (qualified) |
| kept               | cleared         | `label : entity fifo`           | direct entity instantiation (unqualified — `fifo` resolved as a directly visible name) |
| cleared            | cleared         | `label : fifo`                  | component instantiation (`fifo` bound to a separately declared component) |

Clearing `$3` alone and keeping `$2` is the only combination of the four
that doesn't collapse a `$2`/`$3` pair to nothing — VHDL's direct entity
instantiation accepts a bare `entity_name` in place of a library-qualified
`library.entity_name`, per the LRM's `entity_aspect` grammar, so this row is
valid VHDL rather than a leftover fragment.

### What the template does, and doesn't, decide

`trim_blocks=True` strips the newline that would otherwise follow a
`{% ... %}` tag; `lstrip_blocks=True` strips the leading whitespace before
one on the same line — together, the two mean a `{% if %}`/`{% for %}`/
`{% endif %}` line contributes no blank line or stray indentation of its
own to the output, only the lines inside it do. Without both, every control
line in the template above would leave behind an empty line where it stood.

`{% if generics %}`/`{% if ports %}` omit a whole clause — heading, entries,
and closing paren — when that list is empty, which is what makes the
`bare` signature from Section 2 render as just its header line, with
neither `generic map` nor `port map` appearing at all. `{{ "," if not loop.
last }}` places a comma after every map_entry except the last in its own
`{% for %}` loop, which is Jinja2's built-in `loop.last` — true only on a
loop's final iteration — doing the comma-joining a hand-written version
would otherwise need an index check for.

The template does not, and cannot cleanly, own the trailing `;` that closes
the whole instantiation statement: which clause ends up last — the port
map's closing `)`, the generic map's (if there are no ports), or just the
header (if there are neither) — depends on which of `generics`/`ports` is
non-empty, so there is no fixed line inside the template to attach `;` to.
`body.rstrip() + ";\n$0"` appends it afterward instead, trimming whatever
trailing newline the last rendered line left and adding the closing `;` and
the final `$0` cursor position (Section 1) in its place — the one seam in
this renderer that lives in Python rather than in the template.

## 7. Worked trace

`render_instantiation(fifo_signature)` — every style flag at its default of
`True` — renders to:

```
${1:fifo_inst} : ${2:entity }${3:work.}${4:fifo}
  generic map (
    WIDTH => ${5:8},
    DEPTH => ${6}
  )
  port map (
    clk   => ${7:clk},
    rst   => ${8:rst},
    sin   => ${9:sin},
    write => ${10:write},
    dout  => ${11:dout},
    dio   => ${12:dio}
  );
$0
```

`$1`–`$4` are the label, `entity ` keyword, library, and entity name,
unconditional per Section 6. `$5` (`WIDTH`) carries its declared default
`"8"` as prefill text; `$6` (`DEPTH`) does not, since `Generic.default` is
`None` for it — the empty-tabstop row of Section 4's table. `$7`–`$12` are
the six ports, each pre-filled with its own name, and left-padded (`clk`
through `write` to width 5, matching `write`, the longest port name) since
`style.align` defaults to `True`.

With every flag set to `False` instead, the same signature renders with no
tabstops at all past the header's four (which, as Section 1 noted, are
never subject to the three style flags), no prefill text, and no alignment
padding:

```
${1:fifo_inst} : ${2:entity }${3:work.}${4:fifo}
  generic map (
    WIDTH => ,
    DEPTH => 
  )
  port map (
    clk => ,
    rst => ,
    sin => ,
    write => ,
    dout => ,
    dio => 
  );
$0
```

And `render_instantiation(bare_signature)` — an entity with neither
generics nor ports — collapses to just the header, both `{% if %}` clauses
in Section 6 evaluating false:

```
${1:bare_inst} : ${2:entity }${3:work.}${4:bare};
$0
```

## 8. Deferred work

An entity-vs-component instantiation switch, and splitting `entity`/`work`
into independently tab-stoppable pieces, were both once listed here as
deferred; Section 6's four-tabstop header (`$1`–`$4`) now implements both in
one snippet body rather than as a separate `_Style` flag — see "Four
tabstops, three instantiation styles" above for which tabstops to clear for
which VHDL form.

A Verilog/SystemVerilog renderer (`_verilog_instantiate.py`, registered
alongside the VHDL entry in `_RENDERERS`) has not been started; Section 1
covers what of `_snippet.py` such a renderer would and wouldn't be able to
reuse unchanged.
