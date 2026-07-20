"""CI helper: parse Bandit JSON report and exit non-zero on HIGH severity issues.

This script is invoked by .github/workflows/ci.yml to enforce that
no HIGH severity security issues are introduced. It accepts the
report path as argv[1] (default: /tmp/bandit-report.json).
"""
import json
import sys


def main(report_path: str = "/tmp/bandit-report.json") -> int:
    try:
        with open(report_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"::error::Bandit report not found: {report_path}")
        return 1
    except json.JSONDecodeError as e:
        print(f"::error::Invalid Bandit JSON: {e}")
        return 1

    high = [r for r in data.get("results", []) if r.get("issue_severity") == "HIGH"]
    if high:
        print(f"::error::Bandit found {len(high)} HIGH severity issues")
        for r in high[:10]:
            test_id = r["test_id"]
            test_name = r["test_name"]
            filename = r["filename"]
            line = r["line_number"]
            print(f"  - {test_id} {test_name}: {filename}:{line}")
        return 1
    print("Bandit: 0 HIGH severity issues")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bandit-report.json"
    sys.exit(main(path))
