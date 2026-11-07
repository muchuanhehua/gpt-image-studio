"""Compose a submitted prompt without rewriting preset bodies.

Read task, design, images[{path, role}], and optional style_settings as JSON on stdin.
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


def preset_body(path):
    text = existing_file(path).read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        text = "".join(lines[1:])
    return required_text(text, f"preset body: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", type=Path)
    parser.add_argument("--series", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = json.load(sys.stdin)
    if not isinstance(spec, dict):
        raise ValueError("Input must be a JSON object")
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
    style = preset_body(args.style) if args.style else None
    if style:
        sections.append("画风\n" + style)
    settings = spec.get("style_settings")
    if settings is not None:
        if not style:
            raise ValueError("style_settings requires --style")
        sections.append("本次画风设置\n" + required_text(settings, "style_settings"))
    for path in args.series:
        sections.append("内容系列\n" + preset_body(path))
    sections.append("本次设计与约束\n" + design)
    prompt = "\n\n".join(sections) + "\n"

    output = args.output.expanduser().resolve()
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(prompt)
    print(json.dumps({
        "prompt_file": str(output),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "referenced_image_paths": paths,
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"compose_prompt: {exc}")
