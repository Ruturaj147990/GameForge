"""Re-export boundary protection from security.boundary."""
from .security.boundary import BoundaryManager, SecurityViolationError

__all__ = ["BoundaryManager", "SecurityViolationError"]
