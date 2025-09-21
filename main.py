"""Application PySide6 pour dialoguer avec un agent n8n via un webhook."""

from __future__ import annotations

import json
from typing import Any

import requests
from PySide6 import QtCore, QtWidgets


DEFAULT_WEBHOOK_URL = "http://localhost:5678/webhook/seo-optimize"


class RequestWorker(QtCore.QObject):
    """Worker exécuté dans un QThread pour lancer l'appel HTTP."""

    finished = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, url: str, payload: dict[str, Any], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._payload = payload

    @QtCore.Slot()
    def run(self) -> None:
        """Effectue la requête POST vers le webhook."""

        try:
            response = requests.post(self._url, json=self._payload, timeout=15)
            response.raise_for_status()
            try:
                data: Any = response.json()
            except ValueError:
                data = response.text
            self.finished.emit(data)
        except requests.RequestException as exc:  # pragma: no cover - dépend du réseau
            self.error.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Interface n8n Chat")

        self.settings = QtCore.QSettings("ProjetA", "WebhookChat")
        self.webhook_url: str = self.settings.value("webhook_url", DEFAULT_WEBHOOK_URL, str)

        self.request_thread: QtCore.QThread | None = None
        self.request_worker: RequestWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.addTab(self._build_settings_tab(), "Paramètres")
        tab_widget.addTab(self._build_chat_tab(), "Chat")

        self.setCentralWidget(tab_widget)

    def _build_settings_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        form_layout = QtWidgets.QFormLayout()
        self.webhook_input = QtWidgets.QLineEdit(self.webhook_url)
        form_layout.addRow("URL du webhook :", self.webhook_input)

        save_button = QtWidgets.QPushButton("Sauvegarder")
        save_button.clicked.connect(self.save_settings)

        layout.addLayout(form_layout)
        layout.addWidget(save_button)
        layout.addStretch()

        return widget

    def _build_chat_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        self.chat_display = QtWidgets.QListWidget()
        self.chat_display.setWordWrap(True)
        self.chat_display.setAlternatingRowColors(True)
        self.chat_display.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

        input_layout = QtWidgets.QHBoxLayout()
        self.chat_input = QtWidgets.QLineEdit()
        self.chat_input.setPlaceholderText("Écrire un message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)

        self.send_button = QtWidgets.QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_chat_message)

        input_layout.addWidget(self.chat_input, stretch=1)
        input_layout.addWidget(self.send_button)

        layout.addWidget(self.chat_display)
        layout.addLayout(input_layout)

        return widget

    # ------------------------------------------------------------------
    # Gestion des paramètres
    # ------------------------------------------------------------------
    @QtCore.Slot()
    def save_settings(self) -> None:
        self.webhook_url = self.webhook_input.text().strip() or DEFAULT_WEBHOOK_URL
        self.settings.setValue("webhook_url", self.webhook_url)
        QtWidgets.QMessageBox.information(self, "Paramètres", "URL sauvegardée avec succès.")

    # ------------------------------------------------------------------
    # Gestion du chat
    # ------------------------------------------------------------------
    def append_message(self, sender: str, message: str, alignment: QtCore.Qt.AlignmentFlag) -> None:
        text = f"{sender} :\n{message}" if "\n" in message else f"{sender} : {message}"
        item = QtWidgets.QListWidgetItem(text)
        item.setTextAlignment(alignment | QtCore.Qt.AlignVCenter)
        self.chat_display.addItem(item)
        self.chat_display.scrollToBottom()

    def _format_response(self, data: Any) -> str:
        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(data)
        return str(data)

    @QtCore.Slot()
    def send_chat_message(self) -> None:
        message = self.chat_input.text().strip()
        if not message:
            return

        self.append_message("Vous", message, QtCore.Qt.AlignRight)
        self.chat_input.clear()
        self._set_inputs_enabled(False)

        payload = {"message": message}
        self.request_thread = QtCore.QThread()
        self.request_worker = RequestWorker(self.webhook_url, payload)
        self.request_worker.moveToThread(self.request_thread)

        self.request_thread.started.connect(self.request_worker.run)
        self.request_worker.finished.connect(self.on_request_success)
        self.request_worker.error.connect(self.on_request_error)
        self.request_worker.finished.connect(self._cleanup_request_thread)
        self.request_worker.error.connect(self._cleanup_request_thread)
        self.request_thread.finished.connect(self.request_thread.deleteLater)

        self.request_thread.start()

    @QtCore.Slot(object)
    def on_request_success(self, data: Any) -> None:
        self.append_message("Agent", self._format_response(data), QtCore.Qt.AlignLeft)

    @QtCore.Slot(str)
    def on_request_error(self, message: str) -> None:
        self.append_message("Erreur", message, QtCore.Qt.AlignLeft)

    @QtCore.Slot()
    def _cleanup_request_thread(self) -> None:
        if self.request_thread is not None:
            self.request_thread.quit()
            self.request_thread.wait()
            self.request_thread = None
            if self.request_worker is not None:
                self.request_worker.deleteLater()
                self.request_worker = None
        self._set_inputs_enabled(True)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.chat_input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if enabled:
            self.chat_input.setFocus()


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(640, 480)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
