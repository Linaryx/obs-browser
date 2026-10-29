# Fork comparison

Base: `obsproject/obs-browser` `d4db73e` (2.27.5), fetched 2026-10-29.

| Source | Compared revision | Decision |
|---|---|---|
| WizardCM `master` | `b798763` | Already contained in upstream; do not merge the older tree. |
| WizardCM `views-example` | `1706e9f`, based on `68af8e8` | Reference only. Its embedding code uses `HWND`/`SetParent`. Stock CEF 156 Views can create a native Wayland top-level window, not embed it in a Qt dock. |
| WizardCM `texture-fixes` | `8ed0d4d` | Patch-equivalent hide/show resize notification is already upstream. |
| WizardCM `restore-dock-focus-qt` | `6114a00` | Already upstream as `bdac160`. |
| WizardCM `better-source-update` | `fd6a0b0` | Defer. The old patch's `destroy` flag defeats its no-reload path; CSS-only updates need a separate adaptation. |
| WizardCM `render-select-in-source` | `7a093dc` | Defer. Popup composition is useful, but its accelerated-paint API predates `CefAcceleratedPaintInfo`. |
| blastorg `fix/source_tearing` | `ab2c14d` / PR #531 | Adapt ownership, not D3D11 calls: import during the callback, copy to an owned texture, complete the copy, then release the import. Keep Linux completion synchronization. |
| obs-rust `master` | `92a28ed`, common base `07227af` | Select individual fixes; upstream has newer navigation, startup, logging and security fixes. |
| obs-rust readiness | `0c3b700` + `7c92b29` | Adapted: context-ready callback, guarded task submission, initialization-result event, safe failed-init shutdown and early source destruction. |
| obs-rust `fix/4-os-event-init` | `6383653` | Same tree/patch as `7c92b29`; do not apply twice. |
| obs-rust navigation | `434cc38` | Patch-equivalent to upstream `7962467`; already present. |
| obs-rust sandbox/audio changes | `48aa373` series, `4b88708`, `27307dc` | Not included. Sandbox integration requires a nonstandard frontend API; audio patches change page APIs or packet timing. |

The readiness port omits the explicit global request context: passing `nullptr` already selects it
in CEF 156. Startup regression tests adapt obs-rust `37bc20b`, `722370d`, `a9a56fd` and `4f26bda`.

CEF #4238 is already present in the pinned 156.0.14 runtime. No second SharedImage patch is applied.
The Linux copy target uses the renderable generalized format, avoiding the extra render-format
texture where possible. `glFinish` remains: the Windows patch's `gs_flush()` is not a Linux fence.

Native Qt-embedded Wayland docks remain blocked on CEF #4233's unmerged surface/bounds APIs.
Views top-level windows are not labelled as docks. OSR-in-QWidget would need a separate input,
IME, popup and presentation implementation; it is outside the accelerated-source path.
