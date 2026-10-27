#!/usr/bin/env python3

"""Manage named repos (groups of Git repositories) stored in ~/.git-repo.json.

Usage:
    git-repo [--dir <dir>]
    git-repo create [--dir <dir>]
    git-repo update [--dir <dir>]
    git-repo remove [--dir <dir>]
    git-repo (-h | --help)

Commands:
    (none)              Interactive menu: list repos, then Go / Select / Quit.
    create              Select Git repositories of <dir> and save them as a new repo.
    update              Add/remove Git repositories of the repo registered for <dir>.
    remove              Remove a repo from the config (the one of <dir> if --dir, else pick from a list).

Options:
    --dir <dir>         Directory to scan / look up (current directory if omitted).
    -h --help           Show this help message.

Note:
    For "Go" to cd into the repo directory, source the script:
        . git-repo
"""

import contextlib
import io
import json
import os
import shlex
import sys
from pathlib import Path

import dialog
from docopt import docopt


ENV_FILE = "/tmp/env.sh"
CONFIG_FILE = Path("~/.git-repo.json").expanduser()
DEFAULT_KEY = "default_repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_git_repos(base_dir: Path) -> list[str]:
    """Return names of immediate subdirectories of *base_dir* that are Git repositories."""
    try:
        entries = sorted(base_dir.iterdir())
    except OSError:
        return []
    return [e.name for e in entries if e.is_dir() and (e / ".git").exists()]


def load_config() -> dict:
    """Load the repos config from CONFIG_FILE, returning {} on miss."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict) -> None:
    """Persist *config* to CONFIG_FILE (default_repo first)."""
    ordered = {}
    if config.get(DEFAULT_KEY):
        ordered[DEFAULT_KEY] = config[DEFAULT_KEY]
    ordered.update({k: v for k, v in config.items() if k != DEFAULT_KEY})
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=2, ensure_ascii=False)
        f.write("\n")


def repo_names(config: dict) -> list[str]:
    return [k for k, v in config.items() if k != DEFAULT_KEY and isinstance(v, dict)]


def find_repo_by_dir(config: dict, base_dir: Path) -> str | None:
    """Return the name of the repo whose path is *base_dir*, if any."""
    for name in repo_names(config):
        path = config[name].get("path")
        if path and Path(path).expanduser().resolve() == base_dir:
            return name
    return None


def drop_repo(config: dict, name: str) -> None:
    """Delete repo *name* and fix up the default."""
    config.pop(name, None)
    remaining = repo_names(config)
    if config.get(DEFAULT_KEY) == name or config.get(DEFAULT_KEY) not in remaining:
        config.pop(DEFAULT_KEY, None)
        if len(remaining) == 1:
            config[DEFAULT_KEY] = remaining[0]


def clear_screen() -> None:
    os.system("printf '\033c'")


def new_dialog() -> dialog.Dialog:
    return dialog.Dialog(dialog="dialog")


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

def ask_checklist(dial, text, title, names, checked, ok_label, cancel_label) -> list[str] | None:
    """Checklist of *names*; return the checked ones or None if cancelled."""
    choices = [(n, "", n in checked) for n in names]
    code, selected = dial.checklist(
        text,
        title=title,
        choices=choices,
        width=80,
        list_height=min(len(choices) + 2, 18),
        ok_label=ok_label,
        cancel_label=cancel_label,
    )
    return selected if code == dial.OK else None


def ask_name(dial, config: dict) -> str | None:
    """Ask for a new repo name; return None if cancelled."""
    text = "Enter a name for the new repo:"
    while True:
        code, name = dial.inputbox(text, title="Repo Name", width=60)
        if code != dial.OK:
            return None
        name = name.strip()
        if not name:
            text = "Name cannot be empty. Enter a name for the new repo:"
        elif name == DEFAULT_KEY or name in config:
            text = f"'{name}' already exists. Enter another name:"
        else:
            return name


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def do_create(base_dir: Path) -> int:
    """Interactive creation of a repo from the Git repositories of *base_dir*."""
    dial = new_dialog()
    config = load_config()

    existing = find_repo_by_dir(config, base_dir)
    if existing:
        dial.msgbox(
            f"'{base_dir}' is already registered as repo '{existing}'.\n"
            "Use update to change its Git repositories.",
            title="Create", width=70, height=8,
        )
        clear_screen()
        return 1

    found = find_git_repos(base_dir)
    if not found:
        clear_screen()
        print(f"No Git repositories found in '{base_dir}'.")
        return 1

    selected = ask_checklist(
        dial, f"Git repositories in {base_dir}:", "Create Repo",
        found, set(found), "Create", "Cancel",
    )
    if selected is None:
        clear_screen()
        print("Cancelled.")
        return 0
    if not selected:
        clear_screen()
        print("No repositories selected. Nothing saved.")
        return 0

    name = ask_name(dial, config)
    if name is None:
        clear_screen()
        print("Cancelled.")
        return 0

    config[name] = {"path": str(base_dir), "git_repo": selected}

    if len(repo_names(config)) == 1:
        config[DEFAULT_KEY] = name
    elif dial.yesno(
        f"Set '{name}' as the default repo?", title="Default Repo", width=60,
    ) == dial.OK:
        config[DEFAULT_KEY] = name

    save_config(config)
    clear_screen()
    return 0


def do_update(name: str, base_dir: Path) -> int:
    """Update repo *name* from the Git repositories found in *base_dir*."""
    dial = new_dialog()
    config = load_config()
    current = config[name].get("git_repo", [])

    found = find_git_repos(base_dir)
    if not found:
        clear_screen()
        print(f"No Git repositories found in '{base_dir}'.")
        return 1

    selected = ask_checklist(
        dial, f"Repo: {name}\nGit repositories in {base_dir}:", f"Update Repo '{name}'",
        found, set(current), "OK", "Cancel",
    )
    if selected is None:
        clear_screen()
        print("Cancelled.")
        return 0

    if not selected:
        if dial.yesno(
            f"No Git repository selected.\nDelete repo '{name}'?",
            title="Update Repo", width=60, height=8,
        ) != dial.OK:
            clear_screen()
            print("Cancelled.")
            return 0
        drop_repo(config, name)
        save_config(config)
        clear_screen()
        return 0

    config[name]["git_repo"] = selected
    save_config(config)
    clear_screen()
    return 0


def do_remove(name: str) -> int:
    """Remove repo *name* from the config file (never touches Git repos on disk)."""
    dial = new_dialog()
    config = load_config()

    if dial.yesno(
        f"Remove repo '{name}' from {CONFIG_FILE}?\n"
        "(Git repositories on disk are not deleted.)",
        title="Remove", width=70, height=8,
    ) != dial.OK:
        clear_screen()
        print("Cancelled.")
        return 0

    was_default = config.get(DEFAULT_KEY) == name
    drop_repo(config, name)
    remaining = repo_names(config)

    if was_default and len(remaining) > 1:
        code, new_default = dial.menu(
            "Choose the new default repo:",
            title="Default Repo",
            choices=[(n, config[n].get("path", "")) for n in remaining],
            width=100,
            menu_height=min(len(remaining) + 2, 16),
        )
        if code == dial.OK:
            config[DEFAULT_KEY] = new_default

    save_config(config)
    clear_screen()
    return 0


def do_update_dir(base_dir: Path) -> int:
    """`git-repo update`: propose creation when *base_dir* is not registered."""
    config = load_config()
    name = find_repo_by_dir(config, base_dir)
    if name is None:
        dial = new_dialog()
        if dial.yesno(
            f"'{base_dir}' is not part of any repo.\nCreate a new repo?",
            title="Update", width=70, height=8,
        ) != dial.OK:
            clear_screen()
            print("Cancelled.")
            return 0
        return do_create(base_dir)
    return do_update(name, base_dir)


def do_remove_dir(base_dir: Path, dir_given: bool) -> int:
    """`git-repo remove`: remove the repo of *base_dir*, or pick one from the list."""
    config = load_config()
    if dir_given:
        name = find_repo_by_dir(config, base_dir)
        if name is None:
            print(f"'{base_dir}' is not part of any repo.")
            return 1
        return do_remove(name)

    names = repo_names(config)
    if not names:
        print("No repo defined.")
        return 1
    default = config.get(DEFAULT_KEY)
    dial = new_dialog()
    code, name = dial.menu(
        "Select the repo to remove:",
        title="Remove Repo",
        choices=[
            (n, ("[default] " if n == default else "") + config[n].get("path", ""))
            for n in names
        ],
        width=100,
        menu_height=min(len(names) + 2, 16),
        ok_label="Remove",
        cancel_label="Cancel",
    )
    if code != dial.OK:
        clear_screen()
        print("Cancelled.")
        return 0
    return do_remove(name)


def show_list(dial, name: str, config: dict) -> int | None:
    """List the Git repositories of *name*. Return an exit code if Go was chosen, else None."""
    data = config[name]
    base = Path(data.get("path", ""))
    choices = [(r, str(base / r)) for r in data.get("git_repo", [])]
    if not choices:
        dial.msgbox("No Git repository.", title=f"List '{name}'", width=40, height=6)
        return None
    code, selected = dial.menu(
        f"Path: {base}",
        title=f"List '{name}'",
        choices=choices,
        width=100,
        menu_height=min(len(choices) + 2, 16),
        ok_label="Go",
        cancel_label="Back",
    )
    if code != dial.OK:
        return None
    return do_go_path(str(base / selected))


def do_go(name: str) -> int:
    return do_go_path(load_config()[name].get("path", ""))


def do_go_path(path: str) -> int:
    with open(ENV_FILE, "w") as f:
        f.write(f"cd {shlex.quote(path)}\n")
    clear_screen()
    print(path)
    return 0


def run_quiet(func, *args) -> None:
    """Run *func* without printing its output; show it only on failure."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(*args)
    if rc != 0:
        print(buf.getvalue(), end="")


def repo_menu(name: str) -> int | None:
    """Actions on repo *name*. Return an exit code to quit, None to go back to the list."""
    while True:
        config = load_config()
        if name not in config:
            return None
        dial = new_dialog()
        default = " [default]" if config.get(DEFAULT_KEY) == name else ""
        code, action = dial.menu(
            f"Repo: {name}{default}\nPath: {config[name].get('path', '')}",
            title=f"Repo '{name}'",
            choices=[
                ("List", "List the Git repositories"),
                ("Update", "Add/remove Git repositories"),
                ("Remove", "Remove this repo from the config"),
            ],
            width=70,
            menu_height=3,
            ok_label="Select",
            cancel_label="Quit",
            extra_button=True,
            extra_label="Back",
        )
        if code == dial.CANCEL:
            clear_screen()
            return 0
        if code != dial.OK:
            return None

        if action == "List":
            rc = show_list(dial, name, config)
            if rc is not None:
                return rc
        elif action == "Update":
            path = Path(config[name].get("path", "")).expanduser()
            run_quiet(do_update, name, path)
        elif action == "Remove":
            run_quiet(do_remove, name)


def main_menu(base_dir: Path) -> int:
    while True:
        config = load_config()
        names = repo_names(config)
        dial = new_dialog()

        if not names:
            if dial.yesno(
                "No repo defined.\nCreate one from the Git repositories of\n"
                f"{base_dir} ?",
                title="git-repo", width=70, height=9,
            ) != dial.OK:
                clear_screen()
                return 0
            rc = do_create(base_dir)
            if rc != 0 or not repo_names(load_config()):
                return rc
            continue

        default = config.get(DEFAULT_KEY)
        choices = [
            (n, ("[default] " if n == default else "") + config[n].get("path", ""))
            for n in names
        ]
        code, selected = dial.menu(
            "Select a repo:",
            title="Git Repos",
            choices=choices,
            width=100,
            menu_height=min(len(choices) + 2, 16),
            ok_label="Select",
            cancel_label="Quit",
            extra_button=True,
            extra_label="Go",
        )

        if code == dial.EXTRA:
            return do_go(selected)
        if code == dial.OK:
            rc = repo_menu(selected)
            if rc is not None:
                return rc
        else:
            clear_screen()
            return 0


def main() -> int:
    args = docopt(__doc__)

    base_dir = Path(args["--dir"] or ".").expanduser().resolve()

    if not base_dir.is_dir():
        print(f"Error: '{base_dir}' is not a directory.")
        return 1

    try:
        Path(ENV_FILE).unlink(missing_ok=True)
    except OSError:
        pass

    if args["create"]:
        return do_create(base_dir)
    if args["update"]:
        return do_update_dir(base_dir)
    if args["remove"]:
        return do_remove_dir(base_dir, args["--dir"] is not None)
    return main_menu(base_dir)


if __name__ == "__main__":
    sys.exit(main())
