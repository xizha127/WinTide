# Security and isolation changes

The experimental Yttrium Windows driver requires test-signing and imports its bundled test certificate into Windows Root and TrustedPublisher stores. The installer requires explicit opt-in, verifies the release SHA-256, records certificate preexistence, exports BCD, saves display drivers and backs up system DLLs named by the INF. Only the configured VM's Windows boot entry is changed. **The Windows OS files and certificate stores are shared with its native boot**, so a private EFI image does not make all guest changes private. Do not enable this on an installation where these security changes are unacceptable.

After the matching host graphics device is running, setup explicitly selects the
pinned driver for its exact VirtIO GPU hardware ID using Windows' driver update
API. It restarts Windows and verifies the selected INF, version and device status;
staging a package alone does not prove that Windows uses it. This does not disable
additional Windows security protections.

The driver's INF can replace system OpenGL DLLs. `guest/Restore-Graphics.ps1` removes the Yttrium package, reinstalls saved display drivers, removes certificates introduced by setup, and invokes SFC for the original OpenGL DLLs. See [rollback](rollback.md).

QEMU uses the desktop UID so its GTK console can reach the existing Wayland session. It uses the tss group for the virtual TPM socket. Running a VM under the desktop UID gives its process more host-user access than a separately confined libvirt account; this recipe is a desktop integration experiment, not a hardened multi-tenant boundary. It does not disable all QEMU sandboxing: only process spawning is allowed for Venus render workers. The local renderer patch avoids the unnecessary `setpgid` call while keeping privilege restrictions.

The host GPU remains bound to Linux. Device access is added to libvirt's base `cgroup_device_acl`, which affects system-libvirt VMs generally. Existing entries are merged and backed up; no blanket device-controller bypass, GPU unbinding or world-writable chmod is performed. The distro GPU node ACL must already authorize the configured desktop UID.

RDP retains NLA and firewall access is scoped to the configured Linux-host address. RemoteApp policy permits unlisted programs for the authenticated Windows user. Use a dedicated/local account with a real password. The Linux password file is mode `0600` and passed through askpass, never `/p:...` on the client command line. It remains plaintext on the local filesystem; encrypted host storage and a suitably protected Linux session matter.

The script executes its explicitly requested Windows setup through QEMU Guest Agent as SYSTEM. Inspect scripts before running them. It never changes account passwords, automatically removes a PIN, disables Defender/Windows Update, or disables arbitrary startup applications.

The RemoteApp launch socket is private to the Linux user and verifies the peer
UID. It authorizes that same user to launch programs in the connected Windows
session; it does not isolate mutually untrusted processes sharing a Linux UID.
Full-desktop connections are outside its reuse behavior.

`guest/Configure-SSH.ps1` is used by guided setup unless `--skip-ssh` is selected.
It installs the Windows OpenSSH Server capability when absent and requires an
existing administrator account. It configures key-only access
for the specified user, restricts the SSH firewall rule to the host address, and
changes OpenSSH's default shell to cmd. Setup invokes it through QEMU Guest Agent;
the installed `wintide --ssh` command then uses SSH directly. Review those SSH
policy changes before running setup.
