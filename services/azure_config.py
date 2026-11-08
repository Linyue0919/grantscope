"""Environment-first Azure settings and keyless authentication; no calls on import."""
import os
import subprocess

def settings(source=None):
    names = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT",
             "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_AUTH_MODE", "GRANTSCOPE_AZURE_CLI",
             "AZURE_OPENAI_RESEARCH_DEPLOYMENT", "AZURE_OPENAI_RESEARCH_MODEL_VERSION", "RESEARCH_TPM")
    result = {}
    for name in names:
        value = os.environ.get(name)
        if not value and source is not None:
            try: value = source.get(name)
            except Exception: value = None  # Streamlit secrets file is optional.
        if value: result[name] = str(value).strip()
    if not result.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("GRANTSCOPE_AZURE_ENDPOINT"):
        result["AZURE_OPENAI_ENDPOINT"] = os.environ["GRANTSCOPE_AZURE_ENDPOINT"]
    return result

def auth_mode(config):
    mode = config.get("AZURE_OPENAI_AUTH_MODE", "auto")
    if mode == "auto":
        return "azure_cli" if config.get("GRANTSCOPE_AZURE_CLI") else "api_key"
    if mode not in ("api_key", "azure_cli", "managed_identity"):
        raise ValueError("Unsupported Azure authentication mode")
    return mode

def token_provider(config):
    if auth_mode(config) == "azure_cli":
        cli = config.get("GRANTSCOPE_AZURE_CLI", "az")
        def token():
            result = subprocess.run([cli, "account", "get-access-token", "--resource",
                "https://cognitiveservices.azure.com/", "--query", "accessToken", "-o", "tsv",
                "--only-show-errors"], capture_output=True, text=True, timeout=60)
            if result.returncode or not result.stdout.strip():
                raise RuntimeError("Azure interactive authentication required")
            return result.stdout.strip()
        return token
    from azure.identity import ManagedIdentityCredential, get_bearer_token_provider
    return get_bearer_token_provider(ManagedIdentityCredential(), "https://cognitiveservices.azure.com/.default")
