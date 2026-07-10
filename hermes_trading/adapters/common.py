class SchemaError(RuntimeError):
    """Raised when an adapter returns an unexpected schema."""

EXPECTED_SCHEMA_VERSION = 1

def validate(payload: dict, required: set[str], name: str) -> dict:
    if not isinstance(payload, dict):
        raise SchemaError(f"{name}: payload is not a dict")
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise SchemaError(f"{name}: schema_version mismatch: {payload.get('schema_version')}")
    missing = required - payload.keys()
    if missing:
        raise SchemaError(f"{name}: missing keys {sorted(missing)}")
    return payload
