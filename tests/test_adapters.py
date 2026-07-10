import pytest
from hermes_trading.adapters.common import validate, SchemaError

def test_schema_validation():
    assert validate({"schema_version":1,"x":1},{"schema_version","x"},"x")["x"] == 1
    with pytest.raises(SchemaError):
        validate({"schema_version":2,"x":1},{"schema_version","x"},"x")
