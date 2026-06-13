---
name: file-operations
description: Safely read and write files following sandbox rules
---

## What I do
- Read file contents with read_file
- Create or overwrite files with write_file
- Run commands to navigate and inspect directories
- Respect sandbox boundaries

## When to use me
Use this when you need to work with files: reading existing code, creating new files, or modifying project content.

## Workflow
1. First inspect the project structure if unfamiliar
2. Read relevant files before making changes
3. Create or modify files with write_file
4. Verify changes by reading the file back

## Rules
- All file operations are sandboxed to the workspace directory
- Use run_command with ls/dir to explore directory structure
- Read before you write - always understand existing content first
