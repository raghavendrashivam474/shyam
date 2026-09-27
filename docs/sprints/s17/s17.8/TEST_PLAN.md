# S17.8 Test Plan

## 1. Scope
The scope of testing covers the new Tkinter-based human visual surface, ensuring:
1. State changes (`SurfaceState`) map correctly to visual indicators and descriptions.
2. User input is successfully sent to `SurfaceCoordinator.handle_request()`.
3. The ecosystem readiness level (`EcosystemReadiness`) propagates and degrades/restores the UI appropriately.
4. No direct bypasses of `SurfaceCoordinator` exist in the UI code.
5. Absolute zero regressions on the existing 437 tests.

## 2. Test Execution Matrix
- **Unit & Headless Integration Tests (`tests/ui/test_ui_window.py`):**
  - Verify that UI window and state updates accurately reflect `SurfaceState` (IDLE, LISTENING, EXECUTING, COMPLETED, FAILED, DEGRADED).
  - Test input validation and request creation with `TextInputAdapter`.
  - Test async dispatch and response consumption without blocking UI.
- **Surface & Architecture Compliance Tests (`tests/ui/test_ui_contract.py`):**
  - Assert that `shyam.ui` only imports from `shyam.surface`, `shyam.core.runtime`, `shyam.core.readiness`, and never directly touches `FluxProvider`, `ZaryaProvider`, `ContinuityService`, `HybridNavigator`, etc.
- **Physical / Interactive Smoke Testing:**
  - Launch the UI application with `--ui` or interactive window and verify clean startup and shutdown.
