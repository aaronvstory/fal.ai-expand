"""
Quick API Test Script
Run this to verify the API server is working correctly
"""

import requests
import sys
from pathlib import Path

API_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint."""
    print("Testing /health endpoint...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Health check passed")
            print(f"  Backend: {data['backend']['type']}")
            print(f"  Available: {data['backend']['available']}")
            print(f"  Message: {data['backend']['message']}")
            return True
        else:
            print(f"✗ Health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def test_outpaint():
    """Test outpaint endpoint."""
    print("\nTesting /outpaint endpoint...")

    test_image = "tests/fixtures/valid/gradient_512.png"
    if not Path(test_image).exists():
        print(f"✗ Test image not found: {test_image}")
        return False

    try:
        with open(test_image, "rb") as f:
            response = requests.post(
                f"{API_URL}/outpaint",
                files={"image": f},
                data={
                    "expand_left": 100,
                    "expand_right": 100,
                    "expand_top": 100,
                    "expand_bottom": 100,
                    "return_file": False,  # Get JSON response
                },
                timeout=120,
            )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Outpaint succeeded")
            print(f"  Backend used: {data['backend_used']}")
            print(f"  Fallback triggered: {data['fallback_triggered']}")
            print(f"  Outputs: {data['num_outputs']}")
            return True
        else:
            print(f"✗ Outpaint failed: HTTP {response.status_code}")
            print(f"  {response.text}")
            return False
    except Exception as e:
        print(f"✗ Outpaint failed: {e}")
        return False


def main():
    print("╔════════════════════════════════════════╗")
    print("║      Quick API Test Suite             ║")
    print("╚════════════════════════════════════════╝\n")

    print(f"Testing API at: {API_URL}")
    print(f"Make sure the server is running!\n")

    results = []
    results.append(("Health Check", test_health()))
    results.append(("Outpaint", test_outpaint()))

    print("\n" + "="*50)
    print("Test Results:")
    print("="*50)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20} {status}")
        if not passed:
            all_passed = False

    print("="*50)

    if all_passed:
        print("\n🎉 All tests passed! API is ready.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the server logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
