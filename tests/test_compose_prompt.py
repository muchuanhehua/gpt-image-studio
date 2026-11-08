"""Exercise the prompt boundary without making image-generation calls."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compose_prompt.py"


class ComposePromptTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="image-studio-")
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.images = []
        for name in ("编辑底图.png", "画风原图.png", "角色原图.png"):
            path = self.root / name
            path.touch()
            self.images.append(path)
        self.notes = self.root / "画风观察.md"
        self.notes.write_text("# 画风\nPRIVATE_ANALYSIS_MUST_STAY_OUT\n", encoding="utf-8")
        self.series = self.root / "内容系列.md"
        self.series_body = "窗边站立，手持一束蓝色花朵。\n保留完整人物剪影。"
        self.series.write_text("# 内容系列标题\n\n" + self.series_body, encoding="utf-8")
        self.output = self.root / "实际提示词.txt"
        self.spec = {
            "task": "修改服装，保留人物身份和构图。",
            "images": [
                {"path": str(path), "role": role}
                for path, role in zip(self.images, ("编辑底图", "整体画风", "角色身份"))
            ],
            "style": {"references": [2], "highlights": ["保留有分量的主轮廓"]},
            "design": "只调整衣袖。",
        }

    def compose(self, spec=None, notes_flag="--style-notes", with_series=False):
        command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT), "--output", str(self.output)]
        if notes_flag:
            command.extend((notes_flag, str(self.notes)))
        if with_series:
            command.extend(("--series", str(self.series)))
        return subprocess.run(
            command, input=json.dumps(self.spec if spec is None else spec, ensure_ascii=False),
            cwd=self.root, text=True, encoding="utf-8", capture_output=True,
        )

    def result(self, process):
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout), self.output.read_text(encoding="utf-8")

    def test_notes_stay_out_and_actual_image_order_is_preserved(self):
        metadata, prompt = self.result(self.compose())
        self.assertNotIn("PRIVATE_ANALYSIS_MUST_STAY_OUT", prompt)
        self.assertNotIn(str(self.notes), prompt)
        self.assertEqual(metadata["style_notes_file"], str(self.notes))
        self.assertEqual(metadata["referenced_image_paths"], [str(path) for path in self.images])
        self.assertIn("模仿图2", prompt)
        self.assertIn(self.spec["style"]["highlights"][0], prompt)
        self.assertEqual(metadata["prompt_sha256"], hashlib.sha256(prompt.encode("utf-8")).hexdigest())

    def test_legacy_style_flag_also_keeps_notes_out(self):
        _, prompt = self.result(self.compose(notes_flag="--style"))
        self.assertNotIn("PRIVATE_ANALYSIS_MUST_STAY_OUT", prompt)

    def test_raw_style_reference_needs_no_notes_or_highlights(self):
        self.spec["style"].pop("highlights")
        metadata, prompt = self.result(self.compose(notes_flag=None))
        self.assertNotIn("style_notes_file", metadata)
        self.assertIn("模仿图2", prompt)

    def test_content_series_keeps_its_body(self):
        _, prompt = self.result(self.compose(with_series=True))
        self.assertIn(self.series_body, prompt)
        self.assertNotIn("内容系列标题", prompt)
        self.assertNotIn("PRIVATE_ANALYSIS_MUST_STAY_OUT", prompt)

    def test_task_without_style_or_images_still_works(self):
        spec = {"task": "生成一张海报。", "design": "中央放置蓝色花朵。"}
        metadata, prompt = self.result(self.compose(spec, notes_flag=None))
        self.assertEqual(metadata["referenced_image_paths"], [])
        self.assertIn(spec["design"], prompt)

    def test_notes_alone_cannot_stand_in_for_style_images(self):
        self.spec.pop("style")
        process = self.compose()
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_invalid_style_references_fail_before_writing(self):
        for references in ([], [0], [4], [True], ["2"], [2, 2]):
            with self.subTest(references=references):
                self.spec["style"]["references"] = references
                process = self.compose()
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_style_cannot_reference_an_empty_image_list(self):
        self.spec["images"] = []
        process = self.compose()
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_legacy_settings_are_not_silently_dropped(self):
        self.spec["style_settings"] = "主描边采用紫褐色。"
        process = self.compose()
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_submitted_prompt_cannot_be_overwritten(self):
        self.result(self.compose())
        original = self.output.read_bytes()
        self.spec["design"] = "改成另一套设计。"
        process = self.compose()
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
