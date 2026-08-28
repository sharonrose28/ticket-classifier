"""Deterministic last-resort classification when no LLM credential is available."""

import re
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
        terms = {
            ClassificationCategory.BILLING: (
                "bill",
                "billing",
                "invoice",
                "payment",
                "charged",
                "charge",
                "refund",
                "price",
                "pricing",
                "subscription",
                "card",
                "checkout",
            ),
            ClassificationCategory.TECHNICAL: (
                "api",
                "server",
                "database",
                "integration",
                "network",
                "timeout",
                "latency",
                "configuration",
                "install",
                "connection",
                "webhook",
            ),
            ClassificationCategory.BUG: (
                "bug",
                "crash",
                "crashes",
                "crashed",
                "exception",
                "stack trace",
                "500 error",
                "not working",
                "broken",
                "freezes",
                "closes instantly",
                "unexpected behavior",
                "blank screen",
            ),
            ClassificationCategory.ACCOUNT: (
                "account",
                "password",
                "login",
                "log in",
                "sign in",
                "locked out",
                "profile",
                "email address",
                "verification",
                "credentials",
                "permission",
                "access denied",
            ),
        }
        scores = {
            category: sum(
                1 for term in category_terms if re.search(rf"\b{re.escape(term)}\b", text)
            )
            for category, category_terms in terms.items()
        }
        best_category, best_score = max(scores.items(), key=lambda item: item[1])
        return best_category if best_score else ClassificationCategory.GENERAL

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
