#!/usr/bin/env python3
"""
Measure the evidence and timeline agents on the labelled demo cases (app/services/investigation_demo.py).

  python scripts/evaluate_investigation.py

Runs on the same redacted text CrimeAI stores, and prints precision and recall per finding type, plus how long the
agents take per case. No database or network needed.
"""
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.nlp.privacy.redaction import redact
from app.services.investigation import Doc, investigate
from app.services.investigation_demo import demo_cases


def labels(findings: list[dict]) -> set[str]:
    return {f"{f['kind']}:{f['subject']}" if f["kind"] == "contradiction" else f["kind"] for f in findings}


def main() -> int:
    tp, fp, fn = Counter(), Counter(), Counter()
    timings = []
    print(f"{'case':<18}{'lang':<6}{'expected':<62}found")
    for case in demo_cases(datetime.now(UTC)):
        docs = [Doc("fir", "FIR", "fir", redact(case["fir"]).text)]
        docs += [Doc(f"d{i}", title, t, redact(text).text, at) for i, (t, title, at, text) in enumerate(case["documents"])]
        start = time.perf_counter()
        result = investigate({"occurred_at": case["occurred_at"]}, docs, [])
        timings.append((time.perf_counter() - start) * 1000)
        found = labels(result["findings"])
        expected = case["expected"]
        for label in found | expected:
            kind = label.split(":")[-1]
            if label in found and label in expected:
                tp[kind] += 1
            elif label in found:
                fp[kind] += 1
            else:
                fn[kind] += 1
        print(f"{case['case_number']:<18}{case['language']:<6}{', '.join(sorted(expected)) or '-':<62}"
              f"{', '.join(sorted(found)) or '-'}")

    print()
    print(f"{'finding':<16}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>8}")
    for kind in sorted(set(tp) | set(fp) | set(fn)):
        p = tp[kind] / (tp[kind] + fp[kind]) if tp[kind] + fp[kind] else 0.0
        r = tp[kind] / (tp[kind] + fn[kind]) if tp[kind] + fn[kind] else 0.0
        print(f"{kind:<16}{tp[kind]:>4}{fp[kind]:>4}{fn[kind]:>4}{p:>11.2f}{r:>8.2f}")
    total_tp, total_fp, total_fn = sum(tp.values()), sum(fp.values()), sum(fn.values())
    print(f"{'all':<16}{total_tp:>4}{total_fp:>4}{total_fn:>4}"
          f"{total_tp / max(total_tp + total_fp, 1):>11.2f}{total_tp / max(total_tp + total_fn, 1):>8.2f}")
    print(f"\nAgents ran in {sum(timings) / len(timings):.1f} ms per case on average.")
    return 0 if not total_fp and not total_fn else 1


if __name__ == "__main__":
    sys.exit(main())
