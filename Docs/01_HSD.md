# 01_HSD.md

# Helix Specification Document (HSD)

## Helix - A Context-Aware Personal Cognitive Operating System (PCOS)

Version: 2.0

Status: Active Development

Owner: Vaibhav Kumar Singh

Category: Research + Engineering Project

Parent Document: 00_VISION.md

---

# 1. Purpose

This document is the constitution of Helix.

Every future module, document, experiment and AI agent contribution must obey this document.

If any future implementation conflicts with this document, this document wins.

---

# 2. North Star Statement

Helix exists to reduce human cognitive effort without reducing human control.

---

# 3. System Identity

Helix is a Context-Aware Personal Cognitive Operating System.

Helix is an intelligent orchestration layer between a human and their digital environment.

It continuously:

* Observes
* Understands
* Remembers
* Suggests
* Assists

while keeping humans in complete control.

---

# 4. Non Negotiable Rules

These rules can never be broken.

N1.

Human authority is supreme.

N2.

No autonomous execution.

N3.

Every action requires permission.

N4.

Everything must work offline first.

N5.

Productivity is prioritized over aesthetics.

N6.

Power efficiency is mandatory.

N7.

Maintainability is mandatory.

N8.

User trust is mandatory.

N9.

Hardware constraints are permanent.

N10.

Overengineering is forbidden.

---

# 5. Core Principles

## P1 Human First

AI collaborates.

Humans decide.

AI never dominates.

---

## P2 Permission First

Every action follows:

Observe

↓

Suggest

↓

Explain

↓

Ask Permission

↓

Execute

---

## P3 Productivity First

Every feature must answer:

How much time does this save?

Features that do not save time should not exist.

---

## P4 Power Efficient First

Battery life is a feature.

Performance is a feature.

Resource usage is a feature.

---

## P5 Local First

Core systems must work without internet.

Internet only enhances capabilities.

---

## P6 Explainability First

Every suggestion must explain:

Why

Benefits

Risks

Alternatives

---

## P7 Modular First

Every module must have one responsibility.

---

## P8 Research First

The architecture must be publishable as a research paper.

---

# 6. Hardware Constraints

These constraints are fixed.

Operating System

Windows 11

CPU

Intel i5-12450H

GPU

RTX3050 6GB

RAM

16GB

Laptop SSD

155GB available

External SSD

368GB

Single user only.

Laptop only.

No distributed systems.

No cloud infrastructure dependency.

---

# 7. Storage Architecture

Laptop SSD:

Runtime Storage

Stores:

Source code

Models

Configurations

Databases

Embeddings

Indexes

Temporary files

Runtime caches

External SSD:

Cold Storage

Stores:

Backups

Logs

Snapshots

Archived memory

Archived projects

Research datasets

Exports

Forbidden:

* Loading models from external SSD
* Running databases from external SSD
* Running vector databases from external SSD
* Running active memory from external SSD

---

# 8. Resource Budget

Idle State

CPU <3%

RAM <1.5GB

GPU = 0%

VRAM = 0GB

Listening State

CPU <10%

RAM <2GB

GPU = 0%

Processing State

CPU <40%

RAM <5GB

VRAM <5GB

Maximum Limits

CPU <70%

RAM <8GB

VRAM <5.5GB

Disk Usage <30GB

---

# 9. Layer Architecture

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

No layer may bypass another layer.

---

# 10. Foundation Layer

Responsibilities:

Configuration

Logging

Permissions

Storage

Event Bus

Rules:

Always running

Minimal resources

Highly stable

Must boot first

---

# 11. Core AI Layer

Responsibilities:

Wake Word

Voice

LLM

Conversation

Rules:

No unnecessary processing

No continuous GPU usage

Low latency mandatory

---

# 12. Memory Layer

Responsibilities:

Conversation memory

Preference memory

Work memory

Explainability

Rules:

Keep only relevant information

Archive old information

Avoid unnecessary memory growth

---

# 13. Context Layer

Responsibilities:

Browser awareness

Project awareness

System awareness

Environment awareness

Rules:

Observe intelligently

Do not constantly scan

Avoid unnecessary polling

---

# 14. Action Layer

Responsibilities:

Automation

Planning

Productivity

Rules:

Never bypass permission system

Never execute hidden actions

---

# 15. Companion Layer

Responsibilities:

Coding Companion

Learning Companion

Future specialized companions

Rules:

Notification first

Voice second

Never interrupt workflow

---

# 16. AI Behaviour Levels

Level 0

Reactive

Level 1

Aware

Level 2

Suggestive

Level 3

Predictive

Level 4

Adaptive

Level 5

Collaborative

Never exceed Level 5.

---

# 17. Performance Requirements

Startup <20s

Voice Response <3s

Interrupt <500ms

Project Switching <5s

Memory Retrieval <200ms

---

# 18. Power Optimization Rules

Mandatory Rules

Avoid continuous polling

Prefer events over loops

Lazy load models

Unload inactive models

Batch expensive tasks

Sleep inactive modules

Reduce disk access

Reduce GPU wakeups

Minimize background tasks

---

# 19. AI Agent Manifest

Every AI agent contributing to Helix must:

Prefer:

Simple solutions

Modular systems

Asynchronous systems

Low power systems

Maintainable systems

Local execution

Avoid:

Overengineering

Hidden automation

Dependency bloat

Continuous scanning

Continuous indexing

Excessive GPU usage

---

# 20. Feature Acceptance Formula

Every future feature must be scored.

Productivity Gain

Frequency of Use

Trust Impact

Power Cost

Complexity

Maintainability

If cost exceeds usefulness.

Reject the feature.

---

# 21. Engineering Compass

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

# 22. Research Compass

Helix belongs to:

Human-Centric AI

Context-Aware Computing

Human AI Collaboration

Persistent Memory Systems

Local First AI

Explainable AI

Energy Efficient AI

AI Orchestration Systems

Personal Cognitive Systems

---

# 23. Completion Definition

A module is only complete if:

Code exists

Tests pass

Resource budget respected

Documentation updated

Research contribution identified

Performance measured

Power usage measured

Decision logged

Status updated

---

# 24. Future Growth Rule

Helix should grow smarter.

Helix should not grow bigger unnecessarily.
