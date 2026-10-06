# Current contained appointment release — 6 October 2026

The application entry is `api/index.py`; it uses this repository's complete
`appointment-system/` package and sibling `appointment-settings/`. It does not
load another client or the factory runtime. The neutral release is
`35b92073c14c709849133063ba4bb31166319a91ecf23acaa2a3f4bb63239af1`,
with 550 manifest files and 34 migrations. Both production common databases are
independently checked at migration 034 with booking OFF authority preserved.
Worker deployment and public website/account acceptance have separate outcomes;
a GitHub commit does not prove that the public website is running this revision.

The local release proof is an exhaustive segmented execution with a focused
AstroAdvice website repair. It retains the original failed native occurrence,
its six passing whole-module repair checks and all required shared-engine checks.
Shared Python and JavaScript statement/branch coverage exceed 90% without
exclusions. Broader marketing-site coverage/design remains separately deferred.

Use the [contained package guide](../appointment-system/README.md), the
[installation profile](../appointment-settings/project.json) and the
[public backup configuration](../appointment-settings/backup.json). Protected
values belong in the existing project-specific account settings, never in source.
Company control is `/company/booking-control`; staff enquiries are separate.
Calendar, client record copy and company record copy approvals remain separate
owner flows. Completed backup Google permissions do not approve these website
resources. Booking remains OFF until its normal readiness/activation checks pass.

## Official backup and independent restore

The active workflows are `.github/workflows/appointment-database-backup.yml`
and `.github/workflows/appointment-backup-validation.yml`. Export gets its
restricted read-only database/writer settings; validation gets a separate reader,
decryption identity and signing key; retention gets writer access plus the signed
proof. No validator restores into production. Every completed triple consists of
an encrypted archive, signed manifest and independently signed restore proof.

Fresh official export, independent stored restore and explicit completed retention
are accepted for this exact common release and 34-migration ledger. Source run
37509098588 at commit 7a018cd729a0c96e718caa399bf08a08946b94ee triggered validator 37509492645. Both jobs
retain these original source identities after cleanup. The stored signed proof
binds the archive/manifest versions and the new OFF restore authority. Retention
reported completion with zero eligible old verified groups removed. Unsupported
old private archives remain preserved; they are not claimed as accepted new-format
proofs. Historical backup commands and the duplicate old engine are retired only
after this replacement proof, with exact original bytes archived locally.
