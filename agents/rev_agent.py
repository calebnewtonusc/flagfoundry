"""
rev_agent.py - Reverse Engineering specialist agent stub.

FF-7 FIX: This stub replaces a missing file that was referenced in orchestrator_agent.py
agent_map under key "rev". Any challenge classified as "rev" (reverse engineering) was
previously failing with ImportError, causing silent fallback to FallbackAgent.

TODO: Implement ReverseEngineeringAgent with:
  - Static analysis (Ghidra, radare2, objdump integration)
  - String extraction and pattern matching
  - Decompiler output reasoning
  - Anti-debug detection and bypass
"""

from loguru import logger


class ReverseEngineeringAgent:
    """
    Specialist agent for reverse engineering CTF challenges.

    Currently a stub — raises NotImplementedError to make missing functionality
    explicit rather than silently falling back to a generic model.

    The orchestrator's FallbackAgent will be used when this raises ImportError/AttributeError,
    but since the import now succeeds, the FallbackAgent fallback in _create_agent() will
    only trigger if this __init__ or solve() raises an unexpected exception.
    """

    def __init__(self, model_path: str = "Qwen/Qwen2.5-Coder-7B-Instruct", device: str = "auto"):
        self.model_path = model_path
        self.device = device
        logger.warning(
            "ReverseEngineeringAgent is a stub. "
            "Implement this agent to handle 'rev' category challenges natively."
        )

    def solve(self, description: str, file_bytes=None, classification=None) -> dict:
        """
        Solve a reverse engineering CTF challenge.

        Not yet implemented. Raises NotImplementedError to indicate this is a stub.
        The orchestrator will catch this and fall back to FallbackAgent.
        """
        raise NotImplementedError(
            "ReverseEngineeringAgent.solve() is not implemented. "
            "This stub exists to make the missing module explicit. "
            "Implement static analysis (Ghidra/radare2), decompiler integration, "
            "and anti-debug reasoning to complete this agent."
        )
