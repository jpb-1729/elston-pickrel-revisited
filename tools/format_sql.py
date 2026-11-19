"""Format SQL files with sqlfluff, leaving DuckDB dot commands alone.

DuckDB command-line instructions such as `.read sql/views.sql` aren't SQL, and
sqlfluff refuses to format a file that contains one. This script turns each
dot-command line into a comment, runs `sqlfluff format`, then turns it back.

Usage:  uv run tools/format_sql.py sql/phase2.sql [more files...]
        uv run tools/format_sql.py --check sql/*.sql
With --check, files are left alone, and the script lists the ones that would
change and exits 1 if there are any.
Settings come from .sqlfluff in the project root.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = "-- format_sql dot command: "
DOT_COMMAND = re.compile(r"^(\.\w.*)$", re.MULTILINE)
HIDDEN = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"(.*)$", re.MULTILINE)
CONFIG = Path(__file__).resolve().parent.parent / ".sqlfluff"


def formatted(text: str) -> str:
    """Return text as sqlfluff formats it, with dot commands kept as they are."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "file.sql"
        path.write_text(DOT_COMMAND.sub(lambda m: MARKER + m.group(1), text))
        cmd = ["format", "--nocolor", "--config", str(CONFIG), str(path)]
        result = subprocess.run(
            [sys.executable, "-m", "sqlfluff", *cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        # sqlfluff exits 1 when it fixed something; higher codes are errors.
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stdout + result.stderr)
        return HIDDEN.sub(lambda m: m.group(1), path.read_text())


def main() -> int:
    args = sys.argv[1:]
    check = "--check" in args
    paths = [Path(a) for a in args if a != "--check"]
    if not paths:
        print(__doc__)
        return 2
    changed = []
    for path in paths:
        original = path.read_text()
        new = formatted(original)
        if new != original:
            changed.append(path)
            if not check:
                path.write_text(new)
    for path in changed:
        print(f"{'would reformat' if check else 'reformatted'}: {path}")
    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
