#!/bin/bash
# Quick script to push ROA to GitHub

echo "🚀 Pushing ROA to GitHub..."
echo ""

# Set branch name to main
git branch -M main

# Add your GitHub remote (replace if it exists)
git remote remove origin 2>/dev/null
git remote add origin https://github.com/OGabou78301/ROA.git

# Push to GitHub
echo "Pushing to branch: main"
git push -u origin main

echo ""
echo "✅ Done! Check your repository at:"
echo "https://github.com/OGabou78301/ROA"
