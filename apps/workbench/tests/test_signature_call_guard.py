"""Static guard: no call site may be written against a stale helper signature.

Why this exists
---------------
``brief_ux.default_brief_asof`` gained a required ``state`` parameter in
v3.10.1 (``c640b5c``).  A later feature — the intel-report ↔ brief crosswalk in
v3.12.5 (``0da5f2d``) — added two call sites still spelled
``default_brief_asof()``.  Every test passed ``asof`` explicitly, so the
``asof or default_brief_asof(...)`` fallback branch never executed, and
``GET /api/research/intel-report/crosswalk`` answered **500 in the browser for
five releases** (v3.12.5 → v3.13.6).  Fixed in v3.13.7.

The behavioural twin of this guard is
``test_intel_report.test_intel_crosswalk_default_asof``.  This module covers the
whole *class* of bug instead of one instance: it checks the syntax of every
intra-package call, so a new call site written against an old signature fails
in CI rather than in the browser.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "stock_platform_workbench"


@dataclass(frozen=True)
class _Sig:
    """What a call site must supply to reach a function without a TypeError."""

    positional: tuple[str, ...]
    required: frozenset[str]
    variadic: bool  # has *args / **kwargs → arity is not decidable statically


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> _Sig:
    args = fn.args
    positional = tuple(a.arg for a in (*args.posonlyargs, *args.args))
    cut = len(positional) - len(args.defaults)
    required = set(positional[:cut])
    required |= {a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None}
    return _Sig(
        positional,
        frozenset(required),
        args.vararg is not None or args.kwarg is not None,
    )


def _package_defs() -> dict[str, _Sig]:
    """Module-level functions defined **exactly once** in the package.

    Names defined more than once are dropped: two same-named functions may have
    different arities and the checker would not know which one a call reaches.
    Erring towards silence keeps this guard free of false positives.
    """
    seen: dict[str, list[_Sig]] = {}
    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.setdefault(node.name, []).append(_signature(node))
    return {name: sigs[0] for name, sigs in seen.items() if len(sigs) == 1}


def _missing_required(node: ast.Call, sig: _Sig) -> tuple[str, ...]:
    if sig.variadic:
        return ()
    if any(k.arg is None for k in node.keywords):  # call site unpacks **kwargs
        return ()
    if any(isinstance(a, ast.Starred) for a in node.args):  # call site unpacks *args
        return ()
    given = set(sig.positional[: len(node.args)])
    given |= {k.arg for k in node.keywords if k.arg in sig.positional or k.arg in sig.required}
    return tuple(sorted(sig.required - given))


def _scan(source: str, defs: dict[str, _Sig], label: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        sig = defs.get(node.func.id)
        if sig is None:
            continue
        missing = _missing_required(node, sig)
        if missing:
            out.append(f"{label}:{node.lineno}: {node.func.id}() missing {', '.join(missing)}")
    return out


def test_guard_has_teeth_on_the_historical_bug() -> None:
    """The checker must flag the exact v3.12.5 mistake, and pass its fix."""
    defs = {"default_brief_asof": _Sig(("state",), frozenset({"state"}), False)}
    stale = "def f():\n    return default_brief_asof()\n"
    fixed = "def f(request):\n    return default_brief_asof(request.app.state.workbench)\n"
    assert _scan(stale, defs, "s") == ["s:2: default_brief_asof() missing state"]
    assert _scan(fixed, defs, "s") == []


def test_guard_ignores_undecidable_shapes() -> None:
    defs = {"f": _Sig(("a",), frozenset({"a"}), False)}
    assert _scan("f(*args)\n", defs, "s") == []
    assert _scan("f(**kwargs)\n", defs, "s") == []
    assert _scan("f(a=1)\n", defs, "s") == []
    # An explicitly keyword-passed required arg counts as satisfied.
    assert _scan("f(a=1, b=2)\n", defs, "s") == []


def test_no_call_site_uses_a_stale_signature() -> None:
    defs = _package_defs()
    # Sanity: the guard really is looking at the package we think it is.
    assert "default_brief_asof" in defs
    assert defs["default_brief_asof"].required == frozenset({"state"})

    violations: list[str] = []
    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        violations.extend(
            _scan(path.read_text(encoding="utf-8"), defs, path.relative_to(PKG).as_posix())
        )
    assert violations == [], "call sites written against a stale signature:\n" + "\n".join(violations)
