"""
``hvx`` command line.

    hvx report --site site.yaml --days 14 -o report.html     # pull live data, build a report
    hvx report --csv data/building_folder -o report.json     # report from CSV folders
    hvx watch  --site site.yaml --every 300                  # live status, refreshed
    hvx site from-ifc building.ifc -o site.yaml              # skeleton site file from IFC
    hvx brick export --site site.yaml -o model.ttl           # Brick 1.4 model
    hvx check  --site site.yaml                              # validate config + source connectivity
    hvx serve                                                # FastAPI backend (extra: api)
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__

SEASONS = click.Choice(["winter", "summer", "all_year"])


def _load_site(path: str):
    from hvx.live import load_site

    try:
        return load_site(path)
    except Exception as exc:
        raise click.ClickException(f"Cannot read site file {path}: {exc}") from exc


def _monitor(site, days: float, interval: str, config=None):
    from hvx.live import LiveMonitor

    try:
        sources = site.build_sources()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    return LiveMonitor(
        *site.entities,
        sources=sources,
        window=timedelta(days=days),
        interval=interval,
        timezone=site.timezone,
        config=config,
    )


@click.group()
@click.version_option(__version__, prog_name="hvx")
@click.option("-v", "--verbose", count=True, help="-v for info, -vv for debug logging.")
def cli(verbose: int) -> None:
    """HVX indoor environmental quality analytics."""
    logging.basicConfig(level=[logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)], format="%(levelname)s %(name)s: %(message)s")


@cli.command()
@click.option("--site", "site_path", type=click.Path(exists=True, dir_okay=False), help="Site YAML with live sources.")
@click.option("--csv", "csv_path", type=click.Path(exists=True), help="CSV folder (connectors.csv layouts).")
@click.option("-o", "--output", type=click.Path(dir_okay=False), required=True, help="Output file; format from extension (.html/.json/.csv).")
@click.option("--days", type=float, default=14.0, show_default=True, help="Live window length (with --site).")
@click.option("--interval", default="15min", show_default=True, help="Resampling interval for live data.")
@click.option("--season", "seasons", type=SEASONS, multiple=True, help="Repeat for full year: --season winter --season summer.")
@click.option("--target", "target_category", type=click.Choice(["I", "II", "III", "IV"]), default="II", show_default=True)
@click.option("--title", default=None)
@click.option("--workers", type=int, default=None, help="Parallel workers (default: auto).")
@click.option("--no-simulations", is_flag=True, help="Skip ventilation/correlation/scenario models (faster).")
def report(site_path, csv_path, output, days, interval, seasons, target_category, title, workers, no_simulations) -> None:
    """Build an IEQ report."""
    from hvx.reporting import ReportBuilder, ReportConfig, write

    if bool(site_path) == bool(csv_path):
        raise click.UsageError("Give exactly one of --site or --csv.")
    config = ReportConfig(
        title=title,
        seasons=tuple(seasons) or ("winter",),
        target_category=target_category,
        max_workers=workers,
        include_simulations=not no_simulations,
    )
    if site_path:
        site = _load_site(site_path)
        monitor = _monitor(site, days, interval, config)
        click.echo(f"Fetching {days:g} days of data for {len(monitor.bindings)} points…", err=True)
        n = monitor.refresh()
        click.echo(f"{n} samples received.", err=True)
        rep = monitor.report(config)
    else:
        from hvx.connectors.csv import load_portfolio

        loaded = load_portfolio(csv_path)
        if loaded.portfolio is None:
            raise click.ClickException("No portfolio found in the CSV folder.")
        rep = ReportBuilder(config).build(loaded.portfolio, loaded.buildings, loaded.floors, loaded.rooms)
    path = write(rep, output)
    s = rep.summary
    click.echo(
        f"Wrote {path}  ({s.rooms_analysed}/{s.rooms_total} rooms, category {s.category or '–'}, "
        f"IEQ score {s.ieq_score if s.ieq_score is not None else '–'}, {rep.duration_s}s)"
    )


def _fmt(value: Optional[float], digits: int = 0) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _print_snapshot(snapshot) -> None:
    click.echo(f"\n{snapshot.generated_at}  season={snapshot.season}")
    click.echo(f"{'Room':<28}{'Now':>5}{'Temp':>8}{'CO2':>7}{'RH':>6}{'Window':>8}{'Score':>7}")
    for state in snapshot.rooms.values():
        cur = state.current
        win = state.window
        click.echo(
            f"{state.room_name[:27]:<28}{state.category_now or '–':>5}"
            f"{_fmt(cur['temperature'].value, 1) if 'temperature' in cur else '–':>8}"
            f"{_fmt(cur['co2'].value) if 'co2' in cur else '–':>7}"
            f"{_fmt(cur['humidity'].value) if 'humidity' in cur else '–':>6}"
            f"{(win.achieved_category if win else None) or '–':>8}"
            f"{_fmt(win.ieq_score if win else None, 1):>7}"
        )
    for alert in snapshot.alerts:
        click.secho(f"  ! {alert}", fg="yellow")


@cli.command()
@click.option("--site", "site_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--days", type=float, default=1.0, show_default=True, help="Rolling assessment window.")
@click.option("--every", type=int, default=300, show_default=True, help="Seconds between refreshes.")
@click.option("--once", is_flag=True, help="Refresh once, print, exit.")
def watch(site_path, days, every, once) -> None:
    """Show live IEQ status, refreshing periodically."""
    site = _load_site(site_path)
    monitor = _monitor(site, days, "5min")
    while True:
        monitor.refresh()
        _print_snapshot(monitor.snapshot())
        if once:
            return
        time.sleep(every)


@cli.command()
@click.option("--site", "site_path", type=click.Path(exists=True, dir_okay=False), required=True)
def check(site_path) -> None:
    """Validate a site file and test source connectivity."""
    from hvx.live import HomeAssistantSource, discover_bindings

    site = _load_site(site_path)
    bindings = discover_bindings(site.rooms.values())
    click.echo(f"{len(site.buildings)} building(s), {len(site.floors)} floor(s), {len(site.rooms)} room(s), {len(bindings)} bound point(s).")
    unbound = [r.name for r in site.rooms.values() if not r.sensor_groups]
    if unbound:
        click.secho(f"Rooms without sensors: {', '.join(unbound)}", fg="yellow")
    ok = True
    for name, source in site.build_sources().items():
        if isinstance(source, HomeAssistantSource):
            try:
                click.echo(f"[{name}] Home Assistant: {source.check()}")
                points = [b.point for b in bindings if b.source == name]
                latest = source.latest(points)
                for p in points:
                    reading = latest.get(p)
                    click.echo(f"  {'✓' if reading else '✗'} {p}" + (f" = {reading.value:g}" if reading else " (missing or non-numeric)"))
                    ok &= reading is not None
            except Exception as exc:
                ok = False
                click.secho(f"[{name}] {exc}", fg="red")
    sys.exit(0 if ok else 1)


@cli.group()
def site() -> None:
    """Site file helpers."""


@site.command("from-ifc")
@click.argument("ifc_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write YAML here (default: stdout).")
def site_from_ifc(ifc_path, output) -> None:
    """Create a site-file skeleton from an IFC model (fill in the sensor ids)."""
    import yaml

    from hvx.core.semantics.ifc import load_ifc
    from hvx.live import site_skeleton

    try:
        result = load_ifc(ifc_path)
    except ImportError as exc:
        raise click.ClickException(f"{exc}  →  pip install 'hvx[ifc]'") from exc
    text = yaml.safe_dump(site_skeleton(result.portfolio, result.buildings, result.floors, result.rooms), sort_keys=False, allow_unicode=True)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Wrote {output} ({len(result.rooms)} rooms). Fill in the sensor entity ids.", err=True)
    else:
        click.echo(text)


@cli.group()
def brick() -> None:
    """Brick Schema export."""


@brick.command("export")
@click.option("--site", "site_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("-o", "--output", type=click.Path(dir_okay=False), required=True)
def brick_export(site_path, output) -> None:
    """Export the site as a Brick 1.4 model (Turtle)."""
    from hvx.core.semantics.brick import export_brick

    s = _load_site(site_path)
    try:
        export_brick(*s.entities, destination=output)
    except ImportError as exc:
        raise click.ClickException(f"{exc}  →  pip install 'hvx[brick]'") from exc
    click.echo(f"Wrote {output}")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve(host: str, port: int) -> None:
    """Run the HTTP API (requires the 'api' extra)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("pip install 'hvx[api]' to run the API server") from exc
    uvicorn.run("hvx.app.api:app", host=host, port=port)


def main(argv: Optional[Tuple[str, ...]] = None) -> None:  # pragma: no cover
    cli(args=argv)


if __name__ == "__main__":  # pragma: no cover
    main()
