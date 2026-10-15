"""Deterministic mock LLM for testing and zero-cost offline benchmark execution."""
import json
import re
from typing import Dict, Any, Optional
from app.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Deterministic LLM simulator producing valid structured JSON."""

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        data = await self.generate_json(prompt, system_prompt)
        return json.dumps(data)

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        sys_lower = (system_prompt or "").lower()
        prompt_lower = prompt.lower()

        # 1. Resolver prompt handling
        if "resolver" in sys_lower:
            return {
                "action_plan": ["Set canary traffic to 0%", "Execute helm rollback payments-api", "Verify /healthz"],
                "runbook_id": "mem_procedural_acme_runbook_safe-rollback-procedure-for-payments",
                "recommendation": "Follow runbook and notify on-call lead.",
                "status": "resolved"
            }

        # 2. Answer generation prompt handling
        if "answer engine" in sys_lower or "<untrusted_evidence>" in prompt:
            citations = re.findall(r"\[Memory ID:\s*([^\]]+)\]", prompt)
            summaries = re.findall(r"Summary:\s*([^\n]+)", prompt)
            chains = re.findall(r"Chain:\s*([^\n]+)", prompt)

            # Check for abstention / missing evidence conditions
            if (not summaries and not chains) or "no evidence found" in prompt_lower or "no relevant evidence" in prompt_lower:
                return {
                    "answer": "I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
                    "citations": [],
                    "confidence": "low",
                    "abstained": True,
                    "follow_ups": ["Would you like to record this fact or incident in OpsMemory?"]
                }

            evidence_text = " ".join(summaries + chains)
            evidence_lower = evidence_text.lower()

            # Check question-evidence grounding
            q_match = re.search(r"Question:\s*([^\n]+)", prompt)
            q_text = (q_match.group(1) if q_match else "").lower()

            # Check for sensitive, absent, or out-of-domain topics that should trigger grounded abstention
            sensitive_or_absent_topics = [
                "lunar", "spacecraft", "astronaut", "credit card", "credit cards", "password",
                "alien", "imaginary", "nonexistent", "hypothetical", "missile", "launch code", "launch codes"
            ]
            if any(topic in q_text for topic in sensitive_or_absent_topics) and not any(topic in evidence_lower for topic in sensitive_or_absent_topics):
                return {
                    "answer": "I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
                    "citations": [],
                    "confidence": "low",
                    "abstained": True,
                    "follow_ups": ["No evidence found matching these criteria."]
                }

            answer = f"Based on persistent records: {evidence_text.strip()}"
            return {
                "answer": answer,
                "citations": citations[:3],
                "confidence": "high",
                "abstained": False,
                "follow_ups": []
            }

        # 3. Triage / Extraction prompt handling
        entities = []
        episodic = []
        semantic = []
        procedural = []

        user_text = prompt.split("\n\n")[-1].strip()
        user_lower = user_text.lower()

        # Service recognition
        services = ["payments-api", "checkout-ui", "auth-service", "postgres-orders", "inventory-svc", "gateway-api", "payments-worker"]
        for s in services:
            if s in user_lower or s.replace("-", " ") in user_lower:
                entities.append({"kind": "service", "name": s, "aliases": []})

        # Version recognition
        versions = re.findall(r"\bv\d+(?:\.\d+)?\b", user_lower)
        for v in versions:
            entities.append({"kind": "version", "name": v, "aliases": []})

        # Incident extraction (only for declarative reports)
        if any(w in user_lower for w in ["incident", "failure", "outage", "broken", "down", "error"]) and not user_lower.startswith(("what", "who", "when", "why", "how", "is")):
            episodic.append({
                "subtype": "incident",
                "title": f"Incident: {user_text[:40].strip()}",
                "summary": user_text.strip(),
                "entity_names": [e["name"] for e in entities],
                "severity": "high" if "severe" in user_lower or "outage" in user_lower else "medium"
            })

        # Semantic facts extraction (e.g. version or owner)
        if "version" in user_lower and not user_lower.startswith(("what", "is ", "who")):
            for v in versions:
                semantic.append({
                    "subtype": "fact",
                    "subject_entity": entities[0]["name"] if entities else "service",
                    "predicate": "current_version",
                    "object_value": v,
                    "confidence_basis": "user_explicit"
                })
        if "owned by" in prompt_lower or "owner" in prompt_lower:
            team_match = re.search(r"team\s+([a-zA-Z0-9_-]+)", prompt_lower)
            team_name = f"team-{team_match.group(1)}" if team_match else "team-core"
            semantic.append({
                "subtype": "fact",
                "subject_entity": entities[0]["name"] if entities else "service",
                "predicate": "owner",
                "object_value": team_name,
                "confidence_basis": "user_explicit"
            })

        # Procedural request
        if "rollback" in prompt_lower or "procedure" in prompt_lower or "runbook" in prompt_lower or "how to" in prompt_lower:
            procedural.append({
                "subtype": "runbook_request",
                "trigger": prompt[:50].strip(),
                "entity_names": [e["name"] for e in entities]
            })

        return {
            "entities": entities,
            "episodic_memories": episodic,
            "semantic_facts": semantic,
            "procedural_requests": procedural,
            "missing_info": []
        }

        # 2. Answer generation prompt handling
        # Extract memory IDs and summaries from evidence block
        citations = re.findall(r"\[Memory ID:\s*([^\]]+)\]", prompt)
        summaries = re.findall(r"Summary:\s*([^\n]+)", prompt)

        # Check for abstention / missing evidence conditions
        if not summaries or "no evidence found" in prompt_lower or "no relevant evidence" in prompt_lower:
            return {
                "answer": "I do not have sufficient recorded evidence in OpsMemory to answer this question accurately.",
                "citations": [],
                "confidence": "low",
                "abstained": True,
                "follow_ups": ["Would you like to record this fact or incident in OpsMemory?"]
            }

        evidence_text = " ".join(summaries)
        answer = f"Based on persistent records: {evidence_text.strip()}"
        return {
            "answer": answer,
            "citations": citations[:3],
            "confidence": "high",
            "abstained": False,
            "follow_ups": []
        }
