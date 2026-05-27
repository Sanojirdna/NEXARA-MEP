from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TimingRecorder:
    """Small helper for stage timings and console logs.

    Args:
        timings: Collected timing data.
        logs: Status log messages.

    Returns:
        TimingRecorder object.
    """

    timings: list[dict[str, float | str]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Print and store a status message.

        Args:
            message: Message to write.

        Returns:
            None.
        """
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.logs.append(line)
        print(line, flush=True)

    @contextmanager
    def stage(self, name: str) -> None:
        """Measure a named stage.

        Args:
            name: Stage name.

        Returns:
            Context manager.
        """
        self.log(f"START {name}")
        start_time = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start_time
            self.timings.append({"stage": name, "seconds": elapsed})
            self.log(f"END   {name} ({elapsed:.3f}s)")

    def to_dict(self) -> dict[str, list]:
        """Convert to dictionary.

        Args:
            None.

        Returns:
            Dictionary with timings and logs.
        """
        return {"timings": self.timings, "logs": self.logs}

    def write_json(self, path: str | Path) -> None:
        """Write timings and logs to JSON.

        Args:
            path: Output JSON path.

        Returns:
            None.
        """
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
