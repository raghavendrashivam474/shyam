"""Local Filesystem Execution Adapter - S10.

Executes local filesystem capabilities:
- file.read: reads content from a file path
- file.write: writes content to a file path
- file.list: lists entries in a directory path
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from shyam.navigation.models import NavigationCandidate
from shyam.workflow.errors import StepExecutionError


class LocalFilesystemExecutor:
    """Executes filesystem operations on the local host."""

    async def execute(
        self,
        target: NavigationCandidate,
        input_data: dict[str, Any],
    ) -> Any:
        """Dispatch local filesystem capability."""
        cap = target.capability_id

        # Run file I/O in thread pool to prevent blocking async event loop
        loop = asyncio.get_running_loop()

        try:
            if cap == "file.read":
                return await loop.run_in_executor(None, self._read_file, input_data)
            elif cap == "file.write":
                return await loop.run_in_executor(None, self._write_file, input_data)
            elif cap == "file.list":
                return await loop.run_in_executor(None, self._list_dir, input_data)
            else:
                raise StepExecutionError(
                    step_id="unknown",
                    capability=cap,
                    reason=f"Unsupported local filesystem capability: '{cap}'",
                )
        except Exception as exc:
            if isinstance(exc, StepExecutionError):
                raise
            raise StepExecutionError(
                step_id="unknown",
                capability=cap,
                reason=str(exc),
            ) from exc

    def _read_file(self, input_data: dict[str, Any]) -> dict[str, Any]:
        path_str = input_data.get("path")
        if not path_str:
            raise ValueError("Missing required 'path' parameter in input_data")
        p = Path(path_str)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {path_str}")
        
        content = p.read_text(encoding=input_data.get("encoding", "utf-8"))
        return {"path": str(p.resolve()), "content": content, "size_bytes": len(content.encode("utf-8"))}

    def _write_file(self, input_data: dict[str, Any]) -> dict[str, Any]:
        path_str = input_data.get("path")
        content = input_data.get("content", "")
        if not path_str:
            raise ValueError("Missing required 'path' parameter in input_data")
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=input_data.get("encoding", "utf-8"))
        return {"path": str(p.resolve()), "written_bytes": len(content.encode("utf-8"))}

    def _list_dir(self, input_data: dict[str, Any]) -> dict[str, Any]:
        path_str = input_data.get("path", ".")
        p = Path(path_str)
        if not p.is_dir():
            raise NotADirectoryError(f"Directory not found: {path_str}")
        entries = [item.name for item in p.iterdir()]
        return {"path": str(p.resolve()), "entries": entries, "count": len(entries)}
