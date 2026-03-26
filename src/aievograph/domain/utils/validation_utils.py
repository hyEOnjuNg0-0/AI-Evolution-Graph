"""Shared parameter validation utilities for domain services."""


def validate_unit_weights(**kwargs: float) -> None:
    """Validate that all provided float parameters are in [0.0, 1.0].

    Args:
        **kwargs: name=value pairs to validate.

    Raises:
        ValueError: If any value is outside [0.0, 1.0].
    """
    for name, value in kwargs.items():
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")


def validate_positive_int(name: str, value: int) -> None:
    """Validate that an integer parameter is >= 1.

    Args:
        name: Parameter name for the error message.
        value: Value to validate.

    Raises:
        ValueError: If value < 1.
    """
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
