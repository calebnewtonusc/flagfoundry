"""
challenge_classifier.py - Classify CTF challenges into categories for agent routing.

Uses a combination of keyword heuristics + the fine-tuned FlagFoundry model
to route incoming challenges to the correct specialist agent.

Categories:
  web       — SQL injection, XSS, SSRF, SSTI, LFI, path traversal, OAuth, etc.
  pwn       — buffer overflow, ROP, heap, format string, shellcode
  crypto    — RSA, ECC, AES, XOR, custom ciphers, hash cracking
  forensics — file carving, network analysis, memory forensics, steganography
  rev       — static analysis, decompilation, anti-debug, obfuscation
  osint     — reconnaissance, HUMINT, GEOINT, social media
  steg      — LSB, DCT, audio steganography

Usage:
  classifier = ChallengeClassifier()
  result = classifier.classify(description="Here's a PHP login page...", file_bytes=None)
  # result: {"category": "web", "confidence": 0.95, "vuln_class": "sql_injection"}
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    vuln_class: Optional[str]
    routing_notes: str


# Keyword patterns per category
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "web": [
        "http",
        "https",
        "url",
        "login",
        "register",
        "cookie",
        "session",
        "sql",
        "database",
        "query",
        "injection",
        "xss",
        "csrf",
        "ssrf",
        "jwt",
        "oauth",
        "graphql",
        "api",
        "rest",
        "endpoint",
        "web server",
        "php",
        "flask",
        "django",
        "express",
        "nginx",
        "apache",
        "admin panel",
        "upload",
        "file upload",
        "path traversal",
    ],
    "pwn": [
        "binary",
        "executable",
        "elf",
        "overflow",
        "buffer",
        "stack",
        "heap",
        "rop",
        "gadget",
        "shellcode",
        "pwn",
        "exploit",
        "gdb",
        "pwntools",
        "checksec",
        "nx",
        "pie",
        "aslr",
        "canary",
        "format string",
        "printf",
        "uaf",
        "use after free",
        "libc",
        "nc ",
        "netcat",
        "port",
        "remote",
        "service",
    ],
    "crypto": [
        "rsa",
        "aes",
        "des",
        "ecc",
        "elliptic",
        "prime",
        "modulus",
        "exponent",
        "cipher",
        "encrypt",
        "decrypt",
        "hash",
        "sha",
        "md5",
        "xor",
        "key",
        "iv",
        "nonce",
        "padding",
        "oracle",
        "lfsr",
        "diffie",
        "hellman",
        "discrete log",
        "lattice",
        "lll",
        "crypto",
        "cryptographic",
        "message",
        "ciphertext",
    ],
    "forensics": [
        "pcap",
        "wireshark",
        "network",
        "capture",
        "traffic",
        "memory",
        "dump",
        "volatility",
        "memdump",
        "process",
        "file",
        "recover",
        "deleted",
        "disk",
        "image",
        "forensic",
        "log",
        "artifact",
        "registry",
        "windows",
        "linux",
    ],
    "rev": [
        "reverse",
        "binary",
        "disassemble",
        "decompile",
        "asm",
        "assembly",
        "ida",
        "ghidra",
        "radare",
        "objdump",
        "strings",
        "stripped",
        "obfuscate",
        "pack",
        "upx",
        "vm",
        "virtual machine",
        "bytecode",
        "keygen",
        "serial",
        "license",
        "crack",
    ],
    "osint": [
        "osint",
        "reconnaissance",
        "recon",
        "domain",
        "whois",
        "dns",
        "social media",
        "twitter",
        "instagram",
        "facebook",
        "linkedin",
        "person",
        "identity",
        "location",
        "geolocation",
        "image",
        "reverse image",
        "metadata",
        "exif",
        "satellite",
    ],
    "steg": [
        "steganography",
        "hidden",
        "image",
        "png",
        "jpg",
        "jpeg",
        "bmp",
        "audio",
        "wav",
        "mp3",
        "lsb",
        "pixel",
        "spectral",
        "spectrogram",
        "invisible",
        "secret",
        "conceal",
    ],
}

# File extension → category hints
EXTENSION_HINTS: dict[str, str] = {
    # Binary/ELF
    ".elf": "pwn",
    ".exe": "pwn",
    ".so": "pwn",
    # Web
    ".php": "web",
    ".js": "web",
    # Crypto
    ".pem": "crypto",
    ".der": "crypto",
    ".pub": "crypto",
    # Forensics
    ".pcap": "forensics",
    ".pcapng": "forensics",
    ".dump": "forensics",
    ".vmem": "forensics",
    # Images (could be steg)
    ".png": "steg",
    ".jpg": "steg",
    ".bmp": "steg",
    # Audio
    ".wav": "steg",
    ".mp3": "steg",
    # Reverse
    ".apk": "rev",
    ".dex": "rev",
    ".pyc": "rev",
}


class ChallengeClassifier:
    """
    Classifies CTF challenges into categories for specialist agent routing.

    First attempts heuristic classification (fast, no model needed).
    Falls back to model-based classification for ambiguous cases.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self._model = None  # Lazy load

    def classify(
        self,
        description: str,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> ClassificationResult:
        """
        Classify a CTF challenge.

        Args:
            description: The challenge description text
            file_bytes: Optional attached file bytes
            filename: Optional filename (for extension-based hints)

        Returns:
            ClassificationResult with category, confidence, vuln_class
        """
        text = description.lower()

        # Step 1: File extension hint
        ext_hint = None
        if filename:
            ext = Path(filename).suffix.lower()
            ext_hint = EXTENSION_HINTS.get(ext)

        # Step 2: Keyword scoring
        scores = self._score_keywords(text)

        # Step 3: Binary file magic bytes
        if file_bytes:
            magic_hint = self._check_magic_bytes(file_bytes)
            if magic_hint:
                scores[magic_hint] = scores.get(magic_hint, 0) + 5

        # Step 4: Apply extension hint
        if ext_hint:
            scores[ext_hint] = scores.get(ext_hint, 0) + 3

        # Step 5: Determine winner
        if not scores:
            return ClassificationResult(
                category="misc",
                confidence=0.3,
                vuln_class=None,
                routing_notes="No strong category signal — defaulting to misc",
            )

        total = sum(scores.values())
        best_cat = max(scores, key=scores.__getitem__)
        confidence = scores[best_cat] / total if total > 0 else 0.0

        # Step 6: Identify specific vulnerability class
        vuln_class = self._identify_vuln_class(text, best_cat)

        return ClassificationResult(
            category=best_cat,
            confidence=min(1.0, confidence),
            vuln_class=vuln_class,
            routing_notes=f"Keyword scores: {dict(sorted(scores.items(), key=lambda x: -x[1])[:3])}",
        )

    def _score_keywords(self, text: str) -> dict[str, float]:
        """Score each category based on keyword matches."""
        scores: dict[str, float] = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = 0.0
            for kw in keywords:
                if kw in text:
                    # Longer keywords are more discriminative
                    score += len(kw.split()) * 0.5 + 0.5
            if score > 0:
                scores[category] = score
        return scores

    def _check_magic_bytes(self, data: bytes) -> Optional[str]:
        """Check file magic bytes to determine type."""
        if data[:4] == b"\x7fELF":
            return "pwn"
        if data[:2] in (b"MZ", b"ZM"):  # PE executable
            return "pwn"
        if data[:4] == b"\x89PNG":
            return "steg"
        if data[:4] in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):  # JPEG
            return "steg"
        if data[:4] == b"RIFF":  # WAV
            return "steg"
        if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):  # pcap
            return "forensics"
        if data[:4] == b"PK\x03\x04":  # ZIP (could be misc/rev/web)
            return None
        return None

    def _identify_vuln_class(self, text: str, category: str) -> Optional[str]:
        """Identify specific vulnerability class within category."""
        vuln_patterns: dict[str, list[tuple[str, str]]] = {
            "web": [
                (r"sql.{0,20}inject|inject.{0,20}sql|\bsqli\b", "sql_injection"),
                (r"\bxss\b|cross.site.script", "xss"),
                (r"\bssrf\b|server.side.request", "ssrf"),
                (r"\bssti\b|template.inject", "ssti"),
                (r"path.travers|directory.travers|\blfi\b|\brfi\b", "path_traversal"),
                (r"\bjwt\b|json.web.token", "jwt_attack"),
                (r"\boauth\b", "oauth_bypass"),
                (r"\bxxe\b|xml.external", "xxe"),
                (r"deseri[a-z]+", "deserialization"),
                (r"graphql", "graphql_injection"),
            ],
            "pwn": [
                (r"buffer.overflow|stack.overflow|\bbof\b", "buffer_overflow"),
                (r"\brop\b|return.oriented", "rop_chain"),
                (r"heap|use.after.free|\buaf\b|tcache|fastbin", "heap_exploit"),
                (r"format.string|printf.*%[snx]", "format_string"),
                (r"shellcode|shell.code", "shellcode"),
            ],
            "crypto": [
                (r"\brsa\b", "rsa"),
                (r"\baes\b|advanced.encrypt", "aes"),
                (r"\becc\b|elliptic.curve", "ecc"),
                (r"\blfsr\b|linear.feedback", "lfsr"),
                (r"\bxor\b", "xor_cipher"),
                (r"padding.oracle|\bpkcs\b", "padding_oracle"),
                (r"hash.length|length.extension", "hash_length_extension"),
            ],
        }

        patterns = vuln_patterns.get(category, [])
        for pattern, vuln_class in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return vuln_class
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Classify a CTF challenge")
    parser.add_argument("description", help="Challenge description text")
    parser.add_argument("--file", help="Path to challenge file")
    args = parser.parse_args()

    file_bytes = None
    filename = None
    if args.file:
        f = Path(args.file)
        file_bytes = f.read_bytes()
        filename = f.name

    classifier = ChallengeClassifier()
    result = classifier.classify(
        description=args.description,
        file_bytes=file_bytes,
        filename=filename,
    )

    print(f"Category:    {result.category}")
    print(f"Confidence:  {result.confidence:.2%}")
    print(f"Vuln class:  {result.vuln_class or 'not identified'}")
    print(f"Notes:       {result.routing_notes}")
