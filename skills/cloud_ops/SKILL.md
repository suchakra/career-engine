---
name: cloud_ops
description: Deploy, validate, and tear down CareerEngine's GCP infrastructure (Terraform) and run the gate suite. Use when working with infrastructure/, make deploy/destroy/tf-check, Cloud Run, Firestore, Secret Manager, or the pending-action sweep job.
---

# CareerEngine — Cloud Ops

Operational runbook for the `infrastructure/` Terraform baseline and the release
gates. Full architecture: [ARCHITECTURE.md §9](../../docs/ARCHITECTURE.md);
layout + variables: [infrastructure/README.md](../../infrastructure/README.md).

## Gates (no credentials needed)

```bash
make check       # ruff + mypy --strict + pytest (application code)
make tf-check    # terraform fmt -check + validate (dev AND prod roots)
```
Both must be green before any deploy. `terraform validate` needs a one-time
`terraform init -backend=false` (handled by `make tf-check`); no GCP creds.

## Deploy / destroy (need GCP credentials)

```bash
gcloud auth application-default login
cp infrastructure/envs/dev/terraform.tfvars.example infrastructure/envs/dev/terraform.tfvars
# edit terraform.tfvars → set project_id (and image once pushed)
make deploy      # terraform -chdir=infrastructure/envs/dev apply
make destroy     # terraform -chdir=infrastructure/envs/dev destroy
```
Prod is driven directly and needs a GCS backend configured in
`infrastructure/envs/prod/main.tf`; prod `image` is **required** (the hello
placeholder is rejected) and Firestore defaults to `ABANDON` (survives destroy).

## What gets created

Cloud Run (v2) + runtime SA · Firestore (Native) · Artifact Registry (Docker) ·
Secret Manager (API + least-privilege `roles/secretmanager.secretAccessor` for
the runtime SA) · Cloud Scheduler (→ 14-day pending-action sweep, OIDC-authed
with the base service URL as audience).

## Guard rails (do NOT violate)

- **Never** add an `allUsers` `run.invoker` binding to "fix" a browser 403 —
  route through Identity-Aware Proxy / Identity Platform (Phase 2B) instead.
- **Never** create per-user BYOK secrets in Terraform — they are created at
  runtime by `auth/key_vault.py` (`ce-key-{user_id}`). No secret material in TF
  or state.
- Keep the TF `contract_version` default in `envs/*/variables.tf` in lockstep
  with `config.py:CONTRACT_VERSION`.
- `terraform.tfvars`, state, and lock files are gitignored — never commit them.

## The sweep job

`jobs/pending_action_sweep.py` runs `run_sweep(store=FirestoreWorkspaceStore(),
today=<date>)`. Cloud Scheduler POSTs the sweep endpoint on a cron (default
`0 3 * * *`); the invoker SA holds `roles/run.invoker`. The sweep is idempotent
and isolates per-user failures.

## Rollback

Re-`apply` a previous commit of `infrastructure/` (declarative). `make destroy`
tears down **dev** only (Firestore `DELETE` there); prod data is retained.
