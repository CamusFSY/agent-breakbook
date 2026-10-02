"""Versioned experiment records; simulated and live evidence never share a label."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CaseId = Literal["lost-ack", "hung-tool", "retry-storm"]
Variant = Literal["broken", "fixed"]


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_timeout: float = Field(default=0.05, ge=0.01, le=60)
    watchdog: float = Field(default=0.25, ge=0.02, le=600)
    max_tool_calls: int = Field(default=8, ge=4, le=100)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    max_turns: int = Field(default=8, ge=1, le=30)
    max_output_tokens: int = Field(default=512, ge=128, le=4096)
    token_budget: int = Field(default=20000, ge=512, le=200000)

    @model_validator(mode="after")
    def ordered(self):
        if self.watchdog <= self.tool_timeout:
            raise ValueError("watchdog must be longer than tool_timeout")
        if self.max_tool_calls <= self.retry_attempts:
            raise ValueError("max_tool_calls must exceed retry_attempts")
        return self


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["sent", "ok", "timed_out", "unavailable", "unknown"]
    receipt_id: str | None = None


class AdapterResult(BaseModel):
    outcome: Outcome = Field(default_factory=lambda: Outcome(status="unknown"))
    termination: str = "completed"
    error: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class Check(BaseModel):
    name: str
    passed: bool
    expected: str
    actual: str


class Trial(BaseModel):
    case: CaseId
    variant: Variant
    adapter: str
    transport: str
    evidence: Literal["scripted", "live-model", "sdk-test-model", "custom-adapter"]
    index: int
    fault: bool
    verdict: Literal["pass", "fail", "infra_error"]
    duration_ms: float
    result: AdapterResult
    checks: list[Check]
    state: dict


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    breakbook_version: str
    created_at: str
    environment: dict[str, str]
    limits: Limits
    trials: list[Trial]

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.trials),
            "pass": sum(t.verdict == "pass" for t in self.trials),
            "fail": sum(t.verdict == "fail" for t in self.trials),
            "infra_error": sum(t.verdict == "infra_error" for t in self.trials),
        }
