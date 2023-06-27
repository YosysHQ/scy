from __future__ import annotations
from dataclasses import dataclass

from yosys_mau.source_str.report import InputError

class SCYTreeException(InputError):
    """Exception for task tree errors"""
    pass
    
class SCYMissingTraceException(SCYTreeException):
    """Exception for missing trace"""
    pass

@dataclass
class SCYSubProcessException(Exception):
    """Exception for a failed sub-process"""
    target: str
    logfile: str | None

    def __str__(self) -> str:
        error_str = f"{self.target} produced an error"
        if self.logfile:
            error_str += f", see {self.logfile} for more information"
        return error_str
