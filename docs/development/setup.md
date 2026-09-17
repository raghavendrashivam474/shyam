# Development Environment Setup

This document guides you through setting up a clean, reproducible local development environment for Shyam.

---

## 1. Prerequisites

* **Python:** Version `3.13` or higher is required.
* **Git:** Version `2.40+` installed and configured.
* **Virtual Environment Tool:** `uv` (recommended) or standard `venv`.

Verify your local Python version:
```bash
python --version
```
## 2. Setting Up Virtual Environment
### Using uv (Fastest)
```Bash
# Create venv with Python 3.13
uv venv --python 3.13

# Activate environment
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install editable package with dev dependencies
uv pip install -e ".[dev]"
```

### Using Standard Python venv
```Bash
# Create venv
python -m venv .venv

# Activate environment
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Upgrade pip and install editable package
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## 3. Running Validation & Tests

>Even though S0 contains no runtime engines, you can verify the test runner:

```Bash
pytest
```
>Run code formatting and linting checks:

```Bash
ruff check .
```

## 4. Troubleshooting

- **PowerShell Execution Policy Error**:
  If you cannot activate .venv\Scripts\Activate.ps1, run:

```PowerShell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- **Python Version Mismatch**:
  Ensure your active shell points to a Python >= 3.13 binary.
