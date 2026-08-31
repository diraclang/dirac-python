# Polyglot Package Management in DIRAC

This document describes how to structure DIRAC projects that use packages from multiple languages (JavaScript, Python, etc.).

## Problem Statement

A DIRAC project may depend on packages written in different languages:
- **JavaScript packages**: Distributed via npm (e.g., `dirac-ear` for audio processing)
- **Python packages**: Distributed via pip (e.g., `dirac-arm` for robotics with numpy/scipy)

Traditional package managers (npm, pip) only handle their own ecosystem. DIRAC needs to support both.

## Real-World Example: dirac-robotic

```
dirac-robotic/
  package.json          # JavaScript dependencies
  requirements.txt      # Python dependencies
  README.md
  
  # JavaScript packages
  node_modules/
    dirac-ear/          # Installed via npm
    dirac-json/
    
  # Python packages  
  venv/                 # Python virtual environment
    lib/python3.x/site-packages/
      dirac_arm/        # Installed via pip
      numpy/
      scipy/
      
  # Your DIRAC code
  src/
    robot.di            # Imports both dirac-ear and dirac-arm
```

## Dependency Declaration

### JavaScript Dependencies (package.json)

```json
{
  "name": "dirac-robotic",
  "version": "1.0.0",
  "description": "Robot control using DIRAC with polyglot packages",
  "dependencies": {
    "dirac-lang": "^0.1.32",
    "dirac-ear": "^1.0.0",
    "dirac-json": "^1.0.0"
  },
  "scripts": {
    "install": "npm install && python3 -m venv venv && venv/bin/python -m pip install -r requirements.txt",
    "start": "dirac src/robot.di"
  }
}
```

### Python Dependencies (requirements.txt)

```txt
dirac-arm>=1.0.0
numpy>=1.24.0
scipy>=1.10.0
```

**Alternative: Modern Python (pyproject.toml)**

```toml
[project]
name = "dirac-robotic"
version = "1.0.0"
description = "Robot control using DIRAC"

dependencies = [
    "dirac-arm>=1.0.0",
    "numpy>=1.24.0",
    "scipy>=1.10.0"
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

## Installation

### Manual Setup

```bash
# Install JavaScript dependencies
npm install

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### Automated Setup Script (setup.sh)

```bash
#!/bin/bash
set -e

echo "Setting up dirac-robotic..."

# Install JavaScript dependencies
echo "Installing JavaScript dependencies..."
npm install

# Set up Python virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Setup complete!"
echo "Run: dirac src/robot.di"
```

### Using npm Scripts

```json
{
  "scripts": {
    "setup": "npm install && python3 -m venv venv && venv/bin/python -m pip install -r requirements.txt",
    "start": "dirac src/robot.di",
    "test": "npm test && python -m pytest"
  }
}
```

## Usage in DIRAC Code

**src/robot.di:**

```xml
<dirac>
  <!-- Import JavaScript package -->
  <import src="dirac-ear" />
  <!-- Runtime resolves: node_modules/dirac-ear/lib/index.di -->
  
  <!-- Import Python package -->
  <import src="dirac-arm" />
  <!-- Runtime resolves: venv/lib/python3.x/site-packages/dirac_arm/lib/index.di -->
  
  <!-- Use JavaScript package -->
  <defvar name="audioData">
    <EAR_LISTEN frequency="20000" duration="5" />
  </defvar>
  
  <!-- Process with Python package -->
  <defvar name="command">
    <eval name="result" language="python">
      import numpy as np
      # Process audio data
      signal = np.array(audioData)
      result = signal.mean()
    </eval>
  </defvar>
  
  <!-- Control robot arm -->
  <ARM_MOVE x="10" y="20" z="5" />
  
  <output>Robot operation complete!</output>
</dirac>
```

## Import Resolution in DIRAC Runtime

The DIRAC runtime must check multiple package locations:

### Resolution Order

1. **npm packages** (node_modules)
2. **pip packages in venv** (venv/lib/python*/site-packages)
3. **pip packages system-wide** (system site-packages)
4. **Relative paths** (local .di files)

### Implementation (src/tags/import.ts)

```typescript
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';
import glob from 'glob';

async function resolvePackage(packageName: string): Promise<string> {
  // 1. Try npm (node_modules)
  const npmPath = path.join(process.cwd(), 'node_modules', packageName, 'lib/index.di');
  if (fs.existsSync(npmPath)) {
    return npmPath;
  }
  
  // 2. Try pip in virtual environment
  const venvPattern = path.join(
    process.cwd(), 
    'venv/lib/python*/site-packages', 
    packageName.replace('-', '_'),  // npm: dirac-arm, pip: dirac_arm
    'lib/index.di'
  );
  const venvMatches = glob.sync(venvPattern);
  if (venvMatches.length > 0) {
    return venvMatches[0];
  }
  
  // 3. Try system Python site-packages
  try {
    const sitePackages = execSync('python3 -c "import site; print(site.getsitepackages()[0])"', {
      encoding: 'utf-8'
    }).trim();
    
    const pythonPath = path.join(
      sitePackages, 
      packageName.replace('-', '_'), 
      'lib/index.di'
    );
    
    if (fs.existsSync(pythonPath)) {
      return pythonPath;
    }
  } catch (error) {
    // Python not available or command failed
  }
  
  // 4. Not found
  throw new Error(`Package not found: ${packageName}. Please install via npm or pip.`);
}
```

## Package Naming Conventions

### JavaScript (npm)
- Package name: `dirac-ear` (kebab-case)
- Directory: `node_modules/dirac-ear/`
- Import: `<import src="dirac-ear" />`

### Python (pip)
- Package name on PyPI: `dirac-arm` (kebab-case)
- Directory: `site-packages/dirac_arm/` (snake_case)
- Import: `<import src="dirac-arm" />` (DIRAC converts to snake_case)

**Key insight**: DIRAC runtime converts `dirac-arm` → `dirac_arm` when searching Python packages.

## Alternative: Unified Config File

Instead of maintaining both `package.json` and `requirements.txt`, you could create a DIRAC-specific config:

### dirac.config.json

```json
{
  "name": "dirac-robotic",
  "version": "1.0.0",
  "description": "Robot control using DIRAC",
  "dependencies": {
    "javascript": {
      "dirac-ear": "^1.0.0",
      "dirac-json": "^1.0.0"
    },
    "python": {
      "dirac-arm": ">=1.0.0",
      "numpy": ">=1.24.0",
      "scipy": ">=1.10.0"
    }
  }
}
```

### Install Helper (dirac-install command)

```javascript
#!/usr/bin/env node
const fs = require('fs');
const { execSync } = require('child_process');

const config = JSON.parse(fs.readFileSync('dirac.config.json', 'utf-8'));

// Generate package.json from JavaScript deps
const packageJson = {
  name: config.name,
  version: config.version,
  dependencies: config.dependencies.javascript || {}
};
fs.writeFileSync('package.json', JSON.stringify(packageJson, null, 2));
console.log('Installing JavaScript dependencies...');
execSync('npm install', { stdio: 'inherit' });

// Generate requirements.txt from Python deps
const pythonDeps = config.dependencies.python || {};
const requirements = Object.entries(pythonDeps)
  .map(([pkg, ver]) => `${pkg}${ver}`)
  .join('\n');
fs.writeFileSync('requirements.txt', requirements);

console.log('Setting up Python environment...');
execSync('python3 -m venv venv', { stdio: 'inherit' });
execSync('venv/bin/python -m pip install -r requirements.txt', { stdio: 'inherit' });

console.log('Setup complete!');
```

**Usage:**
```bash
dirac-install  # Reads dirac.config.json, installs everything
```

## Documentation Template

### README.md for Polyglot Projects

```markdown
# dirac-robotic

Robot control using DIRAC with polyglot packages.

## Installation

This project uses both JavaScript and Python packages.

### Quick Setup
```bash
npm run setup
```

### Manual Setup

1. Install JavaScript dependencies:
```bash
npm install
```

2. Set up Python environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Dependencies

### JavaScript (npm)
- `dirac-ear@^1.0.0` - Audio processing in Node.js

### Python (pip)
- `dirac-arm>=1.0.0` - Robotic arm control with numpy/scipy
- `numpy>=1.24.0` - Numerical computing
- `scipy>=1.10.0` - Scientific computing

## Usage

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the robot control script
dirac src/robot.di
```

## Development

### Running Tests

JavaScript tests:
```bash
npm test
```

Python tests:
```bash
python -m pytest
```

### Adding Dependencies

**JavaScript:**
```bash
npm install --save package-name
```

**Python:**
```bash
pip install package-name
echo "package-name>=version" >> requirements.txt
```

## Architecture

This project demonstrates DIRAC's polyglot capabilities:
- JavaScript packages handle real-time audio processing
- Python packages handle mathematical computations
- DIRAC orchestrates both seamlessly

See [POLYGLOT-PACKAGES.md](../dirac-python/POLYGLOT-PACKAGES.md) for more details.
```

## Best Practices

### 1. Document Language Requirements
Clearly state which languages are needed in README.

### 2. Provide Setup Scripts
Don't make users figure out multi-language setup manually.

### 3. Use Virtual Environments
Always use Python venv to avoid system-wide conflicts.

### 4. Pin Versions
Use specific versions in `requirements.txt` for reproducibility:
```txt
dirac-arm==1.2.3  # Not >=1.0.0
numpy==1.24.2
```

### 5. .gitignore Both Ecosystems
```gitignore
# JavaScript
node_modules/
package-lock.json

# Python
venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
```

### 6. CI/CD for Both Languages
```yaml
# .github/workflows/test.yml
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      # JavaScript setup
      - uses: actions/setup-node@v2
        with:
          node-version: '18'
      - run: npm install
      - run: npm test
      
      # Python setup
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest
```

## Common Patterns

### Pattern 1: JavaScript for I/O, Python for Compute
```xml
<import src="dirac-http" />    <!-- JS: Fast HTTP -->
<import src="dirac-numpy" />   <!-- Python: Math -->

<!-- Fetch data (JavaScript) -->
<defvar name="data">
  <HTTP_GET url="https://api.example.com/data.json" />
</defvar>

<!-- Process data (Python) -->
<eval name="result" language="python">
  import numpy as np
  arr = np.array(data)
  result = np.mean(arr)
</eval>
```

### Pattern 2: Python for ML, JavaScript for Web
```xml
<import src="dirac-express" />  <!-- JS: Web server -->
<import src="dirac-torch" />    <!-- Python: PyTorch -->

<!-- Train model (Python) -->
<eval name="model" language="python">
  import torch
  model = train_model(dataset)
  result = model.state_dict()
</eval>

<!-- Serve via API (JavaScript) -->
<EXPRESS_POST path="/predict">
  <TORCH_PREDICT model="${model}" input="${request.body}" />
</EXPRESS_POST>
```

## Future Considerations

### Multiple Python Versions
Support for different Python versions:
```
dirac-robotic/
  venv-py39/     # Python 3.9 for legacy code
  venv-py311/    # Python 3.11 for new code
```

### Other Languages
This pattern extends to any language:
- **Go**: Use `go.mod` + `go.sum`
- **Ruby**: Use `Gemfile` + `Gemfile.lock`
- **Rust**: Use `Cargo.toml`

### Containerization
Use Docker to bundle all dependencies:
```dockerfile
FROM node:18
RUN apt-get update && apt-get install -y python3 python3-venv

COPY package.json requirements.txt ./
RUN npm install && python3 -m venv venv && venv/bin/pip install -r requirements.txt

COPY . .
CMD ["dirac", "src/robot.di"]
```

## Summary

**Key Principles:**
1. ✅ Use standard package managers for each language (npm, pip)
2. ✅ Maintain separate dependency files (`package.json`, `requirements.txt`)
3. ✅ DIRAC runtime checks both `node_modules/` and `site-packages/`
4. ✅ Provide setup scripts for easy installation
5. ✅ Document multi-language requirements clearly

This approach follows industry standards for polyglot projects (e.g., ML projects using Node.js + Python) and integrates naturally with existing tooling.
