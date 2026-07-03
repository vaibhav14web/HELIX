# 03_SAD.md

# System Architecture Document (SAD)

## Helix - A Context-Aware Personal Cognitive Operating System

Version: 2.0

Status: Active Development

Owner: Vaibhav Kumar Singh

Parent Documents:

00_VISION.md

01_HSD.md

02_PRD.md

---

# 1. Purpose

This document defines how Helix is engineered internally.

It answers:

* How is the system structured?
* What layers exist?
* What modules exist?
* How do modules communicate?
* How is data stored?
* How are resources managed?
* How is power consumption controlled?

---

# 2. Architectural Philosophy

Helix is an event-driven cognitive system.

Everything should be:

* Independent
* Replaceable
* Testable
* Observable
* Power efficient

Helix is NOT microservices.

Helix is NOT a monolith.

Helix is a Modular Cognitive System.

---

# 3. Layer Architecture

```text
User Layer

↓

Foundation Layer

↓

Core AI Layer

↓

Memory Layer

↓

Context Layer

↓

Action Layer

↓

Companion Layer
```

Rules:

No layer may bypass another layer.

Everything communicates through Event Bus.

---

# 4. User Layer

Responsibilities:

User interaction.

Components:

Voice

UI

Notifications

Permission Dialogs

Outputs:

User Intent

Inputs:

System Responses

---

# 5. Foundation Layer

Purpose:

Provide stability.

Modules:

Config Manager

Event Bus

Logger

Permission Manager

Storage Manager

Rules:

Always active.

Minimal resource consumption.

Must boot first.

Target:

CPU <1%

RAM <300MB

---

# 6. Core AI Layer

Purpose:

Convert user input into intelligent output.

Modules:

Wake Word Engine

Voice Engine

LLM Engine

Conversation Engine

Rules:

No continuous GPU usage.

Low latency mandatory.

---

# 7. Memory Layer

Purpose:

Long term cognition.

Modules:

Conversation Memory

Preference Memory

Work Memory

Explainability Engine

Rules:

Archive old data.

Avoid memory explosion.

Keep only useful information active.

---

# 8. Context Layer

Purpose:

Understand current environment.

Modules:

Browser Engine

Project Engine

File Intelligence Engine

System Monitor Engine

Context Aggregator

Rules:

Observe intelligently.

No aggressive scanning.

---

# 9. Action Layer

Purpose:

Execute approved actions.

Modules:

Automation Engine

Planner Engine

Productivity Engine

Rules:

Permission system cannot be bypassed.

---

# 10. Companion Layer

Purpose:

Provide specialized intelligence.

Modules:

Coding Companion

Learning Companion

Future Companions

Rules:

Silent by default.

Notification first.

Never interrupt unnecessarily.

---

# 11. Event Bus Architecture

Communication Standard:

Publisher

↓

Event Bus

↓

Subscribers

Every event contains:

event_id

timestamp

source

event_type

priority

payload

correlation_id

Rules:

No module imports another module directly.

---

# 12. Power Architecture

Power efficiency is mandatory.

Strategies:

Event Driven Systems

Lazy Loading

Model Unloading

Sleep Inactive Modules

Smart Scheduling

Batch Operations

No aggressive polling

---

# 13. Runtime Resource Allocation

Foundation Layer

CPU <1%

RAM <300MB

Core AI Layer

CPU <30%

RAM <3GB

VRAM <5GB

Memory Layer

CPU <5%

RAM <500MB

Context Layer

CPU <5%

RAM <500MB

Action Layer

CPU <20%

RAM <500MB

Companion Layer

CPU <5%

RAM <500MB

---

# 14. Storage Architecture

Laptop SSD

Runtime Storage

Stores:

Source Code

Models

Databases

Embeddings

Indexes

Configs

Caches

External SSD

Cold Storage

Stores:

Backups

Logs

Snapshots

Archived Memories

Research Datasets

Exports

Forbidden:

Running models

Running databases

Running vector stores

Running active memory

---

# 15. Hardware Optimization Rules

Hardware:

Windows 11

Intel i5-12450H

RTX3050 6GB

16GB RAM

Rules:

GPU only wakes when required.

Heavy indexing only when idle.

Continuous microphone processing forbidden.

Continuous browser scanning forbidden.

Continuous file indexing forbidden.

---

# 16. Model Lifecycle

Load

↓

Use

↓

Save state

↓

Unload

Models should never remain loaded unnecessarily.

---

# 17. Project Awareness Architecture

Project Opened

↓

Detect Workspace

↓

Load History

↓

Load Previous Session

↓

Load Open Tasks

↓

Inject Context

↓

Assist User

---

# 18. Permission Architecture

Every action follows:

Observe

↓

Suggest

↓

Explain

↓

Permission

↓

Execute

↓

Report

No exceptions.

---

# 19. Performance Targets

Startup <20s

Voice Response <3s

Interrupt <500ms

Project Load <5s

Memory Retrieval <200ms

Notification <300ms

---

# 20. Failure Philosophy

Never fail silently.

Every error:

Catch

↓

Translate

↓

Explain

↓

Suggest Fix

↓

Log

---

# 21. AI Agent Contribution Rules

Before adding a feature, ask:

Does this improve productivity?

Does this reduce cognitive load?

Does this save time?

Does this fit hardware constraints?

Does this respect power efficiency?

If NO.

Do not implement.

---

# 22. Definition Of Good Architecture

Good architecture for Helix is:

Simple

Fast

Power Efficient

Maintainable

Research Oriented

Human Centered

Trustworthy

Local First
