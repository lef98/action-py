from __future__ import annotations


class DSLError(Exception):
    """Base class for DSL parsing and compilation errors."""


class DSLParseError(DSLError):
    """Raised when DSL source cannot be parsed."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        if line is not None:
            message = f"Line {line}: {message}"
        super().__init__(message)


class DSLSemanticError(DSLError):
    """Raised when parsed DSL source is semantically invalid."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        if line is not None:
            message = f"Line {line}: {message}"
        super().__init__(message)

