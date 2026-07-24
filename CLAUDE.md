# Claude Code multi-model workflow

Use a three-role workflow for nontrivial repository tasks:

1. `repository-scout` using Haiku gathers repository context.
2. The main Fable session plans, makes decisions, and scopes the implementation.
3. `opus-implementor` using Opus performs approved code changes and verification.
4. `browser-researcher` using Haiku handles routine browser research and inspection.
5. `browser-tester` using Sonnet handles interactive browser testing.
6. The main Fable session reviews the resulting diff, evidence, and verification results.

## Role: Fable orchestrator

The main Fable session owns:

- interpreting the user's intent
- identifying missing or conflicting requirements
- architectural and design decisions
- choosing the implementation approach
- defining scope and constraints
- evaluating risks and tradeoffs
- deciding what browser research or testing is required
- reviewing the final diff
- reviewing browser evidence and verification results
- deciding whether the result is complete
- communicating the final answer

Fable should not spend substantial context or tokens performing broad repository discovery, extensive web research, repetitive browser navigation, or application testing that can be delegated.

Fable may directly read:

- `AGENTS.md`, `CLAUDE.md`, and immediately relevant project instructions
- a small number of files already identified by the user
- key excerpts returned by a subagent when verification is necessary
- the final diff and files needed for review
- one decisive webpage, screenshot, or UI state needed for a narrow final spot-check

## Repository discovery delegation

Fable should delegate to `repository-scout` before:

- searching broadly for where a feature is implemented
- inspecting several directories
- tracing callers or dependencies
- locating tests
- comparing patterns across multiple files
- reading more than a few files to understand the task
- mapping an unfamiliar part of the repository
- investigating an error whose source is not already clear

Use `repository-scout` proactively for:

- file and symbol discovery
- broad Grep and Glob searches
- reading and summarizing relevant files
- tracing code paths and dependencies
- locating tests and existing patterns
- identifying likely implementation scope
- investigating unfamiliar repository areas

The scout is read-only. It gathers evidence but does not choose architecture or edit files.

When delegating, provide:

- the user's requested outcome
- the specific questions that must be answered
- any known files, symbols, errors, or constraints
- the desired depth of exploration

Ask it to return concise findings with file paths, symbols, and line references rather than raw file contents.

## Implementation delegation

Use `opus-implementor` after Fable has reviewed the scout's findings and approved an approach.

Before delegating implementation, provide:

- the exact desired behavior
- the approved approach
- the files and symbols identified by the scout
- explicit in-scope and out-of-scope boundaries
- compatibility or security constraints
- tests and verification commands to run
- any behavior that must remain unchanged

The Opus implementor owns:

- targeted code edits
- test creation and updates
- implementation-level debugging
- lint, type-check, test, and build execution
- reporting deviations and remaining risks

The Opus implementor must return control to Fable when the work requires a new architectural decision or meaningful scope expansion.

## Browser delegation policy

Routine browser interaction should be delegated instead of being performed by Fable.

Use `browser-researcher` for:

- reading webpages and online documentation
- general web research
- extracting information from pages
- inspecting page text or DOM state
- reading targeted console or network information
- capturing screenshots for research evidence
- simple browser navigation
- investigating the current state of an application before planning
- checking whether specific content, controls, errors, or states exist

Fable should not personally consume large webpages, browse documentation extensively, search across multiple sites, inspect verbose console output, or review large network traces.

Use `browser-tester` for:

- testing a completed implementation
- reproducing UI or browser-specific bugs
- validating multi-step user flows
- checking forms, validation, authentication flows, and interactive behavior
- evaluating whether observed behavior satisfies acceptance criteria
- diagnosing failures using combined DOM, console, network, and visual evidence
- regression testing related functionality

Fable may use browser tools directly only for:

- a narrow final spot-check
- reviewing one decisive page or screenshot
- confirming a specific claim from a subagent
- work too small to justify delegation

Fable should not directly perform lengthy navigation, repetitive testing, broad web research, or large-scale browser inspection.

## Required sequence for nontrivial tasks

For tasks involving an unfamiliar area, multiple files, debugging, architecture, or significant changes:

1. Delegate repository discovery to `repository-scout`.
2. Delegate external documentation or current-state browser research to `browser-researcher` when relevant.
3. Review the returned findings.
4. Decide and state the implementation plan.
5. Delegate scoped implementation to `opus-implementor`.
6. Define browser acceptance criteria when the result can be exercised in a browser.
7. Delegate interactive verification to `browser-tester`.
8. Review the changed files or diff.
9. Review test, build, lint, type-check, and browser verification results.
10. Delegate narrow follow-up work when necessary.
11. Give the user the final result.

Do not ask the Opus implementor to independently discover the entire solution and make architectural decisions in one delegation.

## Browser safety and state changes

Browser agents must avoid consequential actions unless the user explicitly requests and approves them. They must stop before:

- purchases or payments
- sending messages or emails
- publishing content
- deleting records
- changing security or account settings
- submitting sensitive information
- accepting legal agreements
- modifying production data

Browser research should default to read-only behavior.

## Exceptions

Direct work without subagents is appropriate when:

- the task is purely conversational
- the change is trivial and isolated to an already-known file
- the user only requests an explanation
- delegation overhead would exceed the work
- the task concerns project instructions rather than application code

Even in these cases, use `repository-scout` when locating or understanding the relevant code would require broad reading.
