"""
binary_agent.py - Binary exploitation specialist agent (pwn).

Handles: buffer overflow, ROP chains, heap exploitation, format string,
         shellcode injection, ret2libc, stack pivoting, SROP.

Uses pwntools for all exploit development.
"""

import re
from typing import Optional

from loguru import logger


PWN_SYSTEM_PROMPT = """You are an expert binary exploitation researcher and CTF player.

You specialize in:
- Stack buffer overflows: ret2win, ret2libc, ROP chains (ROPgadget, pwntools ROP)
- Heap exploitation: tcache poisoning, house of spirit, use-after-free, off-by-one
- Format string: arbitrary read (leak libc), arbitrary write (overwrite GOT)
- Shellcode: x86/x64 shellcode, MIPS, ARM, seccomp bypass
- Advanced: SROP (Sigreturn-Oriented Programming), JOP, heap grooming
- PIE bypass: leak binary base from format string or info leak
- ASLR bypass: leak libc from GOT, compute base, ret2libc

Standard workflow:
1. checksec — identify protections (NX, PIE, CANARY, RELRO, ASLR)
2. File analysis — strings, symbols, architecture
3. Disassemble main() and relevant functions
4. Find vulnerability: buffer size vs. read size, format string, UAF
5. Develop exploit: leak → control flow → shell

Always use pwntools:
  from pwn import *
  context.binary = elf = ELF('./chall')
  p = remote(os.environ.get('CHALLENGE_HOST', 'localhost'),
             int(os.environ.get('CHALLENGE_PORT', '1337')))

Build the exploit incrementally. Debug with:
  context.log_level = 'debug'
  gdb.attach(p)  # for local testing"""


class BinaryExploitAgent:
    """Specialist agent for binary exploitation (pwn) CTF challenges."""

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
        """Solve a binary exploitation CTF challenge."""
        self._load_model()

        # Add binary analysis context if we have the binary
        binary_context = ""
        if file_bytes:
            binary_context = self._analyze_binary(file_bytes)

        user_prompt = f"""Binary Exploitation CTF Challenge:

{description}

{binary_context}

Vulnerability class hint: {classification.vuln_class or 'unknown — analyze the binary'}

Write a complete pwntools exploit. Walk through:
1. Binary analysis (checksec, file, strings)
2. Vulnerability identification
3. Exploit strategy
4. Complete exploit code

Extract and print the flag."""

        messages = [
            {"role": "system", "content": PWN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        response = self._generate(messages)

        return {
            "reasoning": self._extract_reasoning(response),
            "exploit": self._extract_code(response),
            "flag": self._extract_flag(response),
            "technique": classification.vuln_class,
        }

    def _analyze_binary(self, file_bytes: bytes) -> str:
        """Extract basic binary metadata from magic bytes."""
        arch = "unknown"
        bits = "unknown"
        if file_bytes[:4] == b"\x7fELF":
            bits = "64-bit" if file_bytes[4] == 2 else "32-bit"
            machine = file_bytes[18]
            arch_map = {0x3e: "x86-64", 0x28: "ARM", 0xb7: "AArch64", 0x08: "MIPS"}
            arch = arch_map.get(machine, f"machine=0x{machine:02x}")

        return f"""
Binary info:
  Architecture: {arch} {bits}
  Size: {len(file_bytes):,} bytes

Run checksec on the binary and pwntools ELF() to get full protection information."""

    def _generate(self, messages: list[dict], max_new_tokens: int = 2000) -> str:
        import torch
        input_ids = self._tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)
        with torch.no_grad():
            output = self._model.generate(
                input_ids, max_new_tokens=max_new_tokens, temperature=0.2,
                do_sample=True, pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(output[0][input_ids.shape[1]:], skip_special_tokens=True)

    def _extract_reasoning(self, text: str) -> list[str]:
        steps = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+.{10,}", line):
                steps.append(line)
        return steps or [text[:300]]

    def _extract_code(self, text: str) -> str:
        for fence in ("```python", "```py", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
        return text[:1000]

    def _extract_flag(self, text: str) -> Optional[str]:
        match = re.search(r"[A-Z0-9_]+\{[^}]+\}", text)
        return match.group(0) if match else None
