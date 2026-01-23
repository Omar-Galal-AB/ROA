# Repository Branch Structure Guide

This document explains different approaches for organizing the ROA repository and answers the question: "Can we have four mains or must they all be inside one main?"

---

## Understanding Git Branches

### What is a "Main" Branch?

In Git, a **main branch** (formerly called "master") is the primary branch where the source code reflects a production-ready state. It's the default branch that people see when they visit your repository.

---

## Option 1: Single Main Branch (Recommended)

### Structure
```
ROA Repository
└── main (single primary branch)
    ├── components/
    │   ├── files-type-importer/
    │   ├── universal-robot-controller/
    │   ├── dimensions-collector/
    │   ├── communication-system/
    │   └── webthread/
    └── ... (other directories)
```

### How It Works
- **One main branch** contains all four components as subdirectories
- Each component is a folder within the repository
- All components share the same version history
- Single source of truth for the entire system

### Advantages ✅
- **Simplicity**: Easy to understand and manage
- **Atomic Changes**: Changes affecting multiple components in one commit
- **Easier Coordination**: No need to sync between repositories
- **Single CI/CD Pipeline**: Build and test everything together
- **Easier Dependency Management**: Components can reference each other easily
- **Single Clone**: Developers get everything with one `git clone`
- **Better for Integration**: Natural for components that work together
- **Unified Documentation**: All docs in one place

### Disadvantages ❌
- **Large Repository**: Can become big over time
- **All or Nothing**: Must clone entire repository
- **Shared History**: Can't version components independently

### When to Use
✅ **Use this for ROA** because:
- Components are tightly integrated (they need each other)
- You want atomic changes across components
- Small team working on everything
- Simpler for academic research projects

---

## Option 2: Multiple Repositories (Monorepo Alternative)

### Structure
```
ROA Organization
├── ROA-files-type-importer (Repository 1)
├── ROA-universal-robot-controller (Repository 2)
├── ROA-dimensions-collector (Repository 3)
├── ROA-communication-system (Repository 4)
└── ROA-webthread (Repository 5)
```

### How It Works
- **Four separate repositories** (one per component)
- Each has its own main branch
- Components versioned independently
- Need to clone each repository separately

### Advantages ✅
- **Independent Versioning**: Each component has own version numbers
- **Smaller Repositories**: Faster clone/checkout
- **Team Separation**: Different teams can own different repos
- **Access Control**: Fine-grained permissions per component
- **Independent CI/CD**: Build/test each component separately

### Disadvantages ❌
- **Complex Coordination**: Hard to sync changes across repos
- **Dependency Hell**: Managing versions between components is difficult
- **No Atomic Changes**: Can't update multiple components in one commit
- **More Setup**: Developers must clone multiple repos
- **Duplication**: Shared code must be in yet another repo
- **Testing Complexity**: Integration testing requires all repos

### When to Use
❌ **NOT recommended for ROA** because:
- Components are tightly coupled (not independent)
- Small team doesn't benefit from separation
- Adds unnecessary complexity
- Makes integration harder

---

## Option 3: Monorepo with Multiple Main Branches (Not Recommended)

### Structure
```
ROA Repository with Multiple Main Branches
├── main-files-type-importer
├── main-universal-robot-controller
├── main-dimensions-collector
├── main-communication-system
└── main-webthread
```

### How It Works
- **One repository with multiple "main" branches**
- Each branch represents a different component
- Unusual Git usage (not standard practice)

### Why This is NOT Recommended ❌
- **Confusing**: Branches are meant for development, not organizing components
- **Against Git Best Practices**: Misuse of branches
- **Hard to Understand**: New developers will be confused
- **Tooling Issues**: Many tools expect single main branch
- **Merge Conflicts**: Difficult to merge between component branches
- **No Standard Support**: CI/CD tools not designed for this

**Don't use this approach!**

---

## Option 4: Git Submodules (Advanced)

### Structure
```
ROA (Main Repository)
├── components/
│   ├── files-type-importer/     → Git submodule
│   ├── universal-robot-controller/  → Git submodule
│   ├── dimensions-collector/    → Git submodule
│   ├── communication-system/    → Git submodule
│   └── webthread/              → Git submodule
└── ... (other directories)
```

### How It Works
- **One main repository** that references other repositories
- Each component is a separate Git repository
- Included as **submodules** in the main repo
- Can version each component independently while maintaining single entry point

### Advantages ✅
- **Independent Versioning**: Each component has own repo/version
- **Single Entry Point**: Main repo provides unified structure
- **Selective Updates**: Can update submodules independently
- **Reusability**: Components can be used in other projects

### Disadvantages ❌
- **Complexity**: Submodules are notoriously difficult to work with
- **Learning Curve**: Team must learn submodule commands
- **Clone Issues**: Need `git clone --recursive` or extra steps
- **Update Friction**: Easy to have outdated submodules
- **Merge Conflicts**: Submodule references can conflict

### When to Use
⚠️ **Maybe for ROA in the future** if:
- Components become truly independent projects
- Different external teams contribute to different components
- Components are reused in other projects
- Team is experienced with Git submodules

---

## Recommended Approach for ROA

### **Use Option 1: Single Main Branch** ✅

**Recommended Structure:**
```
ROA/                              # Main repository
├── main                          # Single main branch
│   ├── components/              # All components in folders
│   │   ├── files-type-importer/
│   │   ├── universal-robot-controller/
│   │   ├── dimensions-collector/
│   │   ├── communication-system/
│   │   └── webthread/
│   ├── shared/                  # Shared code
│   ├── docs/                    # Documentation
│   ├── tests/                   # Integration tests
│   └── ...
```

### Development Workflow

**Feature Branches** for development:
```
main                                    # Production-ready code
├── feature/file-importer-urdf-support  # Work on file importer
├── feature/controller-safety-system    # Work on controller
├── feature/webthread-ros2-bridge       # Work on webthread
└── bugfix/collector-position-tracking  # Fix in collector
```

**How to Work:**
1. **Main branch**: Always stable, production-ready
2. **Feature branches**: Create new branch for each feature/component work
3. **Develop**: Work on your feature branch
4. **Test**: Ensure tests pass
5. **Merge**: Merge feature back to main when done
6. **Repeat**: Create new feature branches as needed

**Example Workflow:**
```bash
# Clone repository
git clone https://github.com/Omar-Galal-AB/ROA.git
cd ROA

# Create feature branch for working on File Importer
git checkout -b feature/file-importer-stl-support

# Make changes to components/files-type-importer/
# ... edit files ...

# Commit changes
git add components/files-type-importer/
git commit -m "Add STL file format support to file importer"

# Push to GitHub
git push origin feature/file-importer-stl-support

# Create Pull Request on GitHub
# After review and approval, merge to main
```

---

## Why Single Main Branch is Best for ROA

### 1. **Components are Interdependent**
- Universal Robot Controller depends on Dimensions Collector
- All components depend on Webthread
- Changes often affect multiple components
- Single repo makes this natural

### 2. **Academic Research Project**
- Focus on functionality, not complex infrastructure
- Small team (possibly just you initially)
- Easier to manage and understand
- Can always refactor later if needed

### 3. **Integration is Key**
- Testing requires all components together
- Single repo makes integration testing easier
- CI/CD simpler with everything in one place

### 4. **Simpler for Contributors**
- Clear entry point for new contributors
- All documentation in one place
- One clone gets everything needed

---

## Alternative: Use Folders with Good Organization

Even with single main branch, you can organize clearly:

```
ROA/
├── .github/                     # GitHub Actions, issue templates
├── components/                  # ← Main components here
│   ├── files-type-importer/
│   │   ├── README.md
│   │   ├── src/
│   │   ├── tests/
│   │   └── docs/
│   ├── universal-robot-controller/
│   │   ├── README.md
│   │   ├── src/
│   │   ├── tests/
│   │   └── docs/
│   ├── dimensions-collector/
│   │   ├── README.md
│   │   ├── src/
│   │   ├── tests/
│   │   └── docs/
│   ├── communication-system/
│   │   ├── README.md
│   │   ├── src/
│   │   ├── tests/
│   │   └── docs/
│   └── webthread/
│       ├── README.md
│       ├── src/
│       ├── tests/
│       └── docs/
├── shared/                      # Shared libraries
├── docs/                        # System-level documentation
├── tests/                       # Integration tests
├── scripts/                     # Build and utility scripts
├── .gitignore
├── README.md
└── LICENSE
```

### Benefits of This Organization:
- ✅ Each component feels independent (own README, tests, docs)
- ✅ Clear separation of concerns
- ✅ Easy to find component-specific code
- ✅ Can still make cross-component changes in single commit
- ✅ Each component can have its own version number (in README/config)
- ✅ Simple to navigate

---

## Answer to Your Question

### "Can I have four mains or must they all be inside one main?"

**Short Answer:** They should all be inside **one main branch**.

**Why:**
1. **Git Standard**: One main branch per repository is standard practice
2. **ROA Components are Integrated**: They work together, not separately
3. **Simplicity**: Easier to develop, test, and deploy
4. **Best Practice**: Recommended for projects like ROA

**How to Organize:**
- ✅ One repository (ROA)
- ✅ One main branch
- ✅ Four components as **folders** within the repository
- ✅ Each component has own directory structure (src, tests, docs)
- ✅ Use **feature branches** for development work on each component

**You Can Still Work Independently:**
Even with one main branch, you can:
- Work on each component separately using feature branches
- Have component-specific documentation
- Version components independently (using tags or version files)
- Organize code clearly in separate folders

---

## Migration Path (If Needed Later)

If in the future you decide components should be separate:

**Option A: Split into Multiple Repos**
```bash
# Use git filter-branch or git-subtree to extract component
git subtree split -P components/files-type-importer -b files-type-importer
```

**Option B: Convert to Monorepo with Submodules**
- Extract each component to own repo
- Add back as submodules

But for now, **start simple** with single main branch!

---

## Summary

| Approach | Recommended for ROA? | Reason |
|----------|---------------------|---------|
| **Single Main Branch** | ✅ **YES** | Simple, integrated, perfect for ROA |
| Multiple Repositories | ❌ No | Too complex for integrated components |
| Multiple Main Branches | ❌ No | Against Git best practices |
| Git Submodules | ⚠️ Maybe later | Too complex for now |

**Recommendation:** Use **single main branch** with **well-organized component folders**.

---

## Practical Example for ROA

### Current Structure (Recommended):
```bash
git clone https://github.com/Omar-Galal-AB/ROA.git
cd ROA
# You now have everything:
# - components/files-type-importer/
# - components/universal-robot-controller/
# - components/dimensions-collector/
# - components/communication-system/
# - components/webthread/
```

### Working on a Component:
```bash
# Work on File Importer
git checkout -b feature/importer-urdf-support
cd components/files-type-importer
# ... make changes ...
git commit -m "Add URDF import support"
git push origin feature/importer-urdf-support
# Create PR on GitHub, merge when ready
```

---

**Last Updated**: Design Phase  
**Status**: Ready for repository organization
