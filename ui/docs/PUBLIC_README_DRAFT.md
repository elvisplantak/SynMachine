# SynMachine user interface — README discussion draft

Status: proposed wording only; the project owner has not finalized this README
or the project license. The current root README is intentionally preserved.

SynMachine is an experimental mechatronics project for developing laboratory
automation. The current work evaluates mechanical assemblies, electronics,
electrical wiring and power systems, and the software that coordinates them.
The longer-term goal is a modular platform for executing reproducible laboratory
procedures.

## Current development stage

The prototype is used to investigate device integration, motion, routing and
software-controlled workflows. Dry commissioning and operator-reported liquid
checks provide development evidence within their documented scopes. They do not
establish general chemical suitability, delivered-volume accuracy or readiness
for arbitrary synthesis procedures.

## Chemical compatibility

PTFE valves and tubing have not yet been installed in the current prototype,
as reported by the project owner. Chemical compatibility of the complete wetted
path has not been validated for the intended reagents, solvents or conditions.
Material selection and compatibility verification remain a separate development
stage before chemical use. The present prototype is an experimental development
platform.

## Project structure

- `labforge-ui`: schematic, procedure editing and operator interaction.
- `labforge-backend`: validation, persistence, routing and orchestration.
- `labforge-firmware`: low-level device execution on Arduino Mega.

SynMachine is the current working name. Existing repository/package names,
configuration variables, profile identities and the `LABFORGE/1` protocol retain
their technical names for compatibility.

## Licensing — decision pending

This README is a discussion draft. A project license and the provenance of any
reused source must be confirmed before describing the software as open source.
Public repository visibility alone does not grant an open-source license.
The final README will identify the chosen license and applicable third-party
notices; this draft does not grant new rights.

## This repository

It provides the machine schematic, Guided Demo, Recipes / Procedure Builder,
execution status and Service controls.
