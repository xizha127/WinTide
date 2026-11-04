// SPDX-License-Identifier: MIT
// All timings are monotonic milliseconds since the window first became visible.
pub const STARTUP_MS: u64 = 3000;
const SETTLE_MS: u64 = 300;

#[derive(Default)]
pub struct Startup {
    maximized_since: Option<u64>,
    done: bool,
}

impl Startup {
    // Exactly one restore per visible-window lifecycle. No permanent maximize ban.
    pub fn restore(&mut self, elapsed: u64, maximized: bool, fullscreen: bool) -> bool {
        if self.done {
            return false;
        }
        if fullscreen || elapsed > STARTUP_MS {
            self.done = true;
            return false;
        }
        if !maximized {
            self.maximized_since = None;
            return false;
        }
        let since = *self.maximized_since.get_or_insert(elapsed);
        if elapsed.saturating_sub(since) < SETTLE_MS {
            return false;
        }
        self.done = true;
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remembered_maximize_is_restored_once_after_settling() {
        let mut startup = Startup::default();
        assert!(!startup.restore(0, true, false));
        assert!(startup.restore(300, true, false));
        assert!(!startup.restore(700, false, false));
        assert!(!startup.restore(900, true, false));
    }

    #[test]
    fn delayed_application_maximize_is_caught() {
        let mut startup = Startup::default();
        assert!(!startup.restore(0, false, false));
        assert!(!startup.restore(700, true, false));
        assert!(startup.restore(1000, true, false));
    }

    #[test]
    fn fullscreen_is_permanently_exempt() {
        let mut startup = Startup::default();
        assert!(!startup.restore(0, false, true));
        assert!(!startup.restore(500, true, false));
    }

    #[test]
    fn later_manual_maximize_is_left_alone() {
        let mut startup = Startup::default();
        assert!(!startup.restore(0, false, false));
        assert!(!startup.restore(STARTUP_MS + 1, true, false));
        assert!(!startup.restore(STARTUP_MS + 1000, true, false));
    }
}
