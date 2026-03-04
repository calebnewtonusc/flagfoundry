"""health_check.py - Post-deploy smoke test for FlagFoundry API."""

import json
import sys

import requests


def check_api(base_url: str = "http://localhost:8080") -> bool:
    print(f"FlagFoundry API health check: {base_url}")

    # Health endpoint
    # FF-22 FIX: Replace bare assert with explicit if/sys.exit(1) so checks are not
    # silently disabled by Python -O (optimize) flag
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"  [FAIL] /health endpoint: HTTP {resp.status_code}")
            return False
        print("  [PASS] /health endpoint")
    except Exception as e:
        print(f"  [FAIL] /health endpoint: {e}")
        return False

    # Classify endpoint
    try:
        resp = requests.post(
            f"{base_url}/v1/classify",
            json={"description": "SQL injection in the login form"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [FAIL] /v1/classify: HTTP {resp.status_code}")
            return False
        data = resp.json()
        if data.get("category") != "web":
            print(f"  [FAIL] /v1/classify: expected category='web', got '{data.get('category')}'")
            return False
        print(f"  [PASS] /v1/classify → {data.get('category')}")
    except Exception as e:
        print(f"  [FAIL] /v1/classify: {e}")
        return False

    # Solve endpoint (minimal test, no Docker sandbox)
    try:
        resp = requests.post(
            f"{base_url}/v1/solve",
            json={
                "description": "md5(flag) = d077f244def8a70e5ea758bd8352fcd8. Recover the flag.",
                "category": "crypto",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  [FAIL] /v1/solve: HTTP {resp.status_code}")
            return False
        data = resp.json()
        if "exploit" not in data:
            print("  [FAIL] /v1/solve: 'exploit' field missing from response")
            return False
        print(f"  [PASS] /v1/solve → category={data.get('category')}")
    except Exception as e:
        print(f"  [FAIL] /v1/solve: {e}")
        return False

    print("\nAll checks passed. FlagFoundry API is healthy.")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()
    ok = check_api(args.url)
    sys.exit(0 if ok else 1)
