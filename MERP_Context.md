# MERP — Context Document

**MERP** = **Managed Enterprise Resilience Platform**

A unified, AI-native operations platform built to replace the patchwork of legacy MSP and enterprise IT tools (ConnectWise, IT Glue, ServiceNow CMDB, Datto, etc.) with five integrated products sitting on top of a shared intelligence layer.

**Tagline:** *Your infrastructure. Self-managing.*

---

## The One-Line Pitch

Five AI-native products. One unified platform. AXO heals, PRISM watches, AEGIS protects, COOP recovers, OTTO patches — running 24/7 so the team doesn't have to.

---

## The Five Products

Each product solves a distinct operational problem. Together they form a closed-loop autonomous IT system, each with an animal mascot for brand identity.

| Product | Mascot | Domain | What It Does |
|---------|--------|--------|--------------|
| **AXO** 🦎 | Axolotl | Self-healing | Detects infrastructure alerts, classifies them with Claude AI, writes remediation scripts, and fixes issues automatically — before clients notice. The execution engine and orchestrator. |
| **PRISM** 🦉 | Vigil Owl | Observability | Full-stack observability across metrics, logs, and traces. AIOps noise reduction. SLO/SLA tracking. |
| **AEGIS** 🦔 | Pavo Hedgehog | Security | Unified threat detection, CSPM, SOAR, and continuous compliance (NIST, HIPAA, PCI DSS, DORA) with automated evidence collection. |
| **COOP** 🦝 | Remi Raccoon | Continuity / DR | Enterprise disaster recovery governance, multicloud failover orchestration, and continuous DR validation. RTO/RPO verified, not just promised. (Also referred to as Remi in some docs.) |
| **OTTO** 🦦 | Otto Otter | Patching | Proactive patch orchestration, configuration baseline enforcement, and software inventory. |

---

## The Foundation — Platform Intelligence Layer (PIL)

The PIL is the shared knowledge graph sitting beneath all five products. It is the single source of truth for every device, client, location, relationship, SOP, and current state across the entire platform.

**Without PIL:** every product re-discovers the same facts about the same devices. No shared memory, no shared context, every product starts from zero.

**With PIL:** one change to a device file propagates to every product instantly. No shadow copies.

### PIL Architecture

```
MERP PRODUCTS
  AXO    PRISM    AEGIS    COOP    OTTO
    │       │       │        │       │
    └───────┴───────┴────────┴───────┘
                    │
                    ▼
        PLATFORM INTELLIGENCE LAYER
          ┌─────────────────────┐
          │   PIL MCP Server    │  ← Tools callable by Claude + AXO
          │   (Python MCP SDK)  │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  GraphQL Middleware │  ← Unified query API
          │  (FastAPI+Strawberry)│
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │   Markdown Vault    │  ← Flat files in Git
          │   (python-frontmatter) Also the Obsidian vault
          └─────────────────────┘
```

### What the PIL Knows
- **Devices / CIs** — every server, switch, firewall, endpoint
- **Clients / Tenants** — ownership, contacts, SLA terms
- **Locations** — physical and logical
- **Relationships** — dependency chains (this switch supports these servers)
- **SOPs / Runbooks** — how to fix or manage each device type and issue category
- **Current State** — live status, updated after every AXO action

### What the PIL Replaces
- **IT Glue** — MSP documentation platform, replaced by Markdown files + wikilinks at zero ongoing cost
- **ServiceNow CMDB** — enterprise CI database, replaced by Git repo + GraphQL middleware (no $100+/user/month)

---

## The Strategic Principle — "Pay Only for Execution Risk"

The economic core of MERP. Most MSP tickets are not ambiguous — a disk at 95% gets a cleanup script, a stopped MSSQL service gets a restart. These don't need a frontier AI model. They need fast, reliable pattern matching, which AXO's rule engine already does.

### Three-Tier Intelligence
1. **AXO Rule Engine** (free) — handles the routine ~85% via pattern matching
2. **Ollama (local LLM)** — handles ambiguous tickets cheaply on local hardware
3. **Claude API** — called *only* at the execution gate, when AXO is about to run a script on a production system. That's when the cost is justified.

Claude is the brain at the gate. Ollama is the cheap brain for routine decisions. The rule engine handles everything else.

---

## Token Economics

- **Full MERP AI cost:** ~$28/day for 10,000 alerts/day across all five products
- **Per-alert cost:** $0.0028 — including triage, runbook execution, threat analysis, and compliance evidence

### Daily Breakdown (10k alerts)
| Product | Workload | Cost |
|---------|----------|------|
| AXO | Alert triage + runbooks | $11.10 |
| AEGIS | Threat + compliance | $8.00 |
| PRISM | Root cause summaries | $4.40 |
| OTTO | Patch risk scoring | $2.50 |
| COOP | DR analysis + reports | $2.00 |

---

## Target Performance Metrics
- **Auto-fix rate:** ~91%
- **Mean time to resolve:** <3 minutes (~2m 47s)
- **SLO compliance:** 99.94%
- **Cost per alert:** $0.0028

---

## Roadmap (14 months)

| Phase | Timeline | Focus |
|-------|----------|-------|
| **01** | Now → Month 3 | **AXO Foundation** — FastAPI + ScienceLogic live, Claude triage engine, JWT + Vault, ConnectWise tickets, Tauri desktop (Mac) |
| **02** | Month 4–6 | **PRISM + AEGIS MVP** — OTel collector + ClickHouse, SLO/SLA engine, Wazuh + OpenSearch SIEM, CSPM via Prowler, AEGIS ↔ AXO bridge |
| **03** | Month 7–10 | **OTTO + COOP/DR** — Patch orchestration, config baselines, DR activation, RTO/RPO live measurement, MCP integration layer |
| **04** | Month 11–14 | **Full MERP Suite** — Cross-product war room, natural language console, client self-service portal, multicloud cost intelligence, white-label MSP edition |

---

## Technology Stack
- **Backend:** Python, FastAPI, Strawberry (GraphQL)
- **Data layer:** Flat Markdown files in Git (doubles as Obsidian vault), python-frontmatter
- **Telemetry:** OpenTelemetry collector → ClickHouse
- **Security:** Wazuh + OpenSearch (SIEM), Prowler (CSPM)
- **Monitoring source:** ScienceLogic
- **Ticketing:** ConnectWise
- **Secrets:** HashiCorp Vault
- **LLM gateway:** Ollama (local, routine) + Claude API (gate, high-risk)
- **Integration protocol:** MCP (Model Context Protocol)
- **Desktop client:** Tauri (Mac first)

---

## What MERP Explicitly Is NOT

These were considered and rejected — do not reintroduce:

- **No Notion** — third-party SaaS, per-seat pricing, vendor lock-in. Replaced by Markdown vault.
- **No n8n** — visual workflow tool. AXO's `orchestrator.py` already does this in Python.
- **No pgvector** — semantic SOP lookup. Data is already structured; tag matching is enough until proven otherwise.
- **No Claude-for-every-ticket** — too expensive ($72–120/month at low volume), creates API dependency on trivial alerts. Reserved for the execution gate.
- **No custom AI triage engine built from scratch** — replaced by the three-tier rule engine + Ollama + Claude API.

---

## How the Pieces Fit Together (End-to-End Flow)

1. **PRISM** ingests alerts from ScienceLogic and other sources.
2. **AXO** picks up the alert, queries the **PIL** for device context (owner, dependencies, SOPs, current state).
3. **AXO's rule engine** handles known patterns directly. Ambiguous ones go to Ollama. High-risk executions hit the Claude API gate.
4. **AXO** executes the runbook, updates ticket in ConnectWise, writes new state back to the PIL.
5. **AEGIS** continuously monitors compliance posture using the same PIL data.
6. **OTTO** plans patches against the same device inventory.
7. **COOP** validates DR readiness against the same topology.

One vault. One graph. Five products. Zero data duplication.

---

## Positioning Summary

MERP positions itself as the AI-native replacement for the traditional MSP/enterprise IT stack:

- Instead of **IT Glue + ServiceNow CMDB** → the PIL (Markdown + Git + GraphQL)
- Instead of **Datadog + Splunk** → PRISM
- Instead of **CrowdStrike + Qualys + Vanta** → AEGIS
- Instead of **Zerto + Veeam DR Orchestrator** → COOP
- Instead of **Automox + Tanium** → OTTO
- Instead of **PagerDuty + manual L1/L2** → AXO

White-label MSP edition planned for Phase 4 — sell MERP as a platform to other MSPs.
