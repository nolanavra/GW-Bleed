import json
import sys
from .pdf_export import export_to_stage


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.read())
        export_to_stage(request, sys.argv[1])
        print(json.dumps({"ok": True}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
