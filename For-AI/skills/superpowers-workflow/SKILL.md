---
name: superpowers-workflow
description: Apply a focused, evidence-led coding workflow for a feature, bug fix, refactor, or review.
---

# Superpowers-derived coding workflow

Use this task-conditional workflow for a focused software change. This local
guide summarizes selected practices; it is not the upstream Superpowers
plugin, does not install it, and does not make its commands available.

Reference: [obra/superpowers](https://github.com/obra/superpowers), reviewed
2026-10-19. Consult the current upstream project when exact plugin behavior or
installation matters.

## Workflow

1. Establish the requested outcome, relevant project authority, constraints,
   and acceptance evidence. For a new or uncertain design, clarify intent and
   review a concise design before implementation; keep tiny changes in the
   conversation when no durable design artifact is useful.
2. For multi-step work, write a short ordered plan with concrete paths and a
   check for each task. Execute it inline or in isolated work, following the
   repository's ownership and delegation rules.
3. For code changes, use a failing regression check first when tests are
   requested or required by the applicable instructions and a meaningful test
   can observe the behavior. Respect higher-priority instructions and the
   repository's established verification policy.
4. Make the smallest complete change. For a bug, trace the cause and affected
   callers before choosing the fix. Use the project's debugging, domain, and
   verification routes when they apply.
5. Review the finished diff against the request and plan. Run the applicable
   checks, report what they observed, and leave uncovered evidence explicit.
   Use code review and branch-finishing procedures when required by the
   repository or useful for the change.

Load installed skills such as `brainstorming`, `writing-plans`,
`test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `requesting-code-review`, and
`finishing-a-development-branch` only when available and relevant. A skill
name in this guide does not prove that skill is installed or that it ran.
