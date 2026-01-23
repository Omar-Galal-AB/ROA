# ?? Bundled Python + XACRO Setup Guide

**Creating Self-Contained XACRO Processor**

---

## ?? **What We're Bundling**

### **Components:**
1. **Python Embeddable Package** (~30MB)
   - Standalone Python runtime
   - No installation required
   - Works from plugin folder

2. **XACRO Python Package** (~500KB)
   - Pure Python implementation
   - No ROS2 dependency
   - MIT License (redistributable)

3. **Dependencies** (~2MB)
   - lxml (XML parsing)
   - PyYAML (YAML support)

**Total Size:** ~33MB (acceptable for plugin)

---

## ?? **Setup Instructions**

### **Step 1: Download Python Embeddable**

```powershell
# Create directory
New-Item -ItemType Directory -Path "Plugins\ROA_PlugIn\ThirdParty\Python" -Force

# Download Python 3.11 Embeddable (Windows x64)
$PythonUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-amd64.zip"
$ZipPath = "Plugins\ROA_PlugIn\ThirdParty\python-embed.zip"

# Download
Invoke-WebRequest -Uri $PythonUrl -OutFile $ZipPath

# Extract
Expand-Archive -Path $ZipPath -DestinationPath "Plugins\ROA_PlugIn\ThirdParty\Python\python-embed-win64" -Force

# Cleanup
Remove-Item $ZipPath
```

### **Step 2: Install get-pip**

```powershell
# Download get-pip.py
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$GetPipPath = "Plugins\ROA_PlugIn\ThirdParty\Python\python-embed-win64\get-pip.py"

Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath

# Run get-pip
cd "Plugins\ROA_PlugIn\ThirdParty\Python\python-embed-win64"
.\python.exe get-pip.py

# Cleanup
Remove-Item get-pip.py
```

### **Step 3: Install XACRO and Dependencies**

```powershell
# Still in python-embed-win64 directory
.\python.exe -m pip install xacro lxml PyYAML --target=".\Lib\site-packages"
```

### **Step 4: Configure Python Path**

Edit `python311._pth` file:
```
# Add these lines
python311.zip
.
Lib
Lib\site-packages
```

### **Step 5: Verify Installation**

```powershell
# Test Python
.\python.exe --version
# Output: Python 3.11.7

# Test XACRO
.\python.exe -c "import xacro; print('XACRO version:', xacro.__version__)"
# Output: XACRO version: 1.14.x
```

---

## ?? **Automated Setup Script**

Create: `setup_bundled_python.ps1`

```powershell
# ROA Plugin - Bundled Python + XACRO Setup Script
# Run this once to setup embedded Python with XACRO

param(
    [string]$PluginDir = "Plugins\ROA_PlugIn"
)

$ErrorActionPreference = "Stop"

Write-Host "ROA Plugin: Setting up bundled Python + XACRO..." -ForegroundColor Green

# Paths
$ThirdPartyDir = Join-Path $PluginDir "ThirdParty\Python"
$PythonDir = Join-Path $ThirdPartyDir "python-embed-win64"
$TempZip = Join-Path $ThirdPartyDir "python-embed.zip"

# URLs
$PythonUrl = "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

# Create directories
Write-Host "Creating directories..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $ThirdPartyDir -Force | Out-Null
New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null

# Check if already setup
if (Test-Path "$PythonDir\python.exe") {
    Write-Host "Python already installed. Checking XACRO..." -ForegroundColor Yellow
    
    $XacroTest = & "$PythonDir\python.exe" -c "import xacro; print('OK')" 2>&1
    if ($XacroTest -eq "OK") {
        Write-Host "XACRO already installed!" -ForegroundColor Green
        Write-Host "Setup complete. Bundled Python + XACRO ready!" -ForegroundColor Green
        exit 0
    }
    else {
        Write-Host "XACRO not found. Installing..." -ForegroundColor Yellow
    }
}
else {
    # Download Python
    Write-Host "Downloading Python 3.11 embeddable..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $PythonUrl -OutFile $TempZip -UseBasicParsing
    
    # Extract
    Write-Host "Extracting Python..." -ForegroundColor Cyan
    Expand-Archive -Path $TempZip -DestinationPath $PythonDir -Force
    Remove-Item $TempZip -Force
    
    # Configure Python path
  Write-Host "Configuring Python path..." -ForegroundColor Cyan
    $PthFile = Join-Path $PythonDir "python311._pth"
    @"
python311.zip
.
Lib
Lib\site-packages
"@ | Out-File -FilePath $PthFile -Encoding ASCII -Force
    
    # Download get-pip
    Write-Host "Downloading get-pip.py..." -ForegroundColor Cyan
    $GetPipPath = Join-Path $PythonDir "get-pip.py"
    Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath -UseBasicParsing
    
    # Install pip
    Write-Host "Installing pip..." -ForegroundColor Cyan
    Push-Location $PythonDir
& ".\python.exe" "get-pip.py" --no-warn-script-location
    Remove-Item "get-pip.py" -Force
    Pop-Location
}

# Install XACRO and dependencies
Write-Host "Installing XACRO and dependencies..." -ForegroundColor Cyan
$SitePackages = Join-Path $PythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null

Push-Location $PythonDir
& ".\python.exe" -m pip install xacro lxml PyYAML --target="$SitePackages" --no-warn-script-location
Pop-Location

# Verify installation
Write-Host "Verifying installation..." -ForegroundColor Cyan
Push-Location $PythonDir

$PythonVersion = & ".\python.exe" --version
Write-Host "  Python: $PythonVersion" -ForegroundColor White

$XacroVersion = & ".\python.exe" -c "import xacro; print(xacro.__version__)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  XACRO: $XacroVersion" -ForegroundColor White
}
else {
    Write-Host "  ERROR: XACRO installation failed!" -ForegroundColor Red
    Pop-Location
    exit 1
}

Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Bundled Python + XACRO installed at:" -ForegroundColor White
Write-Host "  $PythonDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "Plugin will now use bundled XACRO automatically!" -ForegroundColor Green
Write-Host ""
Write-Host "Total size: ~33MB" -ForegroundColor Yellow
Write-Host "Fully self-contained - no external dependencies!" -ForegroundColor Green
```

---

## ?? **Add to .gitignore**

```gitignore
# Bundled Python (large binary files)
Plugins/ROA_PlugIn/ThirdParty/Python/

# Keep the setup script
!Plugins/ROA_PlugIn/ThirdParty/setup_bundled_python.ps1
```

**OR if you want to commit it:**
```gitignore
# Keep bundled Python (team convenience)
# Users won't need to run setup
# But repo will be larger (~33MB)
```

---

## ?? **Usage After Setup**

### **Developers:**
```powershell
# One-time setup
cd D:\ROA\UE5_Projects\ROA_V1
.\Plugins\ROA_PlugIn\ThirdParty\setup_bundled_python.ps1

# Done! Plugin now has embedded Python + XACRO
```

### **End Users:**
```
# Nothing! 
# If you commit bundled Python to repo,
# users just clone and it works!
```

### **CI/CD:**
```yaml
# In your build pipeline
- name: Setup ROA Plugin Dependencies
  run: |
    cd Plugins/ROA_PlugIn/ThirdParty
    ./setup_bundled_python.ps1
```

---

## ?? **License Compliance**

### **Python:**
- License: Python Software Foundation License
- Can redistribute: ? YES
- Commercial use: ? YES

### **XACRO:**
- License: BSD-3-Clause
- Can redistribute: ? YES
- Commercial use: ? YES

### **lxml:**
- License: BSD
- Can redistribute: ? YES

### **PyYAML:**
- License: MIT
- Can redistribute: ? YES

**All components are redistributable! ?**

---

## ?? **Advantages**

### **For Developers:**
- ? One-time setup (5 minutes)
- ? No system Python needed
- ? No version conflicts
- ? Consistent environment

### **For End Users:**
- ? Zero setup required
- ? Plugin just works
- ? No external dependencies
- ? No PATH issues

### **For Your Use Case:**
- ? ROS2 on Linux? Don't need it on Windows!
- ? Self-contained solution
- ? Always works
- ? Future-proof

---

## ?? **Size Breakdown**

```
python-embed-win64/          ~30MB
??? python.exe            ~100KB
??? python311.dll            ~4MB
??? python311.zip            ~25MB
??? Lib/
    ??? site-packages/
    ??? xacro/  ~500KB
        ??? lxml/            ~1.5MB
        ??? yaml/ ~200KB

Total: ~33MB
```

**Is 33MB acceptable?** 
- Modern games: 50-100GB
- UE5 Engine: 50GB
- 33MB for XACRO: 0.03% overhead ?

---

## ?? **Alternative: Download on First Use**

If 33MB is too much for repo:

```cpp
// In FROAXacroProcessor::SetupEmbeddedPython()
bool FROAXacroProcessor::SetupEmbeddedPython()
{
  if (bEmbeddedPythonSetup) return true;
    
    FString PythonPath = GetEmbeddedPythonPath();
    
 // Check if already installed
    if (FPaths::FileExists(PythonPath))
    {
  bEmbeddedPythonSetup = true;
        return true;
    }
    
    // Not installed - offer to download
    FText Title = FText::FromString(TEXT("Download Bundled Python + XACRO?"));
    FText Message = FText::FromString(TEXT(
        "ROA Plugin needs Python + XACRO for XACRO processing.\n\n"
    "Download embedded Python + XACRO? (~33MB)\n"
        "This is a one-time download.\n\n"
     "Alternative: Install standalone XACRO with:\n"
        "pip install xacro"
    ));
    
    EAppReturnType::Type Result = FMessageDialog::Open(
   EAppMsgType::YesNo, Message, Title
    );
    
    if (Result == EAppReturnType::Yes)
    {
        // Download and install automatically
  return DownloadAndInstallBundledPython();
    }
    
    return false;
}
```

---

## ?? **Recommendation**

### **Best Approach:**

1. **Include setup script in repo** ?
2. **Run once during development** ?
3. **Commit bundled Python to repo** (optional)
   - If yes: Users get zero-setup experience
   - If no: Users run setup script once

### **For Your Project:**

```
Recommended: Commit bundled Python

Why?
- Your team doesn't need setup
- CI/CD works out of box
- End users have zero friction
- 33MB is negligible
- Future-proof (no external deps)
```

---

## ?? **Next Steps**

1. **Run setup script:**
   ```powershell
   cd D:\ROA\UE5_Projects\ROA_V1
   New-Item -ItemType File -Path "Plugins\ROA_PlugIn\ThirdParty\setup_bundled_python.ps1"
   # Copy script content from above
   .\Plugins\ROA_PlugIn\ThirdParty\setup_bundled_python.ps1
   ```

2. **Test embedded XACRO:**
   ```powershell
 cd Plugins\ROA_PlugIn\ThirdParty\Python\python-embed-win64
   .\python.exe Resources\Python\xacro_processor.py test.xacro test.urdf
   ```

3. **Commit to repo:**
   ```sh
   git add Plugins/ROA_PlugIn/ThirdParty/
   git commit -m "Add bundled Python + XACRO for self-contained plugin"
   ```

4. **Update documentation:**
   - No setup needed!
   - Plugin works out of box!
 - XACRO conversion always available!

---

**With bundled Python + XACRO, your plugin becomes truly self-contained!** ??

---

**Guide Version:** 1.0  
**Created:** January 2025  
**Size:** ~33MB  
**Setup Time:** 5 minutes (one-time)  
**User Impact:** Zero setup required ?

