"""Public parsing entry points: source text or a file path to a list of Signatures.

parse_string is the primitive - the only one that works purely in memory,
since the live-editor-buffer consumer (the nvim instantiation-template
feature) needs to parse unsaved, possibly mid-edit text that never touches
disk. parse_file is a convenience wrapper over it for callers that only have
a path (e.g. a batch/diagram-renderer consumer), inferring the language from
the file extension so the caller doesn't have to state it twice.
"""

from pathlib import Path
from typing import Callable

from hdl_signature.ir import Language, Signature

from . import _vhdl

_EXTENSION_LANGUAGES: dict[str, Language] = {
    ".vhd": Language.VHDL,
    ".vhdl": Language.VHDL,
    ".v": Language.VERILOG,
    ".sv": Language.SYSTEMVERILOG,
    ".svh": Language.SYSTEMVERILOG,
}

# Only VHDL is implemented so far. Verilog/SystemVerilog extensions are still
# recognised above so parse_file can name the missing language precisely
# (via the NotImplementedError below) rather than reporting a bare
# "unrecognized extension".
_PARSERS: dict[Language, Callable[[str], list[Signature]]] = {
    Language.VHDL: _vhdl.parse,
}


def parse_string(source_text: str, language: Language) -> list[Signature]:
    """Parses every entity/module declaration found in source_text.

    language must be given explicitly - unlike parse_file, there is no file
    extension here to infer it from, and source text alone doesn't reliably
    distinguish plain Verilog from SystemVerilog.
    """
    try:
        parse = _PARSERS[language]
    except KeyError:
        raise NotImplementedError(f"parsing for {language.value} is not implemented yet")
    return parse(source_text)


def parse_file(path: str | Path) -> list[Signature]:
    """Reads path and parses it, inferring the source language from its extension."""
    path = Path(path)
    try:
        language = _EXTENSION_LANGUAGES[path.suffix]
    except KeyError:
        raise ValueError(f"unrecognized HDL file extension: {path.suffix!r}")
    return parse_string(path.read_text(), language)
