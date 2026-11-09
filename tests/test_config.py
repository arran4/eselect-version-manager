"""Unit tests for configuration file parsing, writing, and security."""

import os
import tempfile
try:
    import pytest
except ImportError:
    import tests.compat as pytest

from eselect_version_manager.config import (
    parse_declarative_config,
    update_config_file,
    atomic_write_file,
    tool_key,
    tool_from_key,
)
from eselect_version_manager.errors import InvalidConfigError


def test_tool_key_mapping():
    assert tool_key("go") == "VM_GO"
    assert tool_key("node") == "VM_NODE"
    assert tool_key("test-tool") == "VM_TEST_TOOL"
    assert tool_from_key("VM_GO") == "go"
    assert tool_from_key("VM_NODE") == "node"
    assert tool_from_key("OTHER_KEY") is None


def test_parse_valid_declarative_config(tmp_path):
    conf_file = tmp_path / ".eselect.conf"
    conf_file.write_text(
        "# Gentoo version manager project config\n"
        "VM_GO=\">=1.26 <1.27\"\n"
        "VM_NODE='24'\n"
        "VM_PYTHON=system # inline comment\n"
        "\n"
        "# Another comment\n"
        "VM_FIXTURE=\"2.0\"\n"
    )

    data = parse_declarative_config(str(conf_file))
    assert data["VM_GO"] == ">=1.26 <1.27"
    assert data["VM_NODE"] == "24"
    assert data["VM_PYTHON"] == "system"
    assert data["VM_FIXTURE"] == "2.0"


def test_parse_rejects_command_substitution(tmp_path):
    conf_file = tmp_path / ".eselect.conf"
    conf_file.write_text('VM_GO="$(rm -rf /)"\n')

    with pytest.raises(InvalidConfigError) as exc_info:
        parse_declarative_config(str(conf_file))
    assert "command substitution is forbidden" in str(exc_info.value)


def test_parse_rejects_backticks(tmp_path):
    conf_file = tmp_path / ".eselect.conf"
    conf_file.write_text('VM_GO=`id`\n')

    with pytest.raises(InvalidConfigError) as exc_info:
        parse_declarative_config(str(conf_file))
    assert "command substitution is forbidden" in str(exc_info.value)


def test_parse_rejects_unclosed_quote(tmp_path):
    conf_file = tmp_path / ".eselect.conf"
    conf_file.write_text('VM_GO="1.26\n')

    with pytest.raises(InvalidConfigError) as exc_info:
        parse_declarative_config(str(conf_file))
    assert "unclosed quote" in str(exc_info.value)


def test_update_config_file_preserves_comments(tmp_path):
    conf_file = tmp_path / ".eselect.conf"
    conf_file.write_text(
        "# Header comment\n"
        "VM_NODE=\"20\"\n"
        "# Tool for Go\n"
        "VM_GO=\"1.22\"\n"
    )

    # Update Go, remove Node, add Python
    update_config_file(
        str(conf_file),
        {"VM_GO": "1.23", "VM_NODE": None, "VM_PYTHON": "3.12"}
    )

    result_text = conf_file.read_text()
    assert "# Header comment" in result_text
    assert "# Tool for Go" in result_text
    assert 'VM_GO="1.23"' in result_text
    assert 'VM_PYTHON="3.12"' in result_text
    assert "VM_NODE" not in result_text


def test_atomic_write(tmp_path):
    target = tmp_path / "sub" / "config.conf"
    atomic_write_file(str(target), 'KEY="value"\n')
    assert target.is_file()
    assert target.read_text() == 'KEY="value"\n'
