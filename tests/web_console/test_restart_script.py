from __future__ import annotations

from pathlib import Path
import os
import subprocess


def test_restart_script_stops_when_startup_validation_fails(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    temp_root = tmp_path / "workspace"
    scripts_dir = temp_root / "scripts"
    scripts_dir.mkdir(parents=True)
    script_path = scripts_dir / "restart_dev.sh"
    script_path.write_text(
        (project_root / "scripts" / "restart_dev.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    os.chmod(script_path, 0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "make_called.txt"

    (bin_dir / "python3").write_text(
        "#!/bin/sh\n"
        "echo 'mock startup validation failed' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "make").write_text(
        "#!/bin/sh\n"
        f"echo called > '{marker}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "lsof").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "pkill").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    for name in ("python3", "make", "lsof", "pkill"):
        os.chmod(bin_dir / name, 0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PYTHON_BIN"] = str(bin_dir / "python3")

    result = subprocess.run(
        [str(script_path)],
        cwd=str(temp_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Web Console 启动前置校验失败" in result.stdout
    assert marker.exists() is False


def test_restart_script_prefers_venv_python_for_startup_validation(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    temp_root = tmp_path / "workspace"
    scripts_dir = temp_root / "scripts"
    venv_bin = temp_root / ".venv" / "bin"
    scripts_dir.mkdir(parents=True)
    venv_bin.mkdir(parents=True)
    script_path = scripts_dir / "restart_dev.sh"
    script_path.write_text(
        (project_root / "scripts" / "restart_dev.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    os.chmod(script_path, 0o755)
    bin_dir = tmp_path / "bin"
    marker = tmp_path / "venv_python_used.txt"
    make_marker = tmp_path / "make_called.txt"

    bin_dir.mkdir()
    (bin_dir / "python3").write_text("#!/bin/sh\necho system-python-used >&2\nexit 9\n", encoding="utf-8")
    (bin_dir / "make").write_text(
        "#!/bin/sh\n"
        f"echo called > '{make_marker}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "lsof").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "pkill").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (venv_bin / "python").write_text(
        "#!/bin/sh\n"
        f"echo used > '{marker}'\n"
        "exit 1\n",
        encoding="utf-8",
    )

    for name in ("python3", "make", "lsof", "pkill"):
        os.chmod(bin_dir / name, 0o755)
    os.chmod(venv_bin / "python", 0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [str(script_path)],
        cwd=str(temp_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert marker.exists() is True
    assert "system-python-used" not in result.stderr
    assert make_marker.exists() is False
