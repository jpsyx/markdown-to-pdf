"""Exercise installer contracts without changing the user's installation."""

import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


REPO_ROOT = Path(__file__).resolve().parent


class InstallTests(unittest.TestCase):
    def test_named_install_replaces_only_the_requested_executable(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory)
            for _ in range(2):
                result = subprocess.run(
                    [REPO_ROOT / "install.sh", "--name", "contract-probe"],
                    cwd="/", env=dict(os.environ, BIN_DIR=directory),
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(list(destination.iterdir()), [destination / "contract-probe"])
                result = subprocess.run(
                    [destination / "contract-probe", "--version"],
                    cwd="/", capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith("markdown-to-pdf "))

    def test_help_and_invalid_arguments_never_create_the_destination(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "absent"
            for args, success in [
                (["--help"], True), (["-h"], True),
                (["--name", "custom", "--help"], True),
                (["--unknown"], False), (["--name"], False),
                (["--name", "../escape"], False), (["--name", ""], False),
            ]:
                with self.subTest(args=args):
                    result = subprocess.run(
                        ["/bin/bash", REPO_ROOT / "install.sh", *args],
                        env=dict(os.environ, BIN_DIR=str(destination), PATH=""),
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    self.assertIn("Usage:", result.stdout if success else result.stderr)
                    self.assertFalse(destination.exists())

    def test_repairs_python_with_optional_mermaid_and_diagnoses_a_moved_clone(self):
        for with_npm in [False, True]:
            with self.subTest(with_npm=with_npm), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()
                for name in ["install.sh", "run.sh", "main.py", "requirements.txt", "package.json"]:
                    shutil.copy2(REPO_ROOT / name, source / name)
                python = source / ".venv/bin/python"
                python.parent.mkdir(parents=True)
                python.write_text("#!/bin/sh\nexit 1\n")
                python.chmod(0o755)
                tools = root / "tools"
                tools.mkdir()
                for name in ["bash", "cat", "dirname", "mkdir", "rm", "mktemp", "chmod", "mv", "python3"]:
                    (tools / name).symlink_to(shutil.which(name))
                if with_npm:
                    for name, status in [("npm", 0), ("npx", 1)]:
                        tool = tools / name
                        tool.write_text(f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "$PROVISION_LOG"\nexit {status}\n')
                        tool.chmod(0o755)
                log = root / "provision.log"
                result = subprocess.run(
                    ["/bin/bash", source / "install.sh", "--name", "repaired"],
                    env=dict(os.environ, BIN_DIR=str(root / "bin"), PATH=str(tools), PROVISION_LOG=str(log)),
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run(
                    [python, "-c", "import reportlab, pygments"],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if with_npm:
                    self.assertEqual(log.read_text().splitlines(), [
                        f"npm install --prefix {source}",
                        f"npx --prefix {source} puppeteer browsers install chrome-headless-shell",
                    ])
                markdown = root / "sample.md"
                markdown.write_text("# Installer contract\n\nThe repaired environment renders this document.\n")
                result = subprocess.run(
                    [root / "bin/repaired", markdown], capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / "sample.pdf").read_bytes().startswith(b"%PDF"))
                source.rename(root / "moved")
                result = subprocess.run([root / "bin/repaired", "--help"], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("re-run install.sh", result.stderr)


if __name__ == "__main__":
    unittest.main()
