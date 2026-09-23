# Voice Fleet development instructions

- Write all AI prompts, agent instructions, skill instructions, and implementation tasks in English. User-facing discussion and explanatory documentation may remain Ukrainian.
- Read the current task, docs/product.md, docs/architecture.md, and docs/decisions.md.
- The product serves one organization per independent installation. Do not build a shared multi-tenant SaaS.
- Centralized AI server management, coding agents, DNS, and VPN management are outside the current scope.
- Implement one backlog task at a time. Do not weaken acceptance criteria to make tests pass.
- Preserve user changes. Inspect git diff before finishing.
- Document changes to contracts, configuration, and migrations.
- Verify SDK usage against documentation for the selected version; pin dependencies.
- Published configurations are immutable. Each session pins its configuration version at startup.
- Enforce authorization and tool permissions on the server.
- Never commit secrets, real call recordings, or private client data.
- Regular tests must not require paid APIs. Run live evaluations separately.
- Label mocks explicitly. Never present a test adapter as a working external integration.
- Run appropriate checks before finishing and report actual results and limitations.
- Final reports must include changes, checks, failed or unexecuted checks, and manual acceptance steps.
- Publishing, plugin installation, and production deployment are not automatically included in implementation tasks.
- No executable build or test commands exist yet. Add them in VF-001.
