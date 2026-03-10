# Plan

## Phase 1: Curly truth and emitted contract

- [x] Add a new open local track for the native-first Kotlin autoresearch harness.
- [x] Extend `coordination/coordinate.py` so `emit-harness` publishes `kotlin_autoresearch_adaptation` beside the existing Python adaptation.
- [x] Add focused tests for the new contract, including `runtime_route: kilo`, repo path, first handoff, and JSONL results log path.

## Phase 2: TrikeShed synthetic harness surface

- [x] Add fixed autoresearch contracts/types in `commonMain`.
- [x] Add the mutable synthetic experiment surface plus native runner in `posixMain`.
- [x] Add a dedicated native executable target in `build.gradle.kts`.

## Phase 3: Verification

- [x] Regenerate `coordination/runtime/hrm_training_harness.json` and `coordination/runtime/hrm_training_codex.md`.
- [x] Run focused Curly pytest coverage.
- [ ] Run TrikeShed JVM tests for task loading, execution shape, result schema roundtrip, and verdict gating.
- [ ] Build and smoke the TrikeShed native executable and inspect the emitted JSONL/evidence artifacts.

## Known blocker

- TrikeShed verification is currently blocked by pre-existing compile failures outside the new autoresearch package:
  - `src/commonMain/kotlin/borg/trikeshed/http/SimpleHttpServer.kt:56`
  - `src/commonMain/kotlin/borg/trikeshed/net/channelization/HttpIngressProtocol.kt:32`
  - `src/jvmMain/kotlin/borg/trikeshed/brc/BrcDuckDbJvm.kt:75`
  - `src/jvmMain/kotlin/one/xio/HttpHeaders.kt:1695`
  - `src/jvmMain/kotlin/one/xio/HttpMethod.kt:148`
  - `src/jvmMain/kotlin/rxf/server/CookieRfc6265Util.kt`

## Acceptance

- Curly emits both Python and Kotlin adaptation contracts.
- The Kotlin contract points at `/Users/jim/work/TrikeShed`, records `runtime_route: kilo`, and names the first gate set.
- TrikeShed exposes a native-first synthetic harness with one mutable experiment surface and JVM verification scaffolding.
