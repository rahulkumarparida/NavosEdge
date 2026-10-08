"""
Unit Tests for NavosEdge Network IP Detection & .env Configuration Utility
"""

from pathlib import Path
import sys
from unittest.mock import patch
import pytest

# Add repository root to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.update_env_ip import (
    _is_valid_usable_ip,
    detect_network_ip,
    read_current_env_ip,
    update_env_file,
    main,
)


def test_is_valid_usable_ip_valid():
    """Verify standard valid IPv4 addresses are accepted."""
    assert _is_valid_usable_ip("192.168.1.100") is True
    assert _is_valid_usable_ip("10.103.68.72") is True
    assert _is_valid_usable_ip("172.16.0.5") is True
    assert _is_valid_usable_ip("8.8.8.8") is True


def test_is_valid_usable_ip_rejections():
    """Verify loopback, 0.0.0.0, link-local and invalid strings are rejected."""
    # Loopback
    assert _is_valid_usable_ip("127.0.0.1") is False
    assert _is_valid_usable_ip("127.0.1.1") is False

    # 0.0.0.0
    assert _is_valid_usable_ip("0.0.0.0") is False

    # Link-local (169.254.x.x)
    assert _is_valid_usable_ip("169.254.1.1") is False
    assert _is_valid_usable_ip("169.254.200.50") is False

    # Out of range / Malformed
    assert _is_valid_usable_ip("256.0.0.1") is False
    assert _is_valid_usable_ip("192.168.1") is False
    assert _is_valid_usable_ip("192.168.1.1.1") is False
    assert _is_valid_usable_ip("not-an-ip") is False
    assert _is_valid_usable_ip("") is False
    assert _is_valid_usable_ip(None) is False


def test_read_current_env_ip(tmp_path):
    """Test reading IP and port from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Some comments\n"
        "NAVOS_HOST=0.0.0.0\n"
        "NAVOS_UNO_Q_IP=192.168.1.88\n"
        "NAVOS_UNO_Q_PORT=8425\n",
        encoding="utf-8",
    )

    ip, port = read_current_env_ip(env_file=env_file)
    assert ip == "192.168.1.88"
    assert port == 8425


def test_update_env_file_preserves_comments_and_keys(tmp_path):
    """Test updating .env preserves other variables and comments."""
    env_file = tmp_path / ".env"
    initial_content = (
        "# Configuration File\n"
        "NAVOS_HOST=0.0.0.0\n"
        "NAVOS_PORT=8420\n"
        "NAVOS_NODE_ID=uno-q-001\n"
        "NAVOS_UNO_Q_IP=127.0.0.1\n"
        "NAVOS_UNO_Q_PORT=8420\n"
        "NAVOS_UNO_Q_URL=http://127.0.0.1:8420\n"
        "UNO_Q_HOST_DEFAULT=127.0.0.1\n"
    )
    env_file.write_text(initial_content, encoding="utf-8")

    result = update_env_file(ip="10.103.68.72", port=9000, env_file=env_file)

    assert result["ip"] == "10.103.68.72"
    assert result["port"] == "9000"
    assert result["url"] == "http://10.103.68.72:9000"

    content = env_file.read_text(encoding="utf-8")
    assert "# Configuration File" in content
    assert "NAVOS_HOST=0.0.0.0" in content
    assert "NAVOS_NODE_ID=uno-q-001" in content
    assert "NAVOS_UNO_Q_IP=10.103.68.72" in content
    assert "NAVOS_UNO_Q_PORT=9000" in content
    assert "NAVOS_UNO_Q_URL=http://10.103.68.72:9000" in content
    assert "UNO_Q_HOST_DEFAULT=10.103.68.72" in content


def test_update_env_file_creates_missing_keys(tmp_path):
    """Test appending UNO Q keys if they were not originally present."""
    env_file = tmp_path / ".env"
    env_file.write_text("NAVOS_NODE_ID=uno-q-001\n", encoding="utf-8")

    update_env_file(ip="192.168.4.1", port=8420, env_file=env_file, poll_enabled=True)

    content = env_file.read_text(encoding="utf-8")
    assert "NAVOS_UNO_Q_IP=192.168.4.1" in content
    assert "NAVOS_UNO_Q_PORT=8420" in content
    assert "NAVOS_UNO_Q_URL=http://192.168.4.1:8420" in content
    assert "NAVOS_POLL_ENABLED=true" in content


def test_detect_network_ip_live_or_mocked():
    """Verify detect_network_ip returns a valid usable IP or None."""
    ip = detect_network_ip()
    if ip is not None:
        assert _is_valid_usable_ip(ip) is True


def test_detect_network_ip_retry_success():
    """Verify detect_network_ip retries until found within timeout."""
    attempts = [None, None, "192.168.1.150"]

    def mock_attempt():
        if attempts:
            return attempts.pop(0)
        return "192.168.1.150"

    with patch("scripts.update_env_ip._detect_single_attempt", side_effect=mock_attempt):
        ip = detect_network_ip(timeout_s=3.0)
        assert ip == "192.168.1.150"


def test_cli_detect_only(capsys):
    """Verify CLI --detect-only outputs IP and exits 0."""
    with patch("sys.argv", ["update_env_ip.py", "--detect-only"]):
        with patch("scripts.update_env_ip.detect_network_ip", return_value="10.0.0.42"):
            exit_code = main()
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "10.0.0.42" in captured.out


def test_cli_explicit_ip(tmp_path, capsys):
    """Verify CLI --ip explicitly sets target IP."""
    env_file = tmp_path / ".env"
    env_file.write_text("NAVOS_UNO_Q_IP=127.0.0.1\n", encoding="utf-8")

    with patch("scripts.update_env_ip.get_project_root", return_value=tmp_path):
        with patch("sys.argv", ["update_env_ip.py", "--ip", "10.10.10.10", "--port", "8420", "-q"]):
            exit_code = main()
            assert exit_code == 0
            content = env_file.read_text(encoding="utf-8")
            assert "NAVOS_UNO_Q_IP=10.10.10.10" in content
            assert "NAVOS_UNO_Q_URL=http://10.10.10.10:8420" in content
