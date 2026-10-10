# Optional Vault Git sync

Campfire runs one synchronization operation. A system scheduler may invoke the same command; no daemon, file watcher, automatic enablement or new YAML configuration is required. Vaults without Git continue to work normally.

## Prepare one Vault

The Vault must be a Git worktree root, with at least one commit, a current branch and a remote upstream. Configure identity, credentials and upstream using Git. Review `.gitignore`: synchronization includes eligible additions, edits, attachments, `.campfire.yaml` and deletions throughout the Vault. Ignoring an already tracked file does not untrack it. Device configuration, SQLite and reports stay outside the Vault in `~/.campfire/`.

```bash
campfire --workspace personal workspace git sync
campfire --workspace personal workspace git sync --expected-plan <returned-digest> --confirm
```

Preview reports local changes and cached ahead/behind counts without fetching. Confirmation fetches, checks the local snapshot, stages and commits eligible changes, merges upstream and pushes the configured branch. A scheduled invocation omits `--expected-plan` so it previews the current files internally instead of reusing an old plan.

Unfinished Git operations, manual staged changes, missing upstream and lock contention block synchronization. Submodules are outside the first implementation. Git operations have a timeout and do not prompt for credentials. Both CLI output and exit status matter: `remote_synced: true` is successful synchronization; a local commit without a successful push is not. Failures exit nonzero and report a phase and stable code. Local commits survive failure and the next invocation can retry. No force push, rebase, automatic stash or selection of either conflicting version is used. On merge conflict the command reports paths and attempts to abort only its own merge; if abort fails, resolve the unfinished merge before retrying.

Workspace locking coordinates Campfire operations, not external editors or Git clients. Snapshot checks stop detected external changes; this is not a filesystem transaction. Stop concurrent Git automation on the same worktree, including Obsidian Git, before enabling this mechanism. Enablement authorizes submitting all eligible Vault changes, not just one document.

## Linux example

This is an optional user-managed example, not an automatically installed service. Replace the executable path and Workspace id with the actual local values. The timer interval is a user choice. The user service must have access to the same Git credentials, SSH agent and Campfire configuration as an interactive invocation; do not store tokens in unit files.

`~/.config/systemd/user/campfire-vault-sync.service`:

```ini
[Unit]
Description=Synchronize personal Vault

[Service]
Type=oneshot
ExecStart=%h/.local/bin/campfire --workspace personal workspace git sync --confirm
TimeoutStartSec=180
```

`~/.config/systemd/user/campfire-vault-sync.timer`:

```ini
[Unit]
Description=Periodically synchronize personal Vault

[Timer]
OnStartupSec=2min
OnUnitInactiveSec=5min
Unit=campfire-vault-sync.service

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now campfire-vault-sync.timer
journalctl --user -u campfire-vault-sync.service
# Turn automatic synchronization off:
systemctl --user disable --now campfire-vault-sync.timer
```

A user timer runs while the user manager is active. For unattended operation after logout, an administrator can configure user lingering; this is not enabled by Campfire. Failures remain visible in the journal and service status; no new notification service is included. Other platforms can use their native schedulers to invoke the same command.

## Upgrading existing Vaults to 0.2.2

This release uses a patch number at the user's explicit request and includes breaking Domain configuration changes. Back up the Vault and local state, stop running Campfire operations, and have the local Agent remove `governance` from Domain declarations (`_领域.md`). Global `config.yml` governance directory settings remain valid. Remove obsolete `moc.project_groups` custom configuration if present; one generator now produces the same navigation and direct document lists for every Domain. Retain Project bindings in Vault root `.campfire.yaml`, local paths in `~/.campfire/local.yaml`, and authored content outside generated regions.

Delete the rebuildable `~/.campfire/campfire.db` and its WAL/SHM only after operations have stopped and recovery evidence has been checked. Upgrade the package and resources, run setup/check and synchronize affected MOCs. There is no old-format converter or database migration chain. Git synchronization remains disabled unless invoked or scheduled explicitly.
