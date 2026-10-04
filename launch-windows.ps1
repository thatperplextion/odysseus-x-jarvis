#Requires -Version 5.1
<#
  Odysseus - native Windows launcher (no Docker).

  One command to: create a virtualenv, install dependencies, run first-time
  setup (prints an admin password on first run), and start the server.
  Safe to re-run - it skips whatever already exists.

  Usage:
    powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1
    powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1 -Port 7000 -BindHost 127.0.0.1
    powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1 -Quick        (or double-click "Start Odysseus OS.cmd")

  -Quick  The everyday start: skip the Python / venv / pip / setup steps (run the full script once first), start
          the server in THIS console window, and open http://localhost:<port>/os once it answers. If Odysseus is
          already answering on the port it does not start a second copy, it just opens the browser. Start it from
          here (a normal window) and not from inside another tool's background shell: those get closed when the
          machine runs low on memory, and the open /os page then reports "Failed to fetch".
  -NoBrowser  With -Quick, do not open the browser.
  -NoOllama   With -Quick, do not start Ollama. By default, if Ollama is installed but not answering on
              http://127.0.0.1:11434, -Quick starts it hidden in the background (the tray app when present) so the
              local fallback model in the model chain is there when the main provider is unavailable. It never waits
              for Ollama and never fails the launch because of it.

  The port defaults to 7000, or to the APP_PORT environment variable when it is set (the data folder follows
  ODYSSEUS_DATA_DIR as usual), so a test copy can run beside the real one.

  Tip: bind 127.0.0.1 (default) for local-only use. Use 0.0.0.0 only when you
  intentionally want other devices on your LAN to reach it.
#>
param(
    [int]$Port = $(if ($env:APP_PORT) { [int]$env:APP_PORT } else { 7000 }),
    [string]$BindHost = "127.0.0.1",
    [switch]$Quick,
    [switch]$NoBrowser,
    [switch]$NoOllama
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step($msg) { Write-Host ""; Write-Host ("==> " + $msg) -ForegroundColor Cyan }
function Fail($msg) {
    Write-Host ""
    Write-Host ("ERROR: " + $msg) -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

function Test-WindowsBashStub($path) {
    if (-not $path) { return $false }
    $lowered = $path.ToLowerInvariant()
    foreach ($stub in @("system32\bash.exe", "sysnative\bash.exe", "windowsapps\bash.exe")) {
        if ($lowered.Contains($stub)) { return $true }
    }
    return $false
}

function Find-GitBash {
    $cmd = Get-Command bash -ErrorAction SilentlyContinue
    if ($cmd -and -not (Test-WindowsBashStub $cmd.Source)) { return $cmd.Source }

    $roots = @()
    foreach ($name in @("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LocalAppData")) {
        $base = [Environment]::GetEnvironmentVariable($name)
        if ($base) {
            $roots += (Join-Path $base "Git")
            if ($name -eq "LocalAppData") { $roots += (Join-Path $base "Programs\Git") }
        }
    }
    $roots += @("C:\Program Files\Git", "C:\Program Files (x86)\Git")

    foreach ($root in ($roots | Select-Object -Unique)) {
        foreach ($relative in @("bin\bash.exe", "usr\bin\bash.exe")) {
            $candidate = Join-Path $root $relative
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

# Point CUDA_PATH at a real CUDA toolkit so GPU llama-cpp-python can import, then run the server in this console.
function Start-Odysseus {
    $venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    $cudaBase = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if (Test-Path $cudaBase) {
        $cudaBest = Get-ChildItem $cudaBase -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "bin") } |
            Sort-Object { try { [version]($_.Name -replace "^v", "") } catch { [version]"0.0" } } -Descending |
            Select-Object -First 1
        if ($cudaBest) {
            $env:CUDA_PATH = $cudaBest.FullName
            Write-Host ("Using CUDA_PATH = " + $cudaBest.FullName) -ForegroundColor Cyan
        }
    }

    # Start the server (use `python -m uvicorn` - bare `uvicorn` may not be on PATH)
    Write-Step ("Starting Odysseus at http://{0}:{1}" -f $BindHost, $Port)
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""
    & $venvPy -m uvicorn app:app --host $BindHost --port $Port
}

# ---- -Quick: the everyday "start it and open it" path --------------------------------------------------------------
function Test-PortAnswers([int]$p) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect("127.0.0.1", $p, $null, $null)
        return ($pending.AsyncWaitHandle.WaitOne(600) -and $client.Connected)
    } catch { return $false } finally { $client.Close() }
}

function Test-OdysseusHealthy([int]$p) {
    try {
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/api/health" -f $p) -UseBasicParsing -TimeoutSec 4
        return ($r.Content -match '"status"\s*:\s*"healthy"')
    } catch { return $false }
}

# A console in "QuickEdit" mode freezes the program writing to it as soon as you click inside the window (until you press
# Enter), and a frozen server makes the page report "Failed to fetch". Turn it off for this console only. No-op when the
# console is not a classic one (Windows Terminal never blocks) or when stdin is redirected.
function Disable-ConsoleQuickEdit {
    try {
        Add-Type -Namespace Ody -Name Con -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern System.IntPtr GetStdHandle(int h);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);
'@ -ErrorAction Stop
        $h = [Ody.Con]::GetStdHandle(-10)          # STD_INPUT_HANDLE
        $mode = [uint32]0
        if ([Ody.Con]::GetConsoleMode($h, [ref]$mode)) {
            [void][Ody.Con]::SetConsoleMode($h, (($mode -band (-bnot [uint32]0x40)) -bor [uint32]0x80))     # clear QUICK_EDIT, set EXTENDED_FLAGS
        }
    } catch { }
}

# ---- Ollama: the last model in the fallback chain is local, so have it running -----------------------------------------
function Test-OllamaAnswers {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -UseBasicParsing -TimeoutSec 2
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

# The tray app ("ollama app.exe") starts and supervises the server; fall back to `ollama serve`. $null = not installed.
function Find-Ollama {
    $tray = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
    if (Test-Path -LiteralPath $tray) { return @{ Path = $tray; Args = @() } }
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return @{ Path = $cmd.Source; Args = @("serve") } }
    return $null
}

# Start Ollama hidden when it is installed and not answering. Returns what it did (for the log and the tests):
# "disabled" | "answering" | "already-starting" | "not-installed" | "started" | "failed". Never throws, never waits.
function Start-OllamaIfNeeded {
    if ($NoOllama) { return "disabled" }
    try {
        if (Test-OllamaAnswers) { return "answering" }
        # Already launching (tray app up but the server not listening yet): starting a second one would only add a process.
        if (Get-Process -Name "ollama app", "ollama" -ErrorAction SilentlyContinue) { return "already-starting" }
        $o = Find-Ollama
        if (-not $o) { return "not-installed" }
        $sp = @{ FilePath = $o.Path; WindowStyle = "Hidden" }
        if ($o.Args.Count -gt 0) { $sp.ArgumentList = $o.Args }
        Start-Process @sp | Out-Null
        Write-Host "Started Ollama in the background (local fallback model)." -ForegroundColor DarkGray
        return "started"
    } catch {
        Write-Host ("(Ollama could not be started: " + $_.Exception.Message + " - continuing without it)") -ForegroundColor DarkGray
        return "failed"
    }
}

function Open-OdysseusOS {
    if ($NoBrowser) { return }
    Start-Process ("http://localhost:{0}/os" -f $Port)
}

function Start-Quick {
    $venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Fail ("Odysseus has not been set up in this folder yet (no venv\Scripts\python.exe).`n`n" +
              "Run this once first:`n    powershell -ExecutionPolicy Bypass -File .\launch-windows.ps1`n" +
              "It creates the virtual environment, installs the dependencies and runs the first-time setup. After that, this shortcut is all you need.")
    }

    [void](Start-OllamaIfNeeded)

    if (Test-PortAnswers $Port) {
        if (Test-OdysseusHealthy $Port) {
            Write-Host ("Odysseus is already running on port {0}. Opening it instead of starting a second copy." -f $Port) -ForegroundColor Green
            Open-OdysseusOS
            Start-Sleep -Seconds 3
            exit 0
        }
        Fail ("Port {0} is already in use by something that is not Odysseus.`n`nClose that program, or start Odysseus on another port:`n    Start Odysseus OS.cmd -Port {1}" -f $Port, ($Port + 1))
    }

    $Host.UI.RawUI.WindowTitle = "Odysseus - port $Port - leave this window open"
    Disable-ConsoleQuickEdit
    Write-Host ""
    Write-Host "Odysseus runs in THIS window. Leave it open (minimise it); closing it stops Odysseus." -ForegroundColor Yellow

    # Open the browser as soon as the port answers (uvicorn only listens once the app has finished starting).
    if (-not $NoBrowser) {
        $null = Start-Job -ArgumentList $Port -ScriptBlock {
            param($p)
            for ($i = 0; $i -lt 240; $i++) {
                $c = New-Object System.Net.Sockets.TcpClient
                try {
                    $w = $c.BeginConnect("127.0.0.1", $p, $null, $null)
                    if ($w.AsyncWaitHandle.WaitOne(500) -and $c.Connected) { Start-Process ("http://localhost:{0}/os" -f $p); return }
                } catch { } finally { $c.Close() }
                Start-Sleep -Milliseconds 500
            }
        }
    }

    Start-Odysseus
    Write-Host ""
    Write-Host ("Odysseus stopped (exit code {0})." -f $LASTEXITCODE) -ForegroundColor Yellow
    Read-Host "Press Enter to close this window"
}

if ($Quick) {
    try { Start-Quick } catch { Fail ("Could not start Odysseus: " + $_.Exception.Message) }
    exit 0
}

# 1. Locate a Python interpreter (3.11+ required)
Write-Step "Checking for Python"
function Get-PythonVersionText($launcher, $launcherArgs) {
    try {
        return (& $launcher @launcherArgs -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null).Trim()
    } catch {
        return $null
    }
}

$pyExe = $null
$pyArgs = @()
$pyVersion = $null

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    foreach ($v in @("-3.13", "-3.12", "-3.11")) {
        $ver = Get-PythonVersionText $pyLauncher.Source @($v)
        if ($ver) {
            $pyExe = $pyLauncher.Source
            $pyArgs = @($v)
            $pyVersion = $ver
            break
        }
    }
}

if (-not $pyExe) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $ver = Get-PythonVersionText $pythonCmd.Source @()
        if ($ver) {
            $versionParts = $ver.Split('.')
            $major = [int]$versionParts[0]
            $minor = [int]$versionParts[1]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                $pyExe = $pythonCmd.Source
                $pyVersion = $ver
            }
        }
    }
}

if ($pyExe -like "*WindowsApps*python.exe") {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $pyExe = $pyCmd.Source
        $pyArgs = @("-3.11")
    }
}

if (-not $pyExe) {
    Fail "Couldn't find Python 3.11+ for Windows setup. Install Python 3.11+ (or open the Python launcher with 'py -3.11') from https://www.python.org/downloads/, then re-run this script."
}
$pythonLabel = ("Using Python {0}: {1} {2}" -f $pyVersion, $pyExe, ($pyArgs -join ' ')).TrimEnd()
Write-Host $pythonLabel

# 2. Create the virtualenv if missing
$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Step "Creating virtual environment (venv)"
    & $pyExe @pyArgs -m venv venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Fail "Failed to create the virtual environment." }
} else {
    Write-Host "venv already exists - skipping creation."
}

# 3. Install / update dependencies
Write-Step "Installing dependencies (first run can take a few minutes)"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Dependency install failed. Scroll up for the pip error." }

# 4. First-time setup (creates data dirs, DB, .env, admin user)
Write-Step "Running first-time setup"
& $venvPy setup.py
if ($LASTEXITCODE -ne 0) { Fail "setup.py failed." }

# 5. Friendly note about Git Bash (full Cookbook / agent-shell parity)
if (-not (Find-GitBash)) {
    Write-Host ""
    Write-Host "NOTE: Git Bash (bash.exe) was not found on PATH." -ForegroundColor Yellow
    Write-Host "      The core app works without it. For full Cookbook background" -ForegroundColor Yellow
    Write-Host "      downloads and the agent shell tool, install Git for Windows:" -ForegroundColor Yellow
    Write-Host "      https://git-scm.com/download/win" -ForegroundColor Yellow
}

# 6 + 7. Point CUDA_PATH at a CUDA toolkit and start the server (see Start-Odysseus above)
Start-Odysseus
