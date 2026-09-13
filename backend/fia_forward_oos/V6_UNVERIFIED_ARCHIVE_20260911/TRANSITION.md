This is a partial preservation archive, not recovered evidence.

The event file is the exact 14,518 bytes exported from production Postgres by a
read-only query. Its file SHA-256 is recorded in classification.json. Its
unsigned-event hash matches the original lock hash. The seal is an unchanged
copy of the existing V6 seal. Neither the missing 25,721-byte evidence file nor
LEDGER_HEAD.json is present or reconstructed here.

NQ-FOOS-20260909 is PERMANENTLY_UNVERIFIED and ineligible for validation. Its
record, original timestamp, original hashes, unresolved outcomes and original
seal remain preserved. This classification is an explicit research decision;
it does not rewrite the event to pretend that it never existed. The archive
must never be imported into a successor's active ledger or metrics.

The original V6 campaign is scientifically PARTIAL: its existing event and seal
survive, but the original evidence needed to verify the observation does not.
An event-only database copy is insufficient. Accessible Render service/database
metadata, production SQL schema/rows and deployment/runtime logs were inspected.
The service and database are Free instances: there is no accessible service
shell/persistent disk or managed Postgres recovery backup on those plans.
No claim is made about inaccessible third-party/manual backups.

The repaired code changes the sealed dependency fingerprint. Resuming prospective
collection under that code requires a separately sealed successor campaign. A
healthy HTTP endpoint, successful CI job or desire for a green status is not a
reason to start it. No successor has been created or activated by this repair.

Required transition order:

1. Complete and review release gates at the exact proposed commit. Record every
   failed/unavailable gate. Decide explicitly whether prospective collection is
   ready to resume; infrastructure test success is not predictive evidence.
2. Keep V6 closed to new validation observations. Preserve the old database rows,
   seal, archive and this classification. Do not UPDATE/DELETE production rows,
   rewrite the old seal, regenerate its missing anchor, resolve its outcomes
   using substitute prices, or manufacture its missing evidence.
3. Use a separate empty active campaign root and a unique campaign ID. Any
   active-root/pointer change must be reviewed as part of the release; this PR
   does not silently switch the existing hard-coded active root. Ensure all API
   routes, collector, verifier, monitor and durable store use the same root/ID.
   Archive paths must stay outside that root's active events/evidence directories.
4. Freeze the reviewed code and create the successor seal with the actual current
   timestamp, before its first observation. Verify the new fingerprint, schema,
   empty production ledger, working full-proof backup and exact-byte restoration.
   No old observation, TEST fixture, archived result or missed checkpoint can seed
   its sample. Its initial production observation count is zero, not a PASS claim.
5. Activate only prospectively after the release decision. Future eligible
   observations must follow the existing time/checkpoint rules. Preserve separate
   4H/8H outcomes; no hindsight edits, historical backfill or weight changes.
6. Verify deployed code/active campaign identity and fail-closed API/dashboard
   behavior. Retain the old V6 classification in operational/research reporting.
   Keep predictive edge NOT_PROVEN without qualifying unseen evidence.

Production main, deployment, settings, weights, Shadow Lab and historical result
files were not changed by this repair. New test observations exist only in
disposable local/CI storage. The old campaign has not been repinned or resealed.

Source for platform recovery limits:
[Render Free instances](https://render.com/docs/free) and
[Postgres recovery](https://render.com/docs/postgresql-backups).
