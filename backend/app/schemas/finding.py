from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """How much a finding matters. Ordered worst to least."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    """One issue an auditor reports.

    The model produces these by calling a tool, so the shape is validated on
    arrival instead of being parsed out of prose. A reply that does not fit this
    schema is a failed call, not something to guess at.
    """

    category: str = Field(
        description="Machine-readable kind of issue, lower_snake_case, "
        "for example unused_module or hardcoded_credential",
    )
    file_path: str = Field(description="Path relative to the repository root")
    line: int | None = Field(
        default=None,
        description="1-indexed line the finding anchors to, when it applies to one line",
    )
    severity: Severity
    summary: str = Field(description="One sentence stating the defect")
    evidence: str = Field(description="What in the code shows this, quoted or referenced")


def findings_tool_schema(tool_name: str, description: str) -> dict[str, Any]:
    """Build the JSON Schema an auditor gives the model.

    Derived from the Pydantic model rather than written by hand, so the schema the
    model is asked to fill and the schema we validate against cannot drift apart.
    """
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": description,
                "items": _strip_unsupported(Finding.model_json_schema()),
            }
        },
        "required": ["findings"],
    }


def _strip_unsupported(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove JSON Schema keywords that provider function-calling does not accept.

    Gemini rejects $defs and $ref, and Pydantic emits both for the Severity enum.
    Inlining the enum keeps the constraint while dropping the indirection.
    """
    definitions = schema.pop("$defs", {})
    properties = schema.get("properties", {})

    for name, prop in properties.items():
        # Pydantic emits a bare $ref for a required enum and wraps it in allOf
        # when the field also carries its own keywords. Both shapes appear.
        ref = prop.pop("$ref", None)
        if ref is None and (all_of := prop.pop("allOf", None)):
            ref = all_of[0].get("$ref")

        if ref:
            target = ref.rsplit("/", 1)[-1]
            if target in definitions:
                properties[name] = {**definitions[target], **prop}

    schema.pop("title", None)
    for prop in properties.values():
        prop.pop("title", None)

    return schema
