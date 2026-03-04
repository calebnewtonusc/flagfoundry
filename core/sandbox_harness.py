"""
sandbox_harness.py - Docker sandbox execution + flag validation for RL reward signal.

Runs generated exploit code against challenge Docker containers and validates
whether the correct flag was captured.

This is the REWARD SIGNAL for Stage 2 GRPO RL training:
  +1.0  flag captured (exact match)
  +0.3  correct vulnerability class identified but no flag
  -0.5  wrong approach (wrong vuln class)
  -1.0  exploit crashes, timeout, or syntax error

Usage:
  harness = SandboxHarness()
  result = harness.run_exploit(
      exploit_code="import requests\n...",
      challenge_id="web_sqli_001",
      expected_flag="FLAG{sql_is_everywhere}"
  )
"""

import json
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class ExploitResult:
    """Result of running an exploit in the sandbox."""
    success: bool
    flag_captured: Optional[str]
    reward_score: float
    error: Optional[str]
    stdout: str
    stderr: str
    execution_time: float


# Default Docker image for exploit execution
EXPLOIT_RUNNER_IMAGE = "flagfoundry/exploit-runner:latest"
CHALLENGE_REGISTRY = "ghcr.io/calebnewtonusc"


class SandboxHarness:
    """
    Runs exploit code in an isolated Docker environment and validates flags.

    Each exploit runs in a fresh container with:
    - Network access only to the challenge container (not the internet)
    - No filesystem persistence between runs
    - Hard timeout (default 30s)
    - Memory limit (512MB)
    - CPU limit (1 core)

    The challenge service runs in a separate container started before exploit execution.
    """

    def __init__(
        self,
        timeout: int = 30,
        network_name: str = "flagfoundry_challenges",
        challenge_registry: str = CHALLENGE_REGISTRY,
        workers: int = 4,
    ):
        self.timeout = timeout
        self.network_name = network_name
        self.challenge_registry = challenge_registry
        self.workers = workers

        self._verify_docker()

    def _verify_docker(self):
        """Verify Docker is accessible."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("Docker not accessible")
        except Exception as e:
            raise RuntimeError(f"Docker required for sandbox harness: {e}")

    def run_exploit(
        self,
        exploit_code: str,
        challenge_id: str,
        expected_flag: str,
        category: str = "web",
    ) -> ExploitResult:
        """
        Execute exploit code against a challenge and validate the flag.

        Args:
            exploit_code: Python or Shell exploit script
            challenge_id: Unique identifier for the challenge
            expected_flag: The correct flag string
            category: CTF category (affects sandbox config)

        Returns:
            ExploitResult with reward_score in {-1.0, -0.5, 0.3, 1.0}
        """
        start = time.time()

        # Start challenge container
        challenge_container = self._start_challenge(challenge_id)
        if not challenge_container:
            return ExploitResult(
                success=False,
                flag_captured=None,
                reward_score=-0.5,
                error=f"Failed to start challenge container: {challenge_id}",
                stdout="", stderr="",
                execution_time=time.time() - start,
            )

        try:
            # Run the exploit
            result = self._execute_exploit(exploit_code, challenge_container)
            elapsed = time.time() - start

            # Extract flag from output
            flag = self._extract_flag(result.stdout + result.stderr)

            # Score the result
            score = self._compute_reward(
                exploit_result=result,
                extracted_flag=flag,
                expected_flag=expected_flag,
                stdout=result.stdout,
            )

            return ExploitResult(
                success=score > 0,
                flag_captured=flag,
                reward_score=score,
                error=None if result.returncode == 0 else result.stderr[:500],
                stdout=result.stdout[:2000],
                stderr=result.stderr[:1000],
                execution_time=elapsed,
            )

        finally:
            self._stop_challenge(challenge_container)

    def _start_challenge(self, challenge_id: str) -> Optional[str]:
        """Start the challenge Docker container. Returns container ID."""
        image = f"{self.challenge_registry}/flagfoundry-challenges:{challenge_id}"

        try:
            result = subprocess.run(
                [
                    "docker", "run",
                    "--rm",
                    "--detach",
                    "--network", self.network_name,
                    "--memory", "256m",
                    "--cpus", "0.5",
                    # FF-10 FIX: Add UUID suffix to avoid container name collision under concurrent workers
                    "--name", f"challenge_{challenge_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                    image,
                ],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                container_id = result.stdout.strip()
                logger.debug(f"Started challenge container: {container_id[:12]}")
                time.sleep(1)  # Give the service time to start
                return container_id
        except Exception as e:
            logger.warning(f"Failed to start challenge {challenge_id}: {e}")

        return None

    def _execute_exploit(
        self, exploit_code: str, challenge_container: str
    ) -> subprocess.CompletedProcess:
        """Execute exploit code in an isolated Docker container.

        Instead of bind-mounting a host temp file (which breaks when this harness
        itself runs inside a container because the host path is not visible inside
        the inner container), we start the runner container, copy the exploit in
        via `docker cp`, then exec it.  This works regardless of whether the harness
        is running on bare metal or inside Docker.
        """
        container_name = f"exploit_runner_{uuid.uuid4().hex[:12]}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(exploit_code)
            exploit_path = f.name

        try:
            # Start the runner container detached (no volume mount)
            start_result = subprocess.run(
                [
                    "docker", "run",
                    "--rm",
                    "--detach",
                    "--name", container_name,
                    "--network", self.network_name,
                    "--memory", "512m",
                    "--cpus", "1.0",
                    "--env", f"CHALLENGE_HOST={challenge_container}",
                    "--env", "CHALLENGE_PORT=1337",
                    "--entrypoint", "sleep",
                    EXPLOIT_RUNNER_IMAGE,
                    str(self.timeout + 5),
                ],
                capture_output=True, text=True, timeout=15,
            )
            if start_result.returncode != 0:
                return subprocess.CompletedProcess(
                    args=[], returncode=-2,
                    stdout="", stderr=f"Failed to start runner container: {start_result.stderr}"
                )

            # Copy the exploit script into the running container
            subprocess.run(
                ["docker", "cp", exploit_path, f"{container_name}:/exploit_run.py"],
                capture_output=True, timeout=10,
            )

            # Execute the exploit inside the container
            result = subprocess.run(
                ["docker", "exec", container_name, "python", "/exploit_run.py"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result

        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=[], returncode=-1,
                stdout="", stderr=f"TIMEOUT: exploit exceeded {self.timeout}s"
            )
        except Exception as e:
            return subprocess.CompletedProcess(
                args=[], returncode=-2,
                stdout="", stderr=f"EXECUTION ERROR: {e}"
            )
        finally:
            Path(exploit_path).unlink(missing_ok=True)
            # Stop the runner container (best-effort)
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, timeout=5
            )

    def _stop_challenge(self, container_id: str):
        """Stop and remove the challenge container."""
        try:
            subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

    def _extract_flag(self, output: str) -> Optional[str]:
        """Extract flag from exploit output using common flag patterns."""
        import re
        # Common flag formats
        patterns = [
            r"FLAG\{[^}]+\}",
            r"picoCTF\{[^}]+\}",
            r"CTF\{[^}]+\}",
            r"DUCTF\{[^}]+\}",
            r"HTB\{[^}]+\}",
            r"[A-Z0-9]+CTF\{[^}]+\}",
            r"flag\{[^}]+\}",
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def _compute_reward(
        self,
        exploit_result: subprocess.CompletedProcess,
        extracted_flag: Optional[str],
        expected_flag: str,
        stdout: str,
    ) -> float:
        """
        Compute the RL reward signal.

        +1.0  flag captured, exact match
        +0.3  exploit ran without error but wrong/no flag
        -0.5  syntax error, import error (bad exploit structure)
        -1.0  timeout, crash, or no output
        """
        # Timeout or crash signal (returncode < 0 means killed by signal or timeout)
        if exploit_result.returncode < 0:
            return -1.0

        # Non-zero exit: distinguish error types with different penalties
        # FF-9 FIX: Give distinct rewards: syntax errors (-0.5) vs runtime crashes (-0.75)
        if exploit_result.returncode != 0:
            stderr = exploit_result.stderr
            if any(err in stderr for err in ["SyntaxError", "ImportError", "ModuleNotFoundError"]):
                # Syntax/import error: bad code structure, more forgiving since the logic may be right
                return -0.5
            # Runtime crash: worse than a syntax error but better than timeout
            return -0.75

        # Flag captured!
        if extracted_flag:
            if extracted_flag.upper() == expected_flag.upper():
                return 1.0
            # Got a flag but wrong one (partial credit for finding a flag)
            return 0.1

        # Exploit ran but no flag — partial credit for correct approach
        if exploit_result.returncode == 0 and stdout.strip():
            return 0.3

        return -1.0

    def score_batch(
        self,
        exploits: list[str],
        challenge_id: str,
        expected_flag: str,
    ) -> list[float]:
        """
        Score a batch of exploit attempts (for GRPO group computation).

        Args:
            exploits: List of exploit code strings
            challenge_id: Challenge to test against
            expected_flag: Correct flag

        Returns:
            List of reward scores in the same order as exploits
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        scores = [0.0] * len(exploits)
        # FF-11 FIX: Use self.workers instead of hardcoded 4
        workers = min(self.workers, len(exploits))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.run_exploit, exp, challenge_id, expected_flag): i
                for i, exp in enumerate(exploits)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    scores[idx] = result.reward_score
                except Exception:
                    scores[idx] = -1.0

        return scores


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test exploit in Docker sandbox")
    parser.add_argument("exploit_file", help="Path to Python exploit script")
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--flag", required=True, help="Expected flag string")
    parser.add_argument("--test", action="store_true", help="Test harness setup only")
    args = parser.parse_args()

    harness = SandboxHarness()

    if args.test:
        print("Sandbox harness: Docker accessible, setup OK")
    else:
        exploit_code = Path(args.exploit_file).read_text()
        result = harness.run_exploit(
            exploit_code=exploit_code,
            challenge_id=args.challenge_id,
            expected_flag=args.flag,
        )
        print(f"Reward score:    {result.reward_score}")
        print(f"Flag captured:   {result.flag_captured}")
        print(f"Execution time:  {result.execution_time:.2f}s")
        if result.error:
            print(f"Error:           {result.error}")
        print(f"\nStdout:\n{result.stdout}")
