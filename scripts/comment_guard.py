"""
comment_guard.py — mechanical proof that a "comment-only" edit changed
no real code. Deletable dev tool, not application code; not imported
by anything in `frontend/`.

Two independent checks:

1. AST check (authoritative for *.py): parses the HEAD version and the
   working-tree version of each changed .py file with `ast`, strips the
   leading docstring Expr from every Module/ClassDef/FunctionDef/
   AsyncFunctionDef body (replacing an emptied body with a single
   `ast.Pass()` so the tree stays valid), then compares
   `ast.dump(tree, include_attributes=False)` between the two versions.
   Any difference is a real code change -> FAIL.

2. Line check (for *.html/*.js/*.css, where there is no Python-grade
   parser on hand): runs `git diff -U0` for the file and requires every
   added/removed line to match a comment-only pattern (a Django/Jinja
   `{# #}` or `{% comment %}` line, a `//` or `/* ... */`/`*`/`*/` line)
   or be blank. Anything else is printed for manual justification.

Usage:
    python scripts/comment_guard.py            # checks every file that
                                                # differs from HEAD
    python scripts/comment_guard.py path1 path2  # checks only these

Exit code 0 = clean, 1 = at least one FAIL/violation found.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIR_PARTS = {"migrations"}
EXCLUDE_FILENAMES = {"chart.js"}
EXCLUDE_SUFFIXES = (".min.js", ".min.css")

DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

COMMENT_ONLY_RE = re.compile(
    r'^\s*(#|//|/\*|\*/|\*(?!/)|\{#|\{%\s*(end)?comment\s*%\}).*$'
)


def is_excluded(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    if any(p in EXCLUDE_DIR_PARTS for p in parts):
        return True
    name = Path(rel_path).name
    if name in EXCLUDE_FILENAMES:
        return True
    if name.endswith(EXCLUDE_SUFFIXES):
        return True
    return False


def run_git(args):
    # capture_output + text=True decodes with the OS-locale codepage on
    # Windows (cp1252), silently corrupting non-ASCII source (em-dashes,
    # currency signs) and producing false AST diffs against otherwise
    # byte-identical files. Decode raw bytes as UTF-8 explicitly instead.
    result = subprocess.run(["git"] + args, cwd=REPO_ROOT, capture_output=True)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    return result.returncode, stdout, stderr


def changed_files():
    """Every tracked-modified + untracked file that differs from HEAD,
    restricted to the four extensions this guard understands."""
    files = set()

    rc, out, _ = run_git(["diff", "--name-only", "HEAD"])
    if rc == 0:
        files.update(l.strip() for l in out.splitlines() if l.strip())

    rc, out, _ = run_git(["ls-files", "--others", "--exclude-standard"])
    if rc == 0:
        files.update(l.strip() for l in out.splitlines() if l.strip())

    return sorted(
        f for f in files
        if f.endswith((".py", ".html", ".js", ".css")) and not is_excluded(f)
    )


def get_head_version(rel_path: str):
    rc, out, _ = run_git(["show", f"HEAD:{rel_path}"])
    if rc != 0:
        return None  # file doesn't exist at HEAD (new file)
    return out


def strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, DOCSTRING_OWNERS) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(getattr(first, "value", None), ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body.pop(0)
                if not node.body:
                    node.body.append(ast.Pass())
    return tree


def normalized_dump(source: str) -> str:
    tree = ast.parse(source)
    tree = strip_docstrings(tree)
    return ast.dump(tree, include_attributes=False)


def check_python(rel_path: str):
    working_path = REPO_ROOT / rel_path
    working_src = working_path.read_text(encoding="utf-8")
    head_src = get_head_version(rel_path)

    if head_src is None:
        return "NEW", "no HEAD version to compare (new file) -- not structurally checked"

    try:
        head_dump = normalized_dump(head_src)
    except SyntaxError as e:
        return "ERROR", f"HEAD version fails to parse: {e}"

    try:
        working_dump = normalized_dump(working_src)
    except SyntaxError as e:
        return "ERROR", f"working version fails to parse: {e}"

    if head_dump != working_dump:
        return "FAIL", "AST differs after stripping docstrings -- real code changed"
    return "PASS", None


def check_generic(rel_path: str):
    rc, diff, _ = run_git(["diff", "-U0", "--", rel_path])
    if rc != 0:
        return "ERROR", ["git diff failed"]

    bad_lines = []
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if not (line.startswith("+") or line.startswith("-")):
            continue
        content = line[1:]
        if content.strip() == "":
            continue
        if COMMENT_ONLY_RE.match(content):
            continue
        bad_lines.append(line)

    if bad_lines:
        return "FAIL", bad_lines
    return "PASS", None


def main(argv):
    targets = argv[1:] if len(argv) > 1 else changed_files()

    if not targets:
        print("No changed files to check (clean baseline).")
        return 0

    any_fail = False
    for rel_path in targets:
        rel_path = rel_path.replace("\\", "/")
        if is_excluded(rel_path):
            print(f"SKIP  {rel_path} (excluded)")
            continue

        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            print(f"SKIP  {rel_path} (deleted from working tree)")
            continue

        if rel_path.endswith(".py"):
            status, detail = check_python(rel_path)
        else:
            status, detail = check_generic(rel_path)

        print(f"{status:5} {rel_path}")
        if status == "FAIL":
            any_fail = True
            if isinstance(detail, list):
                for line in detail:
                    print(f"      {line}")
            elif detail:
                print(f"      {detail}")
        elif status == "ERROR":
            any_fail = True
            print(f"      {detail}")

    print()
    print("RESULT:", "FAIL -- real code change detected" if any_fail else "CLEAN")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
