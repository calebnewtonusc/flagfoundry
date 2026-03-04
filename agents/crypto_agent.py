"""
crypto_agent.py - Cryptography specialist agent.

Handles: RSA (small exponent, common modulus, LSB oracle, Wiener, Hastad),
         AES (ECB, CBC padding oracle, GCM nonce reuse), ECC (Pohlig-Hellman,
         invalid curve), custom ciphers, LFSR, XOR (multi-time pad, crib drag),
         hash attacks (length extension, collision).
"""

import re
from typing import Optional


CRYPTO_SYSTEM_PROMPT = """You are an expert cryptographer and CTF player specializing in applied cryptanalysis.

Your expertise covers:
- RSA: small exponent (e=3, Hastad broadcast), Wiener's attack (small d),
       common modulus attack, LSB decryption oracle (binary search),
       Boneh-Durfee, Coppersmith partial key exposure
- AES: ECB byte-at-a-time, CBC padding oracle (PKCS7), CBC bit-flip attack,
       GCM nonce reuse, SBox analysis for reduced-round
- ECC: Pohlig-Hellman on composite order curves, invalid curve attack,
       ECDSA nonce reuse (k-reuse), anomalous curves (Smart's attack)
- Hash attacks: MD5/SHA-1 length extension, birthday collision, Merkle-Damgard
- Stream ciphers: LFSR tap recovery, XOR multi-time pad / crib dragging
- Custom crypto: frequency analysis, Vigenère, substitution, transposition
- Number theory: CRT, Tonelli-Shanks, discrete log (Pohlig-Hellman, BSGS)

Libraries available:
- pycryptodome: AES, RSA, hashing
- sympy: modular arithmetic, primality, factoring
- z3-solver: constraint solving for custom crypto
- gmpy2: fast GCD, modpow, isqrt for RSA attacks
- sage (if available): lattice attacks, elliptic curves

Attack workflow:
1. Parse the cryptographic scheme (identify algorithm, parameters, oracle access)
2. Identify the weakness (math flaw, implementation bug, key reuse, weak parameters)
3. Select the attack algorithm and implement it
4. Recover the key or directly decrypt the ciphertext
5. Extract the flag"""


class CryptoAgent:
    """Specialist agent for cryptography CTF challenges."""

    ATTACK_TEMPLATES = {
        "rsa": """
Check RSA parameters:
- If e=3 and ct < n^(1/3): cube root attack
- If multiple (n, e, c) with same message: Hastad broadcast (CRT)
- If d is small: Wiener's attack (continued fractions on e/n)
- If we have decryption oracle: LSB oracle binary search
- Factor n: try factordb.com, p-1 method, Pollard rho
""",
        "aes_ecb": """
ECB mode is block-permutation cipher. Attack:
1. Confirm ECB: send 48 identical bytes, check for repeating 16-byte blocks
2. Byte-at-a-time: prefix controlled data to align target byte at block boundary
3. Oracle: encrypt chosen plaintext, compare output blocks
""",
        "padding_oracle": """
CBC padding oracle attack:
1. Confirm oracle: tamper last byte of second-to-last block, check for padding error
2. Recover P[n] block by block using bit-flipping
3. Implement PKCS7 unpadding after full recovery
See: pycryptodome, bleichenbacher oracle, Vaudenay attack
""",
    }

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

        attack_context = ""
        vuln_class = classification.vuln_class or "unknown"
        for key, template in self.ATTACK_TEMPLATES.items():
            if key in vuln_class:
                attack_context = template
                break

        user_prompt = f"""Cryptography CTF Challenge:

{description}

Attack type: {vuln_class}
{attack_context}

Solve this cryptography challenge. Show your mathematical reasoning, then write complete Python code.
Use: pycryptodome, sympy, z3-solver, gmpy2 as needed.
Extract and print the flag."""

        messages = [
            {"role": "system", "content": CRYPTO_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        response = self._generate(messages)

        return {
            "reasoning": self._extract_reasoning(response),
            "exploit": self._extract_code(response),
            "flag": self._extract_flag(response),
            "technique": vuln_class,
        }

    def _generate(self, messages: list[dict]) -> str:
        import torch
        input_ids = self._tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)
        with torch.no_grad():
            output = self._model.generate(
                input_ids, max_new_tokens=2000, temperature=0.1,
                do_sample=True, pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(output[0][input_ids.shape[1]:], skip_special_tokens=True)

    def _extract_reasoning(self, text: str) -> list[str]:
        steps = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+.{10,}", line) or re.match(r"^Step\s+\d+", line):
                steps.append(line)
        return steps or [text[:400]]

    def _extract_code(self, text: str) -> str:
        for fence in ("```python", "```sage", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
        return text[:1000]

    def _extract_flag(self, text: str) -> Optional[str]:
        match = re.search(r"[A-Z0-9_]+\{[^}]+\}", text)
        return match.group(0) if match else None
