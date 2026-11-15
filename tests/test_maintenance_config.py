import json
import subprocess
import sys
from pathlib import Path

import pytest

from validate_maintenance_config import ConfigError, validate_config

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "bando_maintenance_sources.json").read_text(encoding="utf-8"))


def clone_config():
    return json.loads(json.dumps(BASE))


def test_current_scheduled_config_is_valid_and_read_only():
    config = validate_config(clone_config(), base_dir=ROOT)
    assert len(config["repositories"]) == 12
    assert config["max_active"] == 3
    assert config["policy"]["activate_top"] is False


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_activate_top_rejects_coercible_or_non_boolean_values(value):
    config = clone_config()
    config["policy"]["activate_top"] = value
    with pytest.raises(ConfigError, match="activate_top"):
        validate_config(config, base_dir=ROOT)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3", None])
def test_max_active_must_be_positive_json_integer(value):
    config = clone_config()
    config["max_active"] = value
    with pytest.raises(ConfigError, match="max_active"):
        validate_config(config, base_dir=ROOT)


@pytest.mark.parametrize("value", ["MASSIVEMAGNETICS/repo", [], ["repo"], [1], ["MASSIVEMAGNETICS/repo", "MASSIVEMAGNETICS/repo"]])
def test_repository_list_rejects_wrong_shape_malformed_and_duplicate_entries(value):
    config = clone_config()
    config["repositories"] = value
    with pytest.raises(ConfigError, match="repositories|duplicate"):
        validate_config(config, base_dir=ROOT)


def test_schema_version_rejects_boolean_true():
    config = clone_config()
    config["schema_version"] = True
    with pytest.raises(ConfigError, match="schema_version"):
        validate_config(config, base_dir=ROOT)


def test_configured_missing_intent_snapshot_fails_closed():
    config = clone_config()
    config["intent_graph_snapshot"] = "missing-intent.json"
    with pytest.raises(ConfigError, match="does not exist"):
        validate_config(config, base_dir=ROOT)


def test_cli_accepts_current_config():
    result = subprocess.run(
        [sys.executable, str(ROOT / "validate_maintenance_config.py"), "--config", str(ROOT / "bando_maintenance_sources.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "activation disabled" in result.stdout


def test_cli_rejects_truthy_string_without_writing_anything(tmp_path):
    config = clone_config()
    config["policy"]["activate_top"] = "false"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "validate_maintenance_config.py"), "--config", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "policy.activate_top must be a JSON boolean" in result.stderr
    assert list(tmp_path.iterdir()) == [path]
