# hdl-signature

Parses a VHDL entity declaration into a shared intermediate representation
(IR) — name, generics, and ports, each with direction and type — analogous
to a C function prototype or Python's `inspect.Signature`: the interface,
not the implementation. Verilog and SystemVerilog module parsing are
planned; the IR is already designed to hold all three without a shape
change once that parsing exists.

The IR is meant to be consumed by more than one renderer without
re-parsing: an instantiation-template generator ships today, and a
documentation-diagram generator is planned.

## Installation

Not yet published on PyPI. Install directly from GitHub:

```
pip install git+https://github.com/mpkopec/hdl-signature.git
```

Requires Python 3.10+. Dependencies (`tree-sitter`, `tree-sitter-vhdl`,
`jinja2`) all ship prebuilt wheels — no VHDL compiler toolchain is
required.

## Usage

```python
import hdl_signature
from hdl_signature.ir import Language

source = """
entity fifo is
  generic (
    WIDTH : integer := 8
  );
  port (
    clk  : in  std_logic;
    dout : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity fifo;
"""

signatures = hdl_signature.parse_string(source, Language.VHDL)
signature = signatures[0]

print(hdl_signature.render_instantiation(signature))
```

`signature.name`, `signature.generics`, and `signature.ports` give the
entity name and its ordered `Generic`/`PurePort` tuples (see
`hdl_signature.ir` for the full dataclass shapes). `hdl_signature.parse_file(path)`
is a convenience wrapper that reads a `.vhd`/`.vhdl` file and infers the
language from its extension.

`render_instantiation` renders a parsed `Signature` as an
instantiation-template snippet body (instance label, generic map, port
map), with `${n}`/`${n:default}` tabstop placeholders in the
TextMate/UltiSnips convention. Three independent keyword flags control its
output: `prefill` (pre-load each right-hand side with the port's own name
or the generic's default), `tabstop` (make each right-hand side an
editable tabstop rather than committed plain text), and `align` (pad names
to the longest in their own map).

## Status

Only VHDL parsing and VHDL instantiation-template rendering are
implemented. The `Signature`/`Generic`/`PurePort`/`InterfacePort` IR
(`hdl_signature.ir`) is designed to also cover Verilog and SystemVerilog;
parsing and rendering for those languages have not been written yet.

## License

MIT — see [LICENSE](LICENSE).
