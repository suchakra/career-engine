"""CareerEngine web (Streamlit) presentation layer.

Thin presentation over the existing runner/session core — NO workflow/business
logic lives here. Rendering is split into a pure view-model
(:func:`web.dashboard.build_dashboard_view`) and an injectable render function
(:func:`web.dashboard.render_dashboard`) so the UX is testable without the
Streamlit runtime.
"""
