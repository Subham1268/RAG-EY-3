# EY Middle East Agentic RAG — Sample Test Questions
# ─────────────────────────────────────────────────────
# Use these to test retrieval quality, citation accuracy, and multi-hop reasoning.
# Grouped by complexity and document coverage.

## ── TIER 1: Single-Document Factual Retrieval ────────────────────────────────
# These should retrieve cleanly from a single source document.

Q1: What were the critical AML gaps identified by EY in the UAE bank assessment?
Expected source: 02_EY_ME_AML_Framework_Assessment_UAE_Bank.pdf
Expected content: CDD gap for correspondent banking, TM calibration, beneficial ownership

Q2: What are the key thresholds in the Bahrain Development Bank risk appetite framework?
Expected source: 04_EY_ME_ERM_Framework_BDB_Bahrain.docx
Expected content: NPL ratio 8%, CAR 14%, LCR 120%, operational loss BHD 3M

Q3: What is the overall cybersecurity maturity score for the Jordanian telecom operator?
Expected source: 10_EY_ME_Cybersecurity_Resilience_Jordan_Telecom.pdf
Expected content: Level 2.3/5 cybersecurity, Level 2.1/5 operational resilience, TRC minimum 3.0 by 2025

Q4: What governance score did the Saudi conglomerate receive for Board Composition & Independence?
Expected source: 09_EY_ME_Governance_Board_Effectiveness_KSA_Conglomerate.pdf
Expected content: 62/100 vs benchmark 80/100, only 25% independent directors

Q5: How much is the total digital transformation investment recommended for the Saudi telecom operator?
Expected source: 01_EY_ME_Digital_Transformation_Roadmap_Telecom_KSA.pdf
Expected content: SAR 2.3 billion over 36 months, 4 horizons


## ── TIER 2: Multi-Document Synthesis ────────────────────────────────────────
# These require combining information from 2+ documents.

Q6: What ERM or risk management frameworks has EY Middle East implemented across GCC countries?
Expected sources: 04 (Bahrain/BDB), 08 (Kuwait/KFH), 12 (GCC dashboard)
Expected content: Compare frameworks across jurisdictions, Basel III, ISO 31000

Q7: Compare EY's approach to cybersecurity and operational resilience across the Jordan telecom and the KSA telecom digital transformation engagement.
Expected sources: 10 (Jordan cybersecurity), 01 + 11 (KSA telecom)
Expected content: Contrasting maturity levels, NIST CSF vs digital transformation focus

Q8: What governance recommendations does EY Middle East typically make for entities preparing for capital markets activity (IPO or investor readiness)?
Expected sources: 09 (KSA conglomerate IPO), 03 (OIA Oman / Santiago Principles)
Expected content: Board independence, governance framework, OECD/Santiago Principles

Q9: What are the common AML and compliance themes across EY Middle East bank assessments in the UAE and Bahrain?
Expected sources: 02 (UAE AML), 04 (BDB ERM / CBB compliance)
Expected content: CBUAE / CBB requirements, FATF, Basel III, control gaps


## ── TIER 3: Methodology & Reuse Queries ─────────────────────────────────────
# The core use case: consultant looking to reuse frameworks and approaches.

Q10: What methodology does EY Middle East use to assess cybersecurity maturity?
Expected sources: 10 (NIST CSF 2.0, ISO 27001:2022, TRC Jordan)
Expected content: 12 domains, NIST CSF 6 functions, pen testing, phishing simulation, SOC review

Q11: How does EY structure the Three Lines of Defence model in its ERM frameworks?
Expected sources: 04 (BDB ERM framework)
Expected content: Business units / ERM function / Internal Audit, KRI dashboards, risk committee reporting

Q12: What KPIs and metrics does EY track on a digital transformation engagement?
Expected sources: 07 (KPI Budget Tracker), 01 (KSA telecom roadmap), 11 (transformation charts)
Expected content: ARPU, NPS, capex allocation, horizon milestones

Q13: What does a target operating model redesign engagement look like for a sovereign wealth fund?
Expected sources: 03 (OIA Oman operating model)
Expected content: 3 investment verticals, 4 enabling functions, 18-month roadmap, Santiago Principles, GIPS

Q14: What transaction monitoring issues has EY identified in banking AML assessments and what are the remediation steps?
Expected sources: 02 (UAE AML — TM calibration)
Expected content: 68% false positives, 14,200 alert backlog, rule recalibration, independent model validation


## ── TIER 4: Challenging / Stress Tests ──────────────────────────────────────
# These test robustness: ambiguous queries, multi-hop, or out-of-scope.

Q15: What is the estimated cost of the AML remediation programme and what does it cover?
Expected: AED 47-62M, technology upgrades AED 28M, 35 FTEs, training

Q16: Which EY Middle East engagements involved a regulatory trigger or supervisory finding?
Expected: UAE AML (CBUAE findings), Jordan cybersecurity (TRC guidelines), BDB (CBB requirement)

Q17: What is the recommended deal approval cycle time after OIA's operating model is implemented?
Expected: 35% reduction → from 42 days to ~27 days

Q18: What specific vulnerabilities were found in penetration testing of the Jordan telecom operator?
Expected: 3 critical + 7 high severity, unauthenticated API endpoint exposing 240,000 subscriber records

Q19: [Out of scope test] What is EY's global revenue for 2023?
Expected behaviour: Agent should state it cannot find this in the EY ME knowledge base

Q20: What cybersecurity tools and investments are recommended for the Jordan telecom over 90 days?
Expected: EDR 85K JOD, SIEM expansion 120K, PAM 95K, IR tabletop 35K, phishing training 25K, DLP 110K, billing DR 320K
