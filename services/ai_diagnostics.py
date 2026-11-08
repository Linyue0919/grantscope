"""Credential-safe diagnostics for Azure OpenAI connectivity.

Turns exceptions from the `openai` SDK (any version) into a sanitized report:
exception type, HTTP status, Azure error code, request id, underlying cause type,
a redacted message and a hint. Secrets (API key, endpoint host, resource name)
and anything that looks like a token are removed before anything is printed.
Pure functions; no network access and no credential loading happen here.
"""
import re

ENDPOINT_SUFFIXES = (".openai.azure.com", ".cognitiveservices.azure.com", ".services.ai.azure.com")
API_VERSION_RX = re.compile(r"^\d{4}-\d{2}-\d{2}(-preview)?$")

HINTS_BY_STATUS = {
    400: "Bad request: often an unsupported API version for this feature (e.g., JSON mode) or an invalid parameter.",
    401: "Authentication failed: the API key is wrong, expired, or belongs to a different resource.",
    403: "Permission denied: key lacks access, network/firewall rules block this client, or the resource is disabled.",
    404: "Not found: check the deployment name (must match Azure AI Foundry exactly) and the API version.",
    408: "Request timed out on the service side; retry.",
    429: "Rate limited or quota exceeded for this deployment; wait and retry, or raise the TPM quota.",
    500: "Azure OpenAI internal error; retry later.",
    503: "Service unavailable or overloaded; retry later.",
}
HINTS_BY_CODE = {
    "DeploymentNotFound": "The deployment name does not exist on this resource (check AZURE_OPENAI_DEPLOYMENT).",
    "404": "Resource path not found: the endpoint should be the base URL only, e.g. https://<name>.openai.azure.com/",
    "InvalidAuthenticationToken": "The key is not valid for this endpoint.",
    "401": "Access denied: invalid subscription key or wrong API endpoint.",
    "AuthenticationTypeDisabled": "Key authentication is disabled on this resource (Entra ID required).",
    "OperationNotSupported": "This API version or operation is not supported by the deployed model.",
    "unsupported_api_version": "Unsupported API version (AZURE_OPENAI_API_VERSION); try a current GA version such "
                               "as 2024-10-21.",
    "content_filter": "The request was blocked by the content filter (unexpected for a ping).",
}
HINTS_BY_CAUSE = {
    "gaierror": "DNS lookup failed: the endpoint host name is wrong or there is no network/DNS access.",
    "ConnectError": "Could not connect: wrong endpoint, firewall/proxy, or no internet access.",
    "ConnectTimeout": "Connection timed out: network, proxy, or firewall issue.",
    "ReadTimeout": "The service did not respond in time; retry.",
    "SSLError": "TLS/SSL failure: a corporate proxy may be intercepting HTTPS, or the endpoint is not Azure.",
    "SSLCertVerificationError": "Certificate verification failed: likely a proxy intercepting HTTPS.",
    "ProxyError": "Proxy error: check HTTPS_PROXY settings.",
}


def redact(text, secrets=()):
    """Remove secrets and secret-looking values from free text."""
    text = str(text or "")
    for secret in sorted({s for s in secrets if s and len(str(s)) >= 4}, key=len, reverse=True):
        text = text.replace(str(secret), "[REDACTED]")
    text = re.sub(r"https?://[^\s'\"<>]+", "[URL]", text)
    text = re.sub(r"\b[\w-]+\.(?:openai|cognitiveservices|services\.ai)\.azure\.com\b", "[HOST]", text)
    text = re.sub(r"(?i)\b(api[-_ ]?key|subscription[-_ ]?key|authorization)\b\s*[:=]?\s*(?:bearer\s+)?\S+",
                  r"\1 [REDACTED]", text)
    text = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b[A-Za-z0-9+/_-]{24,}\b", "[TOKEN]", text)
    return text[:300]


def secrets_from_config(config):
    """Values that must never appear in output: key, endpoint, host, resource name."""
    if not config:
        return []
    endpoint = str(config.get("endpoint") or "")
    host = re.sub(r"^https?://", "", endpoint).split("/")[0]
    return [config.get("api_key"), endpoint, endpoint.rstrip("/"), host, host.split(".")[0]]


def validate_config_format(config):
    """Format checks that never echo values. Returns a list of warnings."""
    warnings = []
    endpoint = str(config.get("endpoint") or "")
    host = re.sub(r"^https?://", "", endpoint).split("/")[0].lower()
    path = re.sub(r"^https?://[^/]+", "", endpoint)
    if not endpoint.startswith("https://"):
        warnings.append("Endpoint should start with https://")
    if host and not host.endswith(ENDPOINT_SUFFIXES):
        warnings.append("Endpoint host does not end with a known Azure OpenAI domain "
                        "(.openai.azure.com / .cognitiveservices.azure.com).")
    if path.strip("/"):
        warnings.append("Endpoint contains a path; use the base URL only (no /openai/deployments/...).")
    if endpoint != endpoint.strip() or any(c.isspace() for c in endpoint):
        warnings.append("Endpoint contains whitespace.")
    key = str(config.get("api_key") or "")
    if key != key.strip() or any(c.isspace() for c in key):
        warnings.append("API key contains whitespace or line breaks (copy/paste issue).")
    if key.strip().lower().startswith(("<", "your")):
        warnings.append("API key still looks like the template placeholder.")
    if config.get("auth_mode", "api_key") == "api_key" and len(key) < 20:
        warnings.append("API key looks too short to be valid.")
    if not API_VERSION_RX.match(str(config.get("api_version") or "")):
        warnings.append("API version should look like 2024-10-21 or 2025-01-01-preview.")
    deployment = str(config.get("deployment") or "")
    if not deployment or deployment != deployment.strip():
        warnings.append("Deployment name is empty or has surrounding whitespace.")
    return warnings


def _error_fields(exc):
    body = getattr(exc, "body", None)
    code = getattr(exc, "code", None)
    message = None
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        code = code or inner.get("code")
        message = inner.get("message")
        inner_err = inner.get("innererror")
        if isinstance(inner_err, dict) and inner_err.get("code"):
            code = f"{code} / {inner_err['code']}" if code else inner_err["code"]
    return (str(code) if code is not None else None), message


def _request_id(exc):
    rid = getattr(exc, "request_id", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not rid and headers is not None:
        for name in ("apim-request-id", "x-request-id", "x-ms-request-id"):
            try:
                rid = headers.get(name)
            except Exception:  # noqa: BLE001
                rid = None
            if rid:
                break
    return str(rid) if rid else None


def _cause_chain(exc, limit=4):
    chain, seen, current = [], set(), exc.__cause__ or exc.__context__
    while current is not None and id(current) not in seen and len(chain) < limit:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return chain


def classify_exception(exc, secrets=()):
    """Sanitized, structured description of an SDK/network exception."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    code, message = _error_fields(exc)
    causes = _cause_chain(exc)
    hint = None
    if code:
        hint = next((h for c, h in HINTS_BY_CODE.items() if c.lower() in code.lower()), None)
    if not hint and isinstance(status, int):
        hint = HINTS_BY_STATUS.get(status) or (HINTS_BY_STATUS[500] if status >= 500 else None)
    if not hint:
        hint = next((HINTS_BY_CAUSE[c] for c in causes if c in HINTS_BY_CAUSE), None)
    if not hint and type(exc).__name__ == "APITimeoutError":
        hint = HINTS_BY_CAUSE["ReadTimeout"]
    if not hint and type(exc).__name__ == "APIConnectionError":
        hint = HINTS_BY_CAUSE["ConnectError"]
    return {
        "exception": type(exc).__name__,
        "http_status": status if isinstance(status, int) else None,
        "error_code": redact(code, secrets) if code else None,
        "request_id": redact(_request_id(exc), secrets) if _request_id(exc) else None,
        "cause": " <- ".join(causes) or None,
        "message": redact(message or str(exc), secrets) or None,
        "hint": hint or "Unrecognized error; share the sanitized fields above.",
    }


def format_report(info):
    lines = [f"  exception  : {info['exception']}"]
    for key in ("http_status", "error_code", "request_id", "cause", "message"):
        if info.get(key) is not None:
            lines.append(f"  {key:<11}: {info[key]}")
    lines.append(f"  hint       : {info['hint']}")
    return "\n".join(lines)
