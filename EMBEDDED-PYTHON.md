# Embedded Python in DIRAC Packages

This document explains how DIRAC packages can embed Python code and automatically manage Python dependencies through npm.

## Overview

DIRAC's polyglot architecture allows packages to contain embedded Python code that executes within DIRAC scripts using `<eval language="python">`. The Node.js-based DIRAC runtime shells out to Python for these code blocks, enabling seamless integration of Python libraries without requiring users to manually manage Python dependencies.

## Architecture

### File-Based Queue Orchestration (dirac-flow)

DIRAC uses **file-based message queues** for workflow orchestration, not HTTP microservices:

```
dirac-robotic/
  package.json              # npm dependencies only
  flows/
    master.di               # Orchestrator (defines queues)
  workers/
    ear-worker.di           # JavaScript logic
    arm-worker.di           # Embedded Python code
    arduino-worker.di       # System commands
  queues/                   # File-based message queues
    audio-requests/
    movements/
    results/
```

### How It Works

1. **Master defines queues and subscriptions**
2. **Workers are simple DIRAC scripts** that read stdin, write stdout
3. **Workers can embed Python** via `<eval language="python">`
4. **Communication via file queues**, not HTTP

## Example: dirac-arm Package

### Package Structure

```
dirac-arm/
  package.json
  requirements.txt          # Python dependencies
  lib/
    arm-worker.di          # DIRAC script with embedded Python
```

### lib/arm-worker.di

```xml
<dirac>
  <!-- Read command from queue (via stdin) -->
  <stdin name="command" />
  
  <subroutine name="move-arm" param-x="number" param-y="number" param-z="number">
    <!-- Python for complex robotics math -->
    <eval name="angles" language="python">
import numpy as np
from scipy.spatial.transform import Rotation

# Inverse kinematics calculation
l1, l2 = 10.0, 8.0
distance = np.sqrt(x**2 + y**2)
theta2 = np.arccos((distance**2 - l1**2 - l2**2) / (2 * l1 * l2))
theta1 = np.arctan2(y, x) - np.arctan2(l2 * np.sin(theta2), l1 + l2 * np.cos(theta2))

result = {
    'shoulder': np.degrees(theta1),
    'elbow': np.degrees(theta2)
}
    </eval>
    
    <!-- JavaScript for device communication -->
    <eval name="moveResult">
      const { SerialPort } = require('serialport');
      const port = new SerialPort('/dev/ttyUSB0');
      port.write(`M ${angles.shoulder} ${angles.elbow}\n`);
      return 'sent';
    </eval>
    
    <!-- Output result to queue -->
    <output><result status="${moveResult}" angles="${angles}" /></output>
  </subroutine>
  
  <execute><variable name="command" /></execute>
</dirac>
```

## Automatic Python Dependency Installation

### The Problem

When a user installs a DIRAC package that contains embedded Python:
```bash
npm install dirac-arm
```

The Python dependencies (numpy, scipy) are not automatically installed because npm doesn't manage Python packages.

### The Solution: postinstall Script

**dirac-arm/package.json:**
```json
{
  "name": "dirac-arm",
  "version": "1.0.0",
  "description": "Robotic arm control with embedded Python",
  "main": "lib/arm-worker.di",
  "scripts": {
    "postinstall": "python3 -m pip install --user -r requirements.txt --quiet || echo '\n⚠️  Warning: Could not auto-install Python packages.\nPlease run manually: pip install -r requirements.txt\n'"
  },
  "files": [
    "lib/",
    "requirements.txt"
  ]
}
```

**dirac-arm/requirements.txt:**
```txt
numpy>=1.24.0
scipy>=1.10.0
```

### How It Works

1. User runs: `npm install dirac-arm`
2. npm downloads the package
3. npm runs the `postinstall` script automatically
4. The script executes: `python3 -m pip install --user -r requirements.txt`
5. Python packages are installed automatically
6. If installation fails, user gets a helpful warning message

### User Experience

```bash
$ npm install dirac-arm

> dirac-arm@1.0.0 postinstall
> python3 -m pip install --user -r requirements.txt --quiet

Successfully installed numpy-1.24.2 scipy-1.10.1

added 1 package
```

**Zero manual steps!** User doesn't need to know Python is involved.

## Best Practices

### 1. Use python3 -m pip

```bash
python3 -m pip install ...
```

More reliable than `pip` command directly. Works across platforms.

### 2. Use --user Flag

```bash
pip install --user ...
```

Installs to user directory, no sudo needed. Avoids permission errors.

### 3. Use --quiet Flag

```bash
pip install --quiet ...
```

Reduces noise during npm install. Only shows errors.

### 4. Graceful Failure

```bash
... || echo '\n⚠️  Warning: ...\n'
```

If pip fails, show helpful message instead of breaking npm install.

### 5. Include requirements.txt in Package

**package.json:**
```json
{
  "files": [
    "lib/",
    "requirements.txt"
  ]
}
```

Ensures `requirements.txt` is included when publishing to npm.

### 6. Document Python Requirements

**README.md:**
```markdown
## Requirements

- Python 3.9+
- pip (Python dependencies installed automatically via npm postinstall)
```

Even though installation is automatic, document the requirement.

## Complete Example: dirac-robotic Project

### Project Structure

```
dirac-robotic/
  package.json
  flows/
    master.di
  workers/
    ear-worker.di
    arm-worker.di
  queues/
```

### package.json

```json
{
  "name": "dirac-robotic",
  "version": "1.0.0",
  "dependencies": {
    "dirac-lang": "^0.1.32",
    "dirac-flow": "^1.0.0",
    "dirac-ear": "^1.0.0",
    "dirac-arm": "^1.0.0"
  },
  "scripts": {
    "start": "dirac flows/master.di"
  }
}
```

### Installation

```bash
cd dirac-robotic
npm install    # Installs all npm packages AND their Python dependencies
npm start      # Everything just works
```

### flows/master.di

```xml
<dirac>
  <import src="dirac-flow"/>
  
  <!-- Define queues -->
  <queue name="audio-requests" dir="./queues"/>
  <queue name="movements" dir="./queues"/>
  <queue name="results" dir="./queues"/>
  
  <!-- Subscribe workers to queues -->
  <subscribe queue="audio-requests" 
             worker="./workers/ear-worker.di" 
             output="movements"/>
  
  <subscribe queue="movements" 
             worker="./workers/arm-worker.di" 
             output="results"/>
  
  <!-- Trigger initial message -->
  <queue-send queue="audio-requests">
    <listen frequency="20000" duration="5" />
  </queue-send>
  
  <output>Flow started. Watching queues...</output>
</dirac>
```

### workers/arm-worker.di

```xml
<dirac>
  <stdin name="command" />
  
  <subroutine name="move-arm" param-x="number" param-y="number" param-z="number">
    <eval name="trajectory" language="python">
import numpy as np
result = calculate_inverse_kinematics(x, y, z)
    </eval>
    
    <system>arduino-cli board move --x ${x} --y ${y} --z ${z}</system>
    
    <output><result status="moved" trajectory="${trajectory}" /></output>
  </subroutine>
  
  <execute><variable name="command" /></execute>
</dirac>
```

## Advantages of This Architecture

### 1. **No Language Mixing in Dependencies**
- `package.json` only lists npm packages
- Python dependencies handled automatically
- No manual `pip install` steps

### 2. **Simple User Experience**
```bash
npm install    # One command
npm start      # Just works
```

### 3. **Workers are Just DIRAC Scripts**
- Not separate HTTP services
- No network overhead
- Simple stdin/stdout communication

### 4. **File-Based Queues**
- No HTTP/REST required
- Simple file I/O
- Easy debugging (inspect queue files)

### 5. **Language Freedom per Worker**
- Each worker can use appropriate language
- JavaScript for I/O, Python for math
- Mix freely within same script

### 6. **Clean Orchestration**
- Master script defines workflow
- Workers implement tasks
- Queues handle communication

## Multi-Language Execution

### JavaScript (Native)

```xml
<eval name="result">
  const data = [1, 2, 3, 4, 5];
  return data.reduce((a, b) => a + b, 0);
</eval>
```

### Python (Embedded)

```xml
<eval name="result" language="python">
import numpy as np
data = [1, 2, 3, 4, 5]
result = np.mean(data)
</eval>
```

### System Commands

```xml
<system name="result">
  ffmpeg -i input.mp4 -vf scale=640:480 output.mp4
</system>
```

### All Together

```xml
<dirac>
  <!-- Fetch data (JavaScript) -->
  <eval name="rawData">
    const response = await fetch('https://api.example.com/data');
    return await response.json();
  </eval>
  
  <!-- Process data (Python) -->
  <eval name="processed" language="python">
import numpy as np
import pandas as pd
df = pd.DataFrame(rawData)
result = df.describe().to_dict()
  </eval>
  
  <!-- Generate report (System command) -->
  <system>
    pandoc report.md -o report.pdf
  </system>
</dirac>
```

## Implementation Requirements

### For DIRAC Runtime

To support embedded Python, the DIRAC runtime needs:

1. **Multi-language eval support** (see TODO.md - High Priority)
2. **Language detection** in `<eval>` tag
3. **Variable passing** to Python subprocess
4. **Result capture** from Python stdout

### Example Implementation (src/tags/eval.ts)

```typescript
export async function executeEval(session: DiracSession, element: DiracElement) {
  const language = element.attributes.language || 'javascript';
  const code = element.text || '';
  const outputVar = element.attributes.name;
  
  let result;
  
  if (language === 'python') {
    // Pass session variables as JSON
    const varsJson = JSON.stringify(session.variables);
    const pythonCode = `
import json
variables = json.loads('''${varsJson}''')
${Object.keys(session.variables).map(k => `${k} = variables['${k}']`).join('\n')}

${code}

if 'result' in locals():
    print(json.dumps(result))
`;
    
    const { execSync } = await import('child_process');
    const output = execSync('python3 -c', {
      input: pythonCode,
      encoding: 'utf-8'
    });
    
    result = JSON.parse(output.trim());
    
  } else {
    // Existing JavaScript execution
    const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
    const fn = new AsyncFunction(...Object.keys(session.variables), code);
    result = await fn(...Object.values(session.variables));
  }
  
  if (outputVar) {
    setVariable(session, outputVar, result);
  }
}
```

## Platform Compatibility

### macOS
```bash
python3 -m pip install --user ...
```
✅ Works out of the box

### Linux
```bash
python3 -m pip install --user ...
```
✅ Works out of the box

### Windows
```bash
python -m pip install --user ...
```
✅ Works (use `python` not `python3`)

### Cross-Platform Script

```json
{
  "scripts": {
    "postinstall": "node scripts/install-python-deps.js"
  }
}
```

**scripts/install-python-deps.js:**
```javascript
const { execSync } = require('child_process');
const os = require('os');

const python = os.platform() === 'win32' ? 'python' : 'python3';
const cmd = `${python} -m pip install --user -r requirements.txt --quiet`;

try {
  execSync(cmd, { stdio: 'inherit' });
} catch (error) {
  console.log('\n⚠️  Python dependencies not installed automatically.');
  console.log(`Please run: ${python} -m pip install -r requirements.txt\n`);
}
```

## Troubleshooting

### Issue: pip not found
```
Error: command not found: python3
```

**Solution:** User needs to install Python 3.9+

### Issue: Permission denied
```
Error: Could not install packages due to an OSError: [Errno 13] Permission denied
```

**Solution:** The `--user` flag should prevent this. If it persists, user may need to fix their Python installation.

### Issue: Virtual environment conflicts
```
Warning: Package already installed in different environment
```

**Solution:** The `--user` flag installs to user directory, separate from venvs. This is intentional.

## Summary

**Key Principles:**

1. ✅ Workers are DIRAC scripts with embedded Python
2. ✅ Python dependencies auto-install via npm postinstall
3. ✅ User only runs `npm install` - no manual Python steps
4. ✅ File-based queues for orchestration (not HTTP)
5. ✅ Each worker can mix JavaScript and Python freely
6. ✅ Simple, clean, no language barrier for users

This architecture provides seamless polyglot capabilities without installation complexity or cognitive overhead.
