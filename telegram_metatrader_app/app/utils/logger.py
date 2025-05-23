import logging
from PyQt5.QtCore import QObject, pyqtSignal

class GuiHandler(logging.Handler, QObject):
    """
    A custom logging handler that emits a PyQt signal for each log record.
    This allows log messages to be displayed in a PyQt GUI element.
    """
    log_received = pyqtSignal(str)

    def __init__(self):
        # Initialize logging.Handler first
        logging.Handler.__init__(self)
        # Then initialize QObject
        QObject.__init__(self)

    def emit(self, record):
        """
        Overrides the default emit method of logging.Handler.
        Formats the log record and emits the log_received signal.
        """
        try:
            msg = self.format(record)
            self.log_received.emit(msg)
        except Exception:
            # Handle exceptions during logging itself, e.g., if formatting fails
            # Or if the signal connection is problematic.
            # For now, just pass, but in a real app, might log to stderr.
            self.handleError(record)


def setup_logging(gui_handler: GuiHandler = None, level=logging.INFO):
    """
    Configures the root logger to output to console and optionally to a GUI handler.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to prevent duplicate logging
    # This is important if this function could be called multiple times,
    # though ideally it's called once at application startup.
    if root_logger.hasHandlers():
        for handler in root_logger.handlers[:]: # Iterate over a copy
            root_logger.removeHandler(handler)
            handler.close() # Close handler to release resources

    # Configure console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level) # Set level for console handler
    root_logger.addHandler(console_handler)

    # Configure GUI handler if provided
    if gui_handler:
        # You can use a different formatter or level for the GUI if desired
        gui_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') # Slightly simpler for GUI
        gui_handler.setFormatter(gui_formatter)
        gui_handler.setLevel(level) # Set level for GUI handler
        root_logger.addHandler(gui_handler)
        logging.info("GUI logging handler configured.")
    
    logging.info("Logging configured. All new log messages will use this setup.")

if __name__ == '__main__':
    # Example usage for testing the logger setup directly
    # This would typically be in your main application file.

    # Dummy QApplication for QObject based GuiHandler to work if testing signals
    try:
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() # Check if an instance already exists
        if app is None:
            app = QApplication(sys.argv) # Create it if it doesn't
        
        test_gui_handler = GuiHandler()
        
        # Example slot to connect to the signal
        def print_log_from_signal(message):
            print(f"FROM SIGNAL: {message.strip()}")

        test_gui_handler.log_received.connect(print_log_from_signal)
        
        setup_logging(gui_handler=test_gui_handler, level=logging.DEBUG)

        logging.debug("This is a debug message.")
        logging.info("This is an info message.")
        logging.warning("This is a warning message.")
        logging.error("This is an error message.")
        
        # Test logging from another module
        logger_test_module = logging.getLogger("TestModule")
        logger_test_module.info("Info message from TestModule.")

        if app: # If we created it, we might want to start its event loop for a moment
            # For non-GUI tests, app.exec_() is not needed.
            # If testing signal emission, you might need to process events.
            # app.processEvents() # Process any pending events
            pass


    except ImportError:
        print("PyQt5 is not installed. Running basic console logging test.")
        setup_logging(level=logging.DEBUG)
        logging.debug("This is a debug message (console only).")
        logging.info("This is an info message (console only).")
        logging.warning("This is a warning message (console only).")
        logging.error("This is an error message (console only).")

    print("Logger test finished.")
