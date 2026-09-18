<#
.SYNOPSIS
    Run Mininet in Docker on Windows (Docker Desktop with the WSL 2 backend).

.DESCRIPTION
    Starts an interactive shell in the Mininet container, or runs a single
    command such as "mn --test pingall". Works with Windows PowerShell 5.1
    and PowerShell 7+. The current directory is mounted at /workspace.

.EXAMPLE
    .\scripts\mininet-docker.ps1
    Interactive shell; then run: mn --test pingall

.EXAMPLE
    .\scripts\mininet-docker.ps1 mn --topo 'tree,depth=2' --test pingall
    Quote arguments containing commas: PowerShell treats a,b as an array.

.EXAMPLE
    .\scripts\mininet-docker.ps1 -Gui
    Start the browser GUI for lab.yaml in the current directory, then open
    the http://localhost:8080/#token=... URL it prints.

.EXAMPLE
    .\scripts\mininet-docker.ps1 -Build
    Build the image from this checkout instead of pulling it.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Build,
    [string]$Image = $(if ($env:MININET_IMAGE) { $env:MININET_IMAGE } else { 'ghcr.io/mangesh-bhattacharya/mininet:latest' }),
    [switch]$NoMount,
    [switch]$DryRun,
    [switch]$Gui,
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Command
)

$ErrorActionPreference = 'Stop'
$LocalImage = 'mininet:local'
$RepoDir = Split-Path -Parent $PSScriptRoot

function Invoke-Docker([string[]]$DockerArgs) {
    if ($DryRun) {
        Write-Output ('docker ' + ($DockerArgs -join ' '))
        return
    }
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $DryRun) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error 'Docker is not installed. Install Docker Desktop: see docs/install/windows.md'
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Docker is installed but not running. Start Docker Desktop and try again.'
    }
}

if ($Build) {
    $Image = $LocalImage
    Invoke-Docker @('build', '-t', $Image, $RepoDir)
}
elseif (-not $DryRun) {
    & docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Pulling $Image ..."
        & docker pull $Image
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Pull failed; building the image locally instead.'
            $Image = $LocalImage
            Invoke-Docker @('build', '-t', $Image, $RepoDir)
        }
    }
}

$runArgs = @('run', '--rm', '--privileged', '--hostname', 'mininet')
if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
    $runArgs += '-i'
}
else {
    $runArgs += '-it'
}
if (-not $NoMount) {
    $runArgs += @('-v', "$((Get-Location).Path):/workspace")
}
if ($Gui) {
    # Loopback only: the GUI can run commands as root in the emulated hosts
    $runArgs += @('-p', "127.0.0.1:${Port}:${Port}")
    if (-not $Command) { $Command = @('mn-gui', '--port', "$Port", '--config', '/workspace/lab.yaml') }
}
$runArgs += $Image
if ($Command) { $runArgs += $Command }

Invoke-Docker $runArgs
