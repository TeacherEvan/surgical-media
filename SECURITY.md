# Security Policy

## Scope

`surgical-media` is a **local, offline-first** skill: it renders videos from
JSON storyboards using Pillow and ffmpeg. It has no network service, no
authentication, no telemetry, and stores no user data. Runtime files that are
never part of the repo: rendered MP4s, voice stems, `*_work/` directories.

## What matters here

- **License compliance for assets.** Fetched imagery is license-allowlisted
  (`by`/`by-sa`/`cc0`/`pdm`) and `*-nd`/`*-nc` rejected. Report a bypassed
  filter or a wrong attribution string via an issue; we treat it as a bug.
- **URL safety in `fetch_assets.py`.** Downloads are `https`-only (including
  redirect targets) and capped at 50 MB. Report a bypass via an issue.
- **Command execution.** All subprocesses use list-form argv, explicit
  `timeout=`, and no `shell=True`. Report any `shell=True` introduction.
- **Supply chain.** Runtime dependency is Pillow only. `edge-tts` is optional
  and never used by tests. Report a transitive-dependency concern via issue.

## Reporting

Open a **private security advisory** on GitHub
(https://github.com/TeacherEvan/surgical-media/security/advisories/new) or a
public issue labeled `security` for low-sensitivity findings. Please do not
post working exploits publicly before we have had a chance to respond.

## Supported versions

Only the latest release (`v1.2.x`) receives fixes. Older tags are kept for
history, not patches.
