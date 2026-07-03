# 04_CFD.md

# Control Flow Document (CFD)

## Helix - A Context-Aware Personal Cognitive Operating System

Version: 2.0

Status: Active Development

Owner: Vaibhav Kumar Singh

Parent Documents:

00_VISION.md

01_HSD.md

02_PRD.md

03_SAD.md

---

# 1. Purpose

This document defines system behavior.

It answers:

What happens?

When does it happen?

Why does it happen?

Who triggers it?

How much resource can it consume?

How should it fail?

---

# 2. Design Philosophy

Helix is event driven.

Helix should remain asleep whenever possible.

Nothing should run continuously without purpose.

Default behavior:

Sleep

↓

Observe

↓

Think

↓

Assist

↓

Sleep Again

---

# 3. System States

Helix always exists in one state.

States:

OFF

BOOTING

IDLE

LISTENING

PROCESSING

SPEAKING

INTERRUPTED

WAITING

PERMISSION_PENDING

EXECUTING

BACKGROUND_ASSIST

SHUTTING_DOWN

---

# 4. Startup Flow

Trigger:

User launches Helix.

Flow:

Initialize Config

↓

Initialize Logger

↓

Initialize Event Bus

↓

Initialize Storage

↓

Initialize Permissions

↓

Load Memory

↓

Load Context

↓

Initialize LLM

↓

Initialize Voice

↓

Initialize UI

↓

Enter IDLE State

Goal:

<20 seconds

---

# 5. Voice Flow

Trigger:

Hola Helix

Flow:

Wake Word Detected

↓

Start Listening

↓

Detect Silence

↓

Speech To Text

↓

Load Context

↓

Load Memory

↓

Build Prompt

↓

LLM Response

↓

Speak Response

↓

Return To IDLE

Goal:

<3 seconds

---

# 6. Interrupt Flow

Trigger:

Stop

Wait

Enough

Flow:

Stop TTS

↓

Save Position

↓

Acknowledge

↓

WAITING

Branches:

Continue

↓

Resume

New Command

↓

Discard Old Task

No Activity 30s

↓

Return To IDLE

Goal:

<500ms

---

# 7. Permission Flow

Trigger:

Action Required

Flow:

Observe

↓

Generate Explanation

↓

Ask User

↓

Approve

or

Reject

Approve:

Execute

↓

Report

Reject:

Discard

↓

Return To IDLE

---

# 8. Browser Awareness Flow

Trigger:

Browser Request

Flow:

Check Browser Availability

↓

Read Tabs

↓

Analyze Relevance

↓

Return Results

Rules:

Never continuously scan browsers.

Only update when:

User requests

or

Context changes significantly.

---

# 9. Project Awareness Flow

Trigger:

Project Opened

Flow:

Detect Workspace

↓

Check Previous Sessions

↓

Load Knowledge

↓

Load Open Tasks

↓

Build Context

↓

Inject Into Memory

↓

Assist User

Rules:

Do not fully reindex every time.

Use incremental updates.

---

# 10. Coding Companion Flow

Trigger Conditions:

Stuck >20 minutes

Repeated errors

Large functions

Missing documentation

Old TODOs

Flow:

Detect

↓

Validate

↓

Create Notification

↓

Wait For Approval

↓

Explain

or

Dismiss

Rules:

Max 3 notifications per 30 minutes.

---

# 11. Learning Companion Flow

Trigger:

LeetCode

GFG

Learning Sessions

Flow:

Detect Problem

↓

Detect Pattern

↓

Track Performance

↓

Store Results

↓

Recommend Improvements

---

# 12. Productivity Flow

Trigger:

Repetitive behavior detected

Flow:

Observe Pattern

↓

Calculate Benefit

↓

Generate Suggestion

↓

Ask Permission

↓

Create Workflow

Rules:

Never automate without permission.

---

# 13. Memory Flow

Session Start:

Load Recent Memory

Load Preferences

Load Project History

Build Context

Session Running:

Store Conversations

Store Context

Store Decisions

Session End:

Archive Old Data

Save New Data

Create Backup

---

# 14. Background Assistance Flow

Background tasks only run when:

CPU <20%

GPU = 0%

User idle

Laptop plugged in preferred

Tasks:

Reconciliation

Compression

Backup

Analytics

Cleanup

Indexing

If user becomes active:

Immediately stop background work.

---

# 15. Resource Flow

IDLE

CPU <3%

RAM <1.5GB

GPU 0%

LISTENING

CPU <10%

RAM <2GB

GPU 0%

PROCESSING

CPU <40%

RAM <5GB

VRAM <5GB

BACKGROUND

CPU <20%

GPU 0%

---

# 16. Power Flow

High Priority Rules

Avoid polling.

Avoid loops.

Avoid unnecessary wakeups.

Prefer events.

Batch expensive operations.

Sleep inactive modules.

---

# 17. External SSD Flow

Allowed:

Backups

Archives

Logs

Snapshots

Exports

Forbidden:

Runtime models

Databases

Embeddings

Memory

Indexes

---

# 18. Error Flow

Error Detected

↓

Retry Once

↓

Still Failed

↓

Translate Error

↓

Explain Fix

↓

Log Error

↓

Continue System

Rules:

Never crash silently.

---

# 19. Shutdown Flow

Trigger:

Helix Shutdown

Flow:

Save Memory

↓

Reconcile Tasks

↓

Archive Data

↓

Backup

↓

Save Logs

↓

Shutdown Modules

↓

Power Off

Goal:

<15 seconds

---

# 20. Continuous Improvement Flow

Observe

↓

Measure

↓

Optimize

↓

Document

↓

Repeat

Every module improvement must update:

Resource Usage

Performance

Research Contribution

Documentation

Decision Log
