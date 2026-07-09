"""Shared intermediate representation (IR) for a parsed HDL entity or module interface.

Mirrors a C function prototype or Python's `inspect.Signature`: it captures the
interface of an entity/module — its name, generics/parameters, and ports — not
its implementation. Two independent renderers consume this IR (an instantiation-
template generator and a documentation-diagram generator), so no field here may
assume how either renderer will use it. Details that don't generalise across
VHDL, Verilog, and SystemVerilog — full type-system semantics chief among them —
are kept as raw, unresolved text rather than modeled structurally, since
reproducing each language's type system has no current consumer that needs it.
"""

from dataclasses import dataclass
from enum import Enum


class Language(Enum):
    VHDL = "vhdl"
    VERILOG = "verilog"
    SYSTEMVERILOG = "systemverilog"


class Direction(Enum):
    """Port/generic direction, unified across all three source languages.

    IN/OUT/INOUT occur in VHDL, Verilog, and SystemVerilog alike. BUFFER and
    LINKAGE are VHDL-only mode-clause values; REF is a SystemVerilog-only port
    kind. Keeping one vocabulary rather than per-language duplicates lets a
    renderer compare directions without first checking which language produced
    the signature.
    """

    IN = "in"
    OUT = "out"
    INOUT = "inout"
    BUFFER = "buffer"
    LINKAGE = "linkage"
    REF = "ref"


@dataclass(frozen=True)
class Generic:
    """A single generic (VHDL) or parameter (Verilog/SystemVerilog)."""

    name: str
    type: str | None = None
    default: str | None = None
    is_type_parameter: bool = False
    """True for SystemVerilog `parameter type T = ...`; when set, `default`
    (if present) names a type rather than a value literal."""


@dataclass(frozen=True)
class PurePort:
    """A port carrying a single scalar or vector signal."""

    name: str
    direction: Direction
    type: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class InterfacePort:
    """A SystemVerilog port that connects to another interface instance.

    Recorded by name only (`interface_name`, `modport`) — the referenced
    interface's own signal list and per-modport directions are not resolved
    here, since connecting two modports only requires a name/modport match,
    not knowledge of what's inside.
    """

    name: str
    interface_name: str
    modport: str | None = None


PortItem = PurePort | InterfacePort


@dataclass(frozen=True)
class Signature:
    """The full interface of one parsed entity/module: name, generics, ports."""

    name: str
    language: Language
    generics: tuple[Generic, ...] = ()
    ports: tuple[PortItem, ...] = ()
