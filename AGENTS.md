# Repository Guidelines

## Project Structure & Module Organization

This repository is currently an empty scaffold: no source, tests, or assets are present. Keep application code in a clearly named source directory (for example, `src/`), tests in `tests/` or alongside their modules, and static files in `assets/`. Update this guide when the project’s actual layout and framework are established.

## Build, Test, and Development Commands

No build system or development commands are configured yet. Once a package manager or build tool is added, document its standard setup, local run, test, and build commands here. Run commands from the repository root, and keep generated output out of source directories where practical.

## Coding Style & Naming Conventions

There are no language-specific conventions or formatter configuration in the scaffold. Follow the formatter and linter selected by the project, use consistent indentation, and prefer descriptive names that match the language’s usual casing (for example, `PascalCase` for many type names and `camelCase` for many functions). Avoid adding a second formatter or linter without a project need.

## Testing Guidelines

No test framework or coverage requirement is configured. Add tests with the framework chosen for the codebase; use names that describe behavior (for example, `posting-schedule.test.ts`). Include the command to run the relevant tests whenever test tooling is introduced.

## Commit & Pull Request Guidelines

Git history is not available in this scaffold, so no existing commit convention can be confirmed. Use concise, imperative commit subjects (such as `Add posting queue`) and keep each change focused. Pull requests should explain the change and its rationale, list validation performed, link related issues when available, and include screenshots for user-facing changes.

## Security & Configuration

Keep credentials and private configuration out of version control. Provide safe example configuration with placeholders, and document required environment variables without including real secrets.
