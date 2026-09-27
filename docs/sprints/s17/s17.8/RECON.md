# S17.8 Recon Report

## 1. Baseline Assessment
- **Baseline Tag:** `s0.17.7`
- **Current Tests:** 437 passing tests.
- **Operating Environment:** Windows 11 / Python 3.13.14.
- **UI Toolkit availability:** standard library `tkinter` is fully functional (Tcl/Tk 8.6).

## 2. Technology Selection
We select **tkinter** as the primary UI toolkit for the following reasons:
1. **Zero External Dependencies:** It is bundled directly with standard Python on Windows, keeping our package size and dependency footprint pristine.
2. **Transient UI Friendly:** It allows for highly customized, minimal, small, lightweight, borderless, or custom-shaped windows.
3. **High Stability:** No risk of cross-compilation errors, rust/node mismatch issues, or system library drift.

## 3. Threading & Concurrency Architecture
Tkinter must run on the **Main Thread** to ensure OS window manager compatibility.
The `ShyamRuntime` and `SurfaceCoordinator` rely entirely on `asyncio`.
To keep both fully responsive, we will:
1. Run the `asyncio` event loop in a dedicated **Background Thread**.
2. Run the Tkinter event loop (`root.mainloop()`) in the **Main Thread**.
3. Use `asyncio.run_coroutine_threadsafe()` to schedule request processing from the UI Thread to the Async Engine Thread.
4. Schedule UI updates from the Async Thread back to the Tkinter Thread using thread-safe tkinter techniques (such as queuing with custom events or `root.after()`).
