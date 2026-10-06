
# CORE / MUST WORK

Basis: the rubric is cumulative — "You can only reach a tier if the previous tier is satisfied" — and Requirements carry **50%** of total marks (Architectural & UI Design 25%, Usability 25%). Items below gate all marking or protect the largest mark blocks.

## C1 — Public, runnable web-app dashboard (submission)
Type: REQUIRED — failure blocks all marking
Marks: Gate for all three criteria (100% of marks). Submission is "URL to a public repository".
Requirement: The RAT is a **web-app dashboard** (not a CLI/library). It is submitted as a URL to a **public** repository that the marker can clone and run.
Constraints: Repo must be public (a private repo blocks marking entirely). Must run from a clean clone without the marker needing any personal credentials. The brief specifies no environment variables, credentials, or external services.
Done when: Marker clones the public repo, follows the documented setup, and the dashboard loads.
Depends on: —

## C2 — Repository ingestion: zip + remote URL
Type: REQUIRED — at least ONE form is the floor for any Requirements credit; BOTH forms are required for the Requirements ≤50% tier
Marks: Requirements (50%): "Either: zip file or remote URL ingestion" = ≤25% tier cap (12.5% of total); "Both: zip file and remote URL ingestion" = unlocks ≤50% tier (25% of total)
Requirement: Accept a repository in two forms: (1) a **zip file of the repo with the `.git` file or directory**; (2) a **remote repository URL that is then deeply cloned**.
Constraints: Remote ingestion must deep clone (full history — a shallow clone cannot produce the metrics). The zip form must include `.git`. Cloning must work for public repos without authentication.
Done when: A repo can be ingested via both forms and analysed; a deep clone of a supplied public URL succeeds.
Depends on: C1

## C3 — Commit/object semantics (metric foundation)
Type: CORE — every metric category depends on these semantics
Marks: Underpins the entire Requirements 50%
Requirement: For each commit \(h\): a single author \(h[a]\) **after author merging**; a previous commit \(h[p]\), with the initial commit having \(h[p] = h_\emptyset\) (an **empty commit**); a committer date \(h[\text{committer-date}]\); file set \(h[F]\) and directory set \(h[D]\); objects identified by **path**. \(\bar{H}\) = the set of **non-merge commits reachable from a specified reference commit \(h_r\)** (typically HEAD); a commit set \(H \subseteq \bar{H}\). \(H_t = \{h \in \bar{H} \mid t \le h[\text{committer-date}]\}\); \(H_{i,j} = \{h \in \bar{H} \mid i \le h[\text{committer-date}] < j\}\). \(H[F] = \bigcup_{h\in H}(h[F] \cup h[p][F])\); \(H[D] = \bigcup_{h\in H}(h[D] \cup h[p][D])\), **including the root**.
Constraints: Merge commits excluded from \(\bar{H}\). **Binary files are not measured** (Git provides the definition and detection). **Rename detection is enabled with a threshold of 50%**: just renaming a file must not change its metrics; changing and renaming only impacts the changed lines, **attributed to the new path**. A deleted object (exists in \(h[p]\) but not \(h\)) is recorded as a change (**lines removed**) on its path. Time filters use **committer-date**; \(H_{i,j}\) is inclusive at \(i\), **exclusive at \(j\)**.
Done when: Metrics computed under these semantics match the sample metrics provided from the specific commit hash for the test repos.
Depends on: C2

## C4 — File Metrics
Type: CORE
Marks: One of the five categories ("repo, file, directory, set, author") required for the Requirements ≤50% tier (25% of total)
Requirement: Per file \(f\), commit \(h\): File Added Lines \(l^+_{h,f}\); File Removed Lines \(l^-_{h,f}\); File Growth \(\delta_{h,f} = l^+_{h,f} - l^-_{h,f}\); File Churn \(\lambda_{h,f} = l^+_{h,f} + l^-_{h,f}\).
Constraints: Binary files excluded; rename/deletion semantics per C3.
Done when: Values match the provided sample metrics (specific commit hash) on the test repos.
Depends on: C3

## C5 — Directory Metrics
Type: CORE
Marks: One of the five categories required for the Requirements ≤50% tier
Requirement: Per directory \(d\), commit \(h\): Added \(l^+_{h,d}\), Removed \(l^-_{h,d}\), Growth \(\delta_{h,d}\), Churn \(\lambda_{h,d}\), each \(= \sum_{f \in d}(\cdot)_{h,f} + \sum_{d' \in d}(\cdot)_{h,d'}\) over **immediate** files and immediate subdirectories. A file \(f\) is in directory \(d\) at commit \(h\) if it is in \(h[F]\) **or** \(h[p][F]\) and is an immediate child of \(d\) (similarly subdirectories with \(h[D]\), \(h[p][D]\)). An immediate object is directly below the specified directory.
Constraints: Recursive immediate-child definition (see the foo/bar.txt, foo/baz/ example). Files deleted in \(h\) (present only in \(h[p]\)) still count in that commit's aggregation. \(H[D]\) includes the root.
Done when: Values match the provided sample metrics on the test repos.
Depends on: C4

## C6 — Repository Metrics
Type: CORE
Marks: One of the five categories required for the Requirements ≤50% tier
Requirement: Repository metrics are **directory metrics on the root** of the commit tree.
Constraints: Root must be a first-class directory object (per C5).
Done when: Root-level values match the provided sample metrics on the test repos.
Depends on: C5

## C7 — Commit Set Metrics
Type: CORE
Marks: One of the five categories required for the Requirements ≤50% tier
Requirement: For \(o \in H[F] \cup H[D]\) over commit set \(H\): Added \(l^+_{H,o}\), Removed \(l^-_{H,o}\), Growth \(\delta_{H,o}\), Churn \(\lambda_{H,o}\) (sums of per-commit values over \(h \in H\)); **Modifications** \(n_{H,o} = \sum_{h\in H} In(h,o)\) where \(In(h,o) = 1\) if \(\lambda_{h,o} > 0\), else 0; **Modification frequency** \(\eta_{H,o} = n_{H,o}/|H|\) if \(|H| \neq 0\), else 0; **Churn rate** \(\rho_{H,o} = \lambda_{H,o}/|H|\) if \(|H| \neq 0\), else 0.
Constraints: Commit sets are subsets of \(\bar{H}\) — selected by time period (\(H_t\), \(H_{i,j}\)) or manually. Zero-division guards are part of the definition, not optional. Commit-set time filters follow C3's committer-date interval semantics.
Done when: Values match the provided sample metrics; an empty commit set (\(|H|=0\)) yields 0, not an error.
Depends on: C4, C5

## C8 — Author Metrics
Type: CORE
Marks: One of the five categories required for the Requirements ≤50% tier
Requirement: Authorship test \(I(a,h) = 1\) if \(a = h[a]\), else 0. **Author Modifications** \(n_{H,o,a} = \sum_{h\in H} I(a,h)\cdot In(h,o)\); **Author Churn** \(\lambda_{H,o,a} = \sum_{h\in H}\lambda_{h,o}\cdot I(a,h)\); **Author Ownership** \(\omega_{H,o,a} = \lambda_{H,o,a}/\lambda_{H,o}\) if \(\lambda_{H,o} \neq 0\), else 0.
Constraints: \(h[a]\) is the author **after author merging** (C8 must work correctly with merging absent; F2 re-derives it when merging is applied). Ownership is 0 when the object has zero churn.
Done when: Values match the provided sample metrics on the test repos.
Depends on: C7

# FEATURE BACKLOG

Rubric tier-3 features: any ONE of F1–F3 unlocks the Requirements ≤75% tier (37.5% of total); ALL THREE are required for ≤100% (50% of total). "Not all features are necessary. Please review the rubric."

## F1 — Filtering
Type: OPTIONAL (mark-earning; tier-3)
Marks: Requirements 50% — one of the three features for ≤75% tier; all three for ≤100%
Requirement: Dashboard filterable by: **a repository; an author; a file or directory; commits** — a specified period of time **or** a manually selected list of commits.
Constraints: Time-period filtering must implement \(H_t\) / \(H_{i,j}\) semantics (committer-date, half-open interval); manual selection means an arbitrary commit list forming \(H \subseteq \bar{H}\).
Done when: All four filter dimensions apply and every metric category (including commit-set and author metrics) respects the active filter.
Depends on: C7, C8; the repository filter requires F3

## F2 — Author Merging
Type: OPTIONAL (mark-earning; tier-3)
Marks: Requirements 50% — one of the three features for ≤75% tier; all three for ≤100%
Requirement: Merge different email addresses/authors using git's **.mailmap**; **if no mailmap is provided, a user must still be able to merge different authors manually**.
Constraints: Merging changes \(h[a]\), and therefore all author metrics (authorship test, author modifications, author churn, ownership). Non-author metrics are unaffected.
Done when: Commits by the same person under different identities are reported as a single author across the dashboard; manual merging works with no mailmap present.
Depends on: C8

## F3 — Multiple Repository Support
Type: OPTIONAL (mark-earning; tier-3)
Marks: Requirements 50% — one of the three features for ≤75% tier; all three for ≤100%
Requirement: The dashboard supports multiple repositories (more than one ingested and selectable/analysable).
Constraints: The overview calls the RAT "a web-app dashboard for multiple repositories", but the rubric places Multi-repo support in the ≤75%/≤100% tiers — the rubric governs prioritisation.
Done when: Two or more repositories can be ingested and analysed, switchable in the dashboard.
Depends on: C2

## F4 — Efficient algorithms, architecture & visualisation
Type: OPTIONAL (quality criterion; cross-cutting)
Marks: Architectural & UI Design = 25% of total; tiers judged holistically
Requirement: Rubric wording, ascending: "Redundant & slow metric computation, poor visualisation of metrics" (≤25%) → "Reasonable metric computation, okay visualisation of metrics" (≤50%) → "Efficient algorithms for metric computation, good visualisation of metrics" (≤75%) → "Efficient algorithms **and architecture** for metric computation, **inspired** visualisation of metrics" (≤100%).
Constraints: Correctness is judged against the provided repos (including the large git repo), so efficiency is measured on real history, and redundant computation is explicitly the bottom-tier descriptor.
Done when: Metric computation avoids redundant work per dashboard query; metric visualisation is clear and good.
Depends on: C3–C8

## F5 — Usability: navigation, error handling, performance, QoL
Type: OPTIONAL (quality criterion; cross-cutting)
Marks: Usability = 25% of total; tiers judged holistically
Requirement: Rubric wording, ascending: "Poor navigation, no error handling, slow performance on small (~1000 commits) repos, no QoL features" (≤25%) → "Okay navigation, minimal error handling, okay performance on small repositories, slow performance on medium (~10000 commits) repos, minimal to none QoL features" (≤50%) → "Good navigation, error handling, good performance on medium repositories, QoL features" (≤75%) → "Excellent navigation, good performance on large (~100000 commits) repos" (≤100%).
Constraints: Performance tiers are defined by commit-count scale (~1000 / ~10000 / ~100000); the provided test repos span these scales.
Done when: Navigation is good, ingestion/parse errors are surfaced (bad zip, missing .git, failed clone), medium repos perform well.
Depends on: C1–C8

# CONFIGURATION / SECRETS

The brief specifies **no environment variables, database credentials, API keys, tokens, ports, runtime versions, or authenticated external services**. There are **no REAL SECRETS** in this test. The only configuration-adjacent values that exist:

## Remote repository URL (runtime user input)
Type: NORMAL CONFIG
Required: Yes — for remote-URL ingestion (C2); supplied per-upload by whoever uses the dashboard.
How supplied: Entered in the web UI at runtime; never pre-configured or hardcoded.
Commit to Git: NO — runtime input, not repository content.
Marker setup: None — public repo URLs (the three test repos are open source); must not require any token or authentication.
Clean-clone impact: None.

## Test repository URLs (cJSON / Redis / Git)
Type: SAFE LOCAL CONFIG (public, open-source GitHub URLs)
Required: Yes, for correctness validation — "Metric correctness is determined against a set of test repositories" with "sample metrics from each of these repos… provided from a specific commit hash".
How supplied: Given in the brief (https://github.com/DaveGamble/cJSON.git, https://github.com/redis/redis.git, https://github.com/git/git.git); public HTTPS clone URLs.
Commit to Git: YES — safe, public values (useful in README/tests if referenced).
Marker setup: None — repos are public; sample metrics are provided by the course from a specific commit hash.
Clean-clone impact: None.

## Public submission repository URL
Type: NORMAL CONFIG (submission mechanism, not app config)
Required: Yes — "Submission: URL to a public repository".
How supplied: The URL you submit as your answer; not stored inside the repo.
Commit to Git: NO / N-A.
Marker setup: Opens/clones the public URL with no credentials.
Clean-clone impact: If the repo is not public, marking is blocked entirely.

## Implementer-chosen app configuration (port, runtime, etc.)
Type: NORMAL CONFIG
Required: Not required by the brief (no ports, runtimes, or services are specified). Any such values are your choice.
How supplied: Safe local defaults that work on a clean clone, documented in the README. Do not require undocumented environment variables. `.env.example` is only needed if you actually introduce environment variables (the brief does not require one); any real `.env` must then be gitignored.
Commit to Git: YES for defaults (nothing secret exists to keep out); never credentials.
Marker setup: Follows the README setup instructions.
Clean-clone impact: Must run with documented defaults on the marker's machine — no access to your private machine. Note: the brief does not explicitly require a README, but since submission is a public repo URL the marker must run, undocumented setup risks losing all marking.

# DO NOT VIOLATE

- Do not submit a private repository — submission is a "URL to a public repository"; the marker must not need your credentials.
- Do not build a CLI/library only — the RAT "should be a web-app dashboard".
- Do not shallow-clone — remote URL ingestion must be "deeply cloned".
- Do not accept a zip without `.git` as the intended form — the required form is "a zip file of the repo with the .git file or directory".
- Do not measure binary files — "Binary files are not measured"; use Git's definition and detection.
- Do not disable rename detection or change the 50% threshold — a pure rename must not change metrics; a change plus rename must attribute only the changes to the **new** path.
- Do not include merge commits in \(\bar{H}\) — it is the set of **non-merge** commits.
- Do not skip the initial commit's baseline — \(h[p] = h_\emptyset\), an **empty commit**, so the initial commit's lines count as additions.
- Do not ignore deletions — an object in \(h[p]\) but not in \(h\) must be recorded as lines removed **on its path**, and it still participates in that commit's directory aggregation.
- Do not use author-date for commit-set filters — the definitions use **committer-date**, with \(H_{i,j}\) inclusive at \(i\) and **exclusive at \(j\)**.
- Do not divide by zero — \(\eta_{H,o}\) and \(\rho_{H,o}\) are **0** when \(|H| = 0\); ownership \(\omega\) is **0** when \(\lambda_{H,o} = 0\).
- Do not compute a directory's Modifications by summing children's modification counts — \(n_{H,o}\) counts **commits** with \(\lambda_{h,o} > 0\) (one commit touching several files in a directory = 1 modification).
- Do not drop the root directory from \(H[D]\) — repository metrics are directory metrics on the root.
- Do not hardcode HEAD as the only reference commit — \(\bar{H}\) is reachable from "a specified reference commit \(h_r\) (typically HEAD)", and the sample metrics are provided "from a specific commit hash".
- Do not assume all overview features are required — the brief states "Not all features are necessary. Please review the rubric"; the rubric tiers govern.
- Do not skip rubric tiers — "Requirements are cumulative. You can only reach a tier if the previous tier is satisfied. Each tier is judged holistically."
- Do not invent or commit secrets — the brief requires none (no PATs for cloning, no personal absolute paths, no keys).
- Do not eyeball correctness — validate against the provided sample metrics from the specific commit hash for the provided repos.

# PRIORITY ORDER

Brief allows 2.5 hours. If you actually have 2 hours, apply the cut-lines marked [CUT].

1. **Pass/fail, zero-risk (~10 min)** — C1: runnable web-app dashboard scaffold + README run instructions; verify a fresh clone runs before building anything else.
2. **Required core (~70 min)** — C2 (remote URL deep clone first — simpler — then zip with .git) → C3 semantics → C4–C8 **all five metric categories**. Validate against the provided sample metrics from the specific commit hash, starting with the small repo (cJSON), then medium (Redis), then large (Git). This secures the Requirements ≤50% tier = 25% of total marks, the single largest block, and both ingestion forms are mandatory for it.
3. **High-mark / low-risk tier-3 features (~40 min)** — cheapest first: F3 Multi-repo → F1 Filtering (time period, then manual commit list) → F2 Author Merge (mailmap first, manual merging second). The **first** completed feature unlocks the Requirements ≤75% tier (+12.5 points); the remaining two are only needed for the final 12.5 points. [2-hour cut-line: stop after the first tier-3 feature.]
4. **Lower-value / riskier, last (~30 min)** — F4/F5 polish: visualisation quality, error handling (bad zip, missing .git, failed clone), navigation and QoL; large-repo (~100000 commits) performance. [2-hour cut-line: only error handling + basic visualisation.] Build computation efficiently from the start (avoid redundant recomputation) — correctness testing itself runs against the large git repo, and "redundant & slow" is the bottom Architecture tier.
5. **Final submission check (below)** — reserve ~10 min.

# FINAL SUBMISSION CHECK

- No real secrets, PATs, API keys, or production credentials committed — the brief requires none; re-scan the repo (including clone helpers and test scripts) to confirm none were accidentally added.
- Required environment variables documented — the brief requires none; if you introduced any, they are safe local values, defaulted and documented in the README.
- Secret-containing `.env` files ignored — nothing in this test needs secrets; if a `.env` exists it is gitignored.
- `.env.example` present **if needed** — only if you actually introduced environment variables (the brief does not require one).
- Clean clone can be run using the documented setup — test with a fresh clone before submitting.
- Marker does not need your personal credentials — public submission repo; public test repos; deep clone over public HTTPS with no auth; zip ingestion needs nothing. The brief never asks the marker to use your credentials.
- Submission is a **public** repository URL.
- Metric correctness verified against the provided sample metrics from the specific commit hash for all three provided repos (cJSON, Redis, Git).
- Both ingestion forms work: zip **with** `.git`, and remote URL **deep** clone.
- Awkward cases re-tested: initial commit vs empty commit; deletions; pure renames; change+rename (attributed to new path); binary file exclusion; merge-commit exclusion; \(|H| = 0\); zero-churn ownership; \([i, j)\) interval boundaries; root-directory metrics.
- The app is a web-app dashboard (not CLI-only) with working navigation and visible error handling.