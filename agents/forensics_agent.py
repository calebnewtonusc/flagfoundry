"""
forensics_agent.py - Forensics and steganography specialist agent.

Handles: file carving, PCAP analysis, memory forensics, disk image analysis,
         LSB steganography, DCT steganography, audio steganography, PDF analysis.
"""

import re
from typing import Optional


FORENSICS_SYSTEM_PROMPT = """You are an expert digital forensics investigator and CTF player.

Your expertise covers:
- File carving: binwalk, foremost, scalpel — extract hidden files from containers
- Network forensics: Wireshark/tshark PCAP analysis, HTTP credential extraction,
                     DNS tunneling, TLS traffic (if key material available)
- Memory forensics: Volatility 3 profiles, process dump, registry extraction,
                    network connections, clipboard, browser history
- Disk forensics: EXT4/NTFS/FAT32 deleted file recovery, LVM, filesystem metadata
- Steganography: LSB in PNG/BMP/JPEG, DCT coefficient manipulation, audio LSB,
                 spectral steganography (spectrograms reveal hidden text/images)
- Document forensics: PDF embedded objects/JavaScript, Office macro extraction,
                      EXIF metadata (GPS coordinates, timestamps, camera model)
- Archive analysis: ZIP password cracking (john, hashcat, rockyou.txt),
                    nested archives, symlink attacks

Standard toolkit:
  file, strings, binwalk, foremost
  tshark, scapy, pyshark
  volatility3, yara
  stegsolve, zsteg, steghide, stegseek
  exiftool, identify (ImageMagick)
  john, hashcat

Always start with: file <file>, strings <file>, binwalk -e <file>"""


class ForensicsAgent:
    """Specialist agent for forensics and steganography CTF challenges."""

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

        self._tokenizer = AutoTokenizer.from_pretrained(  # nosec B615
            self.model_path, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(  # nosec B615
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map=self.device,
            trust_remote_code=True,
        )

    def solve(
        self, description: str, file_bytes: Optional[bytes], classification
    ) -> dict:
        self._load_model()

        file_info = ""
        if file_bytes:
            file_info = self._analyze_file(file_bytes)

        user_prompt = f"""Forensics/Steganography CTF Challenge:

{description}

{file_info}

Category: {classification.category} — {classification.vuln_class or "analyze the file"}

Walk through your forensic analysis step by step.
Write Python code (using scapy, PIL, volatility APIs, etc.) to extract the flag.
Try multiple approaches if the first doesn't work."""

        messages = [
            {"role": "system", "content": FORENSICS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        response = self._generate(messages)

        return {
            "reasoning": self._extract_reasoning(response),
            "exploit": self._extract_code(response),
            "flag": self._extract_flag(response),
            "technique": classification.vuln_class,
        }

    def _analyze_file(self, data: bytes) -> str:
        """Quick file type analysis."""
        magic_map = {
            b"\x89PNG": "PNG image",
            b"\xff\xd8\xff": "JPEG image",
            b"BM": "BMP image",
            b"RIFF": "WAV audio or AVI video",
            b"ID3": "MP3 audio",
            b"\xd4\xc3\xb2\xa1": "PCAP network capture",
            b"\x0a\r\x0d\x0a": "PCAPNG network capture",
            b"PK\x03\x04": "ZIP archive",
            b"Rar!": "RAR archive",
            b"\x1f\x8b": "GZIP compressed",
            b"%PDF": "PDF document",
            b"\x7fELF": "ELF executable (consider pwn category)",
        }
        for magic, desc in magic_map.items():
            if data[: len(magic)] == magic:
                return f"File type: {desc} ({len(data):,} bytes)"
        return f"File: unknown type ({len(data):,} bytes) — run file/binwalk"

    def _generate(self, messages: list[dict]) -> str:
        import torch

        input_ids = self._tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)
        with torch.no_grad():
            output = self._model.generate(
                input_ids,
                max_new_tokens=1500,
                temperature=0.3,
                do_sample=True,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            output[0][input_ids.shape[1] :], skip_special_tokens=True
        )

    def _extract_reasoning(self, text: str) -> list[str]:
        steps = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+.{10,}", line):
                steps.append(line)
        return steps or [text[:400]]

    def _extract_code(self, text: str) -> str:
        for fence in ("```python", "```bash", "```shell", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    return text[start:end].strip()
        return text[:800]

    def _extract_flag(self, text: str) -> Optional[str]:
        match = re.search(r"[A-Z0-9_]+\{[^}]+\}", text)
        return match.group(0) if match else None
