# VHDL CST-to-Signature Adapter: Design Walkthrough

`_vhdl.py` turns a tree-sitter parse of VHDL source into `hdl_signature.ir.Signature`
objects. This document explains how: the tree it starts from, the two primitives
it walks that tree with, and how each function builds on the last, from the
entry point down to a single leaf lookup. It is written to be read start to
finish with nothing else open.

## Target shape

The output type is `hdl_signature.ir.Signature`, one per entity declaration
found in the source. `Signature` is part of `hdl_signature.ir`, the package's
shared intermediate representation (IR) — a language-independent description
of an entity/module interface, analogous to a C function prototype:

- `name: str`, `language: Language` (always `Language.VHDL` from this module),
  `generics: tuple[Generic, ...]`, `ports: tuple[PurePort, ...]`.
- A `Generic` is `name: str`, `type: str | None`, `default: str | None`.
- A `PurePort` is `name: str`, `direction: Direction`, `type: str | None`,
  `default: str | None`. `Direction` is an enum with members `IN`, `OUT`,
  `INOUT`, `BUFFER`, `LINKAGE` (`REF` also exists, for SystemVerilog, never
  produced by this module).

`type` and `default` are always kept as raw source text, never parsed into a
structured type system or expression tree — no current consumer of the IR
needs more than printable text for either.

## 1. Concepts

### Concrete syntax tree

tree-sitter produces a **concrete syntax tree (CST)**: every token in the
source — including punctuation, keywords, and whitespace-adjacent separators
like `;` and `,` — becomes its own node. This is unlike an abstract syntax
tree (AST), which would keep only the tokens that carry meaning and discard
the rest. The consequence for this module is that most of its work is lossy
compression in the other direction: reducing a full CST down to only the
`name`/`type`/`default` text a `Signature` needs, by discarding punctuation
nodes entirely, translating grammar text into typed IR values (a mode keyword
string becomes a `Direction` member), and fanning out declarations that name
several generics or ports at once (`A, B : integer := 0`) into one IR object
per name.

### Named vs. anonymous nodes, and `.type`

Every CST node is either **named** or **anonymous**, a distinction fixed by
how the grammar's author wrote that rule — a node is named when its grammar
rule was given an explicit name, and anonymous when the grammar wrote it as a
bare string literal, such as a keyword or a punctuation mark
([tree-sitter docs: named vs. anonymous nodes](https://tree-sitter.github.io/tree-sitter/using-parsers/2-basic-parsing.html#named-vs-anonymous-nodes)).
A node's `.type` attribute then holds that rule's name for a named node, or
the literal token text itself for an anonymous one — this is a tree-sitter
node property, unrelated to Python's own `type()`. For example, the `;`
ending a declaration is an anonymous node with `.type == ";"`, while the
declaration itself is a named node with `.type == "interface_declaration"`.

Tree traversal in this module is built around this split: anonymous
punctuation is never useful IR content, so a node's `.named_children`
(skipping anonymous nodes automatically) is used whenever "all the interesting
children" are wanted, and manual scanning of `.children` (including anonymous
ones) is used only when a specific named type must be located among mixed
siblings.

### No fields in this grammar

tree-sitter grammars can optionally give a child position a **field name** —
`field(name, rule)` in the grammar source — letting calling code fetch that
child with `child_by_field_name(name)` instead of by position or type. This
is a separate, opt-in grammar feature, not a property every node has.
`tree-sitter-vhdl` assigns no field names anywhere relevant to this module:
`child_by_field_name` returns `None` on every node type this module touches
(`entity_declaration`, `interface_declaration`, `entity_head`,
`generic_clause`, `simple_mode_indication`, `initialiser`), confirmed
empirically rather than assumed
([tree-sitter docs: node field names](https://tree-sitter.github.io/tree-sitter/using-parsers/2-basic-parsing.html#node-field-names)).
Consequently, every lookup in this module scans children by `.type` instead —
not as a workaround for something better available, but because field-based
lookup is simply not an option this grammar provides.

## 2. The canonical example

One VHDL source, used throughout this document, exercises every generic/port
variant this module handles, plus a bare entity with neither:

```vhdl
entity fifo is
  generic (
    WIDTH : integer := 8;
    DEPTH : natural
  );
  port (
    clk    : in  std_logic;
    rst    : in  std_logic;
    sin    : in  std_logic;
    write  : in  std_logic;
    dout   : out std_logic_vector(WIDTH - 1 downto 0);
    dio    : inout std_logic
  );
end entity fifo;

entity bare is
end entity bare;
```

Before the full tree, a simplified map of its shape (types only, cardinality
noted where a node can repeat):

```
design_file
 ├─ design_unit                          (fifo)
 │   └─ entity_declaration
 │       ├─ identifier             "fifo"
 │       └─ entity_head
 │           ├─ generic_clause
 │           │   └─ interface_list       (2 interface_declaration entries)
 │           └─ port_clause
 │               └─ interface_list       (6 interface_declaration entries)
 └─ design_unit                          (bare)
     └─ entity_declaration
         ├─ identifier             "bare"
         └─ entity_head                  (no generic_clause / port_clause)
```

And the full tree, a verbatim capture against tree-sitter-vhdl 1.5.0 (not
inferred or hand-typed — `pyproject.toml` does not pin that version, so treat
this as a snapshot that could drift after a grammar upgrade, not a guarantee).
Each row's `[named]`/`[anon]` tag and quoted text are exactly as produced by
the parser. `subtype_indication` and `initialiser` subtrees are cut off here —
each has its own internal expression grammar (`simple_expression`,
`decimal_integer`, ...) that this module never inspects, taking the whole
span as opaque printable text instead (Section 7 covers the one place that
looks one level into `initialiser`):

```
design_file [named]
  design_unit [named]
    entity_declaration [named]
      entity [anon] 'entity'
      identifier [named] 'fifo'
      entity_head [named]
        is [anon] 'is'
        generic_clause [named]
          generic [anon] 'generic'
          ( [anon] '('
          interface_list [named]
            interface_declaration [named] 'WIDTH : integer := 8'
              identifier_list [named]
                library_type [named] 'WIDTH'
              : [anon] ':'
              simple_mode_indication [named]
                subtype_indication [named] 'integer'
                initialiser [named] ':= 8'
            ; [anon] ';'
            interface_declaration [named] 'DEPTH : natural'
              identifier_list [named]
                identifier [named] 'DEPTH'
              : [anon] ':'
              simple_mode_indication [named]
                subtype_indication [named] 'natural'
          ) [anon] ')'
          ; [anon] ';'
        port_clause [named]
          port [anon] 'port'
          ( [anon] '('
          interface_list [named]
            interface_declaration [named] 'clk    : in  std_logic'
              identifier_list [named]
                identifier [named] 'clk'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'in'
                subtype_indication [named] 'std_logic'
            ; [anon] ';'
            interface_declaration [named] 'rst    : in  std_logic'
              identifier_list [named]
                identifier [named] 'rst'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'in'
                subtype_indication [named] 'std_logic'
            ; [anon] ';'
            interface_declaration [named] 'sin    : in  std_logic'
              identifier_list [named]
                library_function [named] 'sin'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'in'
                subtype_indication [named] 'std_logic'
            ; [anon] ';'
            interface_declaration [named] 'write  : in  std_logic'
              identifier_list [named]
                library_function [named] 'write'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'in'
                subtype_indication [named] 'std_logic'
            ; [anon] ';'
            interface_declaration [named] 'dout   : out std_logic_vector(WIDTH -...'
              identifier_list [named]
                identifier [named] 'dout'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'out'
                subtype_indication [named] 'std_logic_vector(WIDTH - 1 downto 0)'
            ; [anon] ';'
            interface_declaration [named] 'dio    : inout std_logic'
              identifier_list [named]
                identifier [named] 'dio'
              : [anon] ':'
              simple_mode_indication [named]
                mode [named] 'inout'
                subtype_indication [named] 'std_logic'
          ) [anon] ')'
          ; [anon] ';'
      end_entity [named] 'end entity fifo'
        end [anon] 'end'
        entity [anon] 'entity'
        identifier [named] 'fifo'
      ; [anon] ';'
  design_unit [named]
    entity_declaration [named]
      entity [anon] 'entity'
      identifier [named] 'bare'
      entity_head [named] 'is'
        is [anon] 'is'
      end_entity [named] 'end entity bare'
        end [anon] 'end'
        entity [anon] 'entity'
        identifier [named] 'bare'
      ; [anon] ';'
```

Two anomalies in this dump are load-bearing for how `_parse_interface_declaration`
is written (Section 6): `sin`/`write` are tagged `library_function`, and
`WIDTH` is tagged `library_type`, instead of `identifier`.
`tree-sitter-vhdl`'s classifier misfires on some identifiers, and does so
regardless of whether the name collides with a VHDL standard-library name —
`sin`/`write` do collide (both are standard-library subprogram names), `WIDTH`
does not — confirmed empirically rather than assumed
([jpt13653903/tree-sitter-vhdl#69](https://github.com/jpt13653903/tree-sitter-vhdl/issues/69)).
Section 6 shows the consequence: declared names are gathered by taking every
named child of `identifier_list`, never by filtering for type `"identifier"`.

The other load-bearing detail is the contrast between the two `entity_head`
rows above: `fifo`'s has three children (`is`, `generic_clause`,
`port_clause`), `bare`'s has exactly one (`is`). `entity_head` itself is
always present, even when an entity declares neither generics nor ports — it
is `generic_clause` and `port_clause` that are each independently optional,
never `entity_head`. Section 4 shows why that distinction determines which
lookups in `parse()` need a `None` check and which do not.

## 3. Two primitives

Every other function in this module is built from these two. Both are pure
lookups with no VHDL-specific knowledge — they would work identically against
a CST from any tree-sitter grammar — so they live in their own module,
`hdl_signature._cst`, rather than in `_vhdl.py`: a future Verilog/SystemVerilog
adapter imports them unchanged instead of redefining them.

```python
def first_child_of_type(node, type_name):
    for child in node.children:
        if child.type == type_name:
            return child
    return None
```

A singleton search: it returns `node`'s first direct child whose `.type`
equals `type_name`, scanning `.children` — both named and anonymous nodes —
from the start, or `None` if no such child exists. Every call re-scans from
scratch; there is no shared cursor or state carried between calls, even when
two calls in a row search the same node for two different `type_name`s (as
Section 4 does for `entity_head`'s `generic_clause` and `port_clause`).

Concretely, `first_child_of_type(entity_decl, "entity_head")` on `fifo`'s
`entity_declaration` from Section 2 scans exactly this list, in this order:

```
entity [anon] 'entity'
identifier [named] 'fifo'
entity_head [named] ...
end_entity [named] 'end entity fifo'
; [anon] ';'
```

`entity_head` is the third child checked — not the first *named* one, since
`identifier` is named too but of the wrong `type_name` — and once it is
returned, `entity`/`end_entity`/`;` are simply never asked for, not filtered
out. This is why the function scans by `type_name` at all rather than using
tree-sitter's `child_by_field_name`: as Section 1 established, this grammar
assigns no field names on any node type this module touches, so type-name
scanning is the only mechanism available here, not a workaround for something
already solved.

```python
def node_text(node, source):
    return source[node.start_byte : node.end_byte].decode()
```

A tree-sitter `Node` stores only byte offsets into the buffer it was parsed
from (`start_byte`/`end_byte`), not its own text, so recovering the text
spanned by any node needs the same `source` bytes that were handed to the
parser. Concretely, `fifo`'s `identifier` node from Section 2 has
`start_byte=7, end_byte=11` — the node itself holds only those two integers,
not the string `"fifo"` — and `node_text` is what turns the pair back into
`source[7:11].decode() == "fifo"`.

## 4. `parse()`: the entry point

```python
def parse(source_text: str) -> list[Signature]:
    source_bytes = source_text.encode()
    tree = _PARSER.parse(source_bytes)

    signatures = []
    for design_unit in tree.root_node.children:
        entity_decl = first_child_of_type(design_unit, "entity_declaration")
        if entity_decl is None:
            continue

        identifier_node = first_child_of_type(entity_decl, "identifier")
        name = node_text(identifier_node, source_bytes)

        entity_head = first_child_of_type(entity_decl, "entity_head")

        generic_clause = first_child_of_type(entity_head, "generic_clause")
        generics = _parse_generic_clause(generic_clause, source_bytes)

        port_clause = first_child_of_type(entity_head, "port_clause")
        ports = _parse_port_clause(port_clause, source_bytes)

        signatures.append(
            Signature(name=name, language=Language.VHDL, generics=generics, ports=ports)
        )
    return signatures
```

A parsed file (`design_file`, the tree's root) is a sequence of
`design_unit`s — entities, architecture bodies, package declarations, and
other top-level VHDL constructs side by side. Only some of these are
entities, so each `design_unit` is checked for an `entity_declaration` child
and skipped (via the `continue`) if it has none — architecture bodies and
package declarations carry no interface information the IR models, and this
is the only place that distinction is made.

For a `design_unit` that does have one, `first_child_of_type` descends one
grammar level per call, matching the shape from Section 2:
`entity_declaration` yields its `identifier` (the entity's name) and its
`entity_head` directly; `entity_head` in turn yields `generic_clause` and
`port_clause`, since those sit one level below it, not directly under
`entity_declaration`. This is the slice of the Section 2 tree this function
itself walks (each clause's own contents are cut off here — Sections 5 and 6
handle those):

```
design_unit [named]
  entity_declaration [named]
    entity [anon] 'entity'
    identifier [named] 'fifo'
    entity_head [named]
      is [anon] 'is'
      generic_clause [named]   <- see Section 5
      port_clause [named]      <- see Section 5
    end_entity [named] 'end entity fifo'
    ; [anon] ';'
design_unit [named]
  entity_declaration [named]
    entity [anon] 'entity'
    identifier [named] 'bare'
    entity_head [named] 'is'
    end_entity [named] 'end entity bare'
    ; [anon] ';'
```

`identifier` and `entity_head` are always present on a valid `entity_declaration`,
so neither lookup above is `None`-checked. `generic_clause` and `port_clause`
are each independently optional — as Section 2 noted, `bare`'s `entity_head`
holds only its `is` token, with no `generic_clause`/`port_clause` at all,
rather than `entity_head` itself being absent — which is exactly why
`_parse_generic_clause`/`_parse_port_clause` (Section 5) each accept `None`
and return `()` for it, instead of `parse()` checking first.

`entity_head` itself never reaches the output; it exists in the grammar only
as scaffolding to reach `generic_clause`/`port_clause`. Once a name, its
generics, and its ports are known, they are combined into one `Signature`
(`language` is always `Language.VHDL` here — a constant this module supplies,
never something extracted from the tree), and the `Signature`s accumulated
this way, one per entity found, are returned at the end.

## 5. Generics and ports: `_parse_generic_clause` / `_parse_port_clause`

```python
def _parse_generic_clause(generic_clause, source):
    if generic_clause is None:
        return ()

    interface_list = first_child_of_type(generic_clause, "interface_list")
    generics = []
    for decl in interface_list.named_children:
        parsed = _parse_interface_declaration(decl, source)
        for name in parsed.names:
            generics.append(
                Generic(name=name, type=parsed.type_text, default=parsed.default_text)
            )
    return tuple(generics)
```

Unlike the singleton searches in `parse()`, an `interface_list` can hold more
than one `interface_declaration` — one per semicolon-separated entry in the
generic list — so this walks all of `interface_list`'s named children
directly instead of looking up a single one. `interface_list.named_children`
already excludes the separating `;` tokens, since those are anonymous
grammar literals, without this function needing to filter them out itself.
The `generic_clause` this function receives, from Section 2 (each
`interface_declaration`'s own contents cut off here — Section 6 handles
those):

```
generic_clause [named]
  generic [anon] 'generic'
  ( [anon] '('
  interface_list [named]
    interface_declaration [named] 'WIDTH : integer := 8'
    ; [anon] ';'
    interface_declaration [named] 'DEPTH : natural'
  ) [anon] ')'
  ; [anon] ';'
```

`interface_list.named_children` here is exactly `[WIDTH's interface_declaration,
DEPTH's interface_declaration]`. Each declaration is then expanded into one
`Generic` per name, since one declaration can name several generics sharing a
type and default at once — e.g. `A, B : integer := 0` — which is why a
name-level loop is nested inside the declaration-level one; `_ParsedInterfaceDeclaration`
(Section 6) is what makes that expansion possible without re-parsing anything.

```python
def _parse_port_clause(port_clause, source):
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
```

Same shape as `_parse_generic_clause` — `interface_list`'s named children are
walked directly, since more than one `interface_declaration` can appear — but
each declaration's `mode_keyword` is additionally translated to a `Direction`
via the `_DIRECTION_BY_MODE` mapping (`"in"` → `Direction.IN`, and so on),
since, unlike generics, every port declaration carries a mode. The
`port_clause` this function receives, from Section 2:

```
port_clause [named]
  port [anon] 'port'
  ( [anon] '('
  interface_list [named]
    interface_declaration [named] 'clk    : in  std_logic'
    ; [anon] ';'
    interface_declaration [named] 'rst    : in  std_logic'
    ; [anon] ';'
    interface_declaration [named] 'sin    : in  std_logic'
    ; [anon] ';'
    interface_declaration [named] 'write  : in  std_logic'
    ; [anon] ';'
    interface_declaration [named] 'dout   : out std_logic_vector(WIDTH -...'
    ; [anon] ';'
    interface_declaration [named] 'dio    : inout std_logic'
  ) [anon] ')'
  ; [anon] ';'
```

Six `interface_declaration` siblings this time, one per port, reached the
same way as generics: `interface_list.named_children`, with the five
anonymous `;` tokens between them already gone.

## 6. One declaration: `_ParsedInterfaceDeclaration` and `_parse_interface_declaration`

A generic and a port entry share the same grammar production
(`interface_declaration`) and differ only in which pieces are present, so one
function parses both, returning a small intermediate value that
`_parse_generic_clause`/`_parse_port_clause` each interpret differently:

```python
class _ParsedInterfaceDeclaration(NamedTuple):
    names: list[str]
    mode_keyword: str | None
    type_text: str | None
    default_text: str | None
```

A plain 4-tuple would force every caller to remember positional order; this
names each field instead. `mode_keyword` is `None` for generics (which have
no mode at all) and, for ports, would never be `None` in valid VHDL — but the
type stays `Optional` regardless, since this class describes one parsed
declaration generically, before the caller has decided which case it is.

```python
def _parse_interface_declaration(decl, source):
    identifier_list = first_child_of_type(decl, "identifier_list")
    names = [node_text(n, source) for n in identifier_list.named_children]

    mode_indication = first_child_of_type(decl, "simple_mode_indication")

    mode_node = first_child_of_type(mode_indication, "mode")
    mode_keyword = None if mode_node is None else node_text(mode_node, source)

    subtype_node = first_child_of_type(mode_indication, "subtype_indication")
    type_text = None if subtype_node is None else node_text(subtype_node, source)

    default_text = _default_text(mode_indication, source)

    return _ParsedInterfaceDeclaration(names, mode_keyword, type_text, default_text)
```

`decl` has two direct named children — `identifier_list` (one or more comma-
separated names) and `simple_mode_indication` (the type, an optional mode
keyword, and an optional default) — plus one anonymous `:` between them,
which is simply never retrieved: nothing here calls `first_child_of_type`
with `type_name=":"`, so it needs no special skipping, unlike the anonymous
`,`/`;` separators the multi-match functions in Section 5 filter out via
`.named_children`.

Two contrasting `interface_declaration`s from Section 2 — a generic with a
default and no mode, a port with a mode and no default
(`subtype_indication`/`initialiser` cut off here, the same opacity boundary
as Section 2):

```
interface_declaration [named] 'WIDTH : integer := 8'
  identifier_list [named]
    library_type [named] 'WIDTH'
  : [anon] ':'
  simple_mode_indication [named]
    subtype_indication [named] 'integer'
    initialiser [named] ':= 8'

interface_declaration [named] 'clk    : in  std_logic'
  identifier_list [named]
    identifier [named] 'clk'
  : [anon] ':'
  simple_mode_indication [named]
    mode [named] 'in'
    subtype_indication [named] 'std_logic'
```

`WIDTH`'s `simple_mode_indication` has no `mode` child at all — not a `mode`
child with empty text — which is why `mode_node` can be `None`; `clk`'s has no
`initialiser` child for the same reason, which is why `default_text` can be
`None`. `names` is gathered by walking `identifier_list`'s named children
directly, since there can be more than one (`A, B : integer := 0`), while
`mode_keyword`/`type_text`/`default_text` are each a singleton search into
`simple_mode_indication`, since at most one of each can exist there.

`WIDTH` is also the anomaly from Section 2: its `identifier_list` child is
named `library_type`, not `identifier`, because `tree-sitter-vhdl` misclassifies
it regardless of the absence of any real standard-library collision. This is
why `names` above takes every named child of `identifier_list`, with no
filter for type `"identifier"` — such a filter would silently drop `WIDTH`
(and, in the port case, `sin`/`write`) from the result.

## 7. Default values: `_default_text`

```python
def _default_text(mode_indication, source):
    initialiser = first_child_of_type(mode_indication, "initialiser")
    if initialiser is None:
        return None

    for child in initialiser.named_children:
        if child.type != "variable_assignment":
            return node_text(child, source)
    return None
```

This is the one place in the module that looks at `initialiser`'s own
children rather than treating it as opaque. `WIDTH`'s `initialiser` (`:= 8`)
from Section 2, shown here one level deeper than Section 2 goes:

```
initialiser [named] ':= 8'
  variable_assignment [named] ':='
  conditional_expression [named] '8'
    simple_expression [named] '8'
      decimal_integer [named] '8'
```

Only the first two rows matter here. `initialiser`'s two named children are
the `:=` operator token itself — named `variable_assignment` in this grammar,
despite being an operator rather than a variable — and the default-value
expression; the loop returns whichever child is *not* the operator, rather
than assuming a fixed position. `conditional_expression`'s own children are
the opaque expression grammar this function stops at, taken as one span of
text via `node_text` rather than walked into further — the same boundary
Section 2's dump is cut off at.
