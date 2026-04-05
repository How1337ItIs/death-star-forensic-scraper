"""
Circuit Breaker — Per-domain failure tracking with automatic recovery.

States:
    CLOSED  — Normal operation, requests pass through
    OPEN    — Domain is blocked, requests fail immediately
    HALF_OPEN — Probing with limited requests to test recovery

Transitions:
    CLOSED -> OPEN: After `failure_threshold` consecutive failures
    OPEN -> HALF_OPEN: After `recovery_timeout` seconds
    HALF_OPEN -> CLOSED: If probe request succeeds
    HALF_OPEN -> OPEN: If probe request fails
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger("death_star_v2.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class DomainCircuit:
    """Circuit state for a single domain."""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_failure_reason: str = ""
    opened_at: float = 0.0
    half_open_attempts: int = 0
    total_failures: int = 0
    total_successes: int = 0


class CircuitBreaker:
    """Per-domain circuit breaker for web scraping resilience.

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=300)

        if not breaker.can_request("example.com"):
            logger.info("Domain circuit open, skipping")
            continue

        try:
            result = await fetch(url)
            breaker.record_success("example.com")
        except Exception as e:
            breaker.record_failure("example.com", reason=str(e))
    """

    # HTTP status codes that count as failures
    FAILURE_STATUSES = {403, 418, 429, 451, 503, 520, 521, 522, 523, 524, 525, 526}

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 300.0,  # 5 minutes
        half_open_max_attempts: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_attempts = half_open_max_attempts
        self._circuits: Dict[str, DomainCircuit] = {}

    def _get_circuit(self, domain: str) -> DomainCircuit:
        if domain not in self._circuits:
            self._circuits[domain] = DomainCircuit()
        return self._circuits[domain]

    def can_request(self, domain: str) -> bool:
        """Check if a request to this domain should be allowed."""
        circuit = self._get_circuit(domain)

        if circuit.state == CircuitState.CLOSED:
            return True

        if circuit.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            elapsed = time.time() - circuit.opened_at
            if elapsed >= self.recovery_timeout:
                circuit.state = CircuitState.HALF_OPEN
                circuit.half_open_attempts = 0
                logger.info(
                    f"Circuit for {domain} transitioning to HALF_OPEN "
                    f"(was open for {elapsed:.0f}s)"
                )
                return True
            return False

        if circuit.state == CircuitState.HALF_OPEN:
            return circuit.half_open_attempts < self.half_open_max_attempts

        return True

    def record_success(self, domain: str):
        """Record a successful request to a domain."""
        circuit = self._get_circuit(domain)
        circuit.total_successes += 1

        if circuit.state == CircuitState.HALF_OPEN:
            # Recovery confirmed — close the circuit
            logger.info(f"Circuit for {domain} CLOSED (recovery confirmed)")
            circuit.state = CircuitState.CLOSED
            circuit.consecutive_failures = 0
            circuit.half_open_attempts = 0
        elif circuit.state == CircuitState.CLOSED:
            circuit.consecutive_failures = 0

    def record_failure(self, domain: str, reason: str = "", status_code: Optional[int] = None):
        """Record a failed request to a domain."""
        circuit = self._get_circuit(domain)
        circuit.consecutive_failures += 1
        circuit.total_failures += 1
        circuit.last_failure_time = time.time()
        circuit.last_failure_reason = reason

        if circuit.state == CircuitState.HALF_OPEN:
            circuit.half_open_attempts += 1
            if circuit.half_open_attempts >= self.half_open_max_attempts:
                # Probe failed — reopen
                circuit.state = CircuitState.OPEN
                circuit.opened_at = time.time()
                logger.warning(
                    f"Circuit for {domain} re-OPENED (probe failed: {reason})"
                )
        elif circuit.state == CircuitState.CLOSED:
            if circuit.consecutive_failures >= self.failure_threshold:
                circuit.state = CircuitState.OPEN
                circuit.opened_at = time.time()
                logger.warning(
                    f"Circuit for {domain} OPENED after {circuit.consecutive_failures} "
                    f"consecutive failures (last: {reason})"
                )

    def is_failure_status(self, status_code: int) -> bool:
        """Check if an HTTP status code should count as a circuit breaker failure."""
        return status_code in self.FAILURE_STATUSES

    def get_state(self, domain: str) -> CircuitState:
        """Get current circuit state for a domain."""
        return self._get_circuit(domain).state

    def get_stats(self) -> Dict[str, Dict]:
        """Get stats for all tracked domains."""
        return {
            domain: {
                "state": circuit.state.value,
                "consecutive_failures": circuit.consecutive_failures,
                "total_failures": circuit.total_failures,
                "total_successes": circuit.total_successes,
                "last_failure_reason": circuit.last_failure_reason,
            }
            for domain, circuit in self._circuits.items()
        }

    def reset(self, domain: str):
        """Manually reset a domain's circuit to CLOSED."""
        if domain in self._circuits:
            self._circuits[domain] = DomainCircuit()
            logger.info(f"Circuit for {domain} manually reset")

    def reset_all(self):
        """Reset all circuits."""
        self._circuits.clear()
