"""
osint_agent.py - OSINT specialist agent.

Handles: domain reconnaissance, GEOINT, social media investigation,
         reverse image search, EXIF metadata, people search.
"""

import re
from typing import Optional


OSINT_SYSTEM_PROMPT = """You are an expert OSINT (Open Source Intelligence) investigator and CTF player.

Your expertise:
- Domain/IP: whois, DNS records (A, MX, TXT, NS), certificate transparency (crt.sh),
             subdomain enumeration, Shodan for exposed services
- Social media: username enumeration across platforms (sherlock), profile scraping,
                archived posts (Wayback Machine), friends/followers graph
- Image intelligence: EXIF data (GPS, timestamps, camera model), reverse image search,
                      landmark recognition, geolocation from environmental clues
- People search: LinkedIn, GitHub, email pattern matching, breached credential DBs
- Code/Document: GitHub commit history, Pastebin leaks, Google dorking,
                 PDF metadata, document version history

OSINT CTF approach:
1. Read challenge carefully — the flag is hidden in publicly accessible data
2. Identify the target (person, domain, image, social account)
3. Build a search strategy: start broad, narrow down
4. Use automated tools (sherlock, theHarvester, amass) for enumeration
5. Manual investigation for the final flag extraction

Write Python scripts using: requests, tweepy, shodan, dnspython, exifread
Note: Some OSINT requires manual browser investigation — describe the steps clearly."""


class OSINTAgent:
    """Specialist agent for OSINT CTF challenges."""

    def __init__(self, model_path: str, device: str = "auto"):
        self.model_path = model_path
        self.device = device
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        if self._model is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path, torch_dtype=torch.bfloat16, device_map=self.device,
            trust_remote_code=True,
        )

    def solve(self, description: str, file_bytes: Optional[bytes], classification) -> dict:
        self._load_model()

        user_prompt = f"""OSINT CTF Challenge:

{description}

Technique: {classification.vuln_class or 'analyze the target — domain/person/image/social'}

Describe your investigation strategy step by step.
Write Python automation where applicable.
The flag should be discoverable from publicly available information."""

        messages = [
            {"role": "system", "content": OSINT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        response = self._generate(messages)

        return {
            "reasoning": self._extract_reasoning(response),
            "exploit": self._extract_code(response),
            "flag": self._extract_flag(response),
            "technique": classification.vuln_class,
        }

    def _generate(self, messages: list[dict]) -> str:
        import torch
        input_ids = self._tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)
        with torch.no_grad():
            output = self._model.generate(
                input_ids, max_new_tokens=1200, temperature=0.4,
                do_sample=True, pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(output[0][input_ids.shape[1]:], skip_special_tokens=True)

    def _extract_reasoning(self, text: str) -> list[str]:
        steps = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+.{10,}", line):
                steps.append(line)
        return steps or [text[:400]]

    def _extract_code(self, text: str) -> str:
        for fence in ("```python", "```bash", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
        return ""

    def _extract_flag(self, text: str) -> Optional[str]:
        match = re.search(r"[A-Z0-9_]+\{[^}]+\}", text)
        return match.group(0) if match else None
