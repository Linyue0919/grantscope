"""Release configuration checks; never acquire tokens or make inference calls."""
from unittest.mock import Mock, patch
import pytest
from services.azure_config import settings, auth_mode
from services.ai_matching import load_ai_config, AzureJSONEvaluator
from services.research_engine import configured_provider


def test_environment_wins_and_missing_streamlit_secrets_are_optional(monkeypatch):
    class Missing:
        def get(self, name): raise FileNotFoundError('No local secrets')
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT', 'https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_AUTH_MODE', 'managed_identity')
    config=load_ai_config(Missing())
    assert config['auth_mode']=='managed_identity'
    assert config['endpoint']=='https://example.openai.azure.com'


def test_deep_research_environment_deployment_and_no_eager_auth(monkeypatch):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_AUTH_MODE','managed_identity')
    monkeypatch.setenv('AZURE_OPENAI_RESEARCH_DEPLOYMENT','reviewed-sol')
    monkeypatch.setenv('AZURE_OPENAI_RESEARCH_MODEL_VERSION','reviewed-version')
    with patch('services.azure_config.token_provider',return_value=Mock()) as provider:
        research=configured_provider({})
        assert research.deployment=='reviewed-sol'
        assert research.expected_model=='reviewed-version'
        provider.return_value.assert_not_called()


def test_dashboard_uses_keyless_client_without_retries(monkeypatch):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://example.openai.azure.com')
    monkeypatch.setenv('AZURE_OPENAI_AUTH_MODE','managed_identity')
    with patch('services.azure_config.token_provider',return_value=Mock()) as token, patch('openai.AzureOpenAI') as client:
        AzureJSONEvaluator(load_ai_config({}))._get_client()
        assert client.call_args.kwargs['azure_ad_token_provider'] is token.return_value
        assert 'api_key' not in client.call_args.kwargs
        assert client.call_args.kwargs['max_retries']==0


def test_invalid_auth_mode_fails_closed():
    with pytest.raises(ValueError): auth_mode({'AZURE_OPENAI_AUTH_MODE':'typo'})


def test_saved_grants_and_research_use_persistent_directory(monkeypatch,tmp_path):
    from services.grant_store import LocalGrantStore
    from services.research_engine import ResearchStore
    monkeypatch.setenv('GRANTSCOPE_DATA_DIR',str(tmp_path))
    assert LocalGrantStore().path==tmp_path/'grants.json'
    assert ResearchStore().root==tmp_path/'research_v1'
