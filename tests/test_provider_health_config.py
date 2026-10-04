from pathlib import Path
import yaml

from web.backend.services import provider_health


def test_provider_health_uses_trusted_local_config(tmp_path, monkeypatch):
    cfg=tmp_path/'model_providers.yaml'
    cfg.write_text(yaml.safe_dump({'default_provider':'local_ollama','providers':{'local_ollama':{'provider_type':'local_ollama','base_url':'http://127.0.0.1:9999'}}}))
    monkeypatch.setenv('AIFACTORY_MODEL_PROVIDERS',str(cfg)); monkeypatch.delenv('AIFACTORY_OLLAMA_URL',raising=False)
    assert provider_health.configured_ollama_base_url() == 'http://127.0.0.1:9999'


def test_provider_health_rejects_remote_probe_target(tmp_path, monkeypatch):
    cfg=tmp_path/'model_providers.yaml'
    cfg.write_text(yaml.safe_dump({'default_provider':'local_ollama','providers':{'local_ollama':{'provider_type':'local_ollama','base_url':'https://evil.example'}}}))
    monkeypatch.setenv('AIFACTORY_MODEL_PROVIDERS',str(cfg)); monkeypatch.delenv('AIFACTORY_OLLAMA_URL',raising=False)
    assert provider_health.configured_ollama_base_url() == 'http://host.docker.internal:11434'
