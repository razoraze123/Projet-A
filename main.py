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


class ChatBubble(QtWidgets.QFrame):
    """Widget représentant une bulle de discussion."""

    def __init__(self, sender: str, message: str, role: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatBubble")
        self.setProperty("role", role)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
        self.setMaximumWidth(560)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        sender_label = QtWidgets.QLabel(sender)
        sender_label.setObjectName("senderLabel")
        sender_label.setAlignment(QtCore.Qt.AlignRight if role == "user" else QtCore.Qt.AlignLeft)

        message_label = QtWidgets.QLabel(message)
        message_label.setObjectName("messageLabel")
        message_label.setAlignment(QtCore.Qt.AlignRight if role == "user" else QtCore.Qt.AlignLeft)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard
        )
        message_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        message_label.setText(message)

        layout.addWidget(sender_label)
        layout.addWidget(message_label)

        # Re-polish to appliquer les styles dépendant des propriétés
        self.style().unpolish(self)
        self.style().polish(self)


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
        tab_widget.setObjectName("mainTabs")
        tab_widget.addTab(self._build_settings_tab(), "Paramètres")
        tab_widget.addTab(self._build_chat_tab(), "Chat")

        self.setCentralWidget(tab_widget)
        self._apply_styles()

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.chat_scroll = QtWidgets.QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.chat_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.chat_container = QtWidgets.QWidget()
        self.chat_layout = QtWidgets.QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(18, 24, 18, 24)
        self.chat_layout.setSpacing(16)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)

        input_panel = QtWidgets.QWidget()
        input_panel.setObjectName("chatInputPanel")
        input_layout = QtWidgets.QHBoxLayout(input_panel)
        input_layout.setContentsMargins(18, 16, 18, 16)
        input_layout.setSpacing(12)

        self.chat_input = QtWidgets.QLineEdit()
        self.chat_input.setPlaceholderText("Écrire un message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)

        self.send_button = QtWidgets.QPushButton("Envoyer")
        self.send_button.clicked.connect(self.send_chat_message)

        input_layout.addWidget(self.chat_input, stretch=1)
        input_layout.addWidget(self.send_button)

        layout.addWidget(self.chat_scroll, stretch=1)
        layout.addWidget(input_panel)

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
    def append_message(self, sender: str, message: str, role: str) -> None:
        bubble = ChatBubble(sender, message, role)
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if role == "user":
            layout.addStretch()
            layout.addWidget(bubble, 0, QtCore.Qt.AlignRight)
        else:
            layout.addWidget(bubble, 0, QtCore.Qt.AlignLeft)
            layout.addStretch()

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container)
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)

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

        self.append_message("Vous", message, "user")
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
        self.append_message("Agent", self._format_response(data), "agent")

    @QtCore.Slot(str)
    def on_request_error(self, message: str) -> None:
        self.append_message("Erreur", f"Impossible de contacter le webhook : {message}", "error")

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

    def _scroll_to_bottom(self) -> None:
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #1b1c21;
            }

            QWidget {
                color: #f2f4f8;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: 12pt;
            }

            QTabWidget#mainTabs::pane {
                border: none;
            }

            QTabBar::tab {
                background-color: #2a2b31;
                color: #c7c9d3;
                padding: 10px 22px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                margin-right: 6px;
            }

            QTabBar::tab:selected {
                background-color: #34353d;
                color: #ffffff;
            }

            QLineEdit {
                background-color: #2c2d35;
                border: 1px solid #3a3b44;
                border-radius: 22px;
                padding: 12px 18px;
                color: #f2f4f8;
            }

            QLineEdit:focus {
                border: 1px solid #4f6bed;
            }

            QPushButton {
                background-color: #4f6bed;
                color: #ffffff;
                border-radius: 20px;
                padding: 12px 24px;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #5d7dff;
            }

            QPushButton:pressed {
                background-color: #425bd4;
            }

            #chatInputPanel {
                background-color: #18191f;
                border-top: 1px solid #2a2b31;
            }

            ChatBubble {
                border-radius: 18px;
                background-color: #2e3038;
            }

            ChatBubble[role="user"] {
                background-color: #3a3d47;
            }

            ChatBubble[role="agent"] {
                background-color: #1f6feb;
            }

            ChatBubble[role="error"] {
                background-color: #c62828;
            }

            ChatBubble > QLabel#senderLabel {
                font-size: 10pt;
                color: rgba(255, 255, 255, 0.65);
                text-transform: uppercase;
                letter-spacing: 1px;
            }

            ChatBubble[role="user"] > QLabel#senderLabel,
            ChatBubble[role="agent"] > QLabel#senderLabel,
            ChatBubble[role="error"] > QLabel#senderLabel {
                color: rgba(255, 255, 255, 0.72);
            }

            ChatBubble > QLabel#messageLabel {
                font-size: 12pt;
                color: #f5f7fb;
            }

            ChatBubble[role="agent"] > QLabel#messageLabel,
            ChatBubble[role="error"] > QLabel#messageLabel {
                color: #ffffff;
            }
            """
        )


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(640, 480)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
