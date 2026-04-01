# Figma Tooling Comparison — Official MCP vs Console MCP

Date: 2025-03-25

## Overview

Two MCP servers, complementary roles. Both connected and tested against Dank (Experimental).

### Official Figma MCP (by Figma, Inc.)
- 16+ tools, closed source, metered/rate-limited
- Plugin API + REST API
- Key tool: use_figma — arbitrary sync JavaScript execution via Plugin API
- Strengths: Code Connect, get_design_context (code gen), generate_figma_design (web capture)

### Figma Console MCP (by Southleft)
- 90+ tools, open source (MIT), free/unlimited
- Plugin API via Desktop Bridge (WebSocket) + REST API
- Key tools: figma_setup_design_tokens, figma_batch_create_variables, figma_audit_design_system, figma_lint_design
- Strengths: Design system management, batch operations, real-time awareness

## Tested Capability Matrix

| Capability | Official MCP | Console MCP | Winner |
|---|---|---|---|
| Variable creation (single) | OK via use_figma | OK dedicated tool | Tie |
| Variable creation (batch) | Hand-rolled loops (20/call) | figma_batch_create_variables (100/call) | Console |
| Atomic token system setup | Must script manually | figma_setup_design_tokens (1 call) | Console |
| Bind variable to node | OK | OK via figma_execute | Tie |
| Tree structure read | get_metadata (XML, 2.4M chars) | figma_get_file_data (JSON, verbosity controls) | Console |
| Property extraction (bulk) | use_figma sync traversal | figma_execute requires async | Official |
| Design system kit export | N/A | OK but published libraries only | Console when applicable |
| Design audit | N/A | figma_audit_design_system (scored) | Console |
| Lint | N/A | figma_lint_design | Console |
| Code generation context | get_design_context | N/A | Official |
| Code Connect | First-party | No | Official |
| Real-time selection tracking | No | Yes | Console |
| Rate limits | Yes (plan-dependent) | No | Console |
| Cost | Will be metered | Free | Console |

## Recommended Usage

- Console MCP for: token/variable CRUD, audit, lint, batch operations, high-volume work
- Official MCP for: use_figma bulk reads (sync simpler), code gen, Code Connect
- Both complement each other — no need to choose

## Setup Reference

- Console MCP config: ~/Library/Application Support/Claude/claude_desktop_config.json
- Desktop Bridge plugin: /Users/mattpacione/.figma-console-mcp/plugin/manifest.json
- Console MCP port: 9224 (9223 occupied)
- NOTE: PAT token needs rotation (was shared in plain text during setup)
