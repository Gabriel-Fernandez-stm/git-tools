#!/usr/bin/env python3

"""Manage named worktree groups across multiple Git repositories.

Usage:
    git-worktree
    git-worktree add
    git-worktree remove
    git-worktree (-h | --help)

Options:
    -h --help           Show this help message.

Examples:
    git-worktree
    git-worktree add
    git-worktree remove

Groups are managed with the 'git-repo' command (git-repo create / update / remove).

Note:
    For the default command to cd into the selected view, call the script via the shell
    wrapper so /tmp/env.sh is sourced:
        . git-worktree
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import dialog
from docopt import docopt


ENV_FILE = "/tmp/env.sh"
CONFIG_FILE = Path("~/.git-repo.json").expanduser()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_groups() -> dict:
    """Load existing worktree groups from CONFIG_FILE, returning {} on miss."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def clear_screen():
    os.system("printf '\033c'")


# ---------------------------------------------------------------------------
# List worktree views
# ---------------------------------------------------------------------------

def _get_worktrees(repo_path: Path) -> list[tuple[str, str, str]]:
    """Return [(wt_path, commit, ref), ...] for a repo."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "worktree", "list"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            entries.append((parts[0], parts[1], " ".join(parts[2:])))
    return entries


def scan_views(group_data: dict) -> list[dict]:
    """Scan all repos in the group and return deduplicated view dicts."""
    base = Path(group_data.get("path", "."))
    git_repos = group_data.get("git_repo", [])
    views: dict[str, dict] = {}  # keyed by view_path

    for repo_name in git_repos:
        repo_path = base / repo_name
        if not repo_path.is_dir():
            continue
        for wt_path, commit, ref in _get_worktrees(repo_path):
            if Path(wt_path).resolve() == repo_path.resolve():
                continue  # skip main worktree
            view_dir = str(Path(wt_path).parent)
            view_name = Path(view_dir).name
            if view_dir not in views:
                views[view_dir] = {
                    "view_name": view_name,
                    "view_path": view_dir,
                    "ref": ref,
                    "components": [],
                }
            views[view_dir]["components"].append(repo_name)

    return sorted(views.values(), key=lambda v: v["view_name"].lower())


def cmd_list() -> int:
    groups = load_groups()
    repo_names = [k for k in groups if k != "default_repo"]

    if not repo_names:
        print("No worktree groups defined. Run 'git-repo create' first.")
        return 1

    dial = dialog.Dialog(dialog="dialog")
    current_group = groups.get("default_repo") or repo_names[0]

    while True:
        group_data = groups.get(current_group, {})
        if not isinstance(group_data, dict):
            break

        views = scan_views(group_data)
        title = f"Worktree Views  [{current_group}]"

        if not views:
            code = dial.yesno(
                f"No worktree views found for group '{current_group}'.\n\nChanger de repos?",
                title=title,
                yes_label="Changer de repos",
                no_label="Cancel",
                width=60,
            )
            clear_screen()
            if code != dial.OK:
                return 0
            chosen = _select_group(dial, groups, current_group)
            if chosen:
                current_group = chosen
            continue

        choices = [
            (str(i), f"{v['view_name']}  ({v['view_path']})")
            for i, v in enumerate(views)
        ]
        code, tag = dial.menu(
            "Select a view  (Ok=cd / Changer de repos / Cancel):",
            title=title,
            choices=choices,
            ok_label="Ok",
            cancel_label="Cancel",
            help_button=True,
            help_label="Changer de repos",
            width=80,
            menu_height=min(len(views) + 2, 16),
        )

        clear_screen()

        if code == dial.HELP:
            chosen = _select_group(dial, groups, current_group)
            if chosen:
                current_group = chosen
            continue

        if code != dial.OK:
            return 0

        # cd to view_path via ENV_FILE (shell wrapper sources it)
        view = views[int(tag)]
        with open(ENV_FILE, "w") as f:
            f.write(f"cd {view['view_path']}\n")
        print(f"→ cd {view['view_path']}")
        return 0


# ---------------------------------------------------------------------------
# Add worktree view
# ---------------------------------------------------------------------------

def _select_group(dial: dialog.Dialog, groups: dict, current: str) -> str | None:
    """Show a radiolist of group names; return the chosen one or None."""
    repo_names = [k for k in groups if k != "default_repo"]
    choices = [(n, "", n == current) for n in repo_names]
    code, selected = dial.radiolist(
        "Select a repo group:",
        title="Select Repo Group",
        choices=choices,
        width=60,
    )
    return selected if code == dial.OK else None


def _checklist_repos(dial: dialog.Dialog, group_name: str, git_repos: list[str]) -> list[str] | None:
    """
    Show a checklist of repos (all pre-selected) with an extra 'Select another Repo' button.
    Returns selected repos, or None on cancel, or the string 'change' to switch group.
    """
    choices = [(r, "", True) for r in git_repos]
    code, selected = dial.checklist(
        f"Select repos for group '{group_name}':",
        title="Add Worktree View",
        choices=choices,
        ok_label="Ok",
        cancel_label="Cancel",
        extra_button=True,
        extra_label="Select another Repo",
        width=70,
        list_height=min(len(git_repos) + 2, 16),
    )
    if code == dial.OK:
        return selected
    if code == dial.EXTRA:
        return "change"
    return None


def cmd_add() -> int:
    groups = load_groups()
    repo_names = [k for k in groups if k != "default_repo"]

    if not repo_names:
        print("No worktree groups defined. Run 'git-repo create' first.")
        return 1

    dial = dialog.Dialog(dialog="dialog")
    cwd = Path.cwd()

    # 1 – pick repos (loop to allow 'Select another Repo')
    current_group = groups.get("default_repo") or repo_names[0]
    selected_repos = None
    while True:
        group_data = groups.get(current_group, {})
        git_repos = group_data.get("git_repo", []) if isinstance(group_data, dict) else []
        group_path = Path(group_data.get("path", ".")) if isinstance(group_data, dict) else cwd

        result = _checklist_repos(dial, current_group, git_repos)
        if result is None:
            clear_screen()
            print("Cancelled.")
            return 0
        if result == "change":
            chosen = _select_group(dial, groups, current_group)
            if chosen:
                current_group = chosen
            continue
        selected_repos = result
        break

    if not selected_repos:
        clear_screen()
        print("No repositories selected. Nothing done.")
        return 0

    # 2 – ask for the view name
    code, view_name = dial.inputbox(
        "Enter a name for the new view:",
        title="Add Worktree View",
        width=60,
    )
    clear_screen()
    if code != dial.OK or not view_name.strip():
        print("Cancelled.")
        return 0
    view_name = view_name.strip()

    # 3 – run git worktree add for each selected repo
    errors = []
    created = []
    for repo in selected_repos:
        repo_path = group_path / repo
        wt_path = cwd / view_name / repo
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "add", str(wt_path), "--detach"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(f"  {repo}: {result.stderr.strip()}")
        else:
            created.append(f"  {wt_path}")

    for path in created:
        print(f"Created: {path}")
    for err in errors:
        print(f"Error:   {err}")

    return 1 if errors else 0


# ---------------------------------------------------------------------------
# Remove worktree view
# ---------------------------------------------------------------------------

def cmd_remove() -> int:
    groups = load_groups()
    repo_names = [k for k in groups if k != "default_repo"]

    if not repo_names:
        print("No worktree groups defined. Run 'git-repo create' first.")
        return 1

    dial = dialog.Dialog(dialog="dialog")
    current_group = groups.get("default_repo") or repo_names[0]

    while True:
        group_data = groups.get(current_group, {})
        if not isinstance(group_data, dict):
            break

        views = scan_views(group_data)
        title = f"Remove Worktree View  [{current_group}]"

        if not views:
            code = dial.yesno(
                f"No worktree views found for group '{current_group}'.\n\nChanger de repos?",
                title=title,
                yes_label="Changer de repos",
                no_label="Cancel",
                width=60,
            )
            clear_screen()
            if code != dial.OK:
                return 0
            chosen = _select_group(dial, groups, current_group)
            if chosen:
                current_group = chosen
            continue

        choices = [
            (str(i), f"{v['view_name']}  ({v['view_path']})")
            for i, v in enumerate(views)
        ]
        code, tag = dial.menu(
            "Select a view to remove  (Ok=remove / Changer de repos / Cancel):",
            title=title,
            choices=choices,
            ok_label="Ok",
            cancel_label="Cancel",
            help_button=True,
            help_label="Changer de repos",
            width=80,
            menu_height=min(len(views) + 2, 16),
        )

        if code == dial.HELP:
            clear_screen()
            chosen = _select_group(dial, groups, current_group)
            if chosen:
                current_group = chosen
            continue

        if code != dial.OK:
            clear_screen()
            return 0

        view = views[int(tag)]
        group_base = Path(group_data["path"])

        # Confirm
        confirm_msg = (
            f"Remove worktree view:\n\n"
            f"  Name : {view['view_name']}\n"
            f"  Path : {view['view_path']}\n\n"
            f"Components: {', '.join(view['components'])}\n\n"
            f"This will run 'git worktree remove --force' for each repo.\n"
            f"Are you sure?"
        )
        if dial.yesno(confirm_msg, title="Confirm Remove", width=72) != dial.OK:
            clear_screen()
            print("Cancelled.")
            return 0

        clear_screen()

        # Remove each component's worktree
        errors = []
        for component in view["components"]:
            repo_path = group_base / component
            wt_path = Path(view["view_path"]) / component
            result = subprocess.run(
                ["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                errors.append(f"  {component}: {result.stderr.strip()}")
            else:
                print(f"Removed: {wt_path}")

        # Remove view directory if empty
        view_dir = Path(view["view_path"])
        try:
            view_dir.rmdir()
        except OSError:
            pass

        if errors:
            for e in errors:
                print(f"Error: {e}")
        else:
            # cd to group base path via ENV_FILE
            with open(ENV_FILE, "w") as f:
                f.write(f"cd {group_base}\n")
            print(f"\u2192 cd {group_base}")

        return 1 if errors else 0

def main() -> int:
    args = docopt(__doc__)

    # Remove any stale ENV_FILE left from a previous run.
    try:
        Path(ENV_FILE).unlink(missing_ok=True)
    except OSError:
        pass

    if args["remove"]:
        return cmd_remove()

    if args["add"]:
        return cmd_add()

    return cmd_list()


if __name__ == "__main__":
    sys.exit(main())
