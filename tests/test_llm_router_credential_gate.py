import asyncio
from pathlib import Path
import yaml
from llm.router import LLMRouter


def test_router_skips_remote_provider_missing_declared_credential(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg={
        "default_provider":"local_ollama",
        "providers":{
            "local_ollama":{"enabled":True,"provider_type":"local_ollama","base_url":"http://127.0.0.1:11434","models":{"heavy":"qwen2.5:3b","light":"qwen2.5:3b"}},
            "openrouter_api":{"enabled":True,"provider_type":"openai_compatible","base_url":"https://openrouter.ai/api/v1","api_key_env":"OPENROUTER_API_KEY","models":{"heavy":"x","light":"x"}},
        },
        "routing_rules":[],
    }
    path=tmp_path/"providers.yaml"; path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    router=LLMRouter(config_path=str(path))
    assert "local_ollama" in router.providers
    assert "openrouter_api" not in router.providers
    asyncio.run(router.close())
