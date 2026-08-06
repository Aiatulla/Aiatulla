from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from app.auditors.rendering import render_repository
from app.llm.protocol import LLMClient, Message, Response, Tool
from app.schemas.finding import Finding, findings_tool_schema


class AuditorError(RuntimeError):
    """Raised when an auditor cannot produce findings from a model reply."""


class Auditor(ABC):
    """One specialised reviewer.

    A subclass supplies three things: a name, a system prompt, and a description
    of what its tool collects. Everything else, including reading the repository
    and validating the reply, is shared.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, used in results and evaluation fixtures."""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Instructions describing what this auditor looks for."""

    @property
    @abstractmethod
    def tool_description(self) -> str:
        """What the findings array should contain, shown to the model."""

    @property
    def tool(self) -> Tool:
        return Tool(
            name="report_findings",
            description=self.tool_description,
            parameters=findings_tool_schema("report_findings", self.tool_description),
        )

    async def run(self, client: LLMClient, repository: Path) -> list[Finding]:
        """Audit a checked-out repository and return validated findings."""
        response = await client.complete(
            messages=[Message(role="user", content=render_repository(repository))],
            tools=[self.tool],
            system=self.system_prompt,
        )
        return self.parse(response)

    def parse(self, response: Response) -> list[Finding]:
        """Validate the model's tool call into Findings.

        :raises AuditorError: when the model answered in prose or produced a
            payload that does not match the schema. Both are failures worth
            surfacing: returning an empty list would be indistinguishable from an
            auditor that legitimately found nothing.
        """
        if not response.tool_calls:
            raise AuditorError(f"{self.name} returned no tool call. Text was: {response.text!r}")

        raw_findings = response.tool_calls[0].arguments.get("findings")
        if raw_findings is None:
            raise AuditorError(f"{self.name} tool call had no findings key")

        try:
            return [Finding.model_validate(item) for item in raw_findings]
        except ValidationError as exc:
            raise AuditorError(
                f"{self.name} produced a finding that failed validation: {exc}"
            ) from exc
