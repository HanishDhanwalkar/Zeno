from __future__ import annotations

import enum


class ToolKind(enum.Enum):
    """Tool permission classification
    
    ``READ_ONLY``: no disc/exec
    ``FILE_EDIT``: mutates file tree (``write`` / ``edit``)
    ``OTHER``: everything else (``bash``, and default for unclassified tools)``)
    """

    READ_ONLY = "read_only"
    FILE_EDIT = "file_edit"
    OTHER = "other"