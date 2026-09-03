import uuid
from datetime import datetime, timezone


def build_envelope(data=None, errors=None, meta: dict | None = None):
    return {
        "data": data,
        "errors": errors if errors is not None else [],
        "meta": {
            "request_id": meta.get("request_id") if meta else str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
