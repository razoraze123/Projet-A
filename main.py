"""Application PySide6 pour dialoguer avec un agent n8n via un webhook."""

from __future__ import annotations

import json
from typing import Any

import requests
from PySide6 import QtCore, QtGui, QtWidgets


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

    def __init__(
        self, sender: str, message: str, role: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("chatBubble")
        self.setProperty("role", role)
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Minimum)
        self.setMaximumWidth(720)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        sender_label = QtWidgets.QLabel(sender)
        sender_label.setObjectName("senderLabel")
        sender_label.setAlignment(QtCore.Qt.AlignLeft)

        message_label = QtWidgets.QLabel(message)
        message_label.setObjectName("messageLabel")
        message_label.setAlignment(QtCore.Qt.AlignLeft)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard
        )
        message_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        message_label.setText(message)

        layout.addWidget(sender_label)
        layout.addWidget(message_label)

        self._repolish()

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class ChatInput(QtWidgets.QPlainTextEdit):
    """Zone de saisie qui envoie le message sur Entrée."""

    submitted = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Poser une question")
        self.setMaximumHeight(140)
        self.setMinimumHeight(64)
        self.document().setDocumentMargin(8)

    def sizeHint(self) -> QtCore.QSize:  # pragma: no cover - dépend de Qt
        size = super().sizeHint()
        size.setHeight(88)
        return size

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # pragma: no cover - dépend de Qt
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and not event.modifiers() & QtCore.Qt.ShiftModifier:
            event.accept()
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Assistant n8n")

        self.settings = QtCore.QSettings("ProjetA", "WebhookChat")
        self.webhook_url: str = self.settings.value("webhook_url", DEFAULT_WEBHOOK_URL, str)

        self.request_thread: QtCore.QThread | None = None
        self.request_worker: RequestWorker | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central_widget = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        central_layout.addWidget(self._build_header())
        central_layout.addWidget(self._build_chat_area(), stretch=1)
        central_layout.addWidget(self._build_input_panel())

        self.setCentralWidget(central_widget)
        self._apply_styles()

    def _build_header(self) -> QtWidgets.QWidget:
        header = QtWidgets.QWidget()
        header.setObjectName("chatHeader")
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("ChatGPT")
        title.setObjectName("chatTitle")

        subtitle = QtWidgets.QLabel("Interagissez avec votre agent n8n")
        subtitle.setObjectName("chatSubtitle")

        title_layout = QtWidgets.QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        layout.addLayout(title_layout)
        layout.addStretch()

        settings_button = QtWidgets.QToolButton()
        settings_button.setObjectName("settingsButton")
        settings_button.setText("Paramètres")
        settings_button.clicked.connect(self.open_settings_dialog)
        layout.addWidget(settings_button)

        return header

    def _build_chat_area(self) -> QtWidgets.QScrollArea:
        self.chat_scroll = QtWidgets.QScrollArea()
        self.chat_scroll.setObjectName("chatScroll")
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.chat_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.chat_container = QtWidgets.QWidget()
        self.chat_layout = QtWidgets.QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(48, 32, 48, 32)
        self.chat_layout.setSpacing(18)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        return self.chat_scroll

    def _build_input_panel(self) -> QtWidgets.QWidget:
        input_panel = QtWidgets.QWidget()
        input_panel.setObjectName("chatInputPanel")
        layout = QtWidgets.QHBoxLayout(input_panel)
        layout.setContentsMargins(48, 24, 48, 36)
        layout.setSpacing(16)

        self.chat_input = ChatInput()
        self.chat_input.submitted.connect(self.send_chat_message)

        self.send_button = QtWidgets.QPushButton("Envoyer")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_chat_message)

        layout.addWidget(self.chat_input, stretch=1)
        layout.addWidget(self.send_button)

        return input_panel

    # ------------------------------------------------------------------
    # Gestion des paramètres
    # ------------------------------------------------------------------
    @QtCore.Slot()
    def open_settings_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Paramètres")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        description = QtWidgets.QLabel(
            "Configurez l'URL du webhook utilisé pour communiquer avec l'agent n8n."
        )
        description.setWordWrap(True)

        webhook_input = QtWidgets.QLineEdit(self.webhook_url)
        webhook_input.setPlaceholderText("https://...")

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        layout.addWidget(description)
        layout.addWidget(webhook_input)
        layout.addWidget(button_box)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self._save_webhook_url(webhook_input.text())

    def _save_webhook_url(self, value: str) -> None:
        self.webhook_url = value.strip() or DEFAULT_WEBHOOK_URL
        self.settings.setValue("webhook_url", self.webhook_url)
        QtWidgets.QMessageBox.information(
            self, "Paramètres", "URL sauvegardée avec succès."
        )

    # ------------------------------------------------------------------
    # Gestion du chat
    # ------------------------------------------------------------------
    def append_message(self, sender: str, message: str, role: str) -> None:
        bubble = ChatBubble(sender, message, role)
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addStretch()
        layout.addWidget(bubble, 0, QtCore.Qt.AlignHCenter)
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
        message = self.chat_input.toPlainText().strip()
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
                background-color: #202123;
            }

            QWidget {
                color: #ECEFF4;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: 11pt;
            }

            #chatHeader {
                background-color: #282B30;
                border-bottom: 1px solid #2F3238;
            }

            #chatTitle {
                font-size: 18pt;
                font-weight: 600;
                color: #FFFFFF;
            }

            #chatSubtitle {
                font-size: 11pt;
                color: rgba(236, 239, 244, 0.7);
            }

            #settingsButton {
                padding: 8px 18px;
                border-radius: 18px;
                background-color: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
            }

            #settingsButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }

            #settingsButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }

            #chatScroll {
                background-color: #343541;
            }

            #chatInputPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #343541, stop:1 #202123);
            }

            ChatInput {
                background-color: #40414F;
                border-radius: 18px;
                padding: 16px 18px;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }

            ChatInput:focus {
                border: 1px solid rgba(134, 160, 246, 0.9);
            }

            QPushButton#sendButton {
                background-color: #10A37F;
                color: #FFFFFF;
                padding: 14px 28px;
                border-radius: 22px;
                font-weight: 600;
            }

            QPushButton#sendButton:hover {
                background-color: #17C190;
            }

            QPushButton#sendButton:pressed {
                background-color: #0D8568;
            }

            ChatBubble {
                border-radius: 18px;
                background-color: #444654;
            }

            ChatBubble[role="user"] {
                background-color: #343541;
            }

            ChatBubble[role="agent"] {
                background-color: #444654;
            }

            ChatBubble[role="error"] {
                background-color: #8B3A3A;
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
                color: #F8F9FD;
            }

            ChatBubble[role="error"] > QLabel#messageLabel {
                color: #FFFFFF;
            }
            """
        )


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(900, 720)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
