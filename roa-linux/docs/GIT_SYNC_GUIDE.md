# Git Sync and Local Connection Guide

This guide explains how to verify your Git connection and sync between the online ROA repository and your local `roa` folder.

---

## Current Repository Configuration

### Remote Repository
- **GitHub URL**: `https://github.com/Omar-Galal-AB/ROA`
- **Branch**: `copilot/add-four-main-parts` (current working branch)
- **Main Branch**: `main` (will merge to this later)

### Local Folder
- **Local Path**: `roa` (lowercase folder on your machine)
- **Purpose**: Local development, testing, and code editing

---

## Verifying Git Connection

### Check Current Connection

Run these commands in your local `roa` folder to verify connection:

```bash
# Navigate to your local roa folder
cd /path/to/roa

# Check if Git is initialized
git status

# Check remote configuration
git remote -v

# Check current branch
git branch
```

**Expected Output:**
```
origin  https://github.com/Omar-Galal-AB/ROA (fetch)
origin  https://github.com/Omar-Galal-AB/ROA (push)
```

---

## Initial Setup (If Not Connected Yet)

### Option 1: Clone Repository (Recommended if starting fresh)

```bash
# Clone the repository to create local roa folder
git clone https://github.com/Omar-Galal-AB/ROA.git roa

# Navigate into the folder
cd roa

# Check current branch
git branch

# Switch to development branch if needed
git checkout copilot/add-four-main-parts
```

### Option 2: Connect Existing Folder

If you already have a `roa` folder:

```bash
# Navigate to your existing folder
cd /path/to/roa

# Initialize Git (if not already)
git init

# Add remote connection
git remote add origin https://github.com/Omar-Galal-AB/ROA.git

# Fetch all branches
git fetch origin

# Checkout the working branch
git checkout -b copilot/add-four-main-parts origin/copilot/add-four-main-parts

# Verify connection
git remote -v
```

---

## Workflow: Online Work → Local Testing

### Step 1: Work is Done Online (GitHub/Copilot)
Changes are made online through GitHub interface or Copilot.

### Step 2: Pull Changes to Local
```bash
# Navigate to your local roa folder
cd /path/to/roa

# Make sure you're on the correct branch
git checkout copilot/add-four-main-parts

# Pull latest changes from online
git pull origin copilot/add-four-main-parts
```

**What This Does:**
- Downloads all new files and changes from GitHub
- Updates your local `roa` folder
- Syncs your local code with online work

### Step 3: Verify Files Are Synced
```bash
# List all files to verify they're present
ls -la

# Check specific documentation files
ls *.md

# Expected files:
# README.md
# ARCHITECTURE.md
# DESIGN_DECISIONS.md
# VSCODE_SETUP.md
# etc.
```

### Step 4: Make Local Changes
```bash
# Edit files locally using VS Code or any editor
code .  # Opens VS Code in current directory

# Make your changes, test locally
# ... edit files ...
```

### Step 5: Push Changes Back to GitHub
```bash
# Check what changed
git status

# Add changed files
git add .

# Commit changes
git commit -m "Your commit message describing changes"

# Push back to GitHub
git push origin copilot/add-four-main-parts
```

---

## Complete Sync Workflow

### Daily Development Cycle

```bash
# Morning: Start work
cd /path/to/roa
git pull origin copilot/add-four-main-parts  # Get latest changes

# During day: Make changes locally
# ... edit code in VS Code ...
# ... test locally ...

# Evening: Push changes back
git add .
git commit -m "Description of what you changed"
git push origin copilot/add-four-main-parts
```

---

## Verify Connection Status

### Quick Connection Check

Create a file `.github-check.sh` in your local `roa` folder:

```bash
#!/bin/bash
echo "=== Git Connection Status ==="
echo ""

echo "Remote Configuration:"
git remote -v
echo ""

echo "Current Branch:"
git branch --show-current
echo ""

echo "Status:"
git status --short
echo ""

echo "Last 3 Commits:"
git log --oneline -3
echo ""

echo "Connection to GitHub:"
if git ls-remote origin &> /dev/null; then
    echo "✅ Connected to GitHub successfully"
else
    echo "❌ Cannot connect to GitHub"
fi
```

Run it:
```bash
chmod +x .github-check.sh
./.github-check.sh
```

---

## Common Sync Scenarios

### Scenario 1: Pull Latest Documentation

After design work is done online:

```bash
cd roa
git pull origin copilot/add-four-main-parts

# Verify new files
ls -la *.md

# You should see:
# ARCHITECTURE.md
# DESIGN_DECISIONS.md
# VSCODE_SETUP.md
# SIM_VS_REA_VERSIONS.md
# etc.
```

### Scenario 2: Test Changes Locally

```bash
# Pull latest
git pull origin copilot/add-four-main-parts

# Open in VS Code
code .

# Make test changes
# ... edit a file ...

# See what changed
git diff

# Discard local test changes if not keeping them
git checkout -- filename.md

# Or commit and push if keeping them
git add filename.md
git commit -m "Test changes"
git push origin copilot/add-four-main-parts
```

### Scenario 3: Work Offline, Sync Later

```bash
# Work locally without internet
cd roa
# ... make changes ...

# When internet is back
git pull origin copilot/add-four-main-parts  # Get any online changes

# Resolve conflicts if any (Git will notify you)

# Push your local changes
git add .
git commit -m "Local changes made offline"
git push origin copilot/add-four-main-parts
```

---

## Handling Conflicts

### If Pull Shows Conflicts

```bash
$ git pull origin copilot/add-four-main-parts
# Output: CONFLICT (content): Merge conflict in filename.md

# Open the conflicting file
code filename.md

# You'll see conflict markers:
<<<<<<< HEAD
Your local changes
=======
Changes from GitHub
>>>>>>> origin/copilot/add-four-main-parts

# Edit to keep what you want, remove markers

# Mark as resolved
git add filename.md
git commit -m "Resolved merge conflict"
git push origin copilot/add-four-main-parts
```

---

## VS Code Integration

### Built-in Git in VS Code

VS Code has built-in Git support:

1. **Open folder in VS Code:**
   ```bash
   cd roa
   code .
   ```

2. **Source Control Panel** (Left sidebar, 3rd icon):
   - Shows changed files
   - Commit interface
   - Push/Pull buttons
   - Branch switcher

3. **Status Bar** (Bottom):
   - Shows current branch
   - Sync button (pulls + pushes)
   - Indicators for changes

4. **Command Palette** (`Ctrl+Shift+P`):
   - "Git: Pull"
   - "Git: Push"
   - "Git: Commit"
   - "Git: Sync"

---

## Automated Sync Script

### Create `sync.sh` for Easy Syncing

```bash
#!/bin/bash
# sync.sh - Easy sync with GitHub

echo "🔄 Syncing with GitHub..."

# Pull latest changes
echo "⬇️  Pulling latest changes..."
git pull origin copilot/add-four-main-parts

if [ $? -ne 0 ]; then
    echo "❌ Pull failed. Please resolve conflicts."
    exit 1
fi

# Check if there are local changes
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Local changes detected"
    
    # Ask if user wants to commit
    read -p "Commit and push local changes? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add .
        read -p "Enter commit message: " commit_msg
        git commit -m "$commit_msg"
        
        echo "⬆️  Pushing changes..."
        git push origin copilot/add-four-main-parts
        
        echo "✅ Sync complete!"
    else
        echo "⏸️  Changes not pushed"
    fi
else
    echo "✅ Already up to date!"
fi
```

Usage:
```bash
chmod +x sync.sh
./sync.sh
```

---

## Testing the Connection

### Quick Test

```bash
# 1. Create a test file locally
cd roa
echo "Test connection" > test-connection.txt

# 2. Add and commit
git add test-connection.txt
git commit -m "Test: Verify Git connection"

# 3. Push to GitHub
git push origin copilot/add-four-main-parts

# 4. Check on GitHub
# Visit: https://github.com/Omar-Galal-AB/ROA
# You should see test-connection.txt in the file list

# 5. Clean up
git rm test-connection.txt
git commit -m "Remove test file"
git push origin copilot/add-four-main-parts
```

---

## Repository Status Check

### What Files Should Be in Your Local `roa` Folder

After syncing, you should have:

```
roa/
├── .git/                          # Git metadata (hidden)
├── .gitignore                     # (if exists)
├── README.md
├── ARCHITECTURE.md
├── PROJECT_STRUCTURE.md
├── DESIGN_DECISIONS.md
├── CLARIFICATIONS_EXPLAINED.md
├── FILESYSTEM_VS_DATABASE.md
├── VSCODE_SETUP.md
├── REPOSITORY_STRUCTURE.md
├── SIM_VS_REA_VERSIONS.md
└── (other files as development progresses)
```

Verify:
```bash
cd roa
ls -la
```

---

## Troubleshooting

### Problem: "fatal: not a git repository"

**Solution:**
```bash
# You're not in the right folder or Git not initialized
cd /path/to/roa
git init
git remote add origin https://github.com/Omar-Galal-AB/ROA.git
git fetch origin
git checkout copilot/add-four-main-parts
```

### Problem: "Permission denied (publickey)"

**Solution:**
```bash
# Use HTTPS instead of SSH
git remote set-url origin https://github.com/Omar-Galal-AB/ROA.git

# Or set up SSH keys (more secure):
# https://docs.github.com/en/authentication/connecting-to-github-with-ssh
```

### Problem: "Your branch is behind 'origin/copilot/add-four-main-parts'"

**Solution:**
```bash
# Simply pull the changes
git pull origin copilot/add-four-main-parts
```

### Problem: "Your branch is ahead of 'origin/copilot/add-four-main-parts'"

**Solution:**
```bash
# You have local commits not pushed yet
# Push them to GitHub
git push origin copilot/add-four-main-parts
```

---

## Best Practices

### 1. Always Pull Before Editing
```bash
# Start your work session
git pull origin copilot/add-four-main-parts
# Now edit files
```

### 2. Commit Often
```bash
# Small, focused commits are better
git add specific-file.md
git commit -m "Update specific section"
git push origin copilot/add-four-main-parts
```

### 3. Use Descriptive Commit Messages
```bash
# Good:
git commit -m "Add SQLite configuration to VSCODE_SETUP.md"

# Bad:
git commit -m "updates"
```

### 4. Check Status Frequently
```bash
git status  # Shows what's changed
```

---

## Summary

**Your Setup:**
- **Remote**: https://github.com/Omar-Galal-AB/ROA
- **Branch**: copilot/add-four-main-parts
- **Local**: `roa` folder on your computer

**Basic Workflow:**
1. `git pull origin copilot/add-four-main-parts` - Get latest changes
2. Edit files locally
3. `git add .` - Stage changes
4. `git commit -m "message"` - Commit changes
5. `git push origin copilot/add-four-main-parts` - Send back to GitHub

**Connection is Working When:**
- ✅ `git remote -v` shows GitHub URL
- ✅ `git pull` downloads files
- ✅ `git push` uploads your changes
- ✅ Changes appear on GitHub website

---

**Last Updated**: Design Phase  
**Status**: Ready for local development with Git sync
