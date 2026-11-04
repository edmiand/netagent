# Claude Project knowledge bundle

Files to attach to a claude.ai Project as project knowledge. They are a condensed, self-contained
snapshot of the repo docs, written for a Claude that can't see the code. Don't attach this README.

| File | Built from |
|---|---|
| 01-netagent-overview.md | CLAUDE.md, README.md, the code (tools, specialists, settings) |
| 02-setup-and-operations.md | README.md, CLAUDE.md |
| 03-hedera-audit-trail.md | HEDERA.md (condensed) |
| 04-hedera-demo-script.md | HEDERA_DEMO.md (nearly verbatim) |
| 05-eqty-lineage.md | CLAUDE.md "EQTY lineage manifests" |
| 06-roadmap.md | ROADMAP.md plus a shipped/partly-shipped status block |
| 07-open5gs-knowledge-base.md | knowledge_base/*.md, merged (headings demoted one level) |

Left out on purpose: chainlit.md (the in-app welcome page; duplicates file 1), the host-Mac IP,
usernames and home paths, the branding logo name, Hedera account details.

This is a snapshot (2026-11-04, commit 9d501a7) and drifts as the repo changes; regenerate it
rather than editing it by hand when the source docs change.
