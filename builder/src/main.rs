// SPDX-License-Identifier: GPL-3.0-or-later
// The builder: a window for the build script kof95_cart.py: pick the dumps (the MVS set is optional), press Build, follow the build.
// The build itself is the Python script, run by the PyPy shipped next to this program (pypy/), with
// KOF95_PROGRESS=1: it then prints "@progress <step> <steps> <fraction|-1> <seconds> <name>" lines on stderr.
#![cfg_attr(windows, windows_subsystem = "windows")]

use eframe::egui;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::time::Duration;

const ROM_SIZE: u64 = 2 * 1024 * 1024;
// Integrity of the dumps (CRC32, as published by Redump and MAME; the BIOS is not checked):
const TRACK1_SECTORS: u64 = 12975; // data track of The King of Fighters '95 (Japan), T-3101G: the same in Redump 1874, 29160 and 29161
const TRACK1_CRC: u32 = 0xd825_22b6; // its 12 975 raw 2352-byte sectors (the audio tracks are not used)
const TRACK1_ISO_CRC: u32 = 0x176e_3b65; // the same sectors as an .iso (2048-byte user data only)
const ROM_CRC: u32 = 0x9041_2e10; // mpr-18811-mx.ic1
const MVS_FILES: [(&str, u32); 4] = [("084-m1.m1", 0x6f2d_7429), ("084-v1.v1", 0x8486_1b56), ("084-v2.v2", 0xb38a_2803),
                                     ("084-v3.v3", 0xd683_a338)]; // MAME set kof95: the sound ROMs the build reads
const CONFIG: &str = "kof95_cart_builder.cfg";

// a dark theme after Discord's: grey-blue grounds, darker fields, grey buttons, "blurple" accent, white text
const BG: egui::Color32 = egui::Color32::from_rgb(0x31, 0x33, 0x38); // window ground
const BG2: egui::Color32 = egui::Color32::from_rgb(0x2b, 0x2d, 0x31); // panels, progress bar ground
const BG3: egui::Color32 = egui::Color32::from_rgb(0x1e, 0x1f, 0x22); // text fields
const LINE: egui::Color32 = egui::Color32::from_rgb(0x3f, 0x41, 0x47);
const BUTTON: egui::Color32 = egui::Color32::from_rgb(0x4e, 0x50, 0x58);
const BUTTON_HOVER: egui::Color32 = egui::Color32::from_rgb(0x6d, 0x6f, 0x78);
const BUTTON_DOWN: egui::Color32 = egui::Color32::from_rgb(0x80, 0x84, 0x8e);
const BLURPLE: egui::Color32 = egui::Color32::from_rgb(0x58, 0x65, 0xf2);
const MUTED: egui::Color32 = egui::Color32::from_rgb(0x94, 0x9b, 0xa4);
const GREEN: egui::Color32 = egui::Color32::from_rgb(0x23, 0xa5, 0x5a);
const YELLOW: egui::Color32 = egui::Color32::from_rgb(0xf0, 0xb2, 0x32);
const RED: egui::Color32 = egui::Color32::from_rgb(0xf2, 0x3f, 0x42);
const CORAL: egui::Color32 = egui::Color32::from_rgb(0xf2, 0x8b, 0x82); // a softer red: a file to fix before Build

fn dark_visuals() -> egui::Visuals {
    let mut v = egui::Visuals::dark();
    let white = egui::Color32::WHITE;
    v.override_text_color = Some(white);
    v.panel_fill = BG;
    v.window_fill = BG2;
    v.faint_bg_color = BG2;
    v.extreme_bg_color = BG3;
    v.code_bg_color = BG3;
    v.window_stroke = egui::Stroke::new(1.0_f32, LINE);
    v.hyperlink_color = egui::Color32::from_rgb(0x00, 0xa8, 0xfc);
    v.warn_fg_color = YELLOW;
    v.error_fg_color = RED;
    v.selection.bg_fill = BLURPLE;
    v.selection.stroke = egui::Stroke::new(1.0_f32, white);
    let r = egui::CornerRadius::same(4);
    let w = &mut v.widgets;
    w.noninteractive.bg_fill = BG2;
    w.noninteractive.weak_bg_fill = BG2;
    w.noninteractive.bg_stroke = egui::Stroke::new(1.0_f32, LINE);
    w.noninteractive.fg_stroke = egui::Stroke::new(1.0_f32, white);
    for (s, fill) in [(&mut w.inactive, BUTTON), (&mut w.hovered, BUTTON_HOVER), (&mut w.active, BUTTON_DOWN), (&mut w.open, BUTTON)] {
        s.bg_fill = fill;
        s.weak_bg_fill = fill;
        s.bg_stroke = egui::Stroke::NONE;
        s.fg_stroke = egui::Stroke::new(1.0_f32, white);
        s.corner_radius = r;
        s.expansion = 0.0;
    }
    w.noninteractive.corner_radius = r;
    v
}

fn main() -> eframe::Result {
    // kof95_cart_builder --check <disc.cue/.bin/.iso> <mpr-18811-mx.ic1> <kof95.zip>: the checks of the window, printed (exit 1 on a failure)
    let args: Vec<String> = std::env::args().collect();
    if args.len() == 5 && args[1] == "--check" {
        let mut ok = true;
        for (name, r) in [("disc", check_disc(&args[2])), ("ROM", check_rom(&args[3])), ("MVS", check_mvs(&args[4]))] {
            ok &= r.is_ok();
            println!("{name}: {}", r.err().unwrap_or_else(|| "OK".into()));
        }
        std::process::exit(if ok { 0 } else { 1 });
    }
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("The King of Fighters '95 Full Cart (Sega Saturn) builder")
            .with_inner_size([880.0, 640.0])
            .with_min_inner_size([700.0, 560.0])
            .with_drag_and_drop(true),
        ..Default::default()
    };
    eframe::run_native("kof95_cart_builder", options, Box::new(|cc| {
        cc.egui_ctx.set_theme(egui::Theme::Dark); // always dark, whatever the system theme
        cc.egui_ctx.set_visuals_of(egui::Theme::Dark, dark_visuals());
        cc.egui_ctx.style_mut_of(egui::Theme::Dark, |s| {
            use egui::{FontFamily::Proportional, FontId, TextStyle};
            s.text_styles = [
                (TextStyle::Heading, FontId::new(24.0, Proportional)),
                (TextStyle::Body, FontId::new(15.5, Proportional)),
                (TextStyle::Button, FontId::new(15.5, Proportional)),
                (TextStyle::Small, FontId::new(13.0, Proportional)),
                (TextStyle::Monospace, FontId::new(14.5, egui::FontFamily::Monospace)),
            ]
            .into();
        });
        Ok(Box::new(App::new()))
    }))
}

#[derive(PartialEq)]
enum State {
    Idle,
    Running,
    Done,
    Failed(String),
}

enum Msg {
    Line(String),
}

struct App {
    disc: String,
    rom: String,
    mvs: String,
    out: String,
    state: State,
    child: Option<Child>,
    rx: Option<Receiver<Msg>>,
    step: usize,
    steps: usize,
    step_name: String,
    fraction: Option<f32>,
    seconds: u64,
    log: Vec<String>,
    results: Vec<String>,
    checked: Option<((String, String, String), [Result<(), String>; 3])>,
    replace: Option<Vec<String>>, // output files already there: Build waits for the user's choice
}

/// The files the build writes in the output folder: the image under its two names (with kof95.zip: 48 MiB, without: 32 MiB).
fn outputs(with_mvs: bool) -> [&'static str; 2] {
    if with_mvs {
        ["kof95_cart.ss", "kof95_cart_48M.bin"]
    } else {
        ["kof95_cart_cd_audio.ss", "kof95_cart_cd_audio_32M.bin"]
    }
}

fn base_dir() -> PathBuf {
    std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf)).unwrap_or_else(|| PathBuf::from("."))
}

/// The interpreter and the script: next to this program (release layout), or given by KOF95_PYTHON / KOF95_SCRIPT.
fn runtime() -> Result<(PathBuf, PathBuf), String> {
    let base = base_dir();
    let python = match std::env::var_os("KOF95_PYTHON") {
        Some(p) => PathBuf::from(p),
        None => {
            let cands = if cfg!(windows) {
                vec![base.join("pypy").join("pypy3.exe"), base.join("pypy").join("python.exe")]
            } else {
                vec![base.join("pypy").join("bin").join("pypy3")]
            };
            cands.into_iter().find(|p| p.is_file()).ok_or("PyPy not found next to this program (folder pypy/)")?
        }
    };
    let script = std::env::var_os("KOF95_SCRIPT").map(PathBuf::from).unwrap_or_else(|| base.join("kof95_cart.py"));
    if !script.is_file() {
        return Err(format!("{} not found", script.display()));
    }
    Ok((python, script))
}

fn crc32(data: &[u8], mut crc: u32) -> u32 {
    crc = !crc;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

/// CRC32 of `len` bytes of a file from `offset` (read in pieces); None if the file is shorter.
fn crc32_file(path: &Path, offset: u64, len: u64) -> Result<Option<u32>, String> {
    use std::io::{Read, Seek, SeekFrom};
    let mut f = std::fs::File::open(path).map_err(|e| e.to_string())?;
    f.seek(SeekFrom::Start(offset)).map_err(|e| e.to_string())?;
    let (mut crc, mut left, mut buf) = (0u32, len, vec![0u8; 1 << 20]);
    while left > 0 {
        let n = f.read(&mut buf[..left.min(1 << 20) as usize]).map_err(|e| e.to_string())?;
        if n == 0 {
            return Ok(None);
        }
        crc = crc32(&buf[..n], crc);
        left -= n as u64;
    }
    Ok(Some(crc))
}

fn check_disc(p: &str) -> Result<(), String> {
    let path = Path::new(p);
    if p.is_empty() {
        return Err("choose the disc (.cue, .bin or .iso)".into());
    }
    if !path.is_file() {
        return Err("file not found".into());
    }
    let lower = p.to_lowercase();
    if lower.ends_with(".iso") {
        return match crc32_file(path, 0, TRACK1_SECTORS * 2048)? {
            Some(c) if c == TRACK1_ISO_CRC => Ok(()),
            Some(c) => Err(format!("not the .iso of the Japanese disc T-3101G (CRC {c:08x}, expected {TRACK1_ISO_CRC:08x})")),
            None => Err("too short: not the .iso of the Japanese disc T-3101G".into()),
        };
    }
    if lower.ends_with(".bin") {
        return match crc32_file(path, 0, TRACK1_SECTORS * 2352)? {
            Some(c) if c == TRACK1_CRC => Ok(()),
            Some(c) => Err(format!("not track 01 of the Japanese disc T-3101G (CRC {c:08x}, expected {TRACK1_CRC:08x})")),
            None => Err("too short: not track 01 of the Japanese disc T-3101G".into()),
        };
    }
    if !lower.ends_with(".cue") {
        return Err("expected the .cue of the disc, its track 01 (.bin) or an .iso".into());
    }
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let dir = path.parent().unwrap_or(Path::new("."));
    // track 01: its file and where its INDEX 01 starts in it (one .bin per track, or a single .bin)
    let (mut file, mut track1): (Option<PathBuf>, Option<(PathBuf, u64)>) = (None, None);
    let mut in_track1 = false;
    for line in text.lines() {
        let l = line.trim();
        let u = l.to_uppercase();
        if u.starts_with("FILE") {
            if let (Some(a), Some(b)) = (l.find('"'), l.rfind('"')) {
                if b > a && !dir.join(&l[a + 1..b]).is_file() {
                    return Err(format!("track missing next to the .cue: {}", &l[a + 1..b]));
                }
                file = Some(dir.join(&l[a + 1..b]));
            }
        } else if u.starts_with("TRACK") {
            in_track1 = u.split_whitespace().nth(1) == Some("01");
            if in_track1 && !u.contains("MODE1/2352") {
                return Err("track 01 must be a raw MODE1/2352 track (the Redump .cue/.bin dump)".into());
            }
        } else if u.starts_with("INDEX 01") && in_track1 && track1.is_none() {
            let msf: Vec<u64> = u.split_whitespace().nth(2).unwrap_or("").split(':').filter_map(|x| x.parse().ok()).collect();
            if msf.len() == 3 {
                if let Some(f) = &file {
                    track1 = Some((f.clone(), ((msf[0] * 60 + msf[1]) * 75 + msf[2]) * 2352));
                }
            }
        }
    }
    let (f, off) = track1.ok_or("no TRACK 01 in this .cue")?;
    match crc32_file(&f, off, TRACK1_SECTORS * 2352)? {
        None => Err("track 01 is too short: not the Japanese disc T-3101G".into()),
        Some(c) if c != TRACK1_CRC => Err(format!("track 01 is not the Japanese disc T-3101G (CRC {c:08x}, expected {TRACK1_CRC:08x})")),
        Some(_) => Ok(()),
    }
}

fn check_rom(p: &str) -> Result<(), String> {
    if p.is_empty() {
        return Err("choose mpr-18811-mx.ic1, the 2 MiB ROM cartridge sold with the game".into());
    }
    match std::fs::metadata(p) {
        Err(_) => Err("file not found".into()),
        Ok(m) if m.len() != ROM_SIZE => Err(format!("{} bytes, expected 2 MiB (2,097,152)", m.len())),
        Ok(_) => match crc32_file(Path::new(p), 0, ROM_SIZE)? {
            Some(c) if c == ROM_CRC => Ok(()),
            c => Err(format!("not mpr-18811-mx.ic1 (CRC {:08x}, expected {ROM_CRC:08x})", c.unwrap_or(0))),
        },
    }
}

/// (name, CRC32) of the entries of a zip, from its central directory (no decompression).
fn zip_entries(data: &[u8]) -> Result<Vec<(String, u32)>, String> {
    let u16le = |o: usize| u16::from_le_bytes([data[o], data[o + 1]]) as usize;
    let u32le = |o: usize| u32::from_le_bytes([data[o], data[o + 1], data[o + 2], data[o + 3]]);
    let end = (0..data.len().saturating_sub(21)).rev().find(|&i| data[i..i + 4] == [0x50, 0x4b, 0x05, 0x06]).ok_or("not a zip file")?;
    let (count, mut o) = (u16le(end + 10), u32le(end + 16) as usize);
    let mut out = Vec::new();
    for _ in 0..count {
        if o + 46 > data.len() || data[o..o + 4] != [0x50, 0x4b, 0x01, 0x02] {
            return Err("damaged zip file".into());
        }
        let (n, x, c) = (u16le(o + 28), u16le(o + 30), u16le(o + 32));
        out.push((String::from_utf8_lossy(&data[o + 46..(o + 46 + n).min(data.len())]).into_owned(), u32le(o + 16)));
        o += 46 + n + x + c;
    }
    Ok(out)
}

fn check_mvs(p: &str) -> Result<(), String> {
    if p.is_empty() {
        return Err("choose kof95.zip, the Neo Geo MVS ROM set (MAME name kof95)".into());
    }
    if !Path::new(p).is_file() {
        return Err("file not found".into());
    }
    let data = std::fs::read(p).map_err(|e| e.to_string())?;
    let entries = zip_entries(&data)?;
    for (name, crc) in MVS_FILES {
        match entries.iter().find(|(n, _)| n == name) {
            None => return Err(format!("{name} not in this zip: not the kof95 MVS set")),
            Some((_, c)) if *c != crc => return Err(format!("{name} is not the right dump (CRC {c:08x}, expected {crc:08x})")),
            Some(_) => {}
        }
    }
    Ok(())
}

impl App {
    fn new() -> Self {
        let mut app = App {
            disc: String::new(),
            rom: String::new(),
            mvs: String::new(),
            out: base_dir().join("out").display().to_string(),
            state: State::Idle,
            child: None,
            rx: None,
            step: 0,
            steps: 12,
            step_name: String::new(),
            fraction: None,
            seconds: 0,
            log: Vec::new(),
            results: Vec::new(),
            checked: None,
            replace: None,
        };
        if let Ok(text) = std::fs::read_to_string(base_dir().join(CONFIG)) {
            for line in text.lines() {
                if let Some((k, v)) = line.split_once('=') {
                    match k {
                        "disc" => app.disc = v.into(),
                        "rom" => app.rom = v.into(),
                        "mvs" => app.mvs = v.into(),
                        "out" => app.out = v.into(),
                        _ => {}
                    }
                }
            }
        }
        app
    }

    fn save_config(&self) {
        let text = format!("disc={}\nrom={}\nmvs={}\nout={}\n", self.disc, self.rom, self.mvs, self.out);
        let _ = std::fs::write(base_dir().join(CONFIG), text);
    }

    /// A dropped file goes to the field it fits.
    fn dropped(&mut self, p: &Path) {
        let s = p.display().to_string();
        let low = s.to_lowercase();
        let size = std::fs::metadata(p).map(|m| m.len()).unwrap_or(0);
        if low.ends_with(".zip") {
            self.mvs = s;
        } else if p.is_file() && size == ROM_SIZE {
            self.rom = s;
        } else if low.ends_with(".cue") || low.ends_with(".bin") || low.ends_with(".iso") {
            self.disc = s;
        } else if p.is_dir() {
            self.out = s;
        }
    }

    fn start(&mut self) {
        let (python, script) = match runtime() {
            Ok(r) => r,
            Err(e) => {
                self.state = State::Failed(e);
                return;
            }
        };
        self.save_config();
        let mut cmd = Command::new(&python);
        cmd.arg(&script).args([&self.disc, &self.rom]);
        if !self.mvs.trim().is_empty() {
            cmd.arg(&self.mvs); // with it: 48 MiB, Neo Geo sound; without: 32 MiB, CD audio
        }
        cmd.arg(&self.out);
        cmd.env("KOF95_PROGRESS", "1").stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: a hidden console, inherited by the build's subprocesses
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            cmd.process_group(0); // its own group, so that Cancel stops the whole build
        }
        match cmd.spawn() {
            Err(e) => self.state = State::Failed(format!("cannot start {}: {e}", python.display())),
            Ok(mut child) => {
                let (tx, rx) = channel();
                for pipe in [child.stdout.take().map(|p| Box::new(p) as Box<dyn std::io::Read + Send>),
                             child.stderr.take().map(|p| Box::new(p) as Box<dyn std::io::Read + Send>)]
                    .into_iter()
                    .flatten()
                {
                    let tx = tx.clone();
                    std::thread::spawn(move || {
                        for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                            let _ = tx.send(Msg::Line(line));
                        }
                    });
                }
                self.log.clear();
                self.results.clear();
                self.step = 0;
                self.fraction = None;
                self.seconds = 0;
                self.step_name = "starting".into();
                self.child = Some(child);
                self.rx = Some(rx);
                self.state = State::Running;
            }
        }
    }

    fn cancel(&mut self) {
        if let Some(child) = &self.child {
            let pid = child.id().to_string();
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                let _ = Command::new("taskkill").args(["/T", "/F", "/PID", &pid]).creation_flags(0x0800_0000).status();
            }
            #[cfg(unix)]
            {
                let _ = Command::new("kill").args(["-INT", &format!("-{pid}")]).status();
            }
        }
    }

    fn poll(&mut self) {
        let mut exit = None;
        if let Some(rx) = &self.rx {
            while let Ok(msg) = rx.try_recv() {
                match msg {
                    Msg::Line(l) => {
                        if let Some(rest) = l.strip_prefix("@progress ") {
                            let f: Vec<&str> = rest.splitn(5, ' ').collect();
                            if f.len() == 5 {
                                self.step = f[0].parse().unwrap_or(0);
                                self.steps = f[1].parse().unwrap_or(12);
                                self.fraction = f[2].parse::<f32>().ok().filter(|x| *x >= 0.0);
                                self.seconds = f[3].parse().unwrap_or(0);
                                self.step_name = f[4].to_string();
                            }
                        } else {
                            if l.contains("identical to the reference") || l.contains("DIFFERENT from the reference") {
                                self.results.push(l.clone());
                            }
                            self.log.push(l);
                        }
                    }
                }
            }
        }
        if self.state == State::Running && exit.is_none() {
            if let Some(child) = &mut self.child {
                if let Ok(Some(status)) = child.try_wait() {
                    // let the reader threads deliver the last lines first
                    std::thread::sleep(Duration::from_millis(100));
                    if let Some(rx) = &self.rx {
                        while let Ok(Msg::Line(l)) = rx.try_recv() {
                            if l.contains("identical to the reference") || l.contains("DIFFERENT from the reference") {
                                self.results.push(l.clone());
                            }
                            if !l.starts_with("@progress ") {
                                self.log.push(l);
                            }
                        }
                    }
                    exit = Some(status.code());
                }
            }
        }
        if let Some(code) = exit {
            self.child = None;
            self.rx = None;
            self.state = match code {
                Some(0) => State::Done,
                _ => {
                    let err = self.log.iter().rev().find(|l| l.starts_with("error")).cloned();
                    State::Failed(err.unwrap_or_else(|| format!("the build stopped (exit code {code:?})")))
                }
            };
        }
    }
}

fn clock(s: u64) -> String {
    if s >= 3600 {
        format!("{}:{:02}:{:02}", s / 3600, s / 60 % 60, s % 60)
    } else {
        format!("{}:{:02}", s / 60, s % 60)
    }
}

fn open_folder(p: &str) {
    let opener = if cfg!(windows) { "explorer" } else { "xdg-open" };
    let _ = Command::new(opener).arg(p).spawn();
}

/// One input field: a title line (label, optional tag, then the check of the current value), an optional hint, the
/// path field over the whole width with the Browse button at the right edge, then the same space before the next field.
#[allow(clippy::too_many_arguments)]
fn row(ui: &mut egui::Ui, label: &str, tag: Option<&str>, hint: Option<&str>, value: &mut String, check: Option<Result<(), String>>,
       pick: impl FnOnce() -> Option<PathBuf>, enabled: bool) {
    ui.horizontal_wrapped(|ui| {
        ui.label(egui::RichText::new(label).strong());
        if let Some(t) = tag {
            ui.label(egui::RichText::new(t).color(MUTED).italics());
        }
        ui.add_space(6.0);
        match check {
            Some(Err(e)) if !value.trim().is_empty() => {
                ui.colored_label(CORAL, format!("⚠ {e}"));
            }
            Some(Ok(())) => {
                ui.colored_label(GREEN, "✔ ok");
            }
            _ => {}
        }
    });
    if let Some(h) = hint {
        ui.label(egui::RichText::new(h).color(MUTED));
    }
    let h = ui.spacing().interact_size.y;   // one line high: the field takes the width left by the button
    ui.allocate_ui_with_layout(egui::vec2(ui.available_width(), h), egui::Layout::right_to_left(egui::Align::Center), |ui| {
        if ui.add_enabled(enabled, egui::Button::new("Browse…").min_size(egui::vec2(96.0, 0.0))).clicked() {
            if let Some(p) = pick() {
                *value = p.display().to_string();
            }
        }
        ui.add_enabled(enabled, egui::TextEdit::singleline(value).desired_width(ui.available_width()));
    });
    ui.add_space(12.0);
}

fn dialog_dir(current: &str) -> rfd::FileDialog {
    let d = rfd::FileDialog::new();
    match Path::new(current).parent() {
        Some(p) if p.is_dir() => d.set_directory(p),
        _ => d,
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.poll();
        let idle = self.state != State::Running;
        if idle {
            for f in ctx.input(|i| i.raw.dropped_files.clone()) {
                if let Some(p) = f.path {
                    self.dropped(&p);
                }
            }
        }
        if !idle {
            ctx.request_repaint_after(Duration::from_millis(100));
        }
        // the checks read the files: only again when a path changed
        let key = (self.disc.clone(), self.rom.clone(), self.mvs.clone());
        if self.checked.as_ref().map(|(k, _)| k != &key).unwrap_or(true) {
            self.checked = Some((key.clone(), [check_disc(&key.0), check_rom(&key.1), check_mvs(&key.2)]));
        }
        let [cd, cr, cm] = self.checked.as_ref().map(|(_, r)| r.clone()).unwrap();
        let with_mvs = !self.mvs.trim().is_empty(); // the MVS set is optional: it decides the kind of cartridge
        let (cd_ok, cr_ok, cm_ok) = (cd.is_ok(), cr.is_ok(), cm.is_ok());
        let ready = cd_ok && cr_ok && (!with_mvs || cm_ok) && !self.out.is_empty();

        if let Some(files) = self.replace.clone() {
            // the output files are already there: replace them, or go back
            let mut go = None;
            let m = egui::Modal::new(egui::Id::new("replace")).show(ctx, |ui| {
                ui.set_width(460.0);
                ui.label(egui::RichText::new("Replace the existing files?").strong().size(18.0));
                ui.add_space(6.0);
                ui.label("These files are already in the output folder:");
                for f in &files {
                    ui.label(egui::RichText::new(format!("   {f}")).color(YELLOW));
                }
                ui.label("The build writes them again (and kof95_cart.log).");
                ui.add_space(10.0);
                ui.horizontal(|ui| {
                    if ui.add(egui::Button::new(egui::RichText::new("  Replace  ").size(16.0)).fill(BLURPLE)).clicked() {
                        go = Some(true);
                    }
                    if ui.button(egui::RichText::new("  Cancel  ").size(16.0)).clicked() {
                        go = Some(false);
                    }
                });
            });
            if m.should_close() && go.is_none() {
                go = Some(false); // Escape or a click outside
            }
            match go {
                Some(true) => {
                    self.replace = None;
                    self.start();
                }
                Some(false) => self.replace = None,
                None => {}
            }
        }

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("The King of Fighters '95 Full Cart (Sega Saturn)");
            ui.label("Builds the cartridge image from your own dumps. Drop the files on this window or browse.");
            ui.add_space(8.0);
            let disc0 = self.disc.clone();
            row(ui, "Saturn disc", Some(".cue, .bin or .iso"), None, &mut self.disc, Some(cd),
                || dialog_dir(&disc0).add_filter("Disc image", &["cue", "bin", "iso"]).pick_file(), idle);
            let rom0 = self.rom.clone();
            row(ui, "Saturn ROM cartridge", Some("mpr-18811-mx.ic1, 2 MiB"), None, &mut self.rom, Some(cr),
                || dialog_dir(&rom0).pick_file(), idle);
            let mvs0 = self.mvs.clone();
            row(ui, "Neo Geo MVS ROM set", Some("kof95.zip, optional"),
                Some("Adds the Neo Geo music, sound effects and voices to the cartridge: no CD needed to play."),
                &mut self.mvs, Some(cm), || dialog_dir(&mvs0).add_filter("Zip", &["zip"]).pick_file(), idle);
            let out0 = self.out.clone();
            row(ui, "Output folder", None, None, &mut self.out, None, || dialog_dir(&out0).pick_folder(), idle);

            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if idle {
                    let b = egui::Button::new(egui::RichText::new("   Build   ").size(18.0)).fill(BLURPLE);
                    if ui.add_enabled(ready, b).clicked() {
                        let there: Vec<String> = outputs(with_mvs).iter()
                            .filter(|n| Path::new(&self.out).join(n).exists()).map(|n| n.to_string()).collect();
                        if there.is_empty() {
                            self.start();
                        } else {
                            self.replace = Some(there);
                        }
                    }
                    // what the fields give, or what is left to do: green ready, amber next step, coral a file to fix
                    let what = if with_mvs {
                        "48 MiB cartridge, Neo Geo music and sounds built in: no CD needed"
                    } else {
                        "32 MiB cartridge, Saturn sound, music from the disc in the drive (Saturn, or Neo Geo CD / PS1 arranged)"
                    };
                    let (color, line) = if self.disc.trim().is_empty() {
                        (YELLOW, "Next: choose the Saturn disc".to_string())
                    } else if !cd_ok {
                        (CORAL, "The disc is not the right one (see above)".to_string())
                    } else if self.rom.trim().is_empty() {
                        (YELLOW, "Next: choose the ROM cartridge mpr-18811-mx.ic1".to_string())
                    } else if !cr_ok {
                        (CORAL, "The ROM cartridge is not the right one (see above)".to_string())
                    } else if with_mvs && !cm_ok {
                        (CORAL, "kof95.zip is not the right set: fix it, or clear it for the 32 MiB cartridge".to_string())
                    } else if self.out.trim().is_empty() {
                        (YELLOW, "Next: choose the output folder".to_string())
                    } else {
                        (GREEN, "Ready to build".to_string())
                    };
                    ui.add_space(8.0);
                    ui.vertical(|ui| {
                        ui.label(egui::RichText::new(line).color(color).strong());
                        ui.label(egui::RichText::new(what).color(MUTED));
                    });
                } else if ui.button(egui::RichText::new("   Cancel   ").size(18.0)).clicked() {
                    self.cancel();
                }
                if self.state == State::Done && ui.button("Open the output folder").clicked() {
                    open_folder(&self.out);
                }
                if matches!(self.state, State::Failed(_)) && ui.button("Open the log").clicked() {
                    let log = Path::new(&self.out).join("kof95_cart.log");
                    open_folder(&log.display().to_string());
                }
            });
            ui.add_space(8.0);

            if self.state != State::Idle {
                // the steps as dots: done, current, to come
                ui.horizontal(|ui| {
                    for i in 1..=self.steps {
                        // drawn, not a glyph: the font of the window has no round bullet
                        let (rect, _) = ui.allocate_exact_size(egui::vec2(16.0, 16.0), egui::Sense::hover());
                        let c = rect.center();
                        if i < self.step || self.state == State::Done {
                            ui.painter().circle_filled(c, 5.5, GREEN);
                        } else if i == self.step {
                            ui.painter().circle_filled(c, 5.5, YELLOW);
                        } else {
                            ui.painter().circle_stroke(c, 5.0, egui::Stroke::new(1.5_f32, MUTED));
                        }
                    }
                    ui.label(format!("   {}", clock(self.seconds)));
                });
                match &self.state {
                    State::Running => {
                        ui.label(format!("Step {}/{}: {}", self.step, self.steps, self.step_name));
                        let bar = match self.fraction {
                            Some(f) => egui::ProgressBar::new(f).show_percentage(),
                            None => egui::ProgressBar::new(0.0).animate(true).text("working…"),
                        };
                        ui.add(bar);
                    }
                    State::Done => {
                        ui.add(egui::ProgressBar::new(1.0).text(format!("done in {}", clock(self.seconds))));
                        for r in &self.results {
                            // "<path>: OK, identical to the reference": the file name only (the folder is the output folder)
                            let ok = r.contains("identical to the reference");
                            let c = if ok { GREEN } else { RED };
                            let (path, what) = r.rsplit_once(": ").unwrap_or((r.as_str(), ""));
                            let name = Path::new(path).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.into());
                            let what = what.trim_start_matches("OK, ");
                            ui.colored_label(c, format!("{} {name}: {what}", if ok { "✔" } else { "✖" }));
                        }
                    }
                    State::Failed(e) => {
                        ui.colored_label(RED, format!("✖ {e}"));
                    }
                    State::Idle => {}
                }
                ui.add_space(6.0);
                egui::CollapsingHeader::new("Log").default_open(false).show(ui, |ui| {
                    egui::ScrollArea::vertical().max_height(140.0).stick_to_bottom(true).show(ui, |ui| {
                        for l in &self.log {
                            ui.monospace(l);
                        }
                    });
                });
            } else if let State::Failed(e) = &self.state {
                ui.colored_label(RED, e);
            }
        });
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        if self.state == State::Running {
            self.cancel();
        }
    }
}
