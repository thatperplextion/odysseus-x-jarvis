# services/os_shell/__init__.py
"""Odysseus OS shell: sandboxed filesystem, process, terminal and assistant services.

Pure service layer (no FastAPI imports) so it can be unit-tested directly;
``routes/os_routes.py`` is the HTTP surface.
"""
