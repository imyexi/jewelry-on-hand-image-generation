import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "aireiter_image_helper.py"
SPEC = importlib.util.spec_from_file_location("aireiter_image_helper", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AIReiterImageHelperTests(unittest.TestCase):
    def test_submit_uses_environment_api_key_when_flag_is_omitted(self) -> None:
        with patch.dict(os.environ, {"AIREITER_API_KEY": "env-key"}, clear=False):
            parser = MODULE.build_parser()
            args = parser.parse_args([
                "submit",
                "--prompt",
                "demo prompt",
                "--aspect-ratio",
                "1:1",
            ])

        self.assertEqual(args.api_key, "env-key")

    def test_submit_allows_missing_flag_until_runtime_without_environment(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(MODULE, "config_api_key", return_value=""):
            parser = MODULE.build_parser()
            args = parser.parse_args([
                "submit",
                "--prompt",
                "demo prompt",
            ])

        self.assertEqual(args.api_key, "")

    def test_submit_task_requires_api_key_when_flag_and_environment_are_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(MODULE, "config_api_key", return_value=""):
            args = MODULE.build_parser().parse_args([
                "submit",
                "--prompt",
                "demo prompt",
            ])
            with self.assertRaises(SystemExit) as exc:
                MODULE.submit_task(args)

        self.assertEqual(exc.exception.code, 1)

    def test_submit_task_uses_defaults_and_image_array(self) -> None:
        args = MODULE.build_parser().parse_args([
            "submit",
            "--api-key",
            "test-key",
            "--prompt",
            "demo prompt",
            "--image",
            "https://example.com/a.jpg",
            "--image",
            "data:image/jpeg;base64,abc",
            "--task-id",
            "task-1",
        ])

        accepted_response = {
            "ok": True,
            "statusCode": 200,
            "data": {"status": "pending", "out_task_id": "task-1"},
        }
        with patch.object(MODULE, "post_json", return_value=accepted_response) as post_json:
            MODULE.submit_task(args)

        payload = post_json.call_args.args[1]
        self.assertEqual(payload["model"], "gpt_image_2")
        self.assertEqual(payload["params"]["aspect_ratio"], "3:4")
        self.assertEqual(payload["params"]["resolution"], "2K")
        self.assertEqual(
            payload["params"]["image_url"],
            ["https://example.com/a.jpg", "data:image/jpeg;base64,abc"],
        )

    def test_submit_task_normalizes_nanobanana_v2_alias(self) -> None:
        args = MODULE.build_parser().parse_args([
            "submit",
            "--api-key",
            "test-key",
            "--model",
            "nanobanana V2",
            "--prompt",
            "demo prompt",
            "--task-id",
            "task-nano",
        ])

        accepted_response = {
            "ok": True,
            "statusCode": 200,
            "data": {"status": "pending", "out_task_id": "task-nano"},
        }
        with patch.object(MODULE, "post_json", return_value=accepted_response) as post_json:
            MODULE.submit_task(args)

        payload = post_json.call_args.args[1]
        self.assertEqual(payload["model"], "nano_banana_v2")
        self.assertEqual(payload["params"]["resolution"], "2K")

    def test_submit_task_uses_environment_model_alias(self) -> None:
        with patch.dict(os.environ, {"AIREITER_MODEL": "nano banana v2 plus"}, clear=False):
            parser = MODULE.build_parser()
            args = parser.parse_args([
                "submit",
                "--api-key",
                "test-key",
                "--prompt",
                "demo prompt",
                "--task-id",
                "task-nano-plus",
            ])

        self.assertEqual(args.model, "nano_banana_v2_plus")

    def test_submit_response_with_433_not_enough_credits_is_not_accepted(self) -> None:
        response = {"ok": True, "statusCode": 433, "message": "not enough credits", "data": None}

        self.assertFalse(MODULE.is_submit_accepted(response))

    def test_submit_response_without_accepted_task_data_is_not_accepted(self) -> None:
        response = {"ok": True, "statusCode": 200, "message": "", "data": None}

        self.assertFalse(MODULE.is_submit_accepted(response))

    def test_submit_response_with_pending_task_data_is_accepted(self) -> None:
        response = {
            "ok": True,
            "statusCode": 200,
            "message": "",
            "data": {"task_id": "", "status": "pending", "out_task_id": "demo-task"},
        }

        self.assertTrue(MODULE.is_submit_accepted(response))

    def test_submit_task_exits_when_submit_response_is_not_accepted(self) -> None:
        args = MODULE.build_parser().parse_args([
            "submit",
            "--api-key",
            "test-key",
            "--prompt",
            "demo prompt",
            "--task-id",
            "task-insufficient-credit",
        ])

        with patch.object(
            MODULE,
            "post_json",
            return_value={"ok": True, "statusCode": 433, "message": "not enough credits", "data": None},
        ):
            with self.assertRaises(SystemExit) as exc:
                MODULE.submit_task(args)

        self.assertEqual(exc.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
