# LocalAgentUI Architecture Overview

This document describes the intended logical architecture and the major mechanisms represented in the current codebase. It is not a claim that every planned capability is fully implemented. See the source modules and release notes for implementation detail.

## 1. Overall system architecture

```mermaid
flowchart TB
  U[Product Owner / User]
  subgraph UI[Presentation Layer]
    CHAT[Chat & Dashboard]
    AM[Agent Management]
    CM[Capability & Tool Management]
    PM[Project & Workspace UI]
    SET[Settings]
  end
  subgraph APP[Application & Governance Layer]
    API[FastAPI APIs]
    WF[Proposal / Project Workflows]
    GOV[Approval & Authorization]
    CTX[Prompt & Context Builder]
  end
  subgraph ORCH[Orchestration Layer]
    MAIN[Main Agent]
    PLAN[Planning & Task Decomposition]
    DISP[Agent Dispatcher]
  end
  subgraph EXEC[Execution Layer]
    SPEC[Specialist Agents]
    CAP[Capability Catalog]
    TOOL[Tool Registry & Handlers]
    LLM[Ollama Runtime]
  end
  subgraph DATA[Local Data & Infrastructure]
    DB[(SQLite)]
    WS[Workspace & Artifact Storage]
    LOG[Logs / Execution Evidence]
  end
  U --> UI
  UI --> API
  API --> WF
  API --> GOV
  API --> MAIN
  MAIN --> CTX
  MAIN --> PLAN
  PLAN --> GOV
  GOV --> DISP
  DISP --> SPEC
  SPEC --> CAP
  CAP --> TOOL
  SPEC --> LLM
  API <--> DB
  TOOL --> WS
  API --> WS
  API --> LOG
  GOV --> LOG
```

## 2. AI organisation model

The Main Agent acts as a team lead/coordinator. Specialist Agents have bounded roles and assigned capabilities. The user remains responsible for direction and designated approvals.

```mermaid
flowchart TB
  PO[Product Owner]
  MA[Main Agent / Team Lead]
  PO -->|Goals, decisions, approvals| MA
  MA -->|Task assignment and supervision| A1[Analyst Agent]
  MA -->|Task assignment and supervision| A2[Developer Agent]
  MA -->|Task assignment and supervision| A3[Research Agent]
  A1 --> C1[Assigned Capabilities]
  A2 --> C2[Assigned Capabilities]
  A3 --> C3[Assigned Capabilities]
  C1 --> T1[Permitted Tools]
  C2 --> T2[Permitted Tools]
  C3 --> T3[Permitted Tools]
```

This is a logical responsibility model, not an unrestricted peer-to-peer agent network. Dispatch does not automatically grant the Main Agent every tool assigned to a Specialist Agent.

## 3. Proposal, project planning and execution workflow

```mermaid
flowchart TD
  U[User Request / Goal] --> R[Requirement Analysis]
  R --> P[Proposal & Scope]
  P --> D{Planning authorised?}
  D -->|No| H1[Wait for user decision]
  D -->|Yes| TP[Team / Project Planning]
  TP --> PR{Formal project approval required?}
  PR -->|Yes| H2[Human review and approval]
  PR -->|No / approved| PJ[Project & Workstream Setup]
  H2 -->|Approved| PJ
  H2 -->|Rejected / revise| P
  PJ --> TD[Task Decomposition & Dependencies]
  TD --> EA{Execution authorised?}
  EA -->|No| H3[Wait for execution authorisation]
  EA -->|Yes| AS[Agent Selection & Assignment]
  AS --> EX[Specialist Execution]
  EX --> QR[Result & Quality Review]
  QR -->|Rework| AS
  QR -->|Accepted by Main Agent| RI[Result Integration]
  RI --> FV[User Review / Final Acceptance]
```

Planning authorisation, formal project approval and execution authorisation are separate business decisions. A goal does not grant blanket permission for every downstream action.

## 4. Capability, Tool and Permission model

```mermaid
flowchart TB
  UI[Management UI]
  AR[Agent Registry]
  CR[Capability Registry]
  TR[Tool Registry]
  PM[Permission / Policy Check]
  RT[Runtime Tool Execution]
  UI --> AR
  UI --> CR
  UI --> TR
  AR -->|assigned capabilities and direct tools| PM
  CR -->|capability tool grants| PM
  TR -->|registered handlers and schemas| PM
  PM -->|effective allowed tools| RT
```

The permission resolution rule is:

```text
Effective Tools = (Capability Tools ∪ Direct Tools) − Explicitly Denied Tools
```

Capability describes a business ability; Tool represents an executable operation; Permission determines whether the operation may run in a given scope. Explicit Deny takes precedence over inherited and direct grants.

## 5. Prompt and context construction

Prompt layers and context sources are related but different concepts. P0–P6 represent instruction layers. Context Builder resolves relevant runtime, business, project, workspace, conversation and artifact information for a specific invocation.

```mermaid
flowchart TB
  subgraph PROMPT[Prompt Layers]
    P0[P0 Platform Safety]
    P1[P1 System Core]
    P2[P2 Agent Role]
    P3[P3 Approved Global Rules]
    P4[P4 Project Instructions]
    P5[P5 Session / Task Context]
    P6[P6 Current Request / Assigned Task]
  end
  subgraph SOURCES[Context Sources]
    B[Business Context]
    PJ[Project Context]
    W[Workspace Context]
    C[Conversation Context]
    A[Artifact Context]
    R[Runtime Environment]
  end
  CB[Unified Context Builder]
  OUT[Final Agent Input]
  P0 --> CB
  P1 --> CB
  P2 --> CB
  P3 --> CB
  P4 --> CB
  P5 --> CB
  P6 --> CB
  B --> CB
  PJ --> CB
  W --> CB
  C --> CB
  A --> CB
  R --> CB
  CB --> OUT
```

## 6. Workspace and Artifact model

```mermaid
flowchart TB
  REG[Artifact Registry]
  subgraph TYPES[Workspace Types]
    TMP[Temporary Workspace]
    PROJ[Project Workspace]
    G[Global Outputs / Resources]
  end
  REG <--> TMP
  REG <--> PROJ
  REG <--> G
  TMP --> TDIR[Inputs / Workspace / Outputs]
  PROJ --> PDIR[Inputs / Workspace / Outputs / Deliverables]
  G --> GDIR[Shared resources and outputs]
  TDIR --> META[Artifact metadata, owner, source, checksum, version, status]
  PDIR --> META
  GDIR --> META
```

Artifact registration is separate from file creation. The backend should verify file existence and workspace path containment before exposing a registered download.

## 7. Governance concepts

- **Goal Authority:** permission to pursue a defined objective or begin planning.
- **Task Authority:** permission to carry out an approved task or work package.
- **Action Authority:** permission to perform a specific operation, especially where risk, external impact or irreversibility is involved.
- **Human approval:** required at configured decision gates; approval state must be persisted and checked by the backend.
- **Execution evidence:** record actual operations and results; an agent's natural-language statement is not execution evidence by itself.

## Implementation status

These diagrams describe the current design model. Some elements are implemented in the current codebase; others remain experimental or planned. Consult `docs/releases/`, `CHANGELOG.md` and the relevant source modules before relying on a feature.
