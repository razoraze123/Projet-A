"""Simple PySide6 desktop app to interact with an N8N webhook.

This module can be executed directly to start the user interface.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Configuration management helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CONFIG: Dict[str, Any] = {"webhook_url": ""}


def load_config() -> Dict[str, Any]:
    """Load configuration from ``config.json`` or return defaults."""
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    return {**DEFAULT_CONFIG, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """Persist configuration to ``config.json`` in a human-readable form."""
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as fp:
            json.dump(config, fp, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise RuntimeError("Unable to save configuration") from exc


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class WebhookClient(QWidget):
    """Main window encapsulating the tabbed interface."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("N8N Webhook Client")
        self.resize(720, 480)
        self.setMinimumSize(520, 360)

        # Load stored configuration once when the UI is initialised.
        self.config: Dict[str, Any] = load_config()
        self.webhook_url: str = self.config.get("webhook_url", "")

        # Build the main layout with three tabs.
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QTabWidget.North)
        layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self._create_settings_tab(), "Paramètres")
        self.tab_widget.addTab(self._create_chat_tab(), "Chat")
        self.tab_widget.addTab(self._create_upload_tab(), "Upload")

        # Apply a subtle stylesheet for a clean look.
        self.setStyleSheet(
            """
            QWidget {
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 14px;
            }
            QPushButton {
                padding: 6px 14px;
                border-radius: 6px;
                background-color: #1976d2;
                color: white;
            }
            QPushButton:disabled {
                background-color: #9e9e9e;
            }
            QPushButton:hover:!disabled {
                background-color: #1565c0;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #b0bec5;
                border-radius: 4px;
                padding: 4px 6px;
            }
            QTabBar::tab {
                padding: 8px 16px;
            }
            """
        )

    # ------------------------------------------------------------------
    # Settings tab
    # ------------------------------------------------------------------

    def _create_settings_tab(self) -> QWidget:
        """Create the settings tab allowing users to configure the webhook."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)

        description = QLabel(
            "Entrez l'URL du webhook N8N qui sera utilisée pour les envois."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.webhook_input = QLineEdit(self.webhook_url)
        self.webhook_input.setPlaceholderText("https://exemple.com/webhook")
        layout.addWidget(self.webhook_input)

        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)

        self.save_button = QPushButton("Sauvegarder")
        self.save_button.clicked.connect(self._handle_save_settings)
        button_layout.addWidget(self.save_button)

        button_layout.addStretch()

        self.status_label = QLabel("")
        status_font = QFont()
        status_font.setPointSize(10)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("color: #388e3c;")
        layout.addWidget(self.status_label)

        return container

    # ------------------------------------------------------------------
    # Chat tab
    # ------------------------------------------------------------------

    def _create_chat_tab(self) -> QWidget:
        """Create a simple chat interface for sending text messages."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText(
            "Les messages échangés avec le webhook apparaîtront ici."
        )
        layout.addWidget(self.chat_display, 1)

        input_layout = QHBoxLayout()
        layout.addLayout(input_layout)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Écrire un message…")
        self.chat_input.returnPressed.connect(self._handle_send_chat)
        input_layout.addWidget(self.chat_input, 1)

        self.chat_send_button = QPushButton("Envoyer")
        self.chat_send_button.clicked.connect(self._handle_send_chat)
        input_layout.addWidget(self.chat_send_button)

        return container

    # ------------------------------------------------------------------
    # Upload tab
    # ------------------------------------------------------------------

    def _create_upload_tab(self) -> QWidget:
        """Create the file upload interface with placeholders."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(12)

        self.selected_file_path: Optional[Path] = None

        instruction = QLabel(
            "Choisissez un fichier à envoyer au webhook sous forme de multipart."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        chooser_layout = QHBoxLayout()
        layout.addLayout(chooser_layout)

        self.choose_file_button = QPushButton("Choisir un fichier")
        self.choose_file_button.clicked.connect(self._handle_choose_file)
        chooser_layout.addWidget(self.choose_file_button)

        self.file_name_label = QLabel("Aucun fichier sélectionné")
        self.file_name_label.setWordWrap(True)
        chooser_layout.addWidget(self.file_name_label, 1)

        self.upload_button = QPushButton("Envoyer")
        self.upload_button.clicked.connect(self._handle_upload_file)
        self.upload_button.setEnabled(False)
        layout.addWidget(self.upload_button)

        return container

    # ------------------------------------------------------------------
    # Event handlers and business logic placeholders
    # ------------------------------------------------------------------

    def _handle_save_settings(self) -> None:
        """Persist the webhook URL to the configuration file."""
        self.webhook_url = self.webhook_input.text().strip()
        self.config["webhook_url"] = self.webhook_url
        try:
            save_config(self.config)
        except RuntimeError:
            QMessageBox.critical(
                self,
                "Erreur",
                "Impossible d'enregistrer la configuration. Vérifiez les permissions.",
            )
            return

        self.status_label.setText("Configuration sauvegardée ✔")
        self.status_label.setStyleSheet("color: #388e3c;")

    def _handle_send_chat(self) -> None:
        """Read the current message and simulate sending it to the webhook."""
        message = self.chat_input.text().strip()
        if not message:
            return

        self.chat_display.append(f"Vous : {message}")
        self.chat_input.clear()

        response = self.send_message_to_webhook(message)
        if response:
            self.chat_display.append(f"Webhook : {response}")

    def _handle_choose_file(self) -> None:
        """Open a file dialog so the user can select a file to upload."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.selected_file_path = Path(selected_files[0])
                self.file_name_label.setText(self.selected_file_path.name)
                self.upload_button.setEnabled(True)
        else:
            self.selected_file_path = None
            self.file_name_label.setText("Aucun fichier sélectionné")
            self.upload_button.setEnabled(False)

    def _handle_upload_file(self) -> None:
        """Simulate the upload of a previously selected file."""
        if not self.selected_file_path:
            QMessageBox.warning(self, "Upload", "Veuillez sélectionner un fichier.")
            return

        self.upload_file_to_webhook(self.selected_file_path)
        QMessageBox.information(
            self, "Upload", f"Fichier '{self.selected_file_path.name}' envoyé !"
        )
        self.file_name_label.setText("Aucun fichier sélectionné")
        self.upload_button.setEnabled(False)
        self.selected_file_path = None

    # ------------------------------------------------------------------
    # Placeholder methods for future HTTP integration
    # ------------------------------------------------------------------

    def send_message_to_webhook(self, message: str) -> str:
        """Placeholder for sending a text message to the webhook.

        Parameters
        ----------
        message:
            The textual content to deliver.

        Returns
        -------
        str
            A simulated response string.
        """

        print(f"[DEBUG] Sending message to {self.webhook_url!r}: {message}")
        return "Message envoyé (simulation)."

    def upload_file_to_webhook(self, file_path: Path) -> None:
        """Placeholder for uploading a file to the webhook."""

        print(
            f"[DEBUG] Uploading file to {self.webhook_url!r}: {file_path}"
        )


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point used when running the module as a script."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = WebhookClient()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
