"""Exports the backend's OpenAPI schema to JSON - the source `openapi-typescript`
(frontend/package.json's `generate:types` script) reads to regenerate
frontend/src/api/schema.ts.

Run this whenever the API/Case File models change, then re-run
`npm run generate:types` in frontend/ and commit both the updated
openapi.json and schema.ts - see frontend/README.md's "Generated API
types" section for the full workflow and why this is a checked-in
generated artifact rather than a live fetch at build time (no backend
needs to be running to build the frontend).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
