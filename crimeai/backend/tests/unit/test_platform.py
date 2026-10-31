"""Configuration hardening, upload sniffing, storage safety, and the patrol cache key fix."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.nlp.documents import sniff_content_type
from app.services.storage import LocalDocumentStore, safe_filename

STRONG = "x" * 48


class TestProductionConfig:
    def test_defaults_rejected_in_production(self):
        with pytest.raises(ValidationError) as exc:
            Settings(APP_ENV="production", _env_file=None)
        message = str(exc.value)
        assert "JWT_SECRET_KEY" in message and "ALLOWED_HOSTS" in message

    def test_hardened_production_config_accepted(self):
        settings = Settings(
            APP_ENV="production", _env_file=None, APP_SECRET_KEY=STRONG, JWT_SECRET_KEY=STRONG, ENTITY_HASH_KEY=STRONG,
            ALLOWED_HOSTS="api.example.in", ALLOWED_ORIGINS="https://app.example.in", ROUTING_URL="http://osrm.internal:5000",
        )
        assert settings.ALLOWED_HOSTS == ["api.example.in"]
        assert not settings.exposes_error_detail

    def test_staging_does_not_leak_error_detail(self):
        settings = Settings(
            APP_ENV="staging", _env_file=None, APP_SECRET_KEY=STRONG, JWT_SECRET_KEY=STRONG, ENTITY_HASH_KEY=STRONG,
            ALLOWED_HOSTS="s.example.in", ROUTING_ENABLED=False,
        )
        assert not settings.exposes_error_detail


    def test_comma_separated_env_values(self, monkeypatch):
        """Regression: list settings from plain env strings used to fail JSON decoding at startup."""
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173, https://app.example.in")
        monkeypatch.setenv("ALLOWED_HOSTS", "*")
        settings = Settings(_env_file=None)
        assert settings.ALLOWED_ORIGINS == ["http://localhost:5173", "https://app.example.in"]
        assert settings.ALLOWED_HOSTS == ["*"]

    def test_json_env_values_still_work(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", '["http://a.test","http://b.test"]')
        assert Settings(_env_file=None).ALLOWED_ORIGINS == ["http://a.test", "http://b.test"]


class TestUploads:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            (b"%PDF-1.7 ...", "application/pdf"),
            (b"\x89PNG\r\n\x1a\nxxxx", "image/png"),
            (b"\xff\xd8\xff\xe0xxxx", "image/jpeg"),
            (b"FIR narrative in plain text", "text/plain"),
            (b"RIFF\x10\x00\x00\x00WEBPVP8 ", "image/webp"),
            (bytes([0x4D, 0x5A, 0x90, 0x00, 0x03]), None),
        ],
    )
    def test_sniffing_ignores_declared_type(self, data, expected):
        assert sniff_content_type(data) == expected

    def test_filename_sanitised(self):
        assert safe_filename("../../etc/passwd") == "passwd"
        assert "/" not in safe_filename("a/b\\c<d>.pdf")

    def test_local_store_blocks_path_traversal(self, tmp_path):
        from app.core.exceptions import StorageError

        with pytest.raises(StorageError):
            LocalDocumentStore(str(tmp_path))._path("../outside.txt")


def test_patrol_checkpoints_rank_by_incident_density():
    from app.services.graph_service import build_checkpoints

    crimes = [{"lat": 28.61, "lng": 77.21, "district": "A", "risk_score": 10.0}] * 5 + [
        {"lat": 28.70, "lng": 77.30, "district": "A", "risk_score": 50.0}
    ]
    checkpoints = build_checkpoints(crimes, num_checkpoints=2)
    assert checkpoints[0]["crime_count"] == 5 and checkpoints[1]["crime_count"] == 1


class TestDeploymentGuards:
    def test_public_routing_server_rejected_in_production(self):
        with pytest.raises(ValidationError, match="ROUTING_URL"):
            Settings(APP_ENV="production", _env_file=None, APP_SECRET_KEY=STRONG, JWT_SECRET_KEY=STRONG,
                     ENTITY_HASH_KEY=STRONG, ALLOWED_HOSTS="api.example.in")

    def test_public_routing_allowed_when_accepted_or_disabled(self):
        base = {"APP_ENV": "production", "_env_file": None, "APP_SECRET_KEY": STRONG, "JWT_SECRET_KEY": STRONG,
                "ENTITY_HASH_KEY": STRONG, "ALLOWED_HOSTS": "api.example.in"}
        assert Settings(**base, ROUTING_ALLOW_PUBLIC=True).ROUTING_ALLOW_PUBLIC
        assert not Settings(**base, ROUTING_ENABLED=False).ROUTING_ENABLED
        assert Settings(**base, ROUTING_URL="http://osrm.internal:5000").ROUTING_URL


async def test_eviction_policy_unknown_when_config_is_forbidden():
    from app.db.redis import eviction_policy

    class Managed:
        async def config_get(self, _):
            raise PermissionError("CONFIG is disabled")

    class Local:
        async def config_get(self, key):
            return {key: "allkeys-lru"}

    assert await eviction_policy(Managed()) is None
    assert await eviction_policy(Local()) == "allkeys-lru"
