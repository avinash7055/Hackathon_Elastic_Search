"""Preview synthetic FAERS data locally without Elasticsearch.

Generates a small sample and saves to a JSON file for inspection.

Usage:
    python -m data.preview_data              # 50 records (default)
    python -m data.preview_data --count 200  # custom count
"""

import json
import argparse
from pathlib import Path
from data.generate_faers_data import generate_all_reports

def main():
    parser = argparse.ArgumentParser(description="Preview synthetic FAERS data")
    parser.add_argument("--count", type=int, default=50, help="Number of records to generate (default: 50)")
    parser.add_argument("--output", default="data/sample_faers.json", help="Output JSON file")
    args = parser.parse_args()

    print(f"Generating {args.count} sample FAERS reports...")
    reports = generate_all_reports(args.count)

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(reports, f, indent=2, default=str)

    print(f"\nSaved {len(reports)} reports to {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")

    # Show summary
    drugs = {}
    for r in reports:
        d = r.get("drug_name", "Unknown")
        drugs[d] = drugs.get(d, 0) + 1

    print(f"\nDrug distribution:")
    for drug, count in sorted(drugs.items(), key=lambda x: -x[1]):
        print(f"  {drug}: {count} reports")

    # Show first 3 records as preview
    print(f"\n--- Sample Records (first 3) ---\n")
    for i, report in enumerate(reports[:3]):
        print(json.dumps(report, indent=2, default=str))
        if i < 2:
            print()

if __name__ == "__main__":
    main()
