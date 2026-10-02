param(
    [string]$ProjectDir = (Split-Path $PSScriptRoot -Parent),
    [string]$AgentDir = $env:EDGE_AGENT_HOME,
    [switch]$SetupOnly,
    [switch]$Check,
    [switch]$Library
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'

function Get-EdgeAgentInstaller {
    param([string]$Destination, [string]$CacheDir)
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'edge-agent-distribution.json') -Raw | ConvertFrom-Json
    $installer = Join-Path $Destination 'scripts\bootstrap.ps1'
    if (Test-Path -LiteralPath $installer) {
        $project = Join-Path $Destination 'pyproject.toml'
        if (Test-Path -LiteralPath $project) {
            $match = [regex]::Match((Get-Content -LiteralPath $project -Raw), '(?m)^version\s*=\s*"(\d+\.\d+\.\d+)"')
            if ($match.Success -and [version]$match.Groups[1].Value -ge [version]$manifest.minimum_version) { return $installer }
        }
    }
    # Before the independent installer exists, only fetch its distribution.
    # Python, inference engines, models and adapters belong to that installer.
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $archive = Join-Path $CacheDir $manifest.asset
    if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive).Hash -ine $manifest.sha256) {
        $ghCommand = Get-Command gh.exe -ErrorAction SilentlyContinue
        if ($ghCommand) { $gh = $ghCommand.Source }
        else {
            $ghDir = Join-Path $env:LOCALAPPDATA 'EdgeAgent\GitHubCLI\2.102.0'
            $gh = Join-Path $ghDir 'bin\gh.exe'
            if (-not (Test-Path -LiteralPath $gh)) {
                $ghZip = Join-Path $CacheDir 'gh_2.102.0_windows_amd64.zip'
                Invoke-WebRequest -UseBasicParsing 'https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_windows_amd64.zip' -OutFile "$ghZip.part" -TimeoutSec 120
                if ((Get-FileHash -LiteralPath "$ghZip.part").Hash -ine 'ae64e556ecc240b200f7eba60d550e4bb60d78e860e69dd88c449405b86067f4') { throw 'GitHub CLI SHA256 mismatch' }
                Move-Item -LiteralPath "$ghZip.part" -Destination $ghZip -Force
                Expand-Archive -LiteralPath $ghZip -DestinationPath $ghDir -Force
            }
        }
        $env:PATH = "$(Split-Path $gh -Parent);$env:PATH"
        & $gh auth status *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Sign in once to obtain the private EdgeAgent distribution.'
            & $gh auth login --hostname github.com --git-protocol https --web
            if ($LASTEXITCODE -ne 0) { throw 'GitHub login was not completed.' }
        }
        $staging = Join-Path $CacheDir ([Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $staging | Out-Null
        & $gh release download $manifest.release --repo $manifest.repository --pattern $manifest.asset --dir $staging
        if ($LASTEXITCODE -ne 0) { throw 'EdgeAgent distribution download failed; retry this launcher.' }
        $downloaded = Join-Path $staging $manifest.asset
        if ((Get-FileHash -LiteralPath $downloaded).Hash -ine $manifest.sha256) { throw 'EdgeAgent distribution SHA256 mismatch' }
        Move-Item -LiteralPath $downloaded -Destination $archive -Force
    }
    if (Test-Path -LiteralPath $Destination) {
        # Never overwrite a previous checkout, its user state or virtual environment.
        if (@(Get-ChildItem -LiteralPath $Destination -Force).Count -gt 0) {
            $Destination = "$Destination-$($manifest.release)"
            $installer = Join-Path $Destination 'scripts\bootstrap.ps1'
            if (Test-Path -LiteralPath $installer) { return $installer }
            if ((Test-Path -LiteralPath $Destination) -and @(Get-ChildItem -LiteralPath $Destination -Force).Count -gt 0) { throw 'The side-by-side EdgeAgent installation is incomplete; select another EDGE_AGENT_HOME.' }
            Write-Host "Preserving previous checkout; installing EdgeAgent at $Destination"
        }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $root = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
        foreach ($entry in $zip.Entries) {
            $candidate = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            if (-not $candidate.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe EdgeAgent archive path.' }
        }
    } finally { $zip.Dispose() }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
    if (-not (Test-Path -LiteralPath $installer)) { throw 'EdgeAgent installer is missing from the distribution.' }
    return $installer
}

function Get-DeploymentState {
    param([string]$Root, [string]$CoreRoot)
    # The completion receipt records deployment inputs and file metadata only.
    # Missing/changed components take the same installer path for repair.
    try {
        $sources = @('requirements.txt', 'config.toml', 'scripts\bootstrap.ps1', 'scripts\setup_copilot.py', 'scripts\edge-agent-distribution.json')
        $signature = @()
        foreach ($source in $sources) {
            $signature += (Get-FileHash -LiteralPath (Join-Path $Root $source)).Hash
        }
        foreach ($source in @('pyproject.toml', 'scripts\bootstrap.ps1', 'edge_agent\runtime.py', 'edge_agent\deploy.py')) {
            $signature += (Get-FileHash -LiteralPath (Join-Path $CoreRoot $source)).Hash
        }
        $required = @(
            (Join-Path $Root '.venv\Scripts\python.exe'),
            (Join-Path $Root '.venv\Scripts\pythonw.exe'),
            (Join-Path $Root '.runtime\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'),
            (Join-Path $CoreRoot '.venv\Scripts\python.exe'),
            (Join-Path $CoreRoot '.runtime\deployment.json'),
            (Join-Path $CoreRoot '.runtime\node\node-v22.23.3-win-x64\node.exe'),
            (Join-Path $CoreRoot '.runtime\pi\node_modules\@earendil-works\pi-coding-agent\dist\index.js'),
            (Join-Path $CoreRoot 'models\Qwen3.5-4B-Q4_K_M.gguf'),
            (Join-Path $CoreRoot 'models\gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf'),
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\edge-agent.cmd'),
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\edge-agent-launch.ps1')
        )
        $engine = Get-Content -LiteralPath (Join-Path $CoreRoot '.runtime\deployment.json') -Raw | ConvertFrom-Json
        $enginePath = [IO.Path]::GetFullPath((Join-Path $CoreRoot $engine.server))
        if (-not $enginePath.StartsWith($CoreRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { return $null }
        $required += $enginePath
        $required += @(Get-ChildItem -LiteralPath (Split-Path $enginePath -Parent) -File | Select-Object -ExpandProperty FullName)
        $required += @(Get-ChildItem -LiteralPath (Join-Path $Root '.runtime\models') -Recurse -File | Where-Object { $_.Extension -in @('.onnx', '.txt') } | Select-Object -ExpandProperty FullName)
        $files = @()
        foreach ($path in ($required | Sort-Object -Unique)) {
            $file = Get-Item -LiteralPath $path -ErrorAction Stop
            if ($file.PSIsContainer -or $file.Length -le 0) { return $null }
            $files += [ordered]@{ path = $file.FullName; bytes = $file.Length; modified = $file.LastWriteTimeUtc.Ticks }
        }
        Push-Location $Root
        try {
            & (Join-Path $Root '.venv\Scripts\python.exe') (Join-Path $Root 'scripts\setup_copilot.py') --probe-assets *> $null
            if ($LASTEXITCODE -ne 0) { return $null }
        } finally { Pop-Location }
        $node = Join-Path $CoreRoot '.runtime\node\node-v22.23.3-win-x64\node.exe'
        $package = Join-Path $CoreRoot '.runtime\pi\node_modules\@earendil-works\pi-coding-agent\dist\index.js'
        $packageUri = ([Uri]$package).AbsoluteUri
        & $node --input-type=module -e 'await import(process.argv[1])' $packageUri *> $null
        if ($LASTEXITCODE -ne 0) { return $null }
        return ([ordered]@{ schema = 1; root = $Root; agent = $CoreRoot; sources = $signature; files = $files } | ConvertTo-Json -Depth 5 -Compress)
    } catch { return $null }
}

function Test-DeploymentReady {
    param([string]$Root, [string]$CoreRoot)
    $receipt = Join-Path $Root '.runtime\deployment-complete'
    if (-not (Test-Path -LiteralPath $receipt)) { return $false }
    $state = Get-DeploymentState $Root $CoreRoot
    return $null -ne $state -and (Get-Content -LiteralPath $receipt -Raw).Trim() -ceq $state
}

function Install-SilentTalk {
    param([string]$Root, [string]$CoreRoot, [bool]$Verify)
    $Root = [IO.Path]::GetFullPath($Root)
    if ([string]::IsNullOrWhiteSpace($CoreRoot)) { $CoreRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'EdgeAgent' }
    $CoreRoot = [IO.Path]::GetFullPath($CoreRoot)
    if ($CoreRoot -eq $Root -or $CoreRoot.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'EDGE_AGENT_HOME must be outside SilentTalk.' }
    $cache = Join-Path $Root '.runtime\downloads'
    $installer = Get-EdgeAgentInstaller $CoreRoot $cache
    $CoreRoot = Split-Path (Split-Path $installer -Parent) -Parent
    if (-not $Verify -and (Test-DeploymentReady $Root $CoreRoot)) {
        $env:PATH = "$(Join-Path $Root '.runtime\ffmpeg\ffmpeg-9.0.2-essentials_build\bin');$(Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links');$env:PATH"
        Write-Host '[OK] Deployment already verified. Starting SilentTalk.'
        return
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -CoreDir $CoreRoot -SetupOnly -CharacterAssets
    if ($LASTEXITCODE -ne 0) { throw 'EdgeAgent installation failed.' }
    # Import deployment helpers only; the application never imports the Agent package.
    . $installer -Library
    $python = Ensure-Python312 $cache
    $venv = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venv)) { Invoke-Checked $python @('-m', 'venv', (Join-Path $Root '.venv')) }
    $requirements = Join-Path $Root 'requirements.txt'
    $digest = (Get-FileHash -LiteralPath $requirements).Hash
    $receipt = Join-Path $Root '.runtime\python-dependencies.sha256'
    $ready = (Test-Path -LiteralPath $receipt) -and (Get-Content -LiteralPath $receipt -Raw).Trim() -eq $digest
    $importsReady = $false
    try { & $venv -c 'import discord,edge_tts,dotenv,sherpa_onnx,numpy,opencc,sounddevice; import discord.ext.voice_recv' *> $null; $importsReady = $LASTEXITCODE -eq 0 } catch { }
    if (-not $ready -or -not $importsReady) {
        Invoke-Checked $venv @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirements)
        Set-Content -LiteralPath $receipt -Value $digest -Encoding ASCII
    }
    $ffmpeg = Join-Path $Root '.runtime\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
    if (-not (Test-Path -LiteralPath $ffmpeg)) {
        $ffZip = Join-Path $cache 'ffmpeg-9.0.2-essentials_build.zip'
        Get-VerifiedFile 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip' $ffZip '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
        Expand-Archive -LiteralPath $ffZip -DestinationPath (Join-Path $Root '.runtime\ffmpeg') -Force
    }
    Invoke-Checked $ffmpeg @('-version')
    $env:PATH = "$(Split-Path $ffmpeg -Parent);$(Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links');$env:PATH"
    Push-Location $Root
    try {
        Invoke-Checked $venv @((Join-Path $Root 'scripts\setup_copilot.py'))
        Invoke-Checked $venv @('-m', 'pip', 'check')
        Invoke-Checked $venv @('-m', 'compileall', '-q', 'app.py', 'silenttalk')
        $complete = Join-Path $Root '.runtime\deployment-complete'
        Invoke-Checked $venv @((Join-Path $Root 'scripts\setup_copilot.py'), '--check-runtime')
        $state = Get-DeploymentState $Root $CoreRoot
        if ($null -eq $state) { throw 'Installed components failed the final readiness probe.' }
        $temporary = "$complete.part"
        Set-Content -LiteralPath $temporary -Value $state -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $complete -Force
    } finally { Pop-Location }
    Write-Host '[OK] SilentTalk and the included EdgeAgent are ready.'
}

if ($Library) { return }
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'This distribution requires Windows x64.' }
$mutex = New-Object Threading.Mutex($false, 'Local\SilentTalk.Install')
$held = $false
try {
    try { $held = $mutex.WaitOne([TimeSpan]::FromMinutes(30)) }
    catch [Threading.AbandonedMutexException] { $held = $true }
    if (-not $held) { throw 'Another SilentTalk installation is still running.' }
    Install-SilentTalk $ProjectDir $AgentDir $Check.IsPresent
} finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
if ($SetupOnly -or $Check) { exit 0 }
$envFile = Join-Path $ProjectDir '.env'
Push-Location $ProjectDir
try {
    $credentialsReady = $false
    try {
        & (Join-Path $ProjectDir '.venv\Scripts\python.exe') -c 'from pathlib import Path; from silenttalk.config import load_settings; load_settings(Path.cwd())' *> $null
        $credentialsReady = $LASTEXITCODE -eq 0
    } catch { }
    if (-not $credentialsReady) {
        Invoke-Checked (Join-Path $ProjectDir '.venv\Scripts\python.exe') @('-m', 'silenttalk.credentials')
    }
    Invoke-Checked (Join-Path $ProjectDir '.venv\Scripts\python.exe') @('-c', 'from pathlib import Path; from silenttalk.config import load_settings; load_settings(Path.cwd())')
} finally { Pop-Location }
& (Join-Path $ProjectDir 'scripts\restart_silenttalk.ps1') -ProjectDir $ProjectDir -Pythonw (Join-Path $ProjectDir '.venv\Scripts\pythonw.exe')
