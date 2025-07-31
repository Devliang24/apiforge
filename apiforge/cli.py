"""
Command-line interface for APIForge.

This module provides the CLI entry point for the installed package.
"""

import asyncio
import sys
import subprocess
import signal
import time
import threading
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

from apiforge import __version__
from apiforge.config import settings
from apiforge.logger import get_logger, setup_logger
from apiforge.generation.orchestrator import OrchestratorError, run_generation
from apiforge.scheduling.models import ExecutionMode

# Initialize console for rich output
console = Console()
logger = get_logger(__name__)


def setup_cli_logging(verbose: bool = False) -> None:
    """Setup logging for CLI usage."""
    if verbose:
        level = "DEBUG"
        log_format = "simple"
    else:
        level = "INFO"
        log_format = settings.log_format
    
    setup_logger(level=level, log_format=log_format)


@click.group()
def cli():
    """APIForge - Enterprise-grade API test case generator."""
    pass


@cli.command()
@click.option("--url", "-u", required=True, help="URL of the OpenAPI/Swagger specification")
@click.option("--output", "-o", required=True, help="Output file path (.json or .csv)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--provider", "-p", default=None, help="LLM provider to use (default: from config)")
@click.option("--mode", "-m", type=click.Choice(['auto', 'fast', 'smart', 'ai-analysis']), 
              default='auto', help="Execution mode")
@click.option("--intermediate", "-i", is_flag=True, help="Save intermediate files")
@click.option("--intermediate-dir", default="intermediate_output", help="Directory for intermediate files")
@click.option("--monitor", "-M", is_flag=True, help="Enable real-time monitoring dashboard")
def generate(url: str, output: str, verbose: bool, provider: str, mode: str, 
             intermediate: bool, intermediate_dir: str, monitor: bool) -> None:
    """Generate test cases from an OpenAPI specification."""
    setup_cli_logging(verbose)
    
    # Show configuration
    console.print(Panel(
        f"[bold cyan]APIForge Test Case Generator[/bold cyan]\n"
        f"Version: {__version__}\n"
        f"Provider: {provider or settings.llm_provider}\n"
        f"Mode: {mode}",
        title="Configuration",
        border_style="cyan"
    ))
    
    # Start monitoring dashboard if requested
    monitor_process = None
    if monitor:
        try:
            monitor_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "apiforge.web.app:app", "--host", "0.0.0.0", "--port", "9099"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            console.print("[yellow]Starting monitoring dashboard...[/yellow]")
            time.sleep(2)
            
            if monitor_process.poll() is None:
                console.print("[green]✓ Monitoring dashboard started![/green]")
                console.print("  Dashboard: http://localhost:9099")
            else:
                console.print("[red]Failed to start monitoring dashboard[/red]")
                monitor_process = None
        except Exception as e:
            console.print(f"[red]Error starting monitoring dashboard: {e}[/red]")
            monitor_process = None
    
    try:
        # Run generation
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Generating test cases...", total=None)
            
            async def run_with_progress():
                try:
                    await run_generation(
                        url=url,
                        output_path=output,
                        provider=provider,
                        mode=ExecutionMode(mode),
                        save_intermediate=intermediate,
                        intermediate_dir=intermediate_dir
                    )
                except OrchestratorError as e:
                    console.print(f"[red]Error: {e}[/red]")
                    sys.exit(1)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Generation interrupted by user[/yellow]")
                    sys.exit(0)
                except Exception as e:
                    console.print(f"[red]Unexpected error: {e}[/red]")
                    logger.exception("Unexpected error during generation")
                    sys.exit(1)
            
            asyncio.run(run_with_progress())
            progress.update(task, completed=True)
        
        console.print(f"[green]✓ Test cases generated successfully![/green]")
        console.print(f"  Output: {output}")
        
        # Keep running if monitor is active
        if monitor_process and monitor_process.poll() is None:
            console.print("\n[cyan]Monitoring dashboard is running. Press Ctrl+C to stop.[/cyan]")
            try:
                while monitor_process.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping monitoring dashboard...[/yellow]")
    
    finally:
        # Cleanup monitoring dashboard
        if monitor_process:
            try:
                monitor_process.terminate()
                monitor_process.wait(timeout=5)
                console.print("[green]✓ Monitoring dashboard stopped[/green]")
            except subprocess.TimeoutExpired:
                monitor_process.kill()


@cli.command()
def dashboard():
    """Start the monitoring dashboard."""
    try:
        import uvicorn
        from apiforge.web.app import app
    except ImportError:
        console.print("[red]Error: Web dependencies not installed[/red]")
        console.print("Install with: pip install apiforge[web]")
        sys.exit(1)
    
    console.print("🚀 Starting APIForge monitoring dashboard...")
    console.print("📊 Dashboard: http://localhost:9099")
    console.print("📈 Real-time Monitor: http://localhost:9099/monitor")
    console.print("📉 Statistics: http://localhost:9099/statistics")
    console.print("\nPress Ctrl+C to stop the dashboard")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=9099, reload=False, access_log=False)
    except KeyboardInterrupt:
        console.print("\n[green]✓ Monitoring dashboard stopped[/green]")


@cli.command()
def version():
    """Show version information."""
    console.print(f"APIForge version {__version__}")


@cli.command()
def info():
    """Show system information."""
    table = Table(title="APIForge System Information", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Version", __version__)
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Provider", settings.llm_provider)
    table.add_row("Execution Mode", settings.execution_mode)
    table.add_row("Max Concurrent", str(settings.max_concurrent_requests))
    table.add_row("Rate Limit", f"{settings.rate_limit_per_minute}/min")
    
    console.print(table)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()