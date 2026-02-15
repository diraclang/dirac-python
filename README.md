# DIRAC Python Implementation

**Status**: 🚧 **Seeking Contributors** - This is a proposed Python port of the DIRAC language runtime.

## Overview

This project aims to create a Python-native implementation of DIRAC, a declarative language that combines XML-based syntax with imperative execution. While the reference implementation is in Node.js/TypeScript ([dirac-lang](https://github.com/diraclang/dirac-flow)), a Python port would unlock new possibilities in the ML/AI and data science ecosystems.

## Why Python?

The Python implementation would offer several unique advantages:

### 1. **Natural Fit for Braket Notation (`.bk` files)**
- Python's indentation-based syntax aligns perfectly with DIRAC's braket notation
- The braket syntax (`<tag|`, `|tag>`) uses indentation for scope, similar to Python
- More ergonomic than the JavaScript runtime for this syntax style

### 2. **ML/AI Ecosystem Integration**
- Seamless integration with PyTorch, TensorFlow, scikit-learn
- Native support for pandas, numpy data structures
- Perfect for LLM-driven agents in data science workflows

### 3. **Data Science Workflows**
- Direct access to Jupyter notebooks
- Integration with data visualization libraries (matplotlib, seaborn)
- Natural fit for exploratory data analysis

### 4. **Python Package Ecosystem**
- Use pip/PyPI for package management
- Access to vast scientific computing libraries
- Integration with existing Python tooling

## What Has Been Built (Node.js Implementation)

The reference implementation in Node.js/TypeScript includes:

### Core Features
- **XML-based syntax (`.di` files)**: Primary syntax using standard XML tags
- **Braket notation (`.bk` files)**: Alternative indentation-based syntax (Python would excel here)
- **LLM integration**: Seamless execution with Anthropic Claude, OpenAI, and local Ollama
- **Declarative + Imperative fusion**: Mix declarative tags with JavaScript execution blocks
- **Subroutines**: First-class functions with parameters and visibility control
- **Variables**: Dynamic variable system with substitution (`${varname}`)
- **Control flow**: Loops (`<loop>`, `<foreach>`, `<break>`), conditionals (`<if>`)
- **Module system**: Import/export with npm package resolution
- **Standard library**: Math, string operations, JSON/array manipulation

### Advanced Features
- **LLM recursive execution**: LLM responses can contain DIRAC code that executes seamlessly
- **Visible subroutines**: Factory pattern - nested subroutines persist after parent returns
- **Dynamic imports**: Variable substitution in import paths (`<import src="${pkg}" />`)
- **Session management**: State preservation across execution contexts
- **RPC support**: Remote execution via HTTP (dirac-remote package)

### Tag System (53 tests passing)
```xml
<dirac>           <!-- Root container -->
<output>          <!-- Print text/variables -->
<defvar>          <!-- Define variables -->
<variable>        <!-- Reference variables -->
<eval>            <!-- Execute JavaScript (Python in your port) -->
<subroutine>      <!-- Define callable functions -->
<call>            <!-- Invoke subroutines -->
<parameters>      <!-- Access function parameters -->
<import>          <!-- Load external modules -->
<llm>             <!-- LLM integration with execution mode -->
<loop>            <!-- Iteration with count -->
<foreach>         <!-- Iterate over collections -->
<break>           <!-- Exit loops early -->
<if>              <!-- Conditional execution -->
<stdin>           <!-- Read user input -->
<execute>         <!-- Run shell commands or external DIRAC scripts -->
```

### Package Ecosystem
- **dirac-json**: JSON parsing, array operations (push, pop, shift, get, length)
- **dirac-stdlib**: String and math utilities
- **dirac-http**: HTTP client operations
- **dirac-mongodb**: MongoDB integration
- **dirac-rdbms**: PostgreSQL, MySQL, SQLite (with pgvector for embeddings)
- **dirac-remote**: RPC and location-transparent execution
- **dirac-flow**: Observable-based orchestration with file queues
- **dirac-vision**: Video processing with worker pools

### Test Coverage
- 57 unit tests passing
- Tests for: imports, subroutines, loops, variables, LLM integration, stdin
- Test framework: Custom `.test.di` runner with assertions

## Python Implementation Goals

### Phase 1: Core Runtime
- [ ] XML parser for `.di` files
- [ ] Braket parser for `.bk` files (indentation-based)
- [ ] Variable system with substitution
- [ ] Subroutine registration and execution
- [ ] Basic tags: `<output>`, `<defvar>`, `<variable>`, `<eval>`
- [ ] Python code execution in `<eval>` blocks (instead of JavaScript)

### Phase 2: Control Flow & I/O
- [ ] Loops: `<loop>`, `<foreach>`, `<break>`
- [ ] Conditionals: `<if>` with test conditions
- [ ] Standard input: `<stdin>`
- [ ] Shell execution: `<execute>`

### Phase 3: Module System
- [ ] Import resolution for Python packages (pip)
- [ ] `<import>` tag with package.json equivalent (setup.py or pyproject.toml)
- [ ] Variable substitution in imports
- [ ] Relative path resolution

### Phase 4: LLM Integration
- [ ] `<llm>` tag with OpenAI/Anthropic/Ollama support
- [ ] Recursive execution of LLM-generated DIRAC code
- [ ] Context management and prompt building

### Phase 5: Package Ecosystem
- [ ] Port core packages to Python:
  - dirac-json → Python dicts, lists
  - dirac-stdlib → String/math utilities
  - dirac-mongodb → pymongo integration
  - dirac-postgres → psycopg2/asyncpg with pgvector

## Why This Matters

### Problem: Braket Notation + JavaScript = Awkward
The Node.js implementation uses JavaScript for `<eval>` blocks, but braket notation relies on strict indentation. Mixing indentation-sensitive syntax with indentation-agnostic JavaScript creates friction.

### Solution: Python + Braket = Natural Fit
Python's indentation-based syntax makes braket notation feel native. Example:

**Braket notation (`.bk` file):**
```
<output|Hello from DIRAC Python!|output>

<defvar|name|defvar>
  <stdin|What's your name? |stdin>
|defvar>

<output|Welcome, <variable|name|variable>!|output>

<subroutine|GREET|name:string|subroutine>
  <eval|result|eval>
    return f"Hello, {name}!"
  |eval>
  <output|<variable|result|variable>|output>
|subroutine>

<GREET|Alice|GREET>
```

This reads naturally in Python with preserved indentation for both DIRAC scope and Python code blocks.

## Technical Considerations

### Package Management
- Use `pip` for package distribution (instead of npm)
- Package naming: `dirac-json`, `dirac-stdlib`, etc. on PyPI
- Import resolution: Map `<import src="dirac-json" />` to Python package imports

### Module Structure
```
dirac-python/
  dirac/
    __init__.py
    runtime/
      parser.py          # XML and braket parser
      interpreter.py     # Tag execution engine
      session.py         # State management
    tags/
      output.py          # <output> implementation
      defvar.py          # <defvar> implementation
      eval.py            # <eval> for Python code
      llm.py             # <llm> LLM integration
      ...
    cli.py               # Command-line interface
```

### Python `<eval>` Execution
Instead of JavaScript:
```xml
<eval name="result">
  import pandas as pd
  df = pd.DataFrame({'a': [1, 2, 3]})
  return df.mean()
</eval>
```

### Virtual Environment Support
- Detect and use active Python virtual environments
- Respect `venv/`, `conda` environments
- Package imports resolve within environment context

## Compatibility with Node.js Version

### What Should Stay the Same
- Core language semantics (tags, subroutines, variables)
- XML syntax for `.di` files (fully compatible)
- Package API contracts (so libraries are portable conceptually)
- Test cases (port tests to validate behavior matches)

### What Can Differ
- `<eval>` contains Python instead of JavaScript
- Import resolution uses Python's module system
- Braket notation can be primary syntax (instead of secondary)
- Performance characteristics (Python vs Node.js)

## Getting Started (For Contributors)

### Prerequisites
- Python 3.10+
- pip or poetry for package management
- Familiarity with XML parsing (xml.etree or lxml)
- Understanding of AST manipulation (for braket parser)

### Suggested Architecture
1. **Parser**: Use `xml.etree.ElementTree` for XML, custom parser for braket
2. **Execution engine**: AST-based interpreter pattern
3. **Variable system**: Dictionary-based with scoping stack
4. **Eval**: Use `exec()` with controlled namespace
5. **Async**: Use `asyncio` for LLM calls and I/O

### Example: Minimal `<output>` Implementation
```python
# dirac/tags/output.py
def execute_output(session, element):
    """Execute <output> tag - print text with variable substitution."""
    text = element.text or ""
    
    # Process child elements (like <variable>)
    for child in element:
        if child.tag == 'variable':
            var_name = child.attrib.get('name')
            text += str(session.variables.get(var_name, ''))
        text += child.tail or ""
    
    # Variable substitution ${varname}
    import re
    def replace_var(match):
        return str(session.variables.get(match.group(1), ''))
    
    text = re.sub(r'\$\{(\w+)\}', replace_var, text)
    
    print(text)
    session.output.append(text)
```

## Current Status

**This is a greenfield project.** No code exists yet. We're looking for:

- **Primary maintainer**: Someone to architect and lead the Python implementation
- **Contributors**: Developers interested in parser design, language runtimes, ML integration
- **Testers**: Help port test cases and validate behavior matches Node.js version

## Resources

- **Reference implementation**: [dirac-lang (Node.js)](https://github.com/diraclang/dirac-flow)
- **npm package**: [dirac-lang on npm](https://www.npmjs.com/package/dirac-lang)
- **Documentation**: See Node.js README for detailed tag reference
- **Examples**: 50+ example `.di` files in Node.js repo showing patterns

## Questions?

Open an issue to discuss:
- Architecture decisions
- API design
- Python-specific features
- Compatibility concerns
- Braket notation parsing strategies

## License

Same as parent project: [License TBD - check main repo]

---

**Ready to contribute?** Fork this repo and start with the core parser! The Node.js implementation took ~6 months to reach v0.1.32 with 57 tests. Let's see how fast we can achieve parity in Python.
