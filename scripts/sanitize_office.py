#!/usr/bin/env python3
"""Remove identifying Office properties without rewriting document content."""
import argparse
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def sanitized_properties(name, content):
    element = ET.fromstring(content)
    if name == "docProps/core.xml":
        for child in list(element):
            element.remove(child)
    elif name == "docProps/custom.xml":
        # Preserve this workbook calculation flag; discard WPS account/build IDs.
        for child in list(element):
            if child.get("name") != "CalculationRule":
                element.remove(child)
    elif name == "docProps/app.xml":
        identifying = {"Company", "Manager", "Template", "HyperlinkBase", "Application", "TotalTime"}
        for child in list(element):
            if child.tag.rsplit("}", 1)[-1] in identifying:
                element.remove(child)
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def sanitize(path):
    with ZipFile(path) as original:
        if original.testzip() is not None:
            raise ValueError(f"Corrupt Office archive: {path}")
        original_parts = {item.filename: original.read(item) for item in original.infolist()}
        changes = {}
        for name in ("docProps/core.xml", "docProps/custom.xml", "docProps/app.xml"):
            if name in original_parts:
                changes[name] = sanitized_properties(name, original_parts[name])
        descriptor, temporary = tempfile.mkstemp(prefix="office_metadata_", suffix=path.suffix, dir=path.parent)
        os.close(descriptor)
        try:
            with ZipFile(temporary, "w") as output:
                output.comment = b""
                for item in original.infolist():
                    item.comment = b""
                    output.writestr(item, changes.get(item.filename, original_parts[item.filename]))
            with ZipFile(temporary) as output:
                if output.testzip() is not None or set(output.namelist()) != set(original_parts):
                    raise ValueError("Office archive verification failed")
                for name, content in original_parts.items():
                    if name not in changes and output.read(name) != content:
                        raise ValueError(f"Document content changed: {name}")
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    os.replace(temporary, path)
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "standards")
    args = parser.parse_args()
    for path in sorted(args.directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
            count = sanitize(path)
            print(f"Sanitized {path.name}: {count} property parts; content parts unchanged")


if __name__ == "__main__":
    main()
