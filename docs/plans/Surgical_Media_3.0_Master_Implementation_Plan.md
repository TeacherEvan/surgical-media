# SURGICAL MEDIA 3.0

## Product, Architecture & Implementation Master Plan

**Prepared for:** Big Boss and the Surgical Media development team\
**Prepared by:** G&L --- Product & Engineering Proposal\
**Document version:** 1.1\
**Status:** Proposal for technical validation and approval\
**Repository:** https://github.com/TeacherEvan/surgical-media\
**Date:** 20 November 2026

------------------------------------------------------------------------

## Document purpose

This document turns the initial repository review into an
implementation-oriented proposal. It defines the intended product
direction, proposed architecture, module boundaries, data contracts,
delivery phases, engineering work packages, acceptance criteria, risks
and decisions required from project ownership.

**Evidence boundary:** This is an architecture and product proposal
based on the repository material reviewed during the initial assessment.
It is not a source-code audit. No claim in this document should be
interpreted as proof that a proposed module, API endpoint, integration
or test already exists. Before implementation, the team must inspect the
current repository, establish the actual baseline, and adapt names and
interfaces to the code that is really present.

## 1. Executive recommendation

### The recommendation in one sentence

**Keep Surgical Media's deterministic rendering core; build a modular
production-intelligence layer around it.**

Surgical Media should evolve from a capable media-rendering workflow
into an agent-operated content production system that can plan,
research, write, direct, render, inspect and package original content
for multiple audiences and publishing destinations.

The objective is not maximum video volume. It is repeatable production
of content that is engaging, distinctive, technically sound, factually
responsible, rights-aware and commercially useful.

### Why this direction

A rendering engine and an AI production director solve different
problems:

-   The production director decides what should be made and coordinates
    the work.
-   Specialist agents contribute research, creative direction, audio and
    visual plans.
-   Structured contracts constrain and validate agent output.
-   The existing rendering engine turns an approved production plan into
    a reproducible media artifact.
-   Technical, visual and editorial checks assess different kinds of
    quality.
-   A publishing layer prepares platform-specific deliverables and
    records what was approved.

This separation protects the reliable parts of the existing system while
allowing new AI providers and agent frameworks to be introduced or
replaced independently.

### Recommended first milestone

Deliver a working **topic-to-validated-storyboard workflow**, then
render one controlled pilot: a short Horse Tenny comedy video. This
tests the production contracts and integration pattern without starting
with the higher research and editorial risks of political content.

------------------------------------------------------------------------

## 2. Product vision and success definition

### 2.1 Intended users

-   Autonomous or semi-autonomous agents that need a dependable
    media-production tool.
-   Human creators producing recurring social content.
-   Editorial teams producing explainers, documentaries and commentary.
-   Businesses producing product and promotional videos.
-   A future managed production service or self-service platform.

### 2.2 Initial content profiles

  -----------------------------------------------------------------------
  Profile                 Typical content         Primary quality
                                                  concerns
  ----------------------- ----------------------- -----------------------
  Entertainment and       Horse Tenny, fictional  Originality, timing,
  comedy                  characters, sketches,   character continuity,
                          dating scenarios        humour

  News and current        News explainers,        Source quality,
  affairs                 timelines,              freshness, accuracy,
                          international affairs   context

  Politics and public     Policy explainers,      Evidence, fairness,
  affairs                 political commentary,   synthetic-media
                          satire                  safeguards, human
                                                  review

  Education and           Horse-care education,   Accuracy, clarity,
  documentary             history, science,       learning value
                          tutorials

  Commercial and          Product explainers,     Product truthfulness,
  promotional             brand stories,          brand approval, rights,
                          campaigns               disclosures
  -----------------------------------------------------------------------

Profiles should be configuration-driven rather than implemented as
separate copies of the production pipeline.

### 2.3 Product principles

1.  **Rendering remains deterministic where practical.** The same
    approved inputs and configuration should produce reproducible
    outputs, subject to provider and rendering differences.
2.  **AI output is untrusted until validated.** Scripts, research, asset
    metadata and storyboards must pass defined checks.
3.  **Every asset has a rights record.** Unknown rights status is not
    equivalent to permission.
4.  **Facts, opinions, allegations and satire remain distinguishable.**
5.  **Human approval is risk-based.** High-impact or sensitive content
    must not silently auto-publish.
6.  **Providers are replaceable.** Avoid hard dependencies on a single
    model or media service.
7.  **Cost is observable and controllable.** Every job should have a
    budget and usage record.
8.  **A technical pass is not a monetization guarantee.** Platform
    decisions remain with the platforms.

### 2.4 Success measures

Measure operational reliability, creative quality and commercial
efficiency separately.

  -----------------------------------------------------------------------
  Area                                Proposed measure
  ----------------------------------- -----------------------------------
  Contract reliability                100% of accepted jobs validate
                                      against the active schema

  Asset governance                    100% of published assets have a
                                      recorded rights status and source

  Technical output                    100% of released exports pass
                                      configured technical QC

  Editorial risk                      100% of high-risk jobs receive
                                      required human review

  Traceability                        100% of completed jobs retain
                                      configuration, asset and approval
                                      provenance

  Cost control                        100% of jobs record estimated and
                                      actual provider/render costs where
                                      measurable

  Creative quality                    Human-reviewed scorecard for hook,
                                      clarity, originality, pacing and
                                      audience value

  Delivery                            Successful export against each
                                      enabled platform profile
  -----------------------------------------------------------------------

Targets are proposed release gates, not claims about current
performance. Define baselines before setting service-level objectives.

------------------------------------------------------------------------

## 3. Current-state validation before design changes

The first engineering activity is a bounded repository audit. It
prevents duplicate development and distinguishes documented capabilities
from verified implementation.

### 3.1 Audit checklist

-   Map repository directories, entry points and module dependencies.
-   Inspect `README`, `SKILL.md`, project plan, security policy and
    contribution guidance.
-   Reconcile any inconsistent version numbers, support statements and
    test counts.
-   Run the documented test suite and record the exact command,
    environment and result.
-   Identify current storyboard and production data structures.
-   Identify current rendering interfaces and supported output profiles.
-   Verify which asset sources and licensing checks are implemented.
-   Verify actual TTS, audio, image and video provider integrations.
-   Identify network calls, credentials, secrets and external service
    boundaries.
-   Review subprocess invocation and FFmpeg argument construction.
-   Inspect file handling, temporary directories and cleanup.
-   Establish render-time, memory and storage baselines using
    representative jobs.
-   Identify existing agent-framework integration points.
-   Record missing tests and known limitations.

### 3.2 Audit output

Create `docs/audits/initial-baseline.md` with:

-   Commit hash and audit date.
-   Environment and dependency versions.
-   Verified features with file-path and line-level evidence.
-   Features described in documentation but not verified.
-   Test commands and results.
-   Security and reliability findings.
-   Performance baseline.
-   Recommended changes to this proposal.

**Gate:** Do not create a new module until the audit confirms that an
equivalent capability does not already exist or that the existing
capability cannot meet the required contract.

------------------------------------------------------------------------

## 4. Target architecture

### 4.1 Logical architecture

``` mermaid
flowchart TD
    A[User or Agent Request] --> B[Production API / CLI]
    B --> C[Production Director]
    C --> D[Job State and Policy Manager]
    D --> E[Research Agent]
    D --> F[Creative Director]
    E --> F
    F --> G[Script and Storyboard Validator]
    G --> H[Audio and Visual Planning]
    H --> I[Asset and Rights Registry]
    I --> J[Existing Surgical Media Renderer]
    J --> K[Technical QC]
    J --> L[Visual QC]
    K --> M[Editorial and Policy Review]
    L --> M
    M --> N{Approval Required?}
    N -->|Yes| O[Human Approval]
    N -->|No, permitted low-risk job| P[Publishing Package]
    O -->|Approved| P
    O -->|Rejected / Changes| F
    P --> Q[Export and Optional Publishing Adapter]
    Q --> R[Provenance and Cost Records]
```

### 4.2 Component responsibilities

  -----------------------------------------------------------------------
  Component               Owns                    Must not own
  ----------------------- ----------------------- -----------------------
  Production Director     Job lifecycle,          Rendering
                          orchestration, retries, implementation
                          status

  Research Director       Evidence collection and Inventing facts or
                          claim/source mapping    deciding final
                                                  editorial approval

  Creative Director       Concepts, scripts,      Altering verified
                          narrative and scene     source records
                          intent

  Audio Director          Voice, narration and    Secret management or
                          audio plan              uncontrolled provider
                                                  calls

  Visual Director         Visual plan and asset   Bypassing rights
                          recommendations         validation

  Contract Validator      Schema and semantic     Creative
                          validation              decision-making

  Asset Registry          Asset metadata,         Assuming unknown rights
                          provenance and rights   are cleared
                          status

  Existing Renderer       Rendering approved      Research or editorial
                          inputs                  decisions

  Technical QC            File, codec, timing and Monetization
                          audio checks            eligibility decisions

  Visual QA               Frame and composition   Replacing human
                          inspection              editorial judgement

  Editorial Review        Risk, evidence,         Guaranteeing platform
                          disclosure and approval acceptance
                          requirements

  Publishing Director     Metadata and platform   Publishing without
                          package preparation     authorization
  -----------------------------------------------------------------------

### 4.3 Architectural constraints

-   Keep the renderer callable without AI services.
-   Make all provider calls pass through explicit adapters.
-   Use versioned JSON contracts at module boundaries.
-   Persist job state and artifacts; do not rely on in-memory
    orchestration alone.
-   Make retries idempotent where possible.
-   Store secrets outside source control.
-   Treat retrieved webpages, prompts embedded in assets and model
    outputs as untrusted input.
-   Keep publishing credentials and permissions separate from generation
    permissions.

------------------------------------------------------------------------

## 5. Proposed module specifications

Names below are suggested. Reuse or extend existing modules where
suitable.

### 5.1 Production Director --- P0/P1

**Suggested location:**
`src/surgical_media/orchestration/production_director.py`

Responsibilities: - Accept and validate a production request. - Create a
unique job and immutable input snapshot. - Select a content profile and
policy configuration. - Build a dependency-aware execution plan. -
Dispatch specialist tasks. - Track state, progress, retries and
failures. - Enforce budget and approval gates. - Assemble the final
production manifest.

Suggested job states:

`DRAFT → VALIDATED → RESEARCHING → SCRIPTING → STORYBOARD_READY → RENDERING → QC_PENDING → REVIEW_PENDING → APPROVED → PACKAGED`

Terminal or exceptional states: `REJECTED`, `FAILED`, `CANCELLED`.

Acceptance: - Invalid requests fail before expensive work starts. - Each
transition is validated and recorded. - Retried tasks do not create
duplicate deliverables. - Job status can be recovered after process
restart. - Budget and approval rules are enforced.

### 5.2 Research Director --- P1

**Suggested location:** `src/surgical_media/agents/research_director.py`

Responsibilities: - Search approved sources through configurable
research providers. - Record source URL, publisher, publication date and
retrieval timestamp. - Extract claims and link each claim to supporting
sources. - Identify conflicting evidence and uncertainty. - Flag stale
information and unsupported assertions. - Produce a structured research
report.

Each material claim should carry: - Claim text. - Claim type: `fact`,
`opinion`, `allegation`, `prediction` or `satire`. - Supporting source
identifiers. - Contradicting source identifiers, if any. - Verification
status. - Confidence rationale. - Last checked timestamp.

Acceptance: - No citation is fabricated. - Unsupported claims are
flagged rather than silently promoted to facts. - Conflicting sources
remain visible. - Time-sensitive claims include source dates. - Research
output validates against its schema.

### 5.3 Creative Director --- P1

**Suggested location:** `src/surgical_media/agents/creative_director.py`

Responsibilities: - Generate and compare multiple concepts. - Create
opening hooks and narrative structure. - Produce narration and
scene-by-scene intent. - Match tone and pacing to the selected
profile. - Preserve character and series continuity. - Reduce repetitive
scripts and generic templates. - Reference research claim IDs for
factual statements.

Acceptance: - Every factual script claim can be traced to a research
claim or is marked for review. - The script meets configured duration
and language constraints. - Scenes contain meaningful visual intent. -
The output is schema-valid and versioned.

### 5.4 Audio Director --- P1/P2

**Suggested location:** `src/surgical_media/agents/audio_director.py`

Responsibilities: - Assign configured voices to narration and
characters. - Store pronunciation dictionaries. - Specify delivery style
and pacing. - Align narration segments to scene timing. - Select
licensed music and sound effects. - Normalize and inspect audio. -
Record provider and voice provenance.

Acceptance: - Audio assets have rights metadata. - Narration timing is
compatible with the storyboard. - Voice assignments are reproducible
where provider capabilities allow. - Missing or failed audio generation
produces a clear job error.

### 5.5 Visual Director and provider adapters --- P2

**Suggested locations:** -
`src/surgical_media/agents/visual_director.py` -
`src/surgical_media/providers/image/` -
`src/surgical_media/providers/video/`

Responsibilities: - Select visual treatment and rendering backend. -
Recommend or request images, clips and generated assets. - Preserve
character and brand references. - Record prompt, provider, model and
asset provenance where permitted. - Enforce licensing and usage
restrictions. - Provide graceful fallback when an optional provider is
unavailable.

Provider interface should expose a small common contract such as: -
`generate(request) → asset_result` -
`get_capabilities() → capabilities` -
`estimate_cost(request) → estimate` - `health_check() → status`

Do not assume every provider supports the same aspect ratios, duration,
reference images, commercial rights or output formats. Capabilities must
be declared and checked.

### 5.6 Platform Adapter --- P2

**Suggested location:** `src/surgical_media/platforms/adapter.py`

Responsibilities: - Load versioned platform profiles. - Apply aspect
ratio, resolution, caption and safe-zone settings. - Produce
platform-specific variants from the same source project. - Validate
export constraints. - Generate a report of any transformations or
limitations.

Initial profiles: - `youtube_standard` - `youtube_shorts` - `tiktok` -
`instagram_reels` - `facebook_reels`

Platform limits and policy rules change. Store configurable profile data
with a `last_reviewed` date and official documentation reference. Do not
hardcode a claim that a file is eligible for monetization.

### 5.7 Visual QA --- P2

**Suggested location:** `src/surgical_media/qa/visual_qa.py`

Responsibilities: - Sample frames at scene boundaries and configurable
intervals. - Detect black or near-black frames. - Inspect text overflow
and safe-zone violations. - Check subtitle legibility and contrast. -
Detect empty, repeated or visually inconsistent scenes. - Return frame
timestamps, severity and repair suggestions.

Use deterministic computer-vision checks for measurable properties where
possible. Use vision models for subjective inspection, with
model/provider provenance and human review for uncertain findings.

### 5.8 Originality Analyzer --- P2/P3

**Suggested location:** `src/surgical_media/qa/originality_analyzer.py`

Responsibilities: - Compare scripts and scene plans against prior
channel content. - Identify repeated wording, story beats and excessive
asset reuse. - Evaluate the presence of original commentary, research
and creative contribution. - Produce an explanation, not merely a
numeric score.

Do not market an originality score as a YouTube or TikTok monetization
prediction. It is an internal review aid.

### 5.9 Editorial and Monetization Review --- P1/P3

**Suggested location:** `src/surgical_media/qa/editorial_review.py`

Responsibilities: - Review factual claims and source quality. - Verify
asset-rights status and attribution. - Identify sensitive topics and
potentially harmful synthetic depictions. - Check required AI,
sponsorship, affiliate or other disclosures. - Apply profile-specific
approval rules. - Produce a publishing-readiness report.

The review must distinguish: 1. Technical validity. 2. Rights and
provenance completeness. 3. Editorial risk. 4. Platform-policy checks.
5. Human approval status.

A pass in one category does not imply a pass in another.

### 5.10 Publishing Director --- P3/P4

**Suggested location:**
`src/surgical_media/publishing/publishing_director.py`

Responsibilities: - Generate titles, descriptions, captions and
hashtags. - Assemble thumbnail variants and credits. - Include
disclosure and provenance metadata. - Prepare platform-specific
publishing packages. - Optionally integrate with official platform APIs
after explicit authorization.

Default behavior should be **prepare, do not publish**. Direct
publishing requires configured credentials, explicit permission,
platform-compliant API use and an approval record.

------------------------------------------------------------------------

## 6. Data contracts

Use JSON Schema with explicit versions. Keep model output separate from
trusted system metadata.

### 6.1 Production job example

``` json
{
  "schema_version": "1.0.0",
  "job_id": "generated-unique-id",
  "topic": "Horse Tenny's disastrous first date",
  "profile": "comedy",
  "audience": "general",
  "language": "en",
  "target_duration_seconds": 45,
  "platforms": ["tiktok", "youtube_shorts"],
  "aspect_ratio": "9:16",
  "approval_policy": "human_before_export",
  "budget": {
    "currency": "USD",
    "maximum_cost": 5.00
  },
  "creative_constraints": {
    "tone": "playful",
    "fictional_content": true
  }
}
```

The example is illustrative. Production identifiers, enums and currency
handling must be defined in the actual schema.

### 6.2 Research report

Minimum fields: - `schema_version` - `subject` - `researched_at` -
`sources[]` - `claims[]` - `conflicts[]` - `limitations[]`

Each source should include a stable ID, URL, publisher, publication date
when available, retrieval time and source type.

### 6.3 Storyboard contract

Each scene should include: - Scene ID and order. - Narration text or
audio reference. - Intended duration. - Visual description. - Asset
references. - Transition. - On-screen text. - Research claim references
where applicable. - Safety/editorial flags. - Rendering instructions
supported by the existing engine.

### 6.4 Asset manifest

Each asset should include: - Asset ID and file reference. - Asset
type. - Source/provider. - Creator or rights holder when known. -
License and permitted use. - Attribution requirement. - Restrictions and
expiry where applicable. - Generation metadata where applicable. -
Verification status.

**Fail closed for publishing:** an asset with unknown or incompatible
rights must be blocked from a commercial publishing package until
resolved.

### 6.5 Editorial review

Record: - Review ID and job ID. - Review policy version. - Findings and
severity. - Claim verification status. - Rights status. - Disclosure
requirements. - Required human approver. - Decision, reviewer and
timestamp.

------------------------------------------------------------------------

## 7. CLI and API proposal

Build and test a stable CLI before adding a web service. The command
examples below are proposed interfaces, not existing commands.

### 7.1 Proposed CLI

``` bash
# Validate a production request
surgical-media job validate ./jobs/example/job.json

# Create a job
surgical-media job create ./jobs/example/job.json

# Inspect job state
surgical-media job status <job-id>

# Generate research and creative plan
surgical-media job plan <job-id>

# Render a preview
surgical-media job preview <job-id>

# Run quality checks
surgical-media job audit <job-id>

# Record human approval
surgical-media job approve <job-id>

# Export a publishing package
surgical-media job export <job-id> --platform tiktok
```

### 7.2 Proposed API, when justified

  -----------------------------------------------------------------------------------
  Method                  Path                                Purpose
  ----------------------- ----------------------------------- -----------------------
  POST                    `/api/v1/jobs`                      Create a production job

  GET                     `/api/v1/jobs/{job_id}`             Retrieve status and
                                                              summary

  GET                     `/api/v1/jobs/{job_id}/artifacts`   List generated
                                                              artifacts

  POST                    `/api/v1/jobs/{job_id}/plan`        Start research and
                                                              creative planning

  POST                    `/api/v1/jobs/{job_id}/preview`     Request a preview
                                                              render

  POST                    `/api/v1/jobs/{job_id}/audit`       Run configured QC and
                                                              editorial checks

  POST                    `/api/v1/jobs/{job_id}/approval`    Record an approval or
                                                              rejection

  POST                    `/api/v1/jobs/{job_id}/exports`     Create a
                                                              platform-specific
                                                              package

  GET                     `/api/v1/profiles`                  List enabled production
                                                              profiles
  -----------------------------------------------------------------------------------

API requirements: - Authentication and authorization. - Request
validation. - Rate limits and job quotas. - Idempotency keys for job
creation and export. - Pagination for job/artifact lists. - Structured
error responses. - Audit logging. - No secret values in responses or
logs.

------------------------------------------------------------------------

## 8. Repository layout proposal

Adapt to the current repository rather than imposing a disruptive
restructure.

``` text
surgical-media/
├── existing-renderer-and-components/
├── src/
│   └── surgical_media/
│       ├── orchestration/
│       ├── agents/
│       ├── contracts/
│       ├── providers/
│       │   ├── research/
│       │   ├── image/
│       │   ├── video/
│       │   ├── audio/
│       │   └── publishing/
│       ├── assets/
│       ├── platforms/
│       ├── qa/
│       └── publishing/
├── schemas/
├── profiles/
│   ├── comedy/
│   ├── documentary/
│   ├── politics/
│   ├── education/
│   └── commercial/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── end_to_end/
└── docs/
    ├── audits/
    ├── architecture/
    ├── decisions/
    └── plans/
```

------------------------------------------------------------------------

## 9. Delivery roadmap and work packages

Priorities: - **P0:** prerequisite / stability. - **P1:** first usable
production workflow. - **P2:** quality and creative differentiation. -
**P3:** editorial and commercial safeguards. - **P4:** publishing and
scale.

Effort estimates should be assigned only after the repository audit and
team-capacity review.

### Wave 0 --- Baseline and design (P0)

Work packages: - `SM30-001` Repository and implementation inventory. -
`SM30-002` Reconcile documentation, version and test claims. -
`SM30-003` Map current renderer and storyboard interfaces. - `SM30-004`
Baseline tests and performance measurements. - `SM30-005` Security and
dependency review. - `SM30-006` Approve production-job and artifact
contracts. - `SM30-007` Record architecture decisions.

Exit criteria: - Baseline report merged. - Current tests reproducibly
run. - Integration points identified. - No duplicate feature development
planned. - Initial schemas reviewed and versioned.

### Wave 1 --- Production orchestration (P1)

Work packages: - `SM30-010` Job model, persistence and lifecycle. -
`SM30-011` Production Director. - `SM30-012` Contract validation and
error model. - `SM30-013` CLI job commands. - `SM30-014` Recovery,
retries and idempotency. - `SM30-015` First end-to-end
topic-to-storyboard test.

Exit criteria: - A request creates a durable job. - Job state survives
restart. - Invalid agent output is rejected. - A valid storyboard is
produced and accepted by the existing renderer.

### Wave 2 --- Research and creative workflow (P1)

Work packages: - `SM30-020` Research provider interface. - `SM30-021`
Source and claim registry. - `SM30-022` Research Director. - `SM30-023`
Creative Director. - `SM30-024` Script-to-claim traceability. -
`SM30-025` Comedy profile and pilot.

Exit criteria: - Sources and claims are traceable. - Unsupported factual
statements are flagged. - Script and storyboard validate. - Pilot can be
rendered using existing components.

### Wave 3 --- Audio, visuals and inspection (P2)

Work packages: - `SM30-030` Audio Director contract. - `SM30-031` Voice
and pronunciation profiles. - `SM30-032` Visual Director. - `SM30-033`
Optional media provider adapter interface. - `SM30-034` Asset provenance
and rights enforcement. - `SM30-035` Visual QA. - `SM30-036` Platform
export profiles.

Exit criteria: - A pilot includes narration and visual assets with
provenance. - Provider failures are handled gracefully. - Visual QA
produces timestamped findings. - Each enabled export profile passes
technical validation.

### Wave 4 --- Editorial and monetization readiness (P3)

Work packages: - `SM30-040` Editorial risk classification. - `SM30-041`
Originality review. - `SM30-042` Disclosure and attribution checks. -
`SM30-043` Human approval workflow. - `SM30-044` Political profile
safeguards. - `SM30-045` Policy profile update process.

Exit criteria: - High-risk content cannot bypass required approval. -
Rights and disclosure gaps block package release. - Editorial findings
are auditable. - No internal score is represented as a platform
monetization guarantee.

### Wave 5 --- Publishing and operations (P4)

Work packages: - `SM30-050` Publishing package generator. - `SM30-051`
Metadata and thumbnail variants. - `SM30-052` Content calendar export. -
`SM30-053` Optional official publishing API adapter. - `SM30-054`
Analytics ingestion adapter. - `SM30-055` Cost and usage reporting.

Exit criteria: - Approved content can be packaged consistently. -
Publishing remains disabled unless explicitly configured and
authorized. - Cost and usage records are available per job. - Platform
integrations have independent tests and permission controls.

------------------------------------------------------------------------

## 10. Testing and release strategy

### 10.1 Test layers

**Unit tests** - Schema validation. - Job state transitions. - Retry and
idempotency behavior. - Claim/source mapping. - Asset rights
decisions. - Platform profile calculations. - QC finding generation.

**Contract tests** - Agent input/output schemas. - Provider adapter
behavior. - Renderer input compatibility. - API request and response
contracts.

**Integration tests** - Production Director to specialist agents. -
Storyboard validator to existing renderer. - Asset registry to editorial
review. - QC results to approval workflow.

**End-to-end tests** 1. Horse Tenny comedy pilot. 2. Educational
horse-care explainer. 3. Current-affairs explainer with dated sources.
4. Political commentary or satire with required safeguards. 5.
Commercial product explainer with rights and disclosure records.

Use deterministic fixtures and mocked external providers in CI. Keep a
smaller, explicitly controlled live-provider test suite separate to
manage cost and nondeterminism.

### 10.2 Release gates

A release candidate must satisfy: - All critical unit and contract tests
pass. - Existing renderer regression tests pass. - No unresolved
critical security finding. - All export artifacts pass technical QC. -
Asset rights status is complete for the intended use. - Required
editorial and human approvals are recorded. - Provider and production
costs are within configured budgets. - Documentation matches the
released behavior.

### 10.3 Human evaluation rubric

Review each pilot on a 1--5 scale: - Opening hook. - Story clarity. -
Pacing. - Audio intelligibility. - Visual composition. - Scene
diversity. - Original creative contribution. - Factual accuracy, where
applicable. - Audience value. - Brand/profile consistency.

Keep reviewer comments and examples. Do not use a model-generated score
as the sole release decision.

------------------------------------------------------------------------

## 11. Security, privacy and operational controls

### Security

-   Never commit API keys, access tokens or credentials.
-   Use environment-based configuration or a secrets manager.
-   Validate all user, agent and provider inputs.
-   Restrict file access to approved job workspaces.
-   Avoid shell interpolation; use safe subprocess argument arrays.
-   Apply timeouts, file-size limits and resource limits.
-   Pin and review dependencies.
-   Enable repository security alerts and dependency review where
    available.
-   Keep publishing credentials separate from generation credentials.

### Prompt and content injection

Treat retrieved pages, uploaded documents, captions, image metadata and
provider responses as untrusted data. They must never be allowed to
override system policy or invoke tools by embedding instructions.

### Privacy and likeness

-   Use only appropriately authorized voices, likenesses and personal
    data.
-   Record consent and permitted-use restrictions where relevant.
-   Do not create deceptive impersonations.
-   Apply stricter review to realistic depictions of identifiable
    people.

### Operational controls

-   Structured logs with job IDs.
-   Redaction of secrets and sensitive values.
-   Job cancellation.
-   Retry limits.
-   Disk and render quotas.
-   Artifact retention policy.
-   Failure alerts.
-   Backup and recovery plan.

------------------------------------------------------------------------

## 12. Cost and performance strategy

Every production job should support: - Maximum budget. - Estimated
provider cost before expensive steps. - Actual provider usage and cost
where available. - Rendering duration. - CPU/GPU and memory observations
where practical. - Asset storage footprint. - Cache hit/miss
information.

Optimization priorities: 1. Avoid unnecessary model calls. 2. Cache
reusable research and approved assets within their rights and freshness
limits. 3. Use lower-cost models for bounded classification tasks. 4.
Reserve stronger models for work that needs them. 5. Reuse validated
intermediate rendering artifacts. 6. Offer preview and final-render
quality settings. 7. Stop or request approval when a job exceeds budget.

Do not cache time-sensitive research indefinitely. Define expiry and
revalidation rules.

------------------------------------------------------------------------

## 13. Commercial direction

Three business models can be supported by the same core architecture.

  -----------------------------------------------------------------------
  Model                   Offering                Potential revenue
  ----------------------- ----------------------- -----------------------
  Managed production      Videos and campaigns    Per-project fees,
                          for clients             retainers

  Subscription product    Self-service agent and  Subscriptions, usage
                          production workflows    credits

  Owned content studio    Original recurring      Eligible platform
                          channels                revenue, sponsorships,
                                                  affiliates
  -----------------------------------------------------------------------

**Recommended sequence:** validate the internal production workflow
first, operate a small number of original content channels, measure real
cost and quality, then decide whether a managed service or SaaS offering
is justified.

Do not build billing, multi-tenant infrastructure or a large customer
dashboard before validating the core production workflow.

------------------------------------------------------------------------

## 14. Content DNA --- longer-term differentiator

Introduce channel-level memory and configuration after job provenance
and profile configuration are stable.

Content DNA may contain: - Channel identity and tone. - Character
profiles and approved likeness references. - Voice assignments. - Visual
identity and brand assets. - Editorial rules. - Audience and format
preferences. - Prior episode references. - Reuse restrictions. -
Performance observations.

Content DNA should guide consistency, not force repetitive outputs. It
must be versioned, reviewable and scoped to the correct channel or
project.

------------------------------------------------------------------------

## 15. Key risks and mitigations

  -----------------------------------------------------------------------
  Risk                    Impact                  Mitigation
  ----------------------- ----------------------- -----------------------
  Building features       Wasted effort           Complete implementation
  already present                                 inventory first

  Agent output is         Failed or unsafe        Strict schemas and
  malformed               production              semantic validation

  Fabricated or weak      Misinformation          Claim-source
  research                                        traceability and human
                                                  review

  Rights are unclear      Copyright and           Rights registry; block
                          commercial exposure     unresolved assets

  Repetitive              Poor audience value and Originality review and
  mass-produced output    platform risk           human evaluation

  Political synthetic     Reputational and policy Risk classification,
  media misleads          risk                    disclosure and human
                                                  approval

  Provider outage or      Production interruption Adapter interfaces and
  lock-in                                         graceful fallback

  Uncontrolled API spend  Financial loss          Per-job budgets,
                                                  estimates and hard
                                                  limits

  Rendering resource      Delays and service      Quotas, concurrency
  exhaustion              failure                 limits and checkpoints

  Platform rules change   Invalid publishing      Versioned profiles and
                          assumptions             scheduled policy review
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 16. Decisions required from project ownership

The following decisions affect architecture and should be resolved
before the relevant implementation wave.

1.  **Media-generation policy:** Should the project remain limited to
    procedural and open-licensed media, or may optional external AI
    image/video providers be used? If permitted, which rights and
    provider requirements apply?
2.  **Agent environment:** Is the primary target Hermes, or should the
    integration contract be framework-neutral from the start?
3.  **Publishing authority:** Should the system only prepare packages,
    or may approved agents publish through official APIs?
4.  **First business objective:** Internal content channels, client
    production, or a future subscription platform?
5.  **Infrastructure:** Local-first deployment, hosted workers, or a
    hybrid model?
6.  **Budget:** What are the maximum per-video and monthly
    provider/render budgets?
7.  **Approval policy:** Which categories always require human approval?
8.  **Initial platforms and languages:** Which should be supported in
    the first release?

Record decisions in `docs/decisions/` using short architecture decision
records.

------------------------------------------------------------------------

## 17. First pilot: Horse Tenny comedy

### Why this pilot

A fictional comedy episode offers a controlled first test of: - Job
creation. - Creative concept generation. - Character continuity. -
Script timing. - Multi-voice narration, if supported. - Scene
planning. - Existing rendering integration. - Vertical export. - Visual
and technical QC. - Thumbnail and caption packaging.

It avoids making the first integration test depend on live political
research or sensitive real-person depictions.

### Pilot brief

**Working title:** Horse Tenny --- The Disastrous First Date\
**Format:** Short-form vertical video\
**Target duration:** Approximately 45 seconds\
**Profile:** Fictional comedy\
**Initial destinations:** TikTok and YouTube Shorts\
**Approval:** Human review before final package release

### Pilot deliverables

-   Production job record.
-   Creative brief and approved script.
-   Storyboard.
-   Audio manifest.
-   Asset manifest with rights records.
-   Rendered preview.
-   Final video export.
-   Technical QC report.
-   Visual QA report.
-   Editorial review.
-   Thumbnail and publishing metadata.
-   Cost and provenance report.

### Pilot success condition

The complete job can be created from a structured request, processed
through the new orchestration layer, rendered by the existing engine and
delivered with traceable assets and passing quality checks.

------------------------------------------------------------------------

## 18. Proposed first sprint backlog

The first sprint should be planning and baseline work, not premature
implementation of every proposed agent.

  ---------------------------------------------------------------------------
  ID                Task                  Priority          Output
  ----------------- --------------------- ----------------- -----------------
  SM30-001          Inspect repository    P0                Baseline audit
                    and map current
                    architecture

  SM30-002          Verify documented     P0                Evidence-backed
                    features and test                       capability
                    claims                                  inventory

  SM30-003          Identify              P0                Interface
                    renderer/storyboard                     specification
                    integration contract

  SM30-004          Review security,      P0                Risk register
                    dependencies and
                    external services

  SM30-005          Agree production job  P0                State diagram and
                    lifecycle                               decision record

  SM30-006          Draft job, storyboard P0                Versioned JSON
                    and asset schemas                       Schemas

  SM30-007          Select the first      P1                Approved pilot
                    pilot profile                           brief

  SM30-008          Estimate effort and   P0                Delivery estimate
                    infrastructure cost
  ---------------------------------------------------------------------------

**Sprint exit:** The team can point to the exact existing code that will
receive a validated storyboard and can demonstrate the baseline tests.
Only then should implementation tickets for the Production Director be
finalized.

------------------------------------------------------------------------

## 19. Definition of done

A feature is not complete merely because the code exists.

Each module is done when: - Its responsibility and boundaries are
documented. - Inputs and outputs are schema-validated. - Errors are
explicit and actionable. - Secrets and permissions are handled safely. -
Unit and contract tests pass. - Integration tests cover its real
boundaries. - Logs and provenance are sufficient for diagnosis. - Cost
and resource behavior are understood. - Documentation and examples match
actual behavior. - A reviewer has approved the change.

A production release is done when the complete workflow passes its
release gates and the team can reproduce the pilot from documented
instructions.

------------------------------------------------------------------------

## 20. Final recommendation

Surgical Media should evolve through deliberate, testable increments.

The recommended sequence is:

1.  Audit and stabilize the actual codebase.
2.  Define versioned production contracts.
3.  Build the Production Director.
4.  Integrate research and creative planning.
5.  Render the first controlled pilot through the existing engine.
6.  Add audio, visual and platform intelligence.
7.  Add originality, rights and editorial safeguards.
8.  Expand publishing and commercial integrations only after the
    workflow is proven.

The core strategic principle is:

> **Build the intelligence around the engine. Preserve what works. Make
> every new component modular, testable, replaceable and accountable.**

The strongest long-term product is not a machine that simply generates
more videos. It is a production system that helps agents and creators
make content people genuinely want to watch, while preserving accuracy,
originality, rights, quality and trust.

------------------------------------------------------------------------

## Reference links

-   Surgical Media repository:
    https://github.com/TeacherEvan/surgical-media
-   YouTube channel monetization policies:
    https://support.google.com/youtube/answer/1311392
-   YouTube altered or synthetic content disclosure:
    https://support.google.com/youtube/answer/14328491
-   TikTok AI-generated content guidance:
    https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content
-   GitHub repository security best practices:
    https://docs.github.com/en/repositories/creating-and-managing-repositories/best-practices-for-repositories

**Policy note:** Platform policies and technical limits change. Verify
the official current requirements at implementation and release time.
This plan does not guarantee monetization eligibility or platform
approval.

------------------------------------------------------------------------

**Prepared by G&L --- Product & Engineering Proposal**\
**Surgical Media 3.0 \| Build the intelligence around the engine.**
