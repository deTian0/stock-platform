"""``dotenv`` loader tests — pure parsing + precedence + pytest guard.

No public net, no real ``.env``: every case injects its own mapping or temp file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.dotenv import (
    ENV_DOTENV_DISABLE,
    DotenvMissingError,
    find_dotenv_path,
    is_disabled,
    load_dotenv,
    parse_dotenv_text,
    reset_dotenv_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_dotenv_cache()
    yield
    reset_dotenv_cache()


# --- parsing ---------------------------------------------------------------


def test_parse_skips_blanks_comments_and_junk() -> None:
    text = "\n".join(
        [
            "# a comment",
            "",
            "   ",
            "PLAIN=value",
            "  SPACED  =  trimmed  ",
            "not-a-pair",
            "=novalue",
        ]
    )
    parsed = parse_dotenv_text(text)
    assert parsed == {"PLAIN": "value", "SPACED": "trimmed"}


def test_parse_handles_export_quotes_and_inline_comment() -> None:
    text = "\n".join(
        [
            "export EXPORTED=yes",
            'DQ="has spaces"',
            "SQ='single'",
            "INLINE=value # trailing comment",
            "HASHY=a#b",  # no space before # → part of the value
        ]
    )
    parsed = parse_dotenv_text(text)
    assert parsed["EXPORTED"] == "yes"
    assert parsed["DQ"] == "has spaces"
    assert parsed["SQ"] == "single"
    assert parsed["INLINE"] == "value"
    assert parsed["HASHY"] == "a#b"


# --- precedence ------------------------------------------------------------


def test_load_does_not_override_existing_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=from_file\nOTHER=x\n", encoding="utf-8")
    env = {"TOKEN": "from_shell"}

    applied = load_dotenv(env_file, env=env, force=True)

    assert env["TOKEN"] == "from_shell"  # explicit wins
    assert env["OTHER"] == "x"
    assert applied == {"OTHER": "x"}  # only what was actually applied


def test_load_override_true_lets_file_win(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=from_file\n", encoding="utf-8")
    env = {"TOKEN": "from_shell"}

    load_dotenv(env_file, override=True, env=env, force=True)

    assert env["TOKEN"] == "from_file"


def test_load_missing_file_is_silent(tmp_path: Path) -> None:
    missing = tmp_path / "nope.env"
    env: dict[str, str] = {}
    assert load_dotenv(missing, env=env, force=True) == {}
    assert env == {}


def test_load_required_raises_when_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    with pytest.raises(DotenvMissingError) as exc:
        load_dotenv(env_file, env={}, required=["A", "MISSING_ONE"], force=True)
    assert "MISSING_ONE" in str(exc.value)


def test_load_required_ok_when_all_present(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=2\n", encoding="utf-8")
    env: dict[str, str] = {}
    load_dotenv(env_file, env=env, required=["A", "B"], force=True)
    assert env == {"A": "1", "B": "2"}


# --- guard -----------------------------------------------------------------


def test_is_disabled_under_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    # pytest sets PYTEST_CURRENT_TEST itself, so the guard is on by default here.
    monkeypatch.delenv(ENV_DOTENV_DISABLE, raising=False)
    assert is_disabled() is True


def test_is_disabled_honours_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_DOTENV_DISABLE, "1")
    assert is_disabled() is True
    monkeypatch.setenv(ENV_DOTENV_DISABLE, "0")
    assert is_disabled({"PYTEST_CURRENT_TEST": ""}) is False


def test_implicit_load_is_a_noop_under_pytest() -> None:
    """The guard is what keeps the developer's real token out of the test env."""
    env: dict[str, str] = {"PYTEST_CURRENT_TEST": "x"}
    assert is_disabled(env) is True
    assert load_dotenv(env=env) == {}


def test_guard_applies_to_injected_env_too(tmp_path: Path) -> None:
    """A caller-supplied mapping must not bypass the guard either."""
    env_file = tmp_path / ".env"
    env_file.write_text("X=1\n", encoding="utf-8")
    env: dict[str, str] = {"PYTEST_CURRENT_TEST": "x"}
    assert load_dotenv(env_file, env=env) == {}
    assert "X" not in env


def test_force_bypasses_guard(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("X=1\n", encoding="utf-8")
    env: dict[str, str] = {"PYTEST_CURRENT_TEST": "x"}
    applied = load_dotenv(env_file, env=env, force=True)
    assert applied == {"X": "1"}
    assert env["X"] == "1"


def test_disable_flag_blocks_even_without_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.setenv(ENV_DOTENV_DISABLE, "true")
    env: dict[str, str] = {}
    assert load_dotenv(env=env) == {}


# --- discovery -------------------------------------------------------------


def test_find_dotenv_prefers_explicit(tmp_path: Path) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text("A=1\n", encoding="utf-8")
    assert find_dotenv_path(env_file) == env_file
    assert find_dotenv_path(tmp_path / "absent.env") is None


def test_find_dotenv_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "via_var.env"
    env_file.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setenv("STOCK_PLATFORM_DOTENV", str(env_file))
    assert find_dotenv_path() == env_file


def test_find_dotenv_walks_up_from_module() -> None:
    """In a source checkout the repo-root .env is discoverable (if it exists)."""
    found = find_dotenv_path()
    if found is not None:
        assert found.name == ".env"
