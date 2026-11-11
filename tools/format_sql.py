"""Format SQL files with sqlfluff, leaving DuckDB dot commands alone.

DuckDB command-line instructions such as `.read sql/views.sql` aren't SQL, and
sqlfluff refuses to format a file that contains one. This script turns each
dot-command line into a comment, runs `sqlfluff format`, then turns it back.

Usage:  uv run tools/format_sql.py sql/phase2.sql [more files...]
Settings come from .sqlfluff in the project root.
"""

import re
import subprocess
import sys
from pathlib import Path

MARKER = "-- format_sql dot command: "
DOT_COMMAND = re.compile(r"^(\.\w.*)$", re.MULTILINE)
HIDDEN = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"(.*)$", re.MULTILINE)


def format_file(path: Path) -> int:
    original = path.read_text()
    path.write_text(DOT_COMMAND.sub(lambda m: MARKER + m.group(1), original))
    try:
        result = subprocess.run([sys.executable, "-m", "sqlfluff", "format", str(path)])
    finally:
        formatted = path.read_text()
        path.write_text(HIDDEN.sub(lambda m: m.group(1), formatted))
    # sqlfluff exits 1 when it fixed something; only treat higher codes as errors.
    return 0 if result.returncode in (0, 1) else result.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    return max(format_file(Path(p)) for p in sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
