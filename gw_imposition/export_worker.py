import json
import sys
from .pdf_export import export_to_stage


def main():
    try:
        raw = sys.stdin.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:
            raise ValueError('Export request exceeds supported size.')
        request = json.loads(raw)
        export_to_stage(request, sys.argv[1])
        print(json.dumps({"ok": True}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
