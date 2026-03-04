"""
orchestrator_agent.py - Routes CTF challenges to specialist sub-agents.

The orchestrator:
  1. Classifies the challenge category
  2. Routes to the correct specialist (web, pwn, crypto, forensics, rev, osint)
  3. Aggregates and formats the final result

Usage:
  agent = OrchestratorAgent(model_path="checkpoints/flagfoundry-final")
  result = agent.solve(description="Find the SQL injection...", file_bytes=binary_data)
"""

import json
from pathlib import Path
from typing import Optional

from loguru import logger

from core.challenge_classifier import ChallengeClassifier, ClassificationResult


class OrchestratorAgent:
    """
    Top-level agent that routes to specialist sub-agents based on challenge category.

    The orchestrator uses the classifier to determine the challenge type,
    then instantiates and calls the appropriate specialist agent.
    """

    def __init__(
        self,
        model_path: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
        device: str = "auto",
    ):
        self.model_path = model_path
        self.device = device
        self.classifier = ChallengeClassifier()

        # Lazy-load specialist agents
        self._agents: dict = {}

    def solve(
        self,
        description: str,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        category_override: Optional[str] = None,
    ) -> dict:
        """
        Solve a CTF challenge end-to-end.

        Args:
            description: Challenge description text
            file_bytes: Optional attached file
            filename: Optional filename for the attached file
            category_override: Force a specific category (skip classification)

        Returns:
            dict with: category, confidence, reasoning, exploit, flag
        """
        # Step 1: Classify
        if category_override:
            classification = ClassificationResult(
                category=category_override,
                confidence=1.0,
                vuln_class=None,
                routing_notes="Category override",
            )
        else:
            classification = self.classifier.classify(
                description=description,
                file_bytes=file_bytes,
                filename=filename,
            )

        logger.info(
            f"Challenge classified: {classification.category} "
            f"(confidence={classification.confidence:.2%})"
        )

        # Step 2: Route to specialist
        agent = self._get_agent(classification.category)
        try:
            result = agent.solve(
                description=description,
                file_bytes=file_bytes,
                classification=classification,
            )
        except NotImplementedError:
            logger.warning(
                f"Agent for category '{classification.category}' raised NotImplementedError — "
                "falling back to generic solver."
            )
            fallback = FallbackAgent(model_path=self.model_path)
            result = fallback.solve(
                description=description,
                file_bytes=file_bytes,
                classification=classification,
            )

        # Step 3: Format and return
        return {
            "category": classification.category,
            "confidence": classification.confidence,
            "vuln_class": classification.vuln_class,
            "routing_notes": classification.routing_notes,
            **result,
        }

    def _get_agent(self, category: str):
        """Lazy-load and return the specialist agent for the given category."""
        if category not in self._agents:
            agent = self._create_agent(category)
            self._agents[category] = agent
        return self._agents[category]

    def _create_agent(self, category: str):
        """Instantiate a specialist agent for the given category."""
        agent_map = {
            "web": "agents.web_exploit_agent.WebExploitAgent",
            "pwn": "agents.binary_agent.BinaryExploitAgent",
            "crypto": "agents.crypto_agent.CryptoAgent",
            "forensics": "agents.forensics_agent.ForensicsAgent",
            "rev": "agents.rev_agent.ReverseEngineeringAgent",
            "osint": "agents.osint_agent.OSINTAgent",
            "steg": "agents.forensics_agent.ForensicsAgent",  # steg uses forensics agent
            "misc": "agents.web_exploit_agent.WebExploitAgent",  # fallback
        }

        module_class = agent_map.get(category, agent_map["misc"])
        module_path, class_name = module_class.rsplit(".", 1)

        import importlib

        try:
            module = importlib.import_module(module_path)
            AgentClass = getattr(module, class_name)
            return AgentClass(model_path=self.model_path, device=self.device)
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning(f"Could not load agent for {category}: {e}")
            return FallbackAgent(model_path=self.model_path)


class FallbackAgent:
    """
    Fallback agent when a specialist is not available.
    Uses the base model with a generic CTF-solving prompt.
    """

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """Load model on first use."""
        if self._model is not None:
            return

        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        self._tokenizer = AutoTokenizer.from_pretrained(  # nosec B615
            self.model_path, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(  # nosec B615
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )

    def solve(
        self,
        description: str,
        file_bytes: Optional[bytes],
        classification,
    ) -> dict:
        """Generate a solution using the base model."""
        self._load_model()

        system = (
            "You are an expert CTF player. Solve this challenge step by step. "
            "Write a complete, working exploit script. Extract the flag."
        )
        user = f"CTF Challenge ({classification.category}):\n\n{description}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        import torch

        input_ids = self._tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)

        with torch.no_grad():
            output = self._model.generate(
                input_ids,
                max_new_tokens=1024,
                temperature=0.3,
                do_sample=True,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        response = self._tokenizer.decode(
            output[0][input_ids.shape[1] :], skip_special_tokens=True
        )

        # Parse response into structured format
        return {
            "reasoning": [response[:500] if len(response) > 500 else response],
            "exploit": self._extract_code(response),
            "flag": self._extract_flag(response),
        }

    def _extract_code(self, text: str) -> str:
        """Extract code block from response."""
        for fence in ("```python", "```bash", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
        return text

    def _extract_flag(self, text: str) -> Optional[str]:
        """Extract flag from response."""
        import re

        match = re.search(r"[A-Z0-9_]+\{[^}]+\}", text)
        return match.group(0) if match else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FlagFoundry Challenge Solver")
    parser.add_argument("--description", required=True, help="Challenge description")
    parser.add_argument("--file", help="Challenge file path")
    parser.add_argument("--category", help="Force category (skip classification)")
    parser.add_argument("--model", default="checkpoints/flagfoundry-final")
    args = parser.parse_args()

    file_bytes = None
    filename = None
    if args.file:
        p = Path(args.file)
        file_bytes = p.read_bytes()
        filename = p.name

    agent = OrchestratorAgent(model_path=args.model)
    result = agent.solve(
        description=args.description,
        file_bytes=file_bytes,
        filename=filename,
        category_override=args.category,
    )

    print(json.dumps(result, indent=2))
