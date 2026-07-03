# 06_ADR.md

# Architecture Decision Records (ADR)

## Helix - A Context-Aware Personal Cognitive Operating System

Version: 2.0

Status: Active Development

Owner: Vaibhav Kumar Singh

Parent Documents:

00_VISION.md

01_HSD.md

02_PRD.md

03_SAD.md

04_CFD.md

05_UI.md

---

# Purpose

This document records every important architectural decision.

The purpose is to eliminate repeated decision making.

Every decision must answer:

What was decided?

Why was it decided?

What alternatives existed?

Why were alternatives rejected?

What are the consequences?

---

# Decision Template

Decision ID:

Title:

Status:

Context:

Decision:

Alternatives:

Consequences:

Review Date:

---

# ADR-001

Title:

Project Category

Status:

Accepted

Context:

The project needs proper academic positioning.

Decision:

Helix will be positioned as a Personal Cognitive Operating System (PCOS).

Alternatives:

AIOS

Jarvis Clone

AI Agent Platform

Rejected Because:

Too generic.

Consequences:

Project becomes research oriented.

---

# ADR-002

Title:

Single User System

Status:

Accepted

Decision:

Helix will only support one user.

Alternatives:

Multi User

Rejected Because:

Adds unnecessary complexity.

Consumes more resources.

Consequences:

Personalization becomes stronger.

---

# ADR-003

Title:

Local First Architecture

Status:

Accepted

Decision:

Helix must work without internet.

Alternatives:

Cloud First

Hybrid First

Rejected Because:

Privacy concerns.

Cost concerns.

Dependency concerns.

Consequences:

Higher engineering complexity.

Better privacy.

---

# ADR-004

Title:

Permission First Architecture

Status:

Accepted

Decision:

Every action requires permission.

Alternatives:

Autonomous agents.

Rejected Because:

Reduces trust.

Consequences:

Higher safety.

---

# ADR-005

Title:

Windows Only

Status:

Accepted

Decision:

Primary platform is Windows 11.

Alternatives:

Cross Platform.

Rejected Because:

Scope expansion.

Consequences:

Faster development.

---

# ADR-006

Title:

Hardware Constraints

Status:

Accepted

Hardware:

Intel i5-12450H

RTX3050 6GB

16GB RAM

Decision:

Architecture must optimize for constrained hardware.

Alternatives:

High End Workstations.

Rejected Because:

Unrealistic deployment target.

Consequences:

Power optimization mandatory.

---

# ADR-007

Title:

External SSD Policy

Status:

Accepted

Decision:

External SSD is cold storage only.

Stores:

Backups

Archives

Logs

Research datasets

Forbidden:

Models

Databases

Embeddings

Memory

Indexes

Reason:

USB bottleneck.

---

# ADR-008

Title:

Event Driven Architecture

Status:

Accepted

Decision:

Everything communicates via Event Bus.

Alternatives:

Direct module communication.

Rejected Because:

Tight coupling.

Consequences:

Better maintainability.

---

# ADR-009

Title:

Power Efficiency First

Status:

Accepted

Decision:

Power consumption is a feature.

Rules:

Idle CPU <3%

Idle RAM <1.5GB

GPU idle = 0

Consequences:

Requires intelligent scheduling.

---

# ADR-010

Title:

Productivity First

Status:

Accepted

Decision:

Features that do not save time should not exist.

Evaluation:

Time saved

Trust gained

Cognitive load reduced

If none improve.

Reject feature.

---

# ADR-011

Title:

Research Paper First Thinking

Status:

Accepted

Decision:

Every module should contribute towards research publication.

Every module must answer:

What problem does it solve?

What novelty does it provide?

How is it evaluated?

Consequences:

Documentation overhead increases.

Research quality increases.

---

# ADR-012

Title:

Voice First Interaction

Status:

Accepted

Decision:

Interaction ratio:

Voice 60%

Typing 20%

Visual 20%

Consequences:

Voice infrastructure becomes critical.

---

# ADR-013

Title:

Companion System

Status:

Accepted

Decision:

Specialized companions will exist.

Examples:

Coding Companion

Learning Companion

Future companions

Rules:

Notification first.

Voice second.

---

# ADR-014

Title:

No Continuous Polling

Status:

Accepted

Decision:

Avoid aggressive loops.

Alternatives:

Continuous polling.

Rejected Because:

Battery drain.

CPU waste.

Consequences:

Event driven design mandatory.

---

# ADR-015

Title:

AI Behaviour Limit

Status:

Accepted

Decision:

Maximum AI Behaviour Level = Collaborative.

AI never becomes autonomous.

Consequences:

User trust preserved.

---

# ADR-016

Title:

Documentation First Development

Status:

Accepted

Decision:

Code never comes before architecture.

Workflow:

Document

↓

Design

↓

Implement

↓

Test

↓

Measure

↓

Document Again

---

# ADR-017

Title:

Research Domains

Status:

Accepted

Domains:

Human AI Collaboration

Context Aware Computing

Local First AI

Energy Efficient AI

Persistent Memory Systems

AI Orchestration

Personal Cognitive Systems

---

# ADR-018

Title:

Engineering Compass

Status:

Accepted

Priority Order:

Buildable

>

Maintainable

>

Productive

>

Power Efficient

>

Scalable

>

Futuristic

---

# ADR-019
# ADR-019

Title:

Memory Tier Architecture

Status:

Accepted

Context:

Global <200ms retrieval conflicts with CPU <5% and RAM <500MB constraints.

Decision:

Helix Memory will operate in three tiers.

Hot Memory

0-7 days

Stored in RAM cache.

Target latency <200ms.

Warm Memory

8-30 days

Stored in Qdrant.

Target latency <500ms.

Cold Memory

30+ days

Stored in Archive Storage.

Target latency <3000ms.

GPU may be used for embedding generation only.

GPU is forbidden for retrieval queries.

Consequences:

Retrieval becomes scalable.

Resource constraints remain achievable.

Review Date:

v2

 
# ADR - 20

# ADR-020

Title:

Memory Retention Policy

Status:

Accepted

Decision:

Conversation Memory

7 active days.

30 archive days.

Preference Memory

Permanent.

Work Memory

Project lifetime.

Explainability Logs

30 days.

Nothing is permanently deleted automatically.

Users may restore archived memories.

# ADR-21

# ADR-021

Title:

Local API Authentication

Status:

Accepted

Decision:

Helix runs on localhost.

Session token generated at startup.

No login screen.

No cloud authentication.

No user accounts.

# ADR-22

# ADR-022

Title:

Storage Budget Allocation

Status:

Accepted

Decision:

30GB applies to Helix ecosystem only.

Operating System excluded.

Allocation:

LLM = 8GB (disk only; VRAM 0-5GB when loaded on demand per ADR-025) (disk; loaded on demand, not resident)

Embedding Models = 2GB

STT/TTS = 3GB

Databases = 5GB

Indexes = 3GB

Logs = 2GB

Caches = 4GB

Reserve = 3GB

Note:

Per ADR-025, the LLM is loaded only during Conversation State.
VRAM usage at any point is bounded by the active state, not the total disk footprint.

# ADR- 023

# ADR-023

Title:

External SSD Failure Handling

Status:

Accepted

Decision:

Helix must never fail startup due to External SSD absence.

Behaviour:

Boot without SSD

↓

Switch to degraded mode

↓

Store temporary data locally

↓

Sync automatically after reconnection

Fatal shutdown is forbidden.


# ADR - 24
# ADR-024

Title:

Battery Aware Scheduling

Status:

Accepted

Decision:

Heavy tasks are blocked on battery.

Examples:

Embedding generation

Large indexing

Dataset processing

Model downloads

Light tasks remain allowed.

Examples:

Notifications

Context updates

Permission checks

Foundation Layer enforces policy globally.

# ADR-025

Title:

State-Based Model Orchestration

Status:

Accepted

Context:

ADR-022 allocated 8GB for the LLM, but the RTX 3050 only has 6GB VRAM.
03_SAD.md §13 caps Core AI Layer VRAM at <5GB.
Continuous model loading violates ADR-009 (GPU idle = 0).
A single always-loaded model strategy is impossible under these constraints.

Decision:

Helix will use state-based model orchestration instead of always-on models.

States:

Sleep State — always active
- Active modules: Wake Word Engine, Event Bus, Logger, Permission Manager
- Memory Layer: lightweight Event Bus subscribers only (no model inference)
- VRAM: 0MB
- RAM: <2GB
- CPU: <3%

Conversation State — activated on wake word or user input
- Pipeline: Wake Word → STT → LLM → TTS → Unload
- VRAM: 4-5GB max
- Models loaded only for the duration of the interaction
- Immediately unload after response delivery

Background State — only when laptop is idle AND plugged in
- Allowed: embedding generation, archiving, memory optimization, index maintenance
- Forbidden: LLM loading
- Foundation Layer enforces power precondition before allowing state transition

Model Loading Rules:
- Models are never preloaded
- Models are loaded on demand
- Models are unloaded after use
- Only one model is loaded at any time
- GPU is used only during active inference, never for idle holding

Consequences:
- Eliminates VRAM conflict
- Meets <5GB Core AI Layer VRAM budget
- Aligns with ADR-009 (GPU idle = 0)
- Enforces ADR-024 (battery-aware scheduling) at the state level

Review Date:

v2


Create a new ADR whenever:

Technology changes.

Architecture changes.

Storage changes.

Hardware changes.

Research direction changes.

Never make undocumented major decisions.
