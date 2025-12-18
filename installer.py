import os
import sys
import zipfile
import shutil
import requests
from pathlib import Path
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont

API_URL = "https://api.github.com/repos/vroot2137/cmb-mc/releases/latest"
DEFAULT_MC = os.path.join(os.getenv("APPDATA", "~"), ".minecraft")

THEME = """
QMainWindow{background:#1a1d23}QGroupBox{font-weight:bold;border:2px solid #2d3139;border-radius:10px;
margin-top:0;padding-top:12px;background:#25282f;font-size:13px}QPushButton{background:#0d6efd;color:#fff;
border:none;border-radius:8px;padding:10px 18px;font-weight:bold;font-size:13px}QPushButton:hover{background:#0b5ed7}
QPushButton:pressed{background:#0a58ca}QPushButton:disabled{background:#495057}QLineEdit{border:2px solid #2d3139;
border-radius:8px;padding:10px 12px;background:#2d3139;color:#e9ecef;font-size:13px}QLineEdit:focus{border:2px solid #0d6efd}
QTextEdit{border:2px solid #2d3139;border-radius:8px;background:#1e2127;color:#e9ecef;padding:8px;font-size:12px}
QProgressBar{border:2px solid #2d3139;border-radius:8px;text-align:center;background:#2d3139;color:#e9ecef;font-weight:bold}
QProgressBar::chunk{background:#0d6efd;border-radius:6px}
"""

class DownloadThread(QThread):
    log, progress, done = pyqtSignal(str), pyqtSignal(int), pyqtSignal(bool, str, str)
    
    def __init__(self, mc_dir):
        super().__init__()
        self.mc_dir = Path(os.path.expandvars(os.path.expanduser(mc_dir))).resolve()
    
    def run(self):
        try:
            r = requests.get(API_URL, timeout=10)
            if r.status_code != 200:
                return self.done.emit(False, "Błąd połączenia z serwerem", "")
            
            data = r.json()
            version = data["tag_name"]
            zip_asset = next((a for a in data.get("assets", []) if a["name"].endswith(".zip")), None)
            
            if not zip_asset:
                return self.done.emit(False, "Brak pliku ZIP", "")
            
            self.log.emit(f"Pobieranie {version}")
            zip_path = Path.cwd() / zip_asset["name"]
            
            with requests.get(zip_asset["browser_download_url"], stream=True) as dl:
                total = int(dl.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in dl.iter_content(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total: self.progress.emit(int(downloaded * 100 / total))
            
            if not self.mc_dir.exists():
                zip_path.unlink(missing_ok=True)
                return self.done.emit(False, f"Nie znaleziono: {self.mc_dir}", "")
            
            self.log.emit("Rozpakowywanie")
            tmp = Path.cwd() / "_tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir()
            
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(tmp)
            
            items = list(tmp.iterdir())
            subdirs = [d for d in items if d.is_dir()]
            root = subdirs[0] if len(subdirs) == 1 and len(items) == 1 else tmp
            
            self.log.emit(f"Kopiowanie z: {root.name}")
            count = 0
            
            for item in root.iterdir():
                dst = self.mc_dir / item.name
                try:
                    if item.is_file():
                        shutil.copy2(item, dst)
                        count += 1
                        self.log.emit(f"Plik: {item.name}")
                    elif item.is_dir():
                        if dst.exists(): shutil.rmtree(dst)
                        shutil.copytree(item, dst)
                        count += 1
                        self.log.emit(f"Folder: {item.name}")
                except Exception as e:
                    self.log.emit(f"Błąd: {item.name} - {e}")
            
            shutil.rmtree(tmp, ignore_errors=True)
            zip_path.unlink(missing_ok=True)
            
            if count == 0:
                return self.done.emit(False, "Nie znaleziono plików do instalacji", "")
            
            self.done.emit(True, f"Pomyślnie zainstalowano {count} elementów", version)
        except Exception as e:
            self.done.emit(False, str(e), "")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prostokątna Awantura")
        self.setFixedSize(720, 600)
        self.setStyleSheet(THEME)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Folder
        folder_group = QGroupBox()
        folder_layout = QVBoxLayout()
        path_layout = QHBoxLayout()
        
        self.mc_input = QLineEdit(DEFAULT_MC)
        self.mc_input.setPlaceholderText("Wybierz folder .minecraft...")
        self.mc_input.textChanged.connect(self.update_local_version)
        path_layout.addWidget(self.mc_input, 1)
        
        browse_btn = QPushButton("Przeglądaj")
        browse_btn.setFixedWidth(120)
        browse_btn.clicked.connect(lambda: self.mc_input.setText(f) if (f := QFileDialog.getExistingDirectory(self, "Wybierz folder gry")) else None)
        path_layout.addWidget(browse_btn)
        
        folder_layout.addLayout(path_layout)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)
        
        # Wersje
        version_group = QGroupBox()
        version_layout = QHBoxLayout()
        version_layout.setSpacing(15)
        
        ver_font = QFont()
        ver_font.setPointSize(26)
        ver_font.setBold(True)
        
        self.local_version = self._create_version_widget("Zainstalowana wersja", "#2d3139", "#b8bec5", ver_font)
        version_layout.addWidget(self.local_version[0], 1)
        
        arrow = QLabel("→")
        arrow.setFont(QFont("", 32, QFont.Weight.Bold))
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFixedWidth(50)
        arrow.setStyleSheet("color:#66b3ff")
        version_layout.addWidget(arrow)
        
        self.github_version = self._create_version_widget("Najnowsza wersja", "#1e3a5f", "#66b3ff", ver_font)
        version_layout.addWidget(self.github_version[0], 1)
        
        version_group.setLayout(version_layout)
        version_group.setMinimumHeight(170)
        layout.addWidget(version_group)
        
        # Status
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("", 11, QFont.Weight.Bold))
        self.status_label.hide()
        layout.addWidget(self.status_label)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(28)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Przyciski
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.check_btn = QPushButton("Sprawdź aktualizacje")
        self.check_btn.setFixedHeight(48)
        self.check_btn.clicked.connect(self.check_update)
        btn_layout.addWidget(self.check_btn)
        
        self.install_btn = QPushButton("Zainstaluj / Aktualizuj")
        self.install_btn.setFixedHeight(48)
        self.install_btn.setStyleSheet("QPushButton{background:#198754;font-size:14px}QPushButton:hover{background:#157347}QPushButton:pressed{background:#146c43}QPushButton:disabled{background:#495057}")
        self.install_btn.clicked.connect(self.install)
        btn_layout.addWidget(self.install_btn, 2)
        
        layout.addLayout(btn_layout)
        
        # Log
        log_group = QGroupBox()
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(110)
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        self.update_local_version()
        self.check_update()
    
    def _create_version_widget(self, title, bg, color, font):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)
        
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(QFont("", 10))
        layout.addWidget(label)
        
        version = QLabel("---")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFont(font)
        layout.addWidget(version)
        
        widget.setStyleSheet(f"QWidget{{background:{bg};border-radius:10px;padding:15px}}QLabel{{color:{color};background:transparent}}")
        version.setStyleSheet(f"color:{color};background:transparent")
        
        return widget, version
    
    def update_local_version(self):
        try:
            ver_file = Path(os.path.expandvars(os.path.expanduser(self.mc_input.text().strip()))) / "version.txt"
            self.local_version[1].setText(ver_file.read_text(encoding="utf-8").strip() if ver_file.exists() else "Brak")
        except:
            self.local_version[1].setText("---")
    
    def check_update(self):
        self.check_btn.setEnabled(False)
        self.github_version[1].setText("⏳")
        self.status_label.hide()
        
        try:
            r = requests.get(API_URL, timeout=5)
            if r.status_code == 200:
                version = r.json()["tag_name"]
                self.github_version[1].setText(version)
                
                local = self.local_version[1].text()
                if local not in ("---", "Brak"):
                    if local != version:
                        self._show_status("Dostępna aktualizacja!", "#664d03", "#fff3cd")
                        self.log_output.append(f"<b style='color:#ff6b35'>➜ Aktualizacja: {local} → {version}</b>")
                    else:
                        self._show_status("Masz najnowszą wersję", "#0f5132", "#d1e7dd")
                        self.log_output.append("<b style='color:#28a745'>Masz najnowszą wersję</b>")
            else:
                self.github_version[1].setText("❌")
                self._show_status("Błąd połączenia", "#842029", "#f8d7da")
        except Exception as e:
            self.github_version[1].setText("❌")
            self._show_status("Błąd połączenia", "#842029", "#f8d7da")
            self.log_output.append(f"<span style='color:#dc3545'>✗ {e}</span>")
        finally:
            self.check_btn.setEnabled(True)
    
    def _show_status(self, text, bg, fg):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"padding:10px;border-radius:8px;font-weight:bold;background:{bg};color:{fg}")
        self.status_label.show()
    
    def install(self):
        if not self.mc_input.text().strip():
            return QMessageBox.warning(self, "Błąd", "Wybierz folder gry")
        
        self.log_output.clear()
        self._toggle_ui(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.hide()
        
        self.thread = DownloadThread(self.mc_input.text().strip())
        self.thread.log.connect(self.log_output.append)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.done.connect(self._finish)
        self.thread.start()
    
    def _toggle_ui(self, enabled):
        for w in (self.install_btn, self.check_btn, self.mc_input):
            w.setEnabled(enabled)
    
    def _finish(self, success, msg, version):
        self._toggle_ui(True)
        self.progress_bar.hide()
        
        if success:
            self._show_status("Instalacja zakończona!", "#0f5132", "#d1e7dd")
            self.local_version[1].setText(version)
            self.log_output.append(f"<b style='color:#28a745'>{msg}</b>")
            QMessageBox.information(self, "Sukces", msg)
        else:
            self._show_status("Błąd instalacji", "#842029", "#f8d7da")
            self.log_output.append(f"<b style='color:#dc3545'>{msg}</b>")
            QMessageBox.critical(self, "Błąd", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
