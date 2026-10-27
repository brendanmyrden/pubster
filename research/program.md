# Pubster bounded research
Adapt the hypothesis → experiment → evaluate → retain/reject method, not model training.
Only deterministic retrieval title-weight candidates are currently implemented. No model calls.
At most two experiments/day, one per maintenance pass, 300 seconds each; compare a
pre-registered MRR objective on the same corpus with a frozen regression suite. Reject
any regression or non-improvement. Only a numeric title_weight in [1, 2, 4, 8] can be
promoted; no arbitrary code or patch execution. Authentication, budgets, permissions,
rights, evaluator, scheduler, remotes, and deployment are not candidate-editable.
No eligible hypothesis or resource headroom means skip. Additional parser/skill
experiments require an independently implemented evaluator and safe candidate runner.
