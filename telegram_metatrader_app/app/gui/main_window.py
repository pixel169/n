import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QLabel, QLineEdit, QPushButton, QTableView, QGroupBox
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt # For Qt.Alignment flags if needed

from app.utils.logger import GuiHandler # Import GuiHandler

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram to MetaTrader 5 Bot")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize GuiHandler and connect its signal
        self.gui_log_handler = GuiHandler()
        self.gui_log_handler.log_received.connect(self.add_log_message)
        
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Configuration Section
        config_group_box = QGroupBox("Configuration")
        config_layout = QVBoxLayout()

        self.telegram_token_input = QLineEdit()
        self.chat_ids_input = QLineEdit()
        self.mt5_login_input = QLineEdit()
        self.mt5_password_input = QLineEdit()
        self.mt5_password_input.setEchoMode(QLineEdit.Password) # Mask password
        self.mt5_server_input = QLineEdit()
        self.save_config_button = QPushButton("Save Configuration")

        config_layout.addWidget(QLabel("Telegram API Token:"))
        config_layout.addWidget(self.telegram_token_input)
        config_layout.addWidget(QLabel("Telegram Chat IDs (comma-separated):"))
        config_layout.addWidget(self.chat_ids_input)
        config_layout.addWidget(QLabel("MT5 Login:"))
        config_layout.addWidget(self.mt5_login_input)
        config_layout.addWidget(QLabel("MT5 Password:"))
        config_layout.addWidget(self.mt5_password_input)
        config_layout.addWidget(QLabel("MT5 Server:"))
        config_layout.addWidget(self.mt5_server_input)
        config_layout.addWidget(self.save_config_button)
        config_group_box.setLayout(config_layout)
        main_layout.addWidget(config_group_box)

        # Control Section
        control_group_box = QGroupBox("Controls")
        control_layout = QHBoxLayout()
        self.start_bot_button = QPushButton("Start Bot")
        self.stop_bot_button = QPushButton("Stop Bot")
        self.stop_bot_button.setEnabled(False) # Initially disabled

        control_layout.addWidget(self.start_bot_button)
        control_layout.addWidget(self.stop_bot_button)
        control_group_box.setLayout(control_layout)
        main_layout.addWidget(control_group_box)

        # Log Display Section
        log_group_box = QGroupBox("Logs")
        log_layout = QVBoxLayout()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        log_group_box.setLayout(log_layout)
        main_layout.addWidget(log_group_box)
        main_layout.setStretchFactor(log_group_box, 1) # Allow log display to expand

        # Order Table Section
        order_group_box = QGroupBox("Orders")
        order_layout = QVBoxLayout()
        self.order_table_view = QTableView()
        
        # Setup basic model for the table
        self.order_table_model = QStandardItemModel()
        self.order_table_model.setHorizontalHeaderLabels(
            ["ID", "Timestamp", "Instrument", "Action", "Entry Range", 
             "Parsed Price", "Volume", "TPs", "SL", "MT5 ID", "Status", "Status Msg", 
             "Exec Price", "Exec Time"]
        )
        self.order_table_view.setModel(self.order_table_model)
        self.order_table_view.setAlternatingRowColors(True)
        self.order_table_view.setEditTriggers(QTableView.NoEditTriggers) # Read-only
        self.order_table_view.horizontalHeader().setStretchLastSection(True)
        # self.order_table_view.resizeColumnsToContents() # Optional: adjust column widths

        order_layout.addWidget(self.order_table_view)
        order_group_box.setLayout(order_layout)
        main_layout.addWidget(order_group_box)
        main_layout.setStretchFactor(order_group_box, 2) # Allow order table to expand more

        central_widget.setLayout(main_layout)

    def add_log_message(self, message: str):
        """Appends a message to the log display."""
        # In a multi-threaded app, this should be done via signals/slots
        # For now, direct append is fine for initial structure.
        self.log_display.append(message)

    def update_order_table(self, orders: list[dict]):
        """Clears and refills the order table with new data."""
        self.order_table_model.removeRows(0, self.order_table_model.rowCount()) # Clear existing rows
        
        if not orders:
            self.add_log_message("Order table updated with no orders.")
            return

        for order_dict in orders:
            row_items = [
                QStandardItem(str(order_dict.get("id", ""))),
                QStandardItem(str(order_dict.get("timestamp", ""))),
                QStandardItem(str(order_dict.get("instrument", ""))),
                QStandardItem(str(order_dict.get("action", ""))),
                QStandardItem(str(order_dict.get("entry_range", ""))),
                QStandardItem(str(order_dict.get("parsed_entry_price", ""))),
                QStandardItem(str(order_dict.get("volume", ""))),
                QStandardItem(str(order_dict.get("tps", "[]"))), # Display list as string
                QStandardItem(str(order_dict.get("sl", ""))),
                QStandardItem(str(order_dict.get("mt5_order_id", ""))),
                QStandardItem(str(order_dict.get("status", ""))),
                QStandardItem(str(order_dict.get("status_message", ""))),
                QStandardItem(str(order_dict.get("executed_price", ""))),
                QStandardItem(str(order_dict.get("executed_time", ""))),
            ]
            self.order_table_model.appendRow(row_items)
        # self.order_table_view.resizeColumnsToContents() # Adjust after populating
        self.add_log_message(f"Order table updated with {len(orders)} orders.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    
    # Example usage of placeholder methods for testing
    main_win.add_log_message("Application started.")
    main_win.add_log_message("This is another log message.")
    
    example_orders = [
        {"id": 1, "timestamp": "2023-10-26 10:00:00", "instrument": "EURUSD", "action": "Buy", "status": "pending", "mt5_order_id": None, "entry_range": "1.0500-1.0505", "parsed_entry_price": 1.0500, "volume": 0.01, "tps": ["1.0520"], "sl": "1.0480"},
        {"id": 2, "timestamp": "2023-10-26 10:05:00", "instrument": "GOLD", "action": "Sell", "status": "executed", "mt5_order_id": 12345, "entry_range": "1980.0-1980.5", "parsed_entry_price": 1980.0, "volume": 0.1, "tps": ["1975.0"], "sl": "1985.0", "executed_price": 1980.1, "executed_time": "2023-10-26 10:05:30"},
    ]
    main_win.update_order_table(example_orders)
    
    main_win.show()
    sys.exit(app.exec_())
