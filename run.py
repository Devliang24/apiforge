"""
Command-line interface for APIForge.

This script provides a simple CLI entry point for generating API test cases
from OpenAPI specifications.
"""

import asyncio
import sys
from pathlib import Path
import subprocess
import signal
import time
import threading

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

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
        log_format = "simple"  # More readable for CLI
    else:
        level = "INFO"
        log_format = settings.log_format
    
    setup_logger(level=level, log_format=log_format)


@click.command()
@click.option(
    "--url",
    "-u",
    required=True,
    help="URL of the OpenAPI/Swagger specification"
)
@click.option(
    "--output",
    "-o",
    required=True,
    help="Output file path for the generated test suite (.json or .csv)"
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging"
)
@click.option(
    "--provider",
    "-p",
    default=None,
    help=f"LLM provider to use (default: {settings.llm_provider})"
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["auto", "fast", "smart", "ai-analysis"], case_sensitive=False),
    default="auto",
    help="Execution mode: auto (intelligent progressive), fast (maximum concurrency), smart (dynamic scheduling), ai-analysis (AI-powered deep analysis)"
)
@click.option(
    "--intermediate",
    "-i",
    is_flag=True,
    help="Save intermediate files for each processing step"
)
@click.option(
    "--intermediate-dir",
    "-d",
    default=None,
    help="Directory for intermediate files (default: <output>_intermediate/)"
)
@click.option(
    "--monitor",
    "-M",
    is_flag=True,
    help="Enable real-time monitoring dashboard"
)
@click.version_option(version="0.1.0", prog_name="APIForge")
def main(url: str, output: str, verbose: bool, provider: str, mode: str, intermediate: bool, intermediate_dir: str, monitor: bool) -> None:
    """
    Generate comprehensive API test cases from OpenAPI specifications.
    
    APIForge automatically analyzes your OpenAPI/Swagger specification
    and generates structured test cases covering positive, negative, and
    boundary scenarios using Large Language Models.
    
    Examples:
        python run.py --url https://petstore.swagger.io/v2/swagger.json --output tests.json
        python run.py --url https://api.example.com/spec.json --output tests.csv
        python run.py --url https://api.example.com/spec.json --output tests.json --intermediate
        python run.py --url https://api.example.com/spec.json --output tests.json --provider qwen
    """
    # Setup logging
    setup_cli_logging(verbose)
    
    # Display header
    console.print()
    console.print(Panel.fit(
        "[bold blue]APIForge[/bold blue]\n"
        "Enterprise-grade API test case generator",
        border_style="blue"
    ))
    console.print()
    
    # Start monitoring dashboard if requested
    monitor_process = None
    if monitor:
        try:
            # Start monitoring dashboard in a subprocess
            monitor_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "apiforge.web.app:app", "--host", "0.0.0.0", "--port", "9099"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            console.print("[yellow]Starting monitoring dashboard...[/yellow]")
            time.sleep(2)  # Give it time to start
            
            # Check if process is running
            if monitor_process.poll() is None:
                console.print("[green]✓ Monitoring dashboard started successfully![/green]")
                console.print("  Dashboard: http://localhost:9099")
                console.print("  Monitor: http://localhost:9099/monitor")
                console.print("  Statistics: http://localhost:9099/statistics")
                console.print()
            else:
                console.print("[red]Failed to start monitoring dashboard[/red]")
                monitor_process = None
        except Exception as e:
            console.print(f"[red]Error starting monitoring dashboard: {e}[/red]")
            monitor_process = None
    
    # Validate inputs
    if not url.startswith(("http://", "https://")):
        console.print("[red]Error: URL must start with http:// or https://[/red]")
        sys.exit(1)
    
    # Ensure output directory exists
    output_path = Path(output)
    if not output_path.suffix:
        output_path = output_path / "test_suite.json"
    
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        console.print(f"[red]Error creating output directory: {e}[/red]")
        sys.exit(1)
    
    # Override provider if specified
    if provider:
        settings.llm_provider = provider
    
    # Convert mode string to ExecutionMode enum
    execution_mode = ExecutionMode(mode)
    
    # Display configuration summary
    config_table = Table(show_header=False, box=None)
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")
    
    config_table.add_row("OpenAPI URL", url)
    config_table.add_row("Output File", str(output_path.absolute()))
    config_table.add_row("LLM Provider", settings.llm_provider)
    config_table.add_row("LLM Model", settings.openai_model)
    config_table.add_row("Execution Mode", f"{execution_mode.value} ({execution_mode.name})")
    config_table.add_row("Max Concurrent", str(settings.max_concurrent_requests))
    config_table.add_row("Intermediate Files", "Enabled" if intermediate else "Disabled")
    if intermediate and intermediate_dir:
        config_table.add_row("Intermediate Dir", intermediate_dir)
    
    console.print(Panel(config_table, title="Configuration", border_style="green"))
    console.print()
    
    # Run the generation workflow
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("Generating test cases...", total=None)
            
            # Run async workflow
            asyncio.run(run_generation(url, str(output_path), intermediate, intermediate_dir, execution_mode))
            
            progress.update(task, description="[green]✓ Test cases generated successfully!")
        
        # Display success message
        console.print()
        success_message = (
            f"[green]✓ Test suite generated successfully![/green]\n\n"
            f"Output file: [bold]{output_path.absolute()}[/bold]\n"
        )
        
        if intermediate:
            intermediate_path = Path(intermediate_dir) if intermediate_dir else output_path.parent / f"{output_path.stem}_intermediate"
            success_message += f"Intermediate files: [bold]{intermediate_path.absolute()}[/bold]\n"
        
        success_message += f"You can now use the generated test cases with your preferred testing framework."
        
        console.print(Panel(
            success_message,
            title="Success",
            border_style="green"
        ))
        
        # If monitoring dashboard was started, inform user to access it
        if monitor_process and monitor_process.poll() is None:
            console.print()
            console.print("[cyan]Monitoring dashboard is still running. Access it at:[/cyan]")
            console.print("  Dashboard: http://localhost:9099")
            console.print("  Press Ctrl+C to stop the monitoring dashboard")
            
            try:
                # Keep the process running if monitoring dashboard is active
                while monitor_process.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping monitoring dashboard...[/yellow]")
        
    except OrchestratorError as e:
        console.print()
        console.print(Panel(
            f"[red]Generation failed:[/red]\n{str(e)}\n\n"
            f"Please check your OpenAPI specification URL and configuration.",
            title="Error",
            border_style="red"
        ))
        logger.error(f"Test generation failed: {str(e)}")
        sys.exit(1)
        
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Generation cancelled by user[/yellow]")
        sys.exit(1)
        
    except Exception as e:
        console.print()
        console.print(Panel(
            f"[red]Unexpected error:[/red]\n{str(e)}\n\n"
            f"Please report this issue if it persists.",
            title="Unexpected Error",
            border_style="red"
        ))
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Cleanup monitoring dashboard process if it was started
        if monitor_process:
            try:
                monitor_process.terminate()
                monitor_process.wait(timeout=5)
                console.print("[green]✓ Monitoring dashboard stopped[/green]")
            except:
                # Force kill if terminate doesn't work
                try:
                    monitor_process.kill()
                except:
                    pass


@click.command()
def info() -> None:
    """Display information about APIForge and available providers."""
    from apiforge.generation.generator import TestCaseGenerator
    
    console.print()
    console.print(Panel.fit(
        "[bold blue]APIForge Information[/bold blue]",
        border_style="blue"
    ))
    console.print()
    
    # System info
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Property", style="cyan")
    info_table.add_column("Value", style="white")
    
    info_table.add_row("Version", "0.1.0")
    info_table.add_row("Python Version", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    console.print(Panel(info_table, title="System Information", border_style="green"))
    console.print()
    
    # Available providers
    providers = TestCaseGenerator.get_available_providers()
    provider_table = Table(show_header=True)
    provider_table.add_column("Provider", style="cyan")
    provider_table.add_column("Status", style="white")
    
    for provider_name in providers:
        try:
            generator = TestCaseGenerator(provider_name)
            generator.provider.validate_configuration()
            status = "[green]✓ Available[/green]"
        except Exception as e:
            status = f"[red]✗ {str(e)}[/red]"
        
        provider_table.add_row(provider_name, status)
    
    console.print(Panel(provider_table, title="Available LLM Providers", border_style="yellow"))
    console.print()


@click.command()
def dashboard() -> None:
    """Start the APIForge monitoring dashboard."""
    import uvicorn
    from apiforge.web.app import app
    
    console.print()
    console.print(Panel.fit(
        "[bold blue]APIForge Monitoring Dashboard[/bold blue]",
        border_style="blue"
    ))
    console.print()
    console.print("🚀 Starting APIForge monitoring dashboard...")
    console.print("📊 Dashboard: http://localhost:9099")
    console.print("📈 Real-time Monitor: http://localhost:9099/monitor")
    console.print("📉 Statistics: http://localhost:9099/statistics")
    console.print("\n[yellow]Press Ctrl+C to stop[/yellow]\n")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=9099, reload=False, access_log=False)
    except KeyboardInterrupt:
        console.print("\n[green]✓ Monitoring dashboard stopped[/green]")


@click.group()
def cli() -> None:
    """APIForge command-line interface."""
    pass


# Add commands to the CLI group
cli.add_command(main, name="generate")
cli.add_command(info)
cli.add_command(dashboard)


def main_entry_point():
    """Entry point for the installed package."""
    cli()


if __name__ == "__main__":
    # If called directly, run the main generate command
    main()