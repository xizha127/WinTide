// SPDX-License-Identifier: MIT
use crate::policy::Startup;
use std::{
    collections::{HashMap, HashSet},
    fs::{self, File, OpenOptions},
    io::Write,
    mem::{size_of, zeroed},
    path::PathBuf,
    ptr::{null, null_mut},
    time::Instant,
};
use windows_sys::Win32::{
    Foundation::*,
    Graphics::{Dwm::*, Gdi::*},
    System::{RemoteDesktop::ProcessIdToSessionId, Threading::*},
    UI::{Accessibility::*, WindowsAndMessaging::*},
};

const EVENT_MESSAGE: u32 = WM_APP + 11;

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(Some(0)).collect()
}

struct Handle(HANDLE);
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}

struct Seen {
    pid: u32,
    first: Instant,
    policy: Startup,
}

// No injected DLL and no work in the callback. The message loop owns all state.
unsafe extern "system" fn event(
    _: HWINEVENTHOOK,
    event: u32,
    hwnd: HWND,
    object: i32,
    child: i32,
    _: u32,
    _: u32,
) {
    if object == OBJID_WINDOW && child == 0 && !hwnd.is_null() {
        PostThreadMessageW(
            GetCurrentThreadId(),
            EVENT_MESSAGE,
            hwnd as usize,
            event as isize,
        );
    }
}

unsafe extern "system" fn collect(hwnd: HWND, param: LPARAM) -> i32 {
    // `EnumWindows` is synchronous; the vector lives for the entire call.
    (*(param as *mut Vec<HWND>)).push(hwnd);
    1
}

fn log(file: &mut File, line: &str) {
    let _ = writeln!(file, "{line}");
    let _ = file.flush();
}

unsafe fn classify(hwnd: HWND) -> Option<(u32, bool, bool)> {
    if IsWindowVisible(hwnd) == 0 || IsIconic(hwnd) != 0 {
        return None;
    }
    let mut pid = 0;
    GetWindowThreadProcessId(hwnd, &mut pid);
    if pid == 0 || pid == GetCurrentProcessId() {
        return None;
    }
    let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
    let extended = GetWindowLongW(hwnd, GWL_EXSTYLE) as u32;
    if style & WS_CHILD != 0 || extended & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) != 0 {
        return None;
    }
    if !GetWindow(hwnd, GW_OWNER).is_null() && style & WS_CAPTION == 0 {
        return None;
    }
    let mut cloaked: u32 = 0;
    if DwmGetWindowAttribute(
        hwnd,
        DWMWA_CLOAKED as u32,
        (&mut cloaked as *mut u32).cast(),
        4,
    ) == 0
        && cloaked != 0
    {
        return None;
    }
    let mut name = [0u16; 256];
    let len = GetClassNameW(hwnd, name.as_mut_ptr(), name.len() as i32);
    let class = String::from_utf16_lossy(&name[..len.max(0) as usize]);
    if matches!(
        class.as_str(),
        "Progman"
            | "WorkerW"
            | "Shell_TrayWnd"
            | "Shell_SecondaryTrayWnd"
            | "TsWindow_GeneralWindowClass"
            | "tooltips_class32"
    ) {
        return None;
    }
    let maximized = IsZoomed(hwnd) != 0;
    let mut rect: RECT = zeroed();
    let monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
    let mut info: MONITORINFO = zeroed();
    info.cbSize = size_of::<MONITORINFO>() as u32;
    if GetWindowRect(hwnd, &mut rect) == 0 || GetMonitorInfoW(monitor, &mut info) == 0 {
        return None;
    }
    let m = info.rcMonitor;
    let covers_monitor = rect.left <= m.left
        && rect.top <= m.top
        && rect.right >= m.right
        && rect.bottom >= m.bottom;
    // A decorated maximized window is the target. F11/borderless fullscreen is not.
    let fullscreen = covers_monitor && (!maximized || style & WS_CAPTION == 0);
    Some((pid, maximized, fullscreen))
}

unsafe fn scan(seen: &mut HashMap<isize, Seen>, file: &mut File) {
    let mut windows = Vec::new();
    EnumWindows(Some(collect), &mut windows as *mut _ as LPARAM);
    let alive: HashSet<isize> = windows.iter().map(|w| *w as isize).collect();
    seen.retain(|hwnd, _| alive.contains(hwnd));
    for hwnd in windows {
        // UWP apps can hide/cloak and later reuse the same top-level HWND.
        // Treat that as another startup, rather than retaining an expired policy.
        let mut cloaked: u32 = 0;
        let hidden = IsWindowVisible(hwnd) == 0
            || (DwmGetWindowAttribute(
                hwnd,
                DWMWA_CLOAKED as u32,
                (&mut cloaked as *mut u32).cast(),
                4,
            ) == 0
                && cloaked != 0);
        if hidden {
            seen.remove(&(hwnd as isize));
            continue;
        }
        let Some((pid, maximized, fullscreen)) = classify(hwnd) else {
            continue;
        };
        let entry = seen.entry(hwnd as isize).or_insert_with(|| Seen {
            pid,
            first: Instant::now(),
            policy: Startup::default(),
        });
        if entry.pid != pid {
            *entry = Seen {
                pid,
                first: Instant::now(),
                policy: Startup::default(),
            };
        }
        if entry.policy.restore(
            entry.first.elapsed().as_millis() as u64,
            maximized,
            fullscreen,
        ) {
            let sent = ShowWindowAsync(hwnd, SW_RESTORE) != 0;
            // No window titles, filenames, command lines, or account details in logs.
            log(
                file,
                &format!("restore hwnd={} pid={pid} queued={sent}", hwnd as usize),
            );
        }
    }
}

pub fn run() -> Result<(), Box<dyn std::error::Error>> {
    unsafe {
        let mut session = 0;
        if ProcessIdToSessionId(GetCurrentProcessId(), &mut session) == 0 || session == 0 {
            return Err(
                "Run in the interactive Windows user session, not SSH/QGA session 0".into(),
            );
        }
        let stop_name = wide(&format!(r"Local\WinTideWindowedStop-{session}"));
        if std::env::args().any(|a| a == "--stop") {
            let handle = OpenEventW(EVENT_MODIFY_STATE, 0, stop_name.as_ptr());
            if !handle.is_null() {
                let handle = Handle(handle);
                SetEvent(handle.0);
            }
            return Ok(());
        }
        let mutex_name = wide(&format!(r"Local\WinTideWindowed-{session}"));
        let mutex = CreateMutexW(null(), 0, mutex_name.as_ptr());
        if mutex.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        let already_running = GetLastError() == ERROR_ALREADY_EXISTS;
        let _mutex = Handle(mutex);
        if already_running {
            return Ok(());
        }
        let stop = CreateEventW(null(), 1, 0, stop_name.as_ptr());
        if stop.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        let stop = Handle(stop);
        ResetEvent(stop.0);
        let path = PathBuf::from(std::env::var("LOCALAPPDATA")?).join("wintide");
        fs::create_dir_all(&path)?;
        let path = path.join(format!("windowed-helper-{session}.log"));
        if fs::metadata(&path).is_ok_and(|m| m.len() > 65536) {
            File::create(&path)?;
        }
        let mut file = OpenOptions::new().create(true).append(true).open(path)?;
        log(
            &mut file,
            &format!(
                "start version={} session={session}",
                env!("CARGO_PKG_VERSION")
            ),
        );
        let mut message: MSG = zeroed();
        // Force creation of this thread's message queue before installing the hook.
        PeekMessageW(&mut message, null_mut(), 0, 0, PM_NOREMOVE);
        let hook = SetWinEventHook(
            EVENT_OBJECT_DESTROY,
            EVENT_OBJECT_HIDE,
            null_mut(),
            Some(event),
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        );
        if hook.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        let timer = SetTimer(null_mut(), 0, 100, None);
        if timer == 0 {
            UnhookWinEvent(hook);
            return Err(std::io::Error::last_os_error().into());
        }
        let mut seen = HashMap::new();
        while GetMessageW(&mut message, null_mut(), 0, 0) > 0 {
            if WaitForSingleObject(stop.0, 0) == WAIT_OBJECT_0 {
                break;
            }
            if message.message == EVENT_MESSAGE {
                // SHOW also rearms apps such as Settings that reuse their window.
                // SW_RESTORE of an already visible maximized window is not a SHOW.
                seen.remove(&(message.wParam as isize));
            }
            if message.message == WM_TIMER {
                // The helper follows the user's session when RDP connects/reconnects.
                // It never manages a native-console desktop.
                if GetSystemMetrics(SM_REMOTESESSION) != 0 {
                    scan(&mut seen, &mut file);
                }
            }
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        KillTimer(null_mut(), timer);
        UnhookWinEvent(hook);
        log(&mut file, "stop");
    }
    Ok(())
}
