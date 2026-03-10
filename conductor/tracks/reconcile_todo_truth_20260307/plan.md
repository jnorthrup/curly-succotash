# Reconcile TODO vs /conductor/ tracks

Objective
---------
Reconcile the `TODO.md` backlog with the authoritative `/conductor/tracks.md` and produce one of:

- mark items in `TODO.md` as completed when local tracks exist and verification evidence is present, or
- create follow-up conductor tracks with an assigned first slice when `TODO.md` items require implementation.

Planned first slice
-------------------
1. Inspect `TODO.md` entries that reference work already represented in `/conductor/tracks/`.
2. For each such entry, if the corresponding track shows completed and verification evidence exists in its folder, update `TODO.md` to mark that item complete and add a one-line note referencing the track.
3. If the item is not satisfied by existing tracks, create a follow-up track under `/conductor/tracks/` and assign its first slice.

Stop condition
--------------
Complete when `TODO.md` no longer contains entries that are satisfied by existing completed tracks without explicit cross-reference.

Owner
-----
Conductor (master) — this plan is local truth and may be updated by the master as verification completes.
