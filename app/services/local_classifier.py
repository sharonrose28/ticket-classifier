"""Deterministic last-resort classification when no LLM credential is available."""

import time

from app.schemas.classification import (
    ClassificationCategory,
    ClassificationResult,
    ClassificationUrgency,
    TicketClassification,
)


class LocalClassificationService:
    """Keep ticket routing operational without pretending a local rule is an LLM."""

    async def classify_ticket(self, *, title: str, description: str) -> ClassificationResult:
        started_at = time.perf_counter()
        text = f"{title} {description}".lower()
        category = self._category(text)
        urgency = self._urgency(text)
        return ClassificationResult(
            classification=TicketClassification(
                urgency=urgency,
                category=category,
                confidence=0.6,
                reasoning="Classified by the deterministic availability fallback.",
            ),
            model="local-rule-fallback-v1",
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=0,
            latency_ms=max(0, round((time.perf_counter() - started_at) * 1000)),
            attempt_count=1,
        )

    @staticmethod
    def _category(text: str) -> ClassificationCategory:
        if any(word in text for word in ("invoice", "billing", "charged", "payment", "refund")):
            return ClassificationCategory.BILLING
        if any(word in text for word in ("bug", "crash", "exception", "stack trace", "500 error")):
            return ClassificationCategory.BUG
        if any(word in text for word in ("password", "login", "account", "locked", "profile")):
            return ClassificationCategory.ACCOUNT
        if any(word in text for word in ("api", "server", "database", "technical", "integration")):
            return ClassificationCategory.TECHNICAL
        return ClassificationCategory.GENERAL

    @staticmethod
    def _urgency(text: str) -> ClassificationUrgency:
        if any(
            phrase in text
            for phrase in (
                "all customers",
                "production down",
                "completely unavailable",
                "security breach",
                "data loss",
            )
        ):
            return ClassificationUrgency.CRITICAL
        if any(word in text for word in ("urgent", "blocked", "cannot", "outage")):
            return ClassificationUrgency.HIGH
        if any(word in text for word in ("error", "failed", "problem", "issue")):
            return ClassificationUrgency.MEDIUM
        return ClassificationUrgency.LOW
