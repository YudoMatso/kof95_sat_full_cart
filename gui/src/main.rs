// SPDX-License-Identifier: GPL-3.0-or-later
// Graphical front end of kof95_cart.py: pick the three dumps, press Start, follow the build.
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
const CONFIG: &str = "kof95_cart_gui.cfg";

fn main() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("KOF '95 Saturn - cartridge edition builder")
            .with_inner_size([640.0, 470.0])
            .with_min_inner_size([520.0, 400.0])
            .with_drag_and_drop(true),
        ..Default::default()
    };
    eframe::run_native("kof95_cart_gui", options, Box::new(|_cc| Ok(Box::new(App::new()))))
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

fn check_disc(p: &str) -> Result<(), String> {
    let path = Path::new(p);
    if p.is_empty() {
        return Err("choose the .cue file of the disc".into());
    }
    if !path.is_file() {
        return Err("file not found".into());
    }
    if !p.to_lowercase().ends_with(".cue") {
        return Err("expected the .cue file (with its .bin tracks next to it)".into());
    }
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let dir = path.parent().unwrap_or(Path::new("."));
    for line in text.lines() {
        let l = line.trim();
        if l.to_uppercase().starts_with("FILE") {
            if let (Some(a), Some(b)) = (l.find('"'), l.rfind('"')) {
                if b > a && !dir.join(&l[a + 1..b]).is_file() {
                    return Err(format!("track missing next to the .cue: {}", &l[a + 1..b]));
                }
            }
        }
    }
    Ok(())
}

fn check_rom(p: &str) -> Result<(), String> {
    if p.is_empty() {
        return Err("choose mpr-18811-mx.ic1, the 2 MiB ROM cartridge sold with the game".into());
    }
    match std::fs::metadata(p) {
        Err(_) => Err("file not found".into()),
        Ok(m) if m.len() != ROM_SIZE => Err(format!("{} bytes, expected 2 MiB (2,097,152)", m.len())),
        Ok(_) => Ok(()),
    }
}

fn check_mvs(p: &str) -> Result<(), String> {
    if p.is_empty() {
        return Err("choose kof95.zip, the Neo Geo MVS ROM set (MAME name kof95)".into());
    }
    if !Path::new(p).is_file() {
        return Err("file not found".into());
    }
    let data = std::fs::read(p).map_err(|e| e.to_string())?;
    // file names are stored in clear in a zip: enough to tell the right set
    if !data.windows(9).any(|w| w == b"084-m1.m1") {
        return Err("084-m1.m1 not in this zip: not the kof95 MVS set".into());
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
        if low.ends_with(".cue") {
            self.disc = s;
        } else if low.ends_with(".zip") {
            self.mvs = s;
        } else if std::fs::metadata(p).map(|m| m.len() == ROM_SIZE).unwrap_or(false) {
            self.rom = s;
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
        cmd.arg(&script).args([&self.disc, &self.rom, &self.mvs, &self.out]);
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

/// One input row: label, path field, Browse button, and the check of the current value.
fn row(ui: &mut egui::Ui, label: &str, value: &mut String, check: Option<Result<(), String>>, pick: impl FnOnce() -> Option<PathBuf>, enabled: bool) {
    ui.label(label);
    ui.horizontal(|ui| {
        ui.add_enabled(enabled, egui::TextEdit::singleline(value).desired_width(ui.available_width() - 80.0));
        if ui.add_enabled(enabled, egui::Button::new("Browse…")).clicked() {
            if let Some(p) = pick() {
                *value = p.display().to_string();
            }
        }
    });
    match check {
        Some(Err(e)) if !value.is_empty() => {
            ui.colored_label(egui::Color32::from_rgb(220, 110, 60), format!("⚠ {e}"));
        }
        Some(Ok(())) => {
            ui.colored_label(egui::Color32::from_rgb(90, 170, 90), "✔ ok");
        }
        _ => {
            ui.label("");
        }
    }
    ui.add_space(2.0);
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
        let ready = cd.is_ok() && cr.is_ok() && cm.is_ok() && !self.out.is_empty();

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("The King of Fighters '95 — Saturn cartridge edition");
            ui.label("Builds the 48 MiB cartridge image from your own dumps. Drop the files on this window or browse.");
            ui.add_space(8.0);
            let disc0 = self.disc.clone();
            row(ui, "Saturn disc (.cue, with its .bin tracks)", &mut self.disc, Some(cd),
                || dialog_dir(&disc0).add_filter("Cue sheet", &["cue"]).pick_file(), idle);
            let rom0 = self.rom.clone();
            row(ui, "Saturn ROM cartridge (mpr-18811-mx.ic1, 2 MiB)", &mut self.rom, Some(cr),
                || dialog_dir(&rom0).pick_file(), idle);
            let mvs0 = self.mvs.clone();
            row(ui, "Neo Geo MVS ROM set (kof95.zip)", &mut self.mvs, Some(cm),
                || dialog_dir(&mvs0).add_filter("Zip", &["zip"]).pick_file(), idle);
            let out0 = self.out.clone();
            row(ui, "Output folder", &mut self.out, None, || dialog_dir(&out0).pick_folder(), idle);

            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if idle {
                    let b = egui::Button::new(egui::RichText::new("   Start   ").size(18.0));
                    if ui.add_enabled(ready, b).clicked() {
                        self.start();
                    }
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
                        let (c, s) = if i < self.step || self.state == State::Done {
                            (egui::Color32::from_rgb(90, 170, 90), "●")
                        } else if i == self.step {
                            (egui::Color32::from_rgb(230, 180, 60), "●")
                        } else {
                            (egui::Color32::GRAY, "○")
                        };
                        ui.colored_label(c, s);
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
                            let ok = r.contains("identical to the reference");
                            let c = if ok { egui::Color32::from_rgb(90, 170, 90) } else { egui::Color32::from_rgb(220, 70, 60) };
                            ui.colored_label(c, if ok { format!("✔ {r}") } else { format!("✖ {r}") });
                        }
                    }
                    State::Failed(e) => {
                        ui.colored_label(egui::Color32::from_rgb(220, 70, 60), format!("✖ {e}"));
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
                ui.colored_label(egui::Color32::from_rgb(220, 70, 60), e);
            }
        });
    }

    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        if self.state == State::Running {
            self.cancel();
        }
    }
}
