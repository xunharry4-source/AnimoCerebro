# Plugin Startup Guide

## Purpose

This guide defines what a "regular plugin" is, how plugin discovery works, and how explicit plugin registration is triggered.

## Mandatory Plugin Structure

A regular plugin must be an independent directory, and must contain all of:

- startup.py
- plugin.json
- register.py
- README.md

## Allowed Plugin Paths

Only these two layouts are valid for plugin auto-registration:

- src/plugins/<plugin>
- src/plugins/<group>/<plugin>

## Disallowed Plugin Path

The following nested layout is invalid and will not be registered:

- src/plugins/<plugin>/<plugin>

The loader only traverses the allowed one-level and two-level layouts above.
Deeper nested directories are ignored unless they are themselves direct matches
for the allowed plugin paths.

## Independence Rule

A plugin unit must be self-contained and should not depend on another plugin unit directory files.
Use only:

- Files inside its own plugin directory
- Shared contracts/services under src/zentex

## Registration Flow

1. Implement plugin factory in project code (typically exported in src/zentex/plugins/boot_exports.py).
2. Create plugin unit directory in an allowed path.
3. Add startup.py, plugin.json, register.py, README.md.
4. Ensure startup.py resolves (plugin_id, factory) from factory catalog.
5. Use plugin service explicit registration APIs when you actually want to write discovered plugins into the database.

## Registration Semantics

Plugin discovery and plugin registration are not the same thing.

- Discovery:
  - Finds plugin unit directories under `src/plugins`
  - Resolves `(plugin_id, factory)` through `startup.py`
- Registration:
  - Writes plugin metadata into plugin storage/database
  - Is an explicit plugins-module action

Recommended public APIs:

- `register_discovered_plugins(service)`
  - Discover and register missing plugins into storage
- `rehydrate_registered_plugins(service)`
  - Load already-registered plugins from storage into runtime memory
- `ensure_default_plugin_relationships(service)`
  - Explicitly seed built-in default relations

`service.bootstrap()` still exists as a legacy combined entry, but new callers should not treat it as the only recommended path.

## Loader Entrypoint

- src/plugins/startup.py

Main APIs:

- discover_plugin_unit_directories()
- resolve_registry_factories(factory_catalog)
- bootstrap_plugins(db_path)

## Architecture Constraint

- `launcher` must not use plugin discovery or registration as part of its normal startup chain.
- If the system needs discovery/registration, that work belongs to the plugins module itself, via `zentex.plugins.service`.
