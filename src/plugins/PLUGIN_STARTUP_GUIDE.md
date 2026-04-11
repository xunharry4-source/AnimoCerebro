# Plugin Startup Guide

## Purpose

This guide defines what a "regular plugin" is and how plugin auto-registration discovers plugin units.

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
5. Bootstrap plugin service to auto-register metadata from plugin.json.

## Loader Entrypoint

- src/plugins/startup.py

Main APIs:

- discover_plugin_unit_directories()
- resolve_registry_factories(factory_catalog)
- bootstrap_plugins(db_path)
