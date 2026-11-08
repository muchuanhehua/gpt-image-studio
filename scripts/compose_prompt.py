"""Compose a prompt from this task's design, image roles, and brief style cues.

Read task, design, images[{path, role}], and optional style{references, highlights}
as JSON on stdin. Style observation notes are never copied into the prompt.
Paths are resolved relative to the current workspace. Never overwrite an output.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys


def required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def existing_file(value):
    path = Path(required_text(str(value), "path")).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    return path


def style_block(value, image_count):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("style must contain references and optional highlights")
    references = value.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("style.references must be a non-empty array of image numbers")
    if any(type(number) is not int or not 1 <= number <= image_count
           for number in references):
        raise ValueError("style.references must identify existing images by 1-based number")
    if len(set(references)) != len(references):
        raise ValueError("style.references must not repeat image numbers")
    highlights = value.get("highlights", [])
    if not isinstance(highlights, list):
        raise ValueError("style.highlights must be an array of brief visible traits")
    highlights = [required_text(item, "style.highlights item") for item in highlights]
    reference_labels = "、".join(f"图{number}" for number in references)
    instruction = f"模仿{reference_labels}的画风，按参考图分工采用整体与局部画法。"
    if highlights:
        instruction += "\n重点保留：" + "；".join(highlights) + "。"
    return instruction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--style-notes", "--style", dest="style_notes", type=Path,
        help="Observation notes: verify the file without copying its contents.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = json.load(sys.stdin)
    if not isinstance(spec, dict):
        raise ValueError("Input must be a JSON object")
    if "style_settings" in spec:
        raise ValueError("Use style.highlights instead of style_settings; attach style references")
    task = required_text(spec.get("task"), "task")
    design = required_text(spec.get("design"), "design")
    images = spec.get("images", [])
    if not isinstance(images, list):
        raise ValueError("images must be an array")

    paths, roles = [], []
    for number, item in enumerate(images, 1):
        if not isinstance(item, dict):
            raise ValueError(f"images[{number}] must contain path and role")
        path_value = required_text(item.get("path"), f"images[{number}].path")
        paths.append(str(existing_file(path_value)))
        roles.append(f"图{number}：{required_text(item.get('role'), f'images[{number}].role')}")

    sections = [f"任务\n{task}"]
    if roles:
        sections.append("参考图分工\n" + "\n".join(roles))
    style = style_block(spec.get("style"), len(paths))
    style_notes = existing_file(args.style_notes) if args.style_notes else None
    if style_notes and not style:
        raise ValueError("--style-notes requires style.references pointing to attached images")
    if style:
        sections.append("画风\n" + style)
    sections.append("本次设计与约束\n" + design)
    prompt = "\n\n".join(sections) + "\n"

    output = args.output.expanduser().resolve()
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(prompt)
    result = {
        "prompt_file": str(output),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "referenced_image_paths": paths,
    }
    if style_notes:
        result["style_notes_file"] = str(style_notes)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"compose_prompt: {exc}")
