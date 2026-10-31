"""The ``zeno`` CLI entrypoint.

Thin by design: it bootstraps logging, then (from task 002 onward) hands off to the
TUI + harness. ``init_logger()`` runs at module level before any other project import.
"""

# TODO: Not Done Yet

from __future__ import annotations

import click
import asyncio
from pathlib import Path

from src.zeno.tui.app import run_app


@click.group(invoke_without_command=True)
@click.option(
    "--mode",
    "mode",
    default=None,
    metavar="MODE",
    help="Runtime mode for the app.",
)
@click.option(
    "--repo",
    "repo",
    default=None,
    metavar="URL-OR-PATH",
    help="Optional repo path or URL to seed the app with.",
)
@click.pass_context
def cli(ctx: click.Context, mode: str | None, repo: str | None) -> None:
    if ctx.invoked_subcommand is not None:
        return

    asyncio.run(run_app(mode=mode, repo=repo))


@cli.command("run")
@click.argument("task", required=False)
@click.option(
    "--model",
    "model",
    default=None,
    metavar="ID",
    help=(
        "Override the active provider's model id for this run (e.g. gemini-2.5-pro); defaults to the "
        "provider's configured model. Does not change the provider (set LLM_PROVIDER for that)."
    ),
)
@click.option(
    "--repo",
    "repo",
    default=None,
    metavar="URL-OR-PATH",
    help="Optional repo to pass into the app runtime.",
)
@click.option(
    "--local",
    "local",
    is_flag=True,
    help="Reserved for local-repo behavior; currently accepted but not used by the app runtime.",
)
@click.option(
    "--max-requests",
    "max_requests",
    default=None,
    type=click.IntRange(min=1),
    metavar="N",
    help="Optional request cap for this run.",
)
@click.option(
    "--summary-json",
    "summary_json",
    default=None,
    metavar="PATH",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output path for a summary JSON document.",
)
def run(
    task: str | None,
    model: str | None,
    repo: str | None,
    local: bool,
    max_requests: int | None,
    summary_json: Path | None,
) -> None:
    del task, model, local, max_requests, summary_json
    asyncio.run(run_app(repo=repo))


if __name__ == "__main__":
    cli()