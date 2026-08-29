"""Terminal visuals — click only, no extra deps."""

from __future__ import annotations

import click

BRAND = "Token Engine"
_WIDTH = 58


def banner(subtitle: str = "") -> None:
    top = f"╔{'═' * _WIDTH}╗"
    mid = f"║{BRAND:^{_WIDTH}}║"
    bot = f"╚{'═' * _WIDTH}╝"
    click.secho(top, fg="cyan")
    click.secho(mid, fg="cyan", bold=True)
    if subtitle:
        sub = f"║{subtitle:^{_WIDTH}}║"
        click.secho(sub, fg="bright_black")
    click.secho(bot, fg="cyan")
    click.echo()


def section(title: str) -> None:
    click.secho(f"\n{title}", fg="cyan", bold=True)
    click.secho("─" * (_WIDTH + 2), fg="bright_black")


def ratio_fg(ratio: float) -> str:
    if ratio >= 0.6:
        return "green"
    if ratio >= 0.35:
        return "yellow"
    return "red"


def bar(ratio: float, width: int = 20) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)


def stat(label: str, value: str, *, width: int = 14) -> None:
    click.secho(f"  {label:<{width}} ", fg="bright_black", nl=False)
    click.secho(str(value), bold=True)


def stat_tokens(label: str, count: int, *, width: int = 14) -> None:
    stat(label, f"{count:>10,} tok", width=width)


def stat_ratio(label: str, ratio: float, *, width: int = 14) -> None:
    pct = f"{ratio * 100:6.1f}%"
    click.secho(f"  {label:<{width}} ", fg="bright_black", nl=False)
    click.secho(pct, fg=ratio_fg(ratio), bold=True)
    click.secho(f"  {bar(ratio)}", fg=ratio_fg(ratio))


def ok(msg: str) -> None:
    click.secho(f"  ✓ {msg}", fg="green")


def warn(msg: str) -> None:
    click.secho(f"  ! {msg}", fg="yellow")


def fail(msg: str) -> None:
    click.secho(f"  ✗ {msg}", fg="red")
