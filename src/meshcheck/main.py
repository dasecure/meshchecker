#!/usr/bin/env python3
"""
Mesh Network Performance Checker by DASecure
TUI app to measure and analyze mesh network performance
"""

import subprocess
import socket
import statistics
import time
import json
import os
import sys
import re
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
    from rich.layout import Layout
    from rich.live import Live
except ImportError:
    print("Installing rich...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich"], check=True)
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
    from rich.layout import Layout
    from rich.live import Live

console = Console()

# Config file location
CONFIG_DIR = Path.home() / ".meshcheck"
CONFIG_FILE = CONFIG_DIR / "config.json"
RESULTS_DIR = CONFIG_DIR / "results"


@dataclass
class MeshNode:
    """Represents a mesh network node"""
    name: str
    ip: str
    is_main: bool = False
    hop_count: int = 0
    
    def __hash__(self):
        return hash(self.ip)


@dataclass
class NodeTestResult:
    """Test results for a single node"""
    node: str
    ip: str
    reachable: bool
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss: Optional[float] = None
    throughput_mbps: Optional[float] = None
    signal_strength: Optional[int] = None
    error: Optional[str] = None


@dataclass
class MeshTestResult:
    """Complete mesh network test results"""
    timestamp: str
    main_node: str
    nodes: List[NodeTestResult]
    internet_download: Optional[float] = None
    internet_upload: Optional[float] = None
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        reachable = [n for n in self.nodes if n.reachable]
        if not reachable:
            return {"reachable": 0, "total": len(self.nodes)}
        
        latencies = [n.latency_ms for n in reachable if n.latency_ms]
        throughputs = [n.throughput_mbps for n in reachable if n.throughput_mbps]
        
        return {
            "reachable": len(reachable),
            "total": len(self.nodes),
            "avg_latency": statistics.mean(latencies) if latencies else None,
            "max_latency": max(latencies) if latencies else None,
            "avg_throughput": statistics.mean(throughputs) if throughputs else None,
            "min_throughput": min(throughputs) if throughputs else None,
        }


class MeshChecker:
    """Main mesh network checker class"""
    
    def __init__(self):
        self.nodes: List[MeshNode] = []
        self.results: List[MeshTestResult] = []
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    config = json.load(f)
                    self.nodes = [MeshNode(**n) for n in config.get("nodes", [])]
            except Exception:
                pass
    
    def _save_config(self):
        """Save configuration to file"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "nodes": [asdict(n) for n in self.nodes]
            }, f, indent=2)
    
    def add_node(self, name: str, ip: str, is_main: bool = False, hop_count: int = 0):
        """Add a mesh node to test"""
        node = MeshNode(name=name, ip=ip, is_main=is_main, hop_count=hop_count)
        if node not in self.nodes:
            self.nodes.append(node)
            self._save_config()
    
    def remove_node(self, ip: str):
        """Remove a node by IP"""
        self.nodes = [n for n in self.nodes if n.ip != ip]
        self._save_config()
    
    def clear_nodes(self):
        """Clear all nodes"""
        self.nodes = []
        self._save_config()
    
    def tcp_latency_test(self, host: str, port: int = 443, count: int = 5) -> Tuple[Optional[float], Optional[float], float]:
        """Test latency using TCP connection"""
        times = []
        failures = 0
        
        for _ in range(count):
            try:
                start = time.time()
                sock = socket.create_connection((host, port), timeout=3)
                end = time.time()
                sock.close()
                times.append((end - start) * 1000)
            except Exception:
                failures += 1
            time.sleep(0.1)
        
        if not times:
            return None, None, 100.0
        
        latency = statistics.mean(times)
        jitter = statistics.stdev(times) if len(times) > 1 else 0
        packet_loss = (failures / count) * 100
        
        return latency, jitter, packet_loss
    
    def iperf3_test(self, server_ip: str, duration: int = 5) -> Optional[float]:
        """Run iperf3 throughput test (requires iperf3 installed)"""
        try:
            # Try to run iperf3 client
            result = subprocess.run(
                ["iperf3", "-c", server_ip, "-t", str(duration), "-f", "m"],
                capture_output=True,
                text=True,
                timeout=duration + 10
            )
            
            # Parse receiver bitrate (download from server perspective)
            # Looking for lines like: [  5]   0.00-5.00   sec  xxx MBytes  xxx Mbits/sec  receiver
            match = re.search(r'(\d+\.?\d*)\s+Mbits/sec\s+receiver', result.stdout)
            if match:
                return float(match.group(1))
            
            # Fallback: look for any Mbits/sec
            matches = re.findall(r'(\d+\.?\d*)\s+Mbits/sec', result.stdout)
            if matches:
                return float(matches[-1])
            
            return None
        except FileNotFoundError:
            return None
        except Exception:
            return None
    
    def check_iperf3_available(self) -> bool:
        """Check if iperf3 is installed"""
        try:
            subprocess.run(["iperf3", "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def get_local_ip(self) -> Optional[str]:
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None
    
    def scan_network(self, base_ip: str = None) -> List[Dict]:
        """Scan local network for potential mesh nodes"""
        local_ip = base_ip or self.get_local_ip()
        if not local_ip:
            return []
        
        # Get network base (assume /24)
        parts = local_ip.split(".")
        base = ".".join(parts[:3])
        
        found = []
        console.print(f"[dim]Scanning {base}.0/24 for hosts...[/dim]")
        
        # Quick ping sweep
        def check_host(i):
            ip = f"{base}.{i}"
            try:
                # TCP ping to common ports
                for port in [80, 443, 22]:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(0.3)
                        result = sock.connect_ex((ip, port))
                        sock.close()
                        if result == 0:
                            # Try to get hostname
                            try:
                                hostname = socket.gethostbyaddr(ip)[0]
                            except:
                                hostname = None
                            return {"ip": ip, "hostname": hostname}
                    except:
                        pass
            except:
                pass
            return None
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(check_host, i) for i in range(1, 255)]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found.append(result)
        
        return found
    
    def test_node(self, node: MeshNode, run_throughput: bool = False) -> NodeTestResult:
        """Test a single mesh node"""
        result = NodeTestResult(node=node.name, ip=node.ip, reachable=False)
        
        # Latency test
        latency, jitter, packet_loss = self.tcp_latency_test(node.ip)
        
        if latency is None:
            result.error = "Node unreachable"
            return result
        
        result.reachable = True
        result.latency_ms = round(latency, 1)
        result.jitter_ms = round(jitter, 1)
        result.packet_loss = round(packet_loss, 1)
        
        # Throughput test (optional, requires iperf3 server on node)
        if run_throughput and self.check_iperf3_available():
            throughput = self.iperf3_test(node.ip, duration=3)
            if throughput:
                result.throughput_mbps = round(throughput, 1)
        
        return result
    
    def run_full_test(self, run_throughput: bool = False, internet_test: bool = True) -> MeshTestResult:
        """Run full mesh network test"""
        if not self.nodes:
            raise ValueError("No nodes configured. Add nodes first.")
        
        main_node = next((n.name for n in self.nodes if n.is_main), self.nodes[0].name if self.nodes else "Unknown")
        
        results = MeshTestResult(
            timestamp=datetime.now().isoformat(),
            main_node=main_node,
            nodes=[]
        )
        
        # Test each node
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Testing mesh nodes...", total=len(self.nodes))
            
            for node in self.nodes:
                progress.update(task, description=f"Testing {node.name} ({node.ip})...")
                node_result = self.test_node(node, run_throughput)
                results.nodes.append(node_result)
                progress.advance(task)
        
        # Internet speed test (optional)
        if internet_test:
            try:
                import speedtest
                st = speedtest.Speedtest()
                st.get_best_server()
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                ) as progress:
                    progress.add_task("Testing internet speed...", total=None)
                    results.internet_download = round(st.download() / 1_000_000, 1)
                    results.internet_upload = round(st.upload() / 1_000_000, 1)
            except:
                pass
        
        # Save results
        self._save_result(results)
        
        return results
    
    def _save_result(self, result: MeshTestResult):
        """Save test result to file"""
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = RESULTS_DIR / filename
        
        # Convert to dict for JSON serialization
        data = {
            "timestamp": result.timestamp,
            "main_node": result.main_node,
            "internet_download": result.internet_download,
            "internet_upload": result.internet_upload,
            "nodes": [
                {
                    "node": n.node,
                    "ip": n.ip,
                    "reachable": n.reachable,
                    "latency_ms": n.latency_ms,
                    "jitter_ms": n.jitter_ms,
                    "packet_loss": n.packet_loss,
                    "throughput_mbps": n.throughput_mbps,
                    "error": n.error
                }
                for n in result.nodes
            ]
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_historical_results(self, limit: int = 10) -> List[Dict]:
        """Get historical test results"""
        if not RESULTS_DIR.exists():
            return []
        
        results = []
        files = sorted(RESULTS_DIR.glob("result_*.json"), reverse=True)[:limit]
        
        for f in files:
            try:
                with open(f) as fp:
                    results.append(json.load(fp))
            except:
                pass
        
        return results


def format_status(value: Optional[float], good_threshold: float, bad_threshold: float, 
                  unit: str = "", reverse: bool = False) -> str:
    """Format a value with color based on thresholds"""
    if value is None:
        return "[dim]N/A[/dim]"
    
    if reverse:
        good = value <= good_threshold
        bad = value >= bad_threshold
    else:
        good = value >= good_threshold
        bad = value <= bad_threshold
    
    if good:
        return f"[green]{value:.1f}{unit}[/green] ✓"
    elif bad:
        return f"[red]{value:.1f}{unit}[/red] ✗"
    else:
        return f"[yellow]{value:.1f}{unit}[/yellow] ~"


def display_results(result: MeshTestResult):
    """Display test results in a nice TUI"""
    console.clear()
    
    # Header
    console.print(Panel.fit(
        "[bold cyan]📡 Mesh Network Performance Checker[/bold cyan]\n"
        "[dim]by DASecure[/dim]",
        box=box.ROUNDED
    ))
    console.print()
    
    # Node results table
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Node", style="white", width=15)
    table.add_column("IP", width=15)
    table.add_column("Status", width=10)
    table.add_column("Latency", width=15)
    table.add_column("Jitter", width=12)
    table.add_column("Loss", width=10)
    table.add_column("Throughput", width=15)
    
    for node in result.nodes:
        status = "[green]●[/green] UP" if node.reachable else "[red]●[/red] DOWN"
        latency = format_status(node.latency_ms, 50, 100, " ms", reverse=True) if node.reachable else "[dim]—[/dim]"
        jitter = format_status(node.jitter_ms, 10, 30, " ms", reverse=True) if node.reachable else "[dim]—[/dim]"
        loss = format_status(node.packet_loss, 1, 5, "%", reverse=True) if node.reachable else "[dim]—[/dim]"
        
        if node.throughput_mbps:
            throughput = format_status(node.throughput_mbps, 50, 10, " Mbps")
        elif node.reachable:
            throughput = "[dim]N/A[/dim]"
        else:
            throughput = "[dim]—[/dim]"
        
        table.add_row(node.node, node.ip, status, latency, jitter, loss, throughput)
    
    console.print(table)
    console.print()
    
    # Summary
    summary = result.get_summary()
    
    summary_table = Table.grid(padding=2)
    summary_table.add_column(style="bold")
    summary_table.add_column()
    
    summary_table.add_row("Nodes Online:", f"[green]{summary['reachable']}[/green] / {summary['total']}")
    
    if summary['avg_latency']:
        summary_table.add_row("Avg Latency:", f"{summary['avg_latency']:.1f} ms")
    if summary['max_latency']:
        summary_table.add_row("Max Latency:", f"{summary['max_latency']:.1f} ms")
    if summary['avg_throughput']:
        summary_table.add_row("Avg Throughput:", f"{summary['avg_throughput']:.1f} Mbps")
    
    if result.internet_download:
        summary_table.add_row("Internet ↓:", f"{result.internet_download:.1f} Mbps")
    if result.internet_upload:
        summary_table.add_row("Internet ↑:", f"{result.internet_upload:.1f} Mbps")
    
    console.print(Panel(summary_table, title="Summary", box=box.ROUNDED))
    console.print()
    
    # Performance assessment
    issues = []
    
    unreachable = [n for n in result.nodes if not n.reachable]
    if unreachable:
        issues.append(f"{len(unreachable)} node(s) unreachable: {', '.join(n.node for n in unreachable)}")
    
    high_latency = [n for n in result.nodes if n.reachable and n.latency_ms and n.latency_ms > 100]
    if high_latency:
        issues.append(f"High latency on: {', '.join(n.node for n in high_latency)}")
    
    high_loss = [n for n in result.nodes if n.reachable and n.packet_loss and n.packet_loss > 1]
    if high_loss:
        issues.append(f"Packet loss on: {', '.join(n.node for n in high_loss)}")
    
    if issues:
        issues_text = "\n".join([f"• {i}" for i in issues])
        console.print(Panel(
            f"[bold yellow]⚠️  Issues Detected[/bold yellow]\n\n{issues_text}",
            box=box.ROUNDED,
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            "[bold green]✅ Mesh Network Healthy[/bold green]\n\nAll nodes responding with good performance.",
            box=box.ROUNDED,
            border_style="green"
        ))
    
    console.print()
    console.print(f"[dim]Tested at {result.timestamp}[/dim]")
    console.print(f"[dim]Results saved to {RESULTS_DIR}[/dim]")


def interactive_setup(checker: MeshChecker):
    """Interactive node setup"""
    console.print(Panel.fit(
        "[bold cyan]📡 Mesh Network Setup[/bold cyan]\n"
        "[dim]Configure your mesh nodes for testing[/dim]",
        box=box.ROUNDED
    ))
    console.print()
    
    if checker.nodes:
        console.print("[bold]Current Nodes:[/bold]")
        for node in checker.nodes:
            main = " [green](Main)[/green]" if node.is_main else ""
            console.print(f"  • {node.name}: {node.ip}{main}")
        console.print()
    
    console.print("[bold]Options:[/bold]")
    console.print("  1. Add node manually")
    console.print("  2. Scan network for nodes")
    console.print("  3. Clear all nodes")
    console.print("  4. Back to main menu")
    console.print()
    
    choice = console.input("[bold]Choice (1-4):[/bold] ").strip()
    
    if choice == "1":
        name = console.input("Node name (e.g., Living Room): ").strip()
        ip = console.input("IP address: ").strip()
        is_main = console.input("Is this the main router? (y/n): ").strip().lower() == 'y'
        
        if name and ip:
            checker.add_node(name, ip, is_main)
            console.print(f"[green]Added node: {name} ({ip})[/green]")
    
    elif choice == "2":
        console.print()
        found = checker.scan_network()
        
        if found:
            console.print(f"\n[bold]Found {len(found)} hosts:[/bold]")
            for i, host in enumerate(found, 1):
                hostname = f" ({host['hostname']})" if host.get('hostname') else ""
                console.print(f"  {i}. {host['ip']}{hostname}")
            
            console.print()
            selection = console.input("Enter numbers to add (comma-separated), or 'all': ").strip()
            
            if selection.lower() == 'all':
                for host in found:
                    checker.add_node(host['ip'], host['ip'])
                console.print(f"[green]Added {len(found)} nodes[/green]")
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(',')]
                    for idx in indices:
                        if 0 <= idx < len(found):
                            host = found[idx]
                            checker.add_node(host['ip'], host['ip'])
                            console.print(f"[green]Added {host['ip']}[/green]")
                except:
                    console.print("[red]Invalid selection[/red]")
        else:
            console.print("[yellow]No hosts found[/yellow]")
    
    elif choice == "3":
        confirm = console.input("Clear all nodes? (y/n): ").strip().lower()
        if confirm == 'y':
            checker.clear_nodes()
            console.print("[green]All nodes cleared[/green]")
    
    console.input("\n[dim]Press Enter to continue...[/dim]")


def show_history(checker: MeshChecker):
    """Show historical test results"""
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]📊 Test History[/bold cyan]",
        box=box.ROUNDED
    ))
    console.print()
    
    results = checker.get_historical_results(20)
    
    if not results:
        console.print("[yellow]No historical results found[/yellow]")
        console.input("\n[dim]Press Enter to continue...[/dim]")
        return
    
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Timestamp", width=20)
    table.add_column("Nodes Up", width=10)
    table.add_column("Avg Latency", width=12)
    table.add_column("Internet ↓", width=12)
    table.add_column("Internet ↑", width=12)
    
    for r in results:
        reachable = sum(1 for n in r.get('nodes', []) if n.get('reachable'))
        total = len(r.get('nodes', []))
        
        latencies = [n.get('latency_ms') for n in r.get('nodes', []) if n.get('latency_ms')]
        avg_lat = f"{sum(latencies)/len(latencies):.1f} ms" if latencies else "N/A"
        
        dl = f"{r.get('internet_download', 'N/A')} Mbps" if r.get('internet_download') else "N/A"
        ul = f"{r.get('internet_upload', 'N/A')} Mbps" if r.get('internet_upload') else "N/A"
        
        table.add_row(
            r.get('timestamp', 'Unknown')[:19],
            f"{reachable}/{total}",
            avg_lat,
            dl,
            ul
        )
    
    console.print(table)
    console.input("\n[dim]Press Enter to continue...[/dim]")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mesh Network Performance Checker by DASecure")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup")
    parser.add_argument("--test", action="store_true", help="Run test immediately")
    parser.add_argument("--throughput", action="store_true", help="Include throughput tests (requires iperf3)")
    parser.add_argument("--no-internet", action="store_true", help="Skip internet speed test")
    parser.add_argument("--history", action="store_true", help="Show test history")
    parser.add_argument("--add-node", nargs=2, metavar=("NAME", "IP"), help="Add a node")
    parser.add_argument("--main", action="store_true", help="Mark added node as main router")
    args = parser.parse_args()
    
    checker = MeshChecker()
    
    # CLI commands
    if args.add_node:
        name, ip = args.add_node
        checker.add_node(name, ip, is_main=args.main)
        console.print(f"[green]Added node: {name} ({ip})[/green]")
        return
    
    if args.history:
        show_history(checker)
        return
    
    if args.setup:
        interactive_setup(checker)
        return
    
    if args.test:
        if not checker.nodes:
            console.print("[red]No nodes configured. Run with --setup first.[/red]")
            return
        
        result = checker.run_full_test(
            run_throughput=args.throughput,
            internet_test=not args.no_internet
        )
        display_results(result)
        return
    
    # Interactive menu
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]📡 Mesh Network Performance Checker[/bold cyan]\n"
            "[dim]by DASecure[/dim]",
            box=box.ROUNDED
        ))
        console.print()
        
        console.print("[bold]Menu:[/bold]")
        console.print("  1. Run full test")
        console.print("  2. Run quick test (no internet speed)")
        console.print("  3. Setup nodes")
        console.print("  4. View history")
        console.print("  5. Exit")
        console.print()
        
        choice = console.input("[bold]Choice (1-5):[/bold] ").strip()
        
        if choice == "1":
            if not checker.nodes:
                console.print("\n[yellow]No nodes configured. Let's set up first.[/yellow]")
                console.input("[dim]Press Enter to continue...[/dim]")
                interactive_setup(checker)
                continue
            
            try:
                result = checker.run_full_test(
                    run_throughput=args.throughput,
                    internet_test=True
                )
                display_results(result)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            console.input("\n[dim]Press Enter to continue...[/dim]")
        
        elif choice == "2":
            if not checker.nodes:
                console.print("\n[yellow]No nodes configured. Let's set up first.[/yellow]")
                console.input("[dim]Press Enter to continue...[/dim]")
                interactive_setup(checker)
                continue
            
            try:
                result = checker.run_full_test(
                    run_throughput=False,
                    internet_test=False
                )
                display_results(result)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            console.input("\n[dim]Press Enter to continue...[/dim]")
        
        elif choice == "3":
            interactive_setup(checker)
        
        elif choice == "4":
            show_history(checker)
        
        elif choice == "5":
            console.print("\n[dim]Goodbye![/dim]")
            break


if __name__ == "__main__":
    main()
