import enum


class UserRole(str, enum.Enum):
    fisherman = "fisherman"
    authority = "authority"
    operator = "operator"


class QualityFlag(str, enum.Enum):
    good = "good"
    suspect = "suspect"
    missing = "missing"


class AgentRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class SourceStatus(str, enum.Enum):
    live = "live"
    cached = "cached"
    stale = "stale"
    unavailable = "unavailable"


class RouteStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class WarningSeverity(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    extreme = "extreme"
