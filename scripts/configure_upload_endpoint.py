"""Bake only the public upload-service URL into a release build."""

import os
from pathlib import Path

from custompresence.images import normalize_image_url


def main():
    endpoint = os.getenv("CUSTOMPRESENCE_UPLOAD_URL", "").strip()
    if not endpoint and os.getenv("GITHUB_EVENT_NAME") == "release":
        raise SystemExit("Set the CUSTOMPRESENCE_UPLOAD_URL Actions variable before publishing upload-enabled releases.")
    if endpoint:
        endpoint = normalize_image_url(endpoint)
    config = Path(__file__).resolve().parents[1] / "custompresence" / "config.py"
    lines = config.read_text(encoding="utf-8").splitlines()
    config.write_text("\n".join(f"UPLOAD_SERVICE_URL = {endpoint!r}" if line.startswith("UPLOAD_SERVICE_URL =")
                              else line for line in lines) + "\n", encoding="utf-8")
    print("Configured public upload endpoint." if endpoint else "Building with public links; upload service is not configured.")


if __name__ == "__main__":
    main()
