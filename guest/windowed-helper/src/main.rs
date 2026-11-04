// SPDX-License-Identifier: MIT
#![cfg_attr(windows, windows_subsystem = "windows")]

mod policy;
#[cfg(windows)]
mod windows;

fn main() {
    #[cfg(windows)]
    if let Err(error) = windows::run() {
        eprintln!("winapps-windowed: {error}");
        std::process::exit(1);
    }
    #[cfg(not(windows))]
    {
        eprintln!("winapps-windowed runs inside Windows, in the RemoteApp user's session.");
        std::process::exit(1);
    }
}
