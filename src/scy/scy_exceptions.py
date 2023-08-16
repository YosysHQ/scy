from __future__ import annotations

from yosys_mau.source_str.report import InputError

class SCYTreeError(InputError):
    """Exception for task tree errors"""
    pass

class SCYUnknownStatementError(SCYTreeError):
    """Exception for encountering an unknown statement type"""
    pass

class SCYValueError(SCYTreeError):
    """SCY specific ValueError"""
    pass

class SCYUnknownCellError(SCYTreeError):
    """Exception for an encountering an unknown enable cell"""
    pass

class SCYMissingTraceException(SCYTreeError):
    """Exception for missing trace"""
    pass

class SCYSubProcessException(Exception):
    """Exception for a failed sub-process"""
    def __init__(self, command: str, logfile = None, bestguess = None) -> None:
        self.command = command
        self.logfile = logfile
        self.bestguess = bestguess

    @property
    def msg(self) -> str:
        return "produced an error"

    def __str__(self) -> str:
        error_str = f"{self.command!r} {self.msg}"
        if self.logfile:
            error_str += f", see {self.logfile} for more information"
        if self.bestguess:
            error_str += f", {self.bestguess}"
        return error_str
