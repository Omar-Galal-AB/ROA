# ROA Plugin - Bundled Python + XACRO Setup Script
# Run this once to setup embedded Python with XACRO
# This makes the plugin fully self-contained!

param(
[string]$PluginDir = "Plugins\ROA_PlugIn"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ROA Plugin: Bundled Python Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Paths
$ThirdPartyDir = Join-Path $PluginDir "ThirdParty\Python"
$PythonDir = Join-Path $ThirdPartyDir "python-embed-win64"
$TempZip = Join-Path $ThirdPartyDir "python-embed.zip"

# URLs
$PythonUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

# Create directories
Write-Host "[1/6] Creating directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $ThirdPartyDir -Force | Out-Null
New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
Write-Host "      Created: $ThirdPartyDir" -ForegroundColor Green

# Check if already setup
if (Test-Path "$PythonDir\python.exe") {
    Write-Host ""
    Write-Host "[2/6] Python already installed!" -ForegroundColor Green
    Write-Host "      Checking XACRO..." -ForegroundColor Yellow
    
    try {
      $XacroTest = & "$PythonDir\python.exe" -c "import xacro; print('OK')" 2>&1
      if ($XacroTest -eq "OK") {
    Write-Host ""
       Write-Host "========================================" -ForegroundColor Green
     Write-Host "  Already Setup!" -ForegroundColor Green
   Write-Host "========================================" -ForegroundColor Green
     Write-Host ""
            Write-Host "Bundled Python + XACRO already installed at:" -ForegroundColor White
  Write-Host "  $PythonDir" -ForegroundColor Cyan
     Write-Host ""
      Write-Host "Plugin is ready to use!" -ForegroundColor Green
   Write-Host ""
          exit 0
      }
    }
    catch {
     Write-Host "   XACRO not found. Installing..." -ForegroundColor Yellow
    }
}
else {
    # Download Python
    Write-Host ""
    Write-Host "[2/6] Downloading Python 3.11 embeddable (~30MB)..." -ForegroundColor Yellow
    Write-Host "   This may take a minute..." -ForegroundColor Cyan
    
    try {
        Invoke-WebRequest -Uri $PythonUrl -OutFile $TempZip -UseBasicParsing
        Write-Host "      Downloaded successfully!" -ForegroundColor Green
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to download Python!" -ForegroundColor Red
 Write-Host "Please check your internet connection." -ForegroundColor Red
        exit 1
    }
    
    # Extract
    Write-Host ""
    Write-Host "[3/6] Extracting Python..." -ForegroundColor Yellow
    Expand-Archive -Path $TempZip -DestinationPath $PythonDir -Force
    Remove-Item $TempZip -Force
    Write-Host "      Extracted to: $PythonDir" -ForegroundColor Green
    
    # Configure Python path
    Write-Host ""
    Write-Host "[4/6] Configuring Python path..." -ForegroundColor Yellow
    $PthFile = Join-Path $PythonDir "python311._pth"
    @"
python311.zip
.
Lib
Lib\site-packages
"@ | Out-File -FilePath $PthFile -Encoding ASCII -Force
    Write-Host " Configuration complete!" -ForegroundColor Green
    
    # Download get-pip
    Write-Host ""
 Write-Host "[5/6] Setting up pip..." -ForegroundColor Yellow
 $GetPipPath = Join-Path $PythonDir "get-pip.py"
    
    try {
        Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath -UseBasicParsing
        Write-Host "      Downloaded get-pip.py" -ForegroundColor Green
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to download get-pip!" -ForegroundColor Red
        exit 1
    }
    
    # Install pip
    Write-Host "Installing pip..." -ForegroundColor Cyan
    Push-Location $PythonDir
    try {
    & ".\python.exe" "get-pip.py" --no-warn-script-location 2>&1 | Out-Null
    Remove-Item "get-pip.py" -Force
  Write-Host "   pip installed successfully!" -ForegroundColor Green
    }
    catch {
        Write-Host ""
        Write-Host "ERROR: Failed to install pip!" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
}

# Install XACRO and dependencies
Write-Host ""
Write-Host "[6/6] Installing XACRO and dependencies..." -ForegroundColor Yellow
Write-Host "      This may take a minute..." -ForegroundColor Cyan

$SitePackages = Join-Path $PythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null

Push-Location $PythonDir
try {
    & ".\python.exe" -m pip install xacro lxml PyYAML --target="$SitePackages" --no-warn-script-location --quiet
 Write-Host "      XACRO installed successfully!" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "ERROR: Failed to install XACRO!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
Push-Location $PythonDir

try {
    $PythonVersion = & ".\python.exe" --version 2>&1
    Write-Host "  ? Python: $PythonVersion" -ForegroundColor Green

    $XacroVersion = & ".\python.exe" -c "import xacro; print(xacro.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ? XACRO:  $XacroVersion" -ForegroundColor Green
    }
    else {
        throw "XACRO verification failed"
    }
  
    $LxmlVersion = & ".\python.exe" -c "import lxml; print(lxml.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
  Write-Host "  ? lxml: $LxmlVersion" -ForegroundColor Green
    }
    
    $YamlVersion = & ".\python.exe" -c "import yaml; print('OK')" 2>&1
    if ($YamlVersion -eq "OK") {
  Write-Host "  ? PyYAML: Installed" -ForegroundColor Green
    }
}
catch {
    Write-Host ""
    Write-Host "ERROR: Installation verification failed!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Pop-Location
    exit 1
}

Pop-Location

# Calculate size
$TotalSize = (Get-ChildItem -Path $PythonDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Installation Details:" -ForegroundColor White
Write-Host "  Location: $PythonDir" -ForegroundColor Cyan
Write-Host "  Size:     $([math]::Round($TotalSize, 1)) MB" -ForegroundColor Cyan
Write-Host ""
Write-Host "What's Included:" -ForegroundColor White
Write-Host "  • Python 3.11 embeddable runtime" -ForegroundColor Cyan
Write-Host "  • XACRO package (robot description processor)" -ForegroundColor Cyan
Write-Host "  • lxml (XML parsing)" -ForegroundColor Cyan
Write-Host "  • PyYAML (YAML support)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Benefits:" -ForegroundColor White
Write-Host "  ? Plugin is now fully self-contained" -ForegroundColor Green
Write-Host "  ? No external dependencies required" -ForegroundColor Green
Write-Host "  ? XACRO conversion works out of the box" -ForegroundColor Green
Write-Host "  ? No system Python conflicts" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor White
Write-Host "  1. Commit this to your repository (optional)" -ForegroundColor Cyan
Write-Host "  2. Launch UE5 Editor" -ForegroundColor Cyan
Write-Host "  3. Drag .xacro files into Content Browser" -ForegroundColor Cyan
Write-Host "  4. Enjoy automatic XACRO ? URDF conversion!" -ForegroundColor Cyan
Write-Host ""
Write-Host "The plugin will automatically use bundled Python!" -ForegroundColor Green
Write-Host ""
