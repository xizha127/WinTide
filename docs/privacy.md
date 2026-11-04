# Publication boundary

This repository was created as a clean source tree, not by committing the existing machine's diagnostic workspace. `.gitignore` starts by ignoring every root path, then allows reviewed source/documentation categories. Global exclusions additionally reject local configs, passwords, keys, logs, images, disk/firmware/BCD backups, guest binaries and build/download directories. `tools/check-publication.py` checks tracked contents too, because `.gitignore` cannot protect a file already tracked or force-added.

Do not commit real VM XML, disk serials/UUIDs, account passwords, Microsoft account details, TPM/NVRAM images, BCD exports, screenshots, host configuration backups, Windows executable discovery output or recovery material. Example config contains only placeholders and conventional network/display examples. Real generated plans use mode `0700` directories and `0600` files under ignored `local-plan/`.

Review the exact staging diff before every push. Secret scanning is supplementary, not proof that arbitrary diagnostic data is safe. The repository does not upload machine diagnostics or enable telemetry. Git commits use a GitHub noreply address rather than the host's configured private email.
