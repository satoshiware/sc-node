from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_probe_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ledger_mvp_probe.py"
    spec = importlib.util.spec_from_file_location("ledger_mvp_probe", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _response(path: str, status: int, payload: dict | None) -> dict:
    return {
        "path": path,
        "url": f"http://api.test{path}",
        "status": status,
        "json": payload,
        "transport_error": None,
    }


def _transport_error(path: str, detail: str) -> dict:
    return {
        "path": path,
        "url": f"http://api.test{path}",
        "status": None,
        "json": None,
        "transport_error": detail,
    }


def _fetcher_factory(module, mapping: dict[str, dict]):
    def _fetcher(base_url: str, token: str, path: str, timeout: float) -> dict:
        assert base_url == "http://api.test"
        assert token == "secret-token"
        assert timeout == 5.0
        assert path in mapping
        return mapping[path]

    return _fetcher


def test_probe_pass_report() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "ok", "configured": True},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {
                "status": "ok",
                "configured": True,
                "data": {
                    "items": [
                        {
                            "channel_id": 7,
                            "join_status": "joined",
                            "worker_identity": "alice.rig01",
                            "share_work_sum": "12345",
                        }
                    ]
                },
            },
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {"status": "ok", "items": [{"blockhash_status": "resolved"}]},
        ),
        module.AZ_REWARDS_PATH: _response(
            module.AZ_REWARDS_PATH,
            200,
            {"blocks": [{"blockhash": "00" * 32}]},
        ),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.PASS
    assert report["warn_count"] == 0
    assert report["fail_count"] == 0


def test_probe_warns_for_translator_readiness_gaps() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "degraded", "configured": True},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {
                "status": "ok",
                "configured": True,
                "data": {
                    "items": [
                        {
                            "channel_id": 11,
                            "join_status": "joined",
                            "worker_identity": None,
                            "share_work_sum": "42",
                        }
                    ]
                },
            },
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {
                "status": "ok",
                "items": [
                    {"blockhash_status": "unresolved"},
                    {"blockhash_status": "resolved"},
                ],
            },
        ),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 200, {"blocks": []}),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.WARN
    messages = [check["message"] for check in report["checks"]]
    assert any("Translator is degraded" in message for message in messages)
    assert any("missing worker_identity" in message for message in messages)
    assert any("unresolved blockhash" in message for message in messages)


def test_probe_warns_on_zero_snapshot_rows() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "unconfigured", "configured": False},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {"status": "unconfigured", "configured": False, "data": {"items": []}},
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {"status": "ok", "items": []},
        ),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 200, {"blocks": []}),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.WARN
    messages = [check["message"] for check in report["checks"]]
    assert any("Translator is unconfigured" in message for message in messages)
    assert any("zero rows" in message for message in messages)


def test_probe_fails_when_api_is_unreachable() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _transport_error(module.HEALTH_PATH, "URLError: refused"),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "ok", "configured": True},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {"status": "ok", "configured": True, "data": {"items": []}},
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {"status": "ok", "items": []},
        ),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 200, {"blocks": []}),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.FAIL
    assert any("API unreachable" in check["message"] for check in report["checks"])


def test_probe_fails_on_auth_failure() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(module.TRANSLATOR_STATUS_PATH, 401, None),
        module.MINER_SNAPSHOT_PATH: _response(module.MINER_SNAPSHOT_PATH, 401, None),
        module.BLOCKS_FOUND_PATH: _response(module.BLOCKS_FOUND_PATH, 401, None),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 401, None),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.FAIL
    assert any("Auth failure" in check["message"] for check in report["checks"])


def test_probe_fails_when_joined_row_is_missing_share_work_sum() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "ok", "configured": True},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {
                "status": "ok",
                "configured": True,
                "data": {
                    "items": [
                        {
                            "channel_id": 3,
                            "join_status": "joined",
                            "worker_identity": "bob.rig02",
                            "share_work_sum": None,
                        }
                    ]
                },
            },
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {"status": "ok", "items": []},
        ),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 200, {"blocks": []}),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.FAIL
    assert any("missing share_work_sum" in check["message"] for check in report["checks"])


def test_probe_fails_when_az_rewards_are_unavailable() -> None:
    module = _load_probe_module()
    mapping = {
        module.HEALTH_PATH: _response(module.HEALTH_PATH, 200, {"status": "ok"}),
        module.TRANSLATOR_STATUS_PATH: _response(
            module.TRANSLATOR_STATUS_PATH,
            200,
            {"status": "ok", "configured": True},
        ),
        module.MINER_SNAPSHOT_PATH: _response(
            module.MINER_SNAPSHOT_PATH,
            200,
            {
                "status": "ok",
                "configured": True,
                "data": {
                    "items": [
                        {
                            "channel_id": 9,
                            "join_status": "joined",
                            "worker_identity": "carol.rig03",
                            "share_work_sum": "100",
                        }
                    ]
                },
            },
        ),
        module.BLOCKS_FOUND_PATH: _response(
            module.BLOCKS_FOUND_PATH,
            200,
            {"status": "ok", "items": []},
        ),
        module.AZ_REWARDS_PATH: _response(module.AZ_REWARDS_PATH, 503, None),
    }

    report = module.probe(
        base_url="http://api.test",
        token="secret-token",
        timeout=5.0,
        fetcher=_fetcher_factory(module, mapping),
    )

    assert report["overall"] == module.FAIL
    assert any("AZ rewards unavailable" in check["message"] for check in report["checks"])


def test_main_uses_env_vars_and_exits_fail_when_missing(monkeypatch, capsys) -> None:
    module = _load_probe_module()
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    exit_code = module.main([])

    captured = capsys.readouterr()
    assert exit_code == module.FAIL
    assert "API_BASE_URL must be set" in captured.out
    assert "API_TOKEN must be set" in captured.out


def test_main_help_exits_zero(capsys) -> None:
    module = _load_probe_module()

    try:
        module.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("expected SystemExit from --help")

    captured = capsys.readouterr()
    assert "Probe SC-node ledger input readiness" in captured.out
