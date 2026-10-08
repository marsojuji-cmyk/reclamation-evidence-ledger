# Security Policy

## What this repository is

`reclamation-evidence-ledger` is an independent satellite watchdog and evidence ledger for Alberta orphan-well reclamation monitoring.

## Reporting a vulnerability

**Preferred: GitHub private vulnerability reporting.** Open the **Security** tab on this repository and
choose **Report a vulnerability**. That channel is private between you and the maintainer, requires no
email, and nothing is posted publicly. Private reporting is enabled on this repository.

If you cannot use that channel, open a **minimal public issue** stating only that you have a security
report and how to reach you. Please do **not** include exploit details, proof-of-concept code, or
affected-version specifics in a public issue.

## Scope

**In scope:**
- Packet verification tampering or cryptographic digest forgery in evidence ledgers.
- Schema bypass or invalid data ingestion that produces misleading verification status.

**Out of scope / stated plainly:**
- Satellite imagery data is derived from open public sources (Copernicus Sentinel-2). The ledger measures observable change; it is not a legal land survey or regulatory compliance audit.

## What to expect

| Stage | Commitment |
|---|---|
| Acknowledgement of your report | within 7 days |
| Initial assessment and severity call | within 14 days |
| Fix, or an agreed public disclosure | coordinated with you |

You will be credited in the fix or advisory unless you ask to remain anonymous.

## What this policy does NOT offer

There is **no bug bounty**, and no monetary reward is offered or implied. This is an independent
research project maintained by one person. What it can offer is a fast, honest response and public
credit.
