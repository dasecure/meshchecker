# Mesh Network Performance Checker 📡

**By DASecure**

A TUI app to measure and analyze mesh network performance.

## Features

- ✅ **Multi-Node Testing** — Test all mesh nodes from one place
- ✅ **Latency & Jitter** — Measure response time and stability
- ✅ **Packet Loss Detection** — Identify connection issues
- ✅ **Throughput Testing** — Optional iperf3 integration
- ✅ **Network Scanning** — Auto-discover nodes
- ✅ **Internet Speed Test** — Check WAN performance
- ✅ **Historical Results** — Track performance over time
- ✅ **Interactive TUI** — Easy-to-use interface

## Installation

### pip (Recommended)

```bash
pip install meshcheck
meshcheck
```

### pipx

```bash
pipx install meshcheck
meshcheck
```

### From Source

```bash
git clone https://github.com/dasecure/meshcheck.git
cd meshcheck
pip install -e .
meshcheck
```

## Quick Start

```bash
# Interactive mode (recommended)
meshcheck

# Quick setup
meshcheck --setup

# Run test immediately
meshcheck --test

# Include throughput tests (requires iperf3)
meshcheck --test --throughput
```

## Adding Nodes

### Interactive Setup
```bash
meshcheck --setup
```

### CLI
```bash
# Add a node
meshcheck --add-node "Living Room" 192.168.1.10

# Add main router
meshcheck --add-node "Main Router" 192.168.1.1 --main
```

## Usage

### Interactive Menu
```
meshcheck
```

Then choose:
1. **Run full test** — Tests all nodes + internet speed
2. **Run quick test** — Tests nodes only (faster)
3. **Setup nodes** — Add/remove nodes
4. **View history** — See past results
5. **Exit**

### Command Line Options

```bash
# Run full test
meshcheck --test

# Quick test (no internet speed test)
meshcheck --test --no-internet

# With throughput testing (requires iperf3 on nodes)
meshcheck --test --throughput

# View history
meshcheck --history
```

## Throughput Testing

For throughput tests, install iperf3 on your mesh nodes:

**macOS:**
```bash
brew install iperf3
```

**Linux:**
```bash
sudo apt install iperf3
```

**Windows:**
Download from https://iperf.fr/

Then run iperf3 server on each node:
```bash
iperf3 -s
```

## Metrics Explained

| Metric | Good | Warning | Poor |
|--------|------|---------|------|
| Latency | < 50ms | 50-100ms | > 100ms |
| Jitter | < 10ms | 10-30ms | > 30ms |
| Packet Loss | < 1% | 1-5% | > 5% |
| Throughput | > 50 Mbps | 10-50 Mbps | < 10 Mbps |

## Results Storage

Results are saved to:
- **macOS/Linux:** `~/.meshcheck/results/`
- **Windows:** `%USERPROFILE%\.meshcheck\results\`

Each test creates a JSON file with full details.

## Troubleshooting

**"No nodes configured"**
Run `meshcheck --setup` or add nodes with `--add-node`

**"Node unreachable"**
- Check IP address is correct
- Ensure node is powered on
- Verify you're on the same network

**Throughput shows "N/A"**
- Install iperf3 on the target node
- Run `iperf3 -s` on the node before testing

## License

MIT © DASecure

## Links

- **GitHub:** https://github.com/dasecure/meshcheck
- **PyPI:** https://pypi.org/project/meshcheck/
- **DASecure:** https://github.com/dasecure
