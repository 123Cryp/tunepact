import ast
import re
import sys
from pathlib import Path

HEADER = [
    "# v0.2.16",
    '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }',
]

TESTNET_OVERRIDES = {
    "DELIVERY_DEADLINE_SEC": 900,
    "CHALLENGE_WINDOW_SEC": 120,
    "JURY_COMMIT_WINDOW_SEC": 180,
    "JURY_REVEAL_WINDOW_SEC": 180,
    "STUCK_TIMEOUT_SEC": 1200,
    "ROUND1_JURY_SIZE": 1,
    "ROUND2_JURY_SIZE": 3,
}


def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def strip_source(src):
    tree = _strip_docstrings(ast.parse(src))
    body = ast.unparse(tree)
    return "\n".join(HEADER) + "\n\n" + body + "\n"


def apply_testnet(src):
    for name, value in TESTNET_OVERRIDES.items():
        pattern = re.compile(r"^" + name + r": int = .*$", re.M)
        if not pattern.search(src):
            raise SystemExit("constant not found: " + name)
        src = pattern.sub(name + ": int = " + str(value), src, count=1)
    return src


def main():
    root = Path(__file__).resolve().parent.parent / "contracts"
    src = (root / "tunepact.py").read_text()
    (root / "tunepact_deploy.py").write_text(strip_source(src))
    (root / "tunepact_testnet.py").write_text(strip_source(apply_testnet(src)))
    print("built tunepact_deploy.py and tunepact_testnet.py")


if __name__ == "__main__":
    main()
