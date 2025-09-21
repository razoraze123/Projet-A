"""Application de bureau PySide6 pour dialoguer avec un agent n8n via un webhook."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
from PySide6 import QtCore, QtWidgets


CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_CONFIG: dict[str, Any] = {"webhook_url": ""}


def load_config() -> dict[str, Any]:
    """Charge la configuration depuis ``config.json``."""

    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {**DEFAULT_CONFIG, **data}
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Sauvegarde la configuration dans ``config.json``."""

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)


class RequestWorker(QtCore.QObject):
    """Effectue la requête HTTP dans un thread séparé."""

    finished = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, url: str, message: str, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._message = message

    @QtCore.Slot()
    def run(self) -> None:
        try:
            response = requests.post(self._url, json={"message": self._message}, timeout=20)
            response.raise_for_status()
            try:
                data: Any = response.json()
            except ValueError:
                data = response.text
            self.finished.emit(data)
        except requests.RequestException as exc:
            self.error.emit(str(exc))


class UploadWorker(QtCore.QObject):
    """Envoie des fichiers vers le webhook n8n dans un thread séparé."""

    finished = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, url: str, files: list[Path], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._files = files

    @QtCore.Slot()
    def run(self) -> None:
        if not self._url:
            self.error.emit("Aucun webhook configuré.")
            return

        try:
            with contextlib.ExitStack() as stack:
                multipart_files = []
                for index, file_path in enumerate(self._files):
                    file_obj = stack.enter_context(file_path.open("rb"))
                    multipart_files.append((
                        f"file{index}",
                        (file_path.name, file_obj, "text/plain"),
                    ))

                response = requests.post(self._url, files=multipart_files, timeout=60)
                response.raise_for_status()
                try:
                    data: Any = response.json()
                except ValueError:
                    data = response.text
        except (OSError, requests.RequestException) as exc:
            self.error.emit(str(exc))
        else:
            self.finished.emit(data)


class ChatBubble(QtWidgets.QFrame):
    """Bulle de conversation avec style personnalisé."""

    def __init__(self, text: str, role: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", role)
        self.setObjectName("chatBubble")
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Minimum)
        self.setMaximumWidth(480)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        label = QtWidgets.QLabel(text)
        label.setObjectName("bubbleText")
        label.setWordWrap(True)
        label.setAlignment(QtCore.Qt.AlignLeft)
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard)
        layout.addWidget(label)


class ChatTab(QtWidgets.QWidget):
    """Onglet de discussion avec l'agent n8n."""

    def __init__(self, webhook_url: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._webhook_url = webhook_url
        self._thread: QtCore.QThread | None = None
        self._worker: RequestWorker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.scroll_widget = QtWidgets.QWidget()
        self.scroll_widget.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.scroll_widget.setStyleSheet("background-color: #0D0D0D;")
        self.messages_layout = QtWidgets.QVBoxLayout(self.scroll_widget)
        self.messages_layout.setAlignment(QtCore.Qt.AlignTop)
        self.messages_layout.setSpacing(10)

        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setSpacing(10)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Écrire un message…")
        self.input_field.returnPressed.connect(self.send_message)

        self.send_button = QtWidgets.QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_field, stretch=1)
        input_layout.addWidget(self.send_button)

        main_layout.addLayout(input_layout)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_webhook_url(self, url: str) -> None:
        self._webhook_url = url

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def _add_bubble(self, text: str, role: str) -> None:
        bubble = ChatBubble(text, role)
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if role == "user":
            layout.addStretch(1)
            layout.addWidget(bubble, 0, QtCore.Qt.AlignRight)
        elif role == "agent":
            layout.addWidget(bubble, 0, QtCore.Qt.AlignLeft)
            layout.addStretch(1)
        else:  # error
            layout.addStretch(1)
            layout.addWidget(bubble, 0, QtCore.Qt.AlignHCenter)
            layout.addStretch(1)

        self.messages_layout.addWidget(container)
        QtCore.QTimer.singleShot(0, self._ensure_visible)

    def _ensure_visible(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ------------------------------------------------------------------
    # Communication
    # ------------------------------------------------------------------
    def send_message(self) -> None:
        message = self.input_field.text().strip()
        if not message:
            return
        if not self._webhook_url:
            self._add_bubble("Aucun webhook configuré.", "error")
            return

        self._add_bubble(message, "user")
        self.input_field.clear()
        self._toggle_inputs(False)

        self._thread = QtCore.QThread(self)
        self._worker = RequestWorker(self._webhook_url, message)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._handle_response)
        self._worker.error.connect(self._handle_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._toggle_inputs(True)

    def _handle_response(self, data: object) -> None:
        if isinstance(data, (dict, list)):
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            pretty = str(data)
        self._add_bubble(pretty, "agent")

    def _handle_error(self, message: str) -> None:
        self._add_bubble(f"Erreur : {message}", "error")

    def _toggle_inputs(self, enabled: bool) -> None:
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)


class ParamsTab(QtWidgets.QWidget):
    """Onglet de gestion des paramètres et de la mise à jour."""

    webhook_changed = QtCore.Signal(str)

    def __init__(self, config: dict[str, Any], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        form_layout.setFormAlignment(QtCore.Qt.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.webhook_input = QtWidgets.QLineEdit(self._config.get("webhook_url", ""))
        form_layout.addRow("URL du webhook", self.webhook_input)

        layout.addLayout(form_layout)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(12)

        self.save_button = QtWidgets.QPushButton("Sauvegarder")
        self.save_button.clicked.connect(self._save_webhook)

        self.update_button = QtWidgets.QPushButton("Mettre à jour l’app")
        self.update_button.clicked.connect(self._update_application)

        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.update_button)
        buttons_layout.addStretch(1)

        layout.addLayout(buttons_layout)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _save_webhook(self) -> None:
        url = self.webhook_input.text().strip()
        self._config["webhook_url"] = url
        try:
            save_config(self._config)
            self.status_label.setText("Configuration sauvegardée.")
            self.webhook_changed.emit(url)
        except OSError as exc:
            self.status_label.setText(f"Erreur lors de la sauvegarde : {exc}")

    def _update_application(self) -> None:
        self.status_label.setText("Mise à jour en cours…")
        QtWidgets.QApplication.processEvents()
        try:
            output = subprocess.check_output(
                ["git", "pull", "origin", "main"],
                stderr=subprocess.STDOUT,
                text=True,
            )
            print(output)
        except subprocess.CalledProcessError as exc:
            self.status_label.setText(f"Échec de la mise à jour : {exc.output}")
            return

        self.status_label.setText("Mise à jour réussie, redémarrage…")
        QtCore.QTimer.singleShot(1500, self._restart_application)

    def _restart_application(self) -> None:
        os.execl(sys.executable, sys.executable, *sys.argv)


class UploadTab(QtWidgets.QWidget):
    """Onglet dédié à l'envoi de fichiers texte vers n8n."""

    def __init__(self, webhook_url: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._webhook_url = webhook_url
        self._selected_files: list[Path] = []
        self._thread: QtCore.QThread | None = None
        self._worker: UploadWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.select_button = QtWidgets.QPushButton("Sélectionner fichiers")
        self.select_button.clicked.connect(self._select_files)

        self.send_button = QtWidgets.QPushButton("Envoyer au webhook")
        self.send_button.clicked.connect(self._send_files)
        self.send_button.setEnabled(False)

        buttons_layout.addWidget(self.select_button)
        buttons_layout.addWidget(self.send_button)
        buttons_layout.addStretch(1)

        layout.addLayout(buttons_layout)

        self.files_list = QtWidgets.QListWidget()
        self.files_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.files_list.setAlternatingRowColors(False)
        self.files_list.setMinimumHeight(160)
        layout.addWidget(self.files_list)

        self.result_edit = QtWidgets.QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("Résultat du webhook…")
        self.result_edit.setMinimumHeight(180)
        layout.addWidget(self.result_edit)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_webhook_url(self, url: str) -> None:
        self._webhook_url = url

    # ------------------------------------------------------------------
    # Gestion des fichiers
    # ------------------------------------------------------------------
    def _select_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des fichiers texte",
            str(Path.home()),
            "Fichiers texte (*.txt)",
        )

        if not paths:
            return

        unique_paths: dict[str, Path] = {}
        for path_str in paths:
            path = Path(path_str)
            unique_paths[str(path)] = path

        self._selected_files = list(unique_paths.values())

        self.files_list.clear()
        for file_path in self._selected_files:
            self.files_list.addItem(str(file_path))

        self.send_button.setEnabled(bool(self._selected_files))

    # ------------------------------------------------------------------
    # Envoi vers le webhook
    # ------------------------------------------------------------------
    def _send_files(self) -> None:
        if not self._selected_files:
            self._show_result("Veuillez sélectionner des fichiers .txt avant l'envoi.")
            return

        if self._thread and self._thread.isRunning():
            return

        self._show_result("Envoi en cours…")
        self._toggle_inputs(False)

        self._thread = QtCore.QThread(self)
        self._worker = UploadWorker(self._webhook_url, self._selected_files.copy())
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._handle_response)
        self._worker.error.connect(self._handle_error)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)

        self._thread.start()

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        self._toggle_inputs(True)

    def _handle_response(self, data: object) -> None:
        if isinstance(data, (dict, list)):
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            pretty = str(data)
        self._show_result(pretty)

    def _handle_error(self, message: str) -> None:
        self._show_result(f"Erreur : {message}")

    def _show_result(self, text: str) -> None:
        self.result_edit.setPlainText(text)

    def _toggle_inputs(self, enabled: bool) -> None:
        self.select_button.setEnabled(enabled)
        self.send_button.setEnabled(enabled and bool(self._selected_files))


class MainWindow(QtWidgets.QMainWindow):
    """Fenêtre principale avec ses trois onglets."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Interface n8n")
        self.resize(900, 620)

        self.config = load_config()

        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)

        self.params_tab = ParamsTab(self.config)
        self.params_tab.webhook_changed.connect(self._update_webhook)
        webhook = self.config.get("webhook_url", "")
        self.chat_tab = ChatTab(webhook)
        self.upload_tab = UploadTab(webhook)

        self.tab_widget.addTab(self.params_tab, "Paramètres")
        self.tab_widget.addTab(self.chat_tab, "Chat")
        self.tab_widget.addTab(self.upload_tab, "Upload")

    def _update_webhook(self, url: str) -> None:
        self.chat_tab.set_webhook_url(url)
        self.upload_tab.set_webhook_url(url)


def create_app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication(sys.argv)
    qss = """
QMainWindow {
    background-color: #0D0D0D;
    color: #E0E0E0;
    font-family: 'Segoe UI', sans-serif;
}

QWidget {
    background-color: #0D0D0D;
    color: #E0E0E0;
    font-family: 'Segoe UI', sans-serif;
}

QTabWidget::pane {
    border: 1px solid #222;
    background: #121212;
    border-radius: 6px;
}

QTabBar::tab {
    background: #2A2A2A;
    color: #CCCCCC;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

QTabBar::tab:selected {
    background: #3A3A3A;
    color: #00CFFF;
    font-weight: bold;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background: #1E1E1E;
    color: #FFFFFF;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 6px;
}

QPushButton {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #3A3A3A;
}

QPushButton:pressed {
    background-color: #00CFFF;
    color: #000000;
    font-weight: bold;
}

QScrollArea {
    background: #0D0D0D;
    border: none;
}

QLabel {
    color: #FFFFFF;
    font-size: 14px;
}

#chatBubble {
    border-radius: 12px;
    padding: 8px;
}

#chatBubble[role="user"] {
    background-color: #2F2F2F;
}

#chatBubble[role="agent"] {
    background-color: #1F3A5B;
}

#chatBubble[role="error"] {
    background-color: #4A1F1F;
}

#chatBubble[role="error"] #bubbleText {
    color: #FF6B6B;
}

#bubbleText {
    color: #FFFFFF;
}
    """
    app.setStyleSheet(qss)
    return app


def main() -> None:
    app = create_app()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
