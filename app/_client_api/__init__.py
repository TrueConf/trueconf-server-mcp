"""Upstream API client layers (no MCP dependencies).

Private package: nothing outside ``app`` should import from here directly.

- ``_trueconf_server`` — pure domain of the TrueConf Server API
  (v4 / v4.1 REST).
- ``_trueconf_server_ai`` — pure domain of the TrueConf AI Server user API
  (transcriptions, from-tcs auth).
"""
