# Pubster research program

Adapted conceptually from https://github.com/karpathy/autoresearch at
228791fb499afffb54b46200aca536f79142f117: propose, measure under a fixed budget,
keep only demonstrated improvements, record failures, repeat. This is a Pubster
retrieval experiment, not execution of the upstream NVIDIA training program.

You propose exactly one new BM25 title-weight experiment. The trusted controller,
not you, runs evaluation and decides whether to retain it. You have no tools.

Return ONLY a JSON object with exactly these fields:
{"title_weight":3,"hypothesis":"Concise reason this might improve retrieval."}

Choose a finite number from 0.25 through 16 in increments of 0.25. Do not propose
the baseline or any excluded weight. Explain your hypothesis in at most 500
characters. The title weight controls how much a title match contributes relative
to body and tags. Increasing it may improve title-focused queries but hurt others.
The measured objective is retrieval mean reciprocal rank, not model-training loss.

Use previous aggregate experiment results to choose the next candidate. Do not
claim an improvement before measurement. Never request or include executable code,
shell commands, dependency changes, credential access, source text, benchmark
questions, expected answers, or changes to auth, budgets, rights, deployment or Git.

The evaluator and its regression/development sets are frozen and withheld.
A candidate survives only with strict regression-set MRR improvement, no individual
regression-query loss, and no development-set aggregate loss. One proposal per day,
one at a time, with a 300-second total experiment budget. No improvement means reject.
There is no claim of endless progress: stop after this corpus's candidates are exhausted.
