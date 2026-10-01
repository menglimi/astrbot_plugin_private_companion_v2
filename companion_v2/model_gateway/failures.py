"""Fixed failure classifications; never carry provider text or exception details."""

from enum import Enum


class ModelFailure(str, Enum):
    PREPARATION = "request_preparation_failed"
    TRANSPORT = "provider_request_failed"
    NATIVE_PARSE = "native_response_parse_failed"
    PROVIDER_RECHECK = "provider_recheck_failed"
    ROLE_RECHECK = "role_recheck_failed"
    WIRE_DECODE = "response_contract_rejected"
    ADAPTER = "adapter_failed"
    INTERRUPTED = "provider_wait_interrupted"
    TIMEOUT = "provider_wait_timed_out"
    GATEWAY_RECHECK = "request_recheck_failed"
    RECOVERY = "runtime_interrupted"
    REFUSAL = "provider_refused"

    def document(self) -> dict[str, str]:
        return {"phase": _PHASES[self], "code": self.value}


_PHASES = {
    ModelFailure.PREPARATION: "preparation",
    ModelFailure.TRANSPORT: "provider_request",
    ModelFailure.NATIVE_PARSE: "native_parse",
    ModelFailure.PROVIDER_RECHECK: "provider_recheck",
    ModelFailure.ROLE_RECHECK: "role_recheck",
    ModelFailure.WIRE_DECODE: "response_validation",
    ModelFailure.ADAPTER: "gateway_adapter",
    ModelFailure.INTERRUPTED: "gateway_wait",
    ModelFailure.TIMEOUT: "gateway_wait",
    ModelFailure.GATEWAY_RECHECK: "gateway_recheck",
    ModelFailure.RECOVERY: "recovery",
    ModelFailure.REFUSAL: "provider_refusal",
}
