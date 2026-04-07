from pydantic import BaseModel, model_validator


class YearRangeRequest(BaseModel):
    """Mixin that validates start_year <= end_year when both are provided."""

    @model_validator(mode="after")
    def validate_year_range(self) -> "YearRangeRequest":
        start = getattr(self, "start_year", None)
        end = getattr(self, "end_year", None)
        if start is not None and end is not None and start > end:
            raise ValueError("start_year must be <= end_year")
        return self


def validate_not_blank(field_name: str, v: str) -> str:
    """Raise ValueError if the string value is blank after stripping."""
    if isinstance(v, str) and not v.strip():
        raise ValueError(f"{field_name} must not be blank")
    return v
