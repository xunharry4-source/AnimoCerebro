# Task Compensation Workspace Cleanup Plugin

Builds a non-destructive cleanup plan for temporary task artifacts.

This plugin intentionally returns a cleanup plan instead of deleting files by default,
so it can be used safely in supervision and compensation flows.
