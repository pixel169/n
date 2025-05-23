import sys
import logging # Standard logging library
import configparser # For future config loading
import threading # For running bot in a separate thread
from PyQt5.QtWidgets import QApplication

# Application-specific imports
from app.gui.main_window import MainWindow
from app.utils.logger import setup_logging # GuiHandler is used within MainWindow and setup_logging
from app.mt5 import initialize_mt5, shutdown_mt5 # get_symbol_info, place_order might be used by GUI/core logic later
from app.db import create_db_and_tables # SessionLocal, get_all_orders might be used by GUI/core logic later
from app.telegram_bot.bot import start_bot
from app.core.logic import process_telegram_signal

# Global variable to signal the bot thread to stop
stop_bot_event = threading.Event()
# Global variable to hold the bot thread reference
bot_thread: Optional[threading.Thread] = None
# Global flag to indicate if MT5 was initialized by the start_bot process
mt5_initialized_by_bot = False


def main():
    app = QApplication(sys.argv)
    main_win = MainWindow()

    # Setup logging: Pass the GuiHandler instance from MainWindow
    setup_logging(gui_handler=main_win.gui_log_handler, level=logging.INFO)

    logging.info("Application starting...")

    try:
        logging.info("Checking/creating database and tables...")
        create_db_and_tables() # This function should ideally log its own success/failure
    except Exception as e:
        logging.error(f"Failed to create database and tables: {e}", exc_info=True)
        main_win.add_log_message(f"CRITICAL: Failed to initialize database: {e}. Check logs. Application may not function correctly.")


    def load_config_values():
        """Loads configuration from config.ini or config.ini.template"""
        config = configparser.ConfigParser()
        # Try actual config first, then template
        if not config.read('config.ini') and not config.read('config.ini.template'):
            logging.error("config.ini or config.ini.template not found or empty. Please configure.")
            main_win.add_log_message("ERROR: config.ini or config.ini.template not found/empty.")
            return None
        
        try:
            cfg = {
                'telegram_token': config.get('TELEGRAM', 'API_TOKEN', fallback=None),
                'chat_ids_str': config.get('TELEGRAM', 'CHAT_IDS', fallback=None),
                'mt5_login': config.getint('METATRADER5', 'LOGIN', fallback=None),
                'mt5_password': config.get('METATRADER5', 'PASSWORD', fallback=None),
                'mt5_server': config.get('METATRADER5', 'SERVER', fallback=None),
            }
            if not all(cfg.values()): # Simple check for None values
                logging.error("One or more configuration values are missing from config.ini.")
                main_win.add_log_message("ERROR: Missing configuration values in config.ini.")
                return None
            
            cfg['chat_ids'] = [chat_id.strip() for chat_id in cfg['chat_ids_str'].split(',')]
            logging.info("Configuration loaded successfully.")
            return cfg
        except Exception as e:
            logging.error(f"Error processing configuration values: {e}", exc_info=True)
            main_win.add_log_message(f"Error loading configuration: {e}")
            return None


    def on_save_config():
        logging.info("Save Configuration button clicked.")
        config = configparser.ConfigParser()
        try:
            # Read existing config to preserve other sections/values if any
            config.read('config.ini') # Or config.ini.template if you want to save to template
            
            if not config.has_section('TELEGRAM'):
                config.add_section('TELEGRAM')
            config.set('TELEGRAM', 'API_TOKEN', main_win.telegram_token_input.text())
            config.set('TELEGRAM', 'CHAT_IDS', main_win.chat_ids_input.text())
            
            if not config.has_section('METATRADER5'):
                config.add_section('METATRADER5')
            config.set('METATRADER5', 'LOGIN', main_win.mt5_login_input.text())
            config.set('METATRADER5', 'PASSWORD', main_win.mt5_password_input.text())
            config.set('METATRADER5', 'SERVER', main_win.mt5_server_input.text())
            
            # For DB, if it were configurable in GUI
            # if not config.has_section('DATABASE'):
            #     config.add_section('DATABASE')
            # config.set('DATABASE', 'TYPE', 'sqlite') # Example
            # config.set('DATABASE', 'PATH', 'trading_app.db') # Example

            with open('config.ini', 'w') as configfile:
                config.write(configfile)
            logging.info("Configuration saved to config.ini")
            main_win.add_log_message("Configuration saved successfully to config.ini.")
        except Exception as e:
            logging.error(f"Error saving configuration: {e}", exc_info=True)
            main_win.add_log_message(f"Error saving configuration: {e}")


    def on_start_bot():
        global bot_thread, mt5_initialized_by_bot
        logging.info("Start Bot button clicked.")
        
        cfg = load_config_values()
        if not cfg:
            return # Error messages handled by load_config_values

        main_win.start_bot_button.setEnabled(False)
        main_win.stop_bot_button.setEnabled(True)
        
        logging.info(f"Initializing MT5 for account {cfg['mt5_login']} on {cfg['mt5_server']}...")
        if not initialize_mt5(cfg['mt5_login'], cfg['mt5_password'], cfg['mt5_server']):
            logging.error("MetaTrader 5 initialization failed. Check credentials and terminal.")
            main_win.add_log_message("ERROR: MT5 initialization failed.")
            main_win.start_bot_button.setEnabled(True)
            main_win.stop_bot_button.setEnabled(False)
            return
        mt5_initialized_by_bot = True # Mark that MT5 was started by this process
        logging.info("MetaTrader 5 initialized successfully.")

        stop_bot_event.clear()
        bot_thread = threading.Thread(
            target=run_telegram_bot_thread, 
            args=(cfg['telegram_token'], cfg['chat_ids'], process_telegram_signal, stop_bot_event),
            daemon=True
        )
        bot_thread.start()
        logging.info("Telegram bot thread started.")
        main_win.add_log_message("Bot started. Listening for signals...")


    def run_telegram_bot_thread(token, chat_ids, callback, stop_event_ref):
        # This function is a wrapper to make start_bot compatible with the threading model
        # and to handle the stop_event if start_bot itself doesn't directly support it.
        # Currently, python-telegram-bot's run_polling is blocking and doesn't check an event.
        # A more advanced setup might involve application.start() and application.stop() if available and non-blocking.
        try:
            logging.info(f"Bot thread: Calling start_bot for chat IDs: {chat_ids}")
            start_bot(token, chat_ids, callback) # This is blocking
            # If start_bot returns, it means polling stopped (e.g. error, or if it's non-blocking in future)
            logging.info("Bot thread: start_bot has finished or polling was interrupted.")
        except Exception as e:
            logging.error(f"Exception in Telegram bot thread: {e}", exc_info=True)
            # Consider how to signal this error to the GUI thread safely (e.g., via a PyQt signal)
            # main_win.add_log_message(f"CRITICAL ERROR in bot thread: {e}. Bot stopped.") # Not thread-safe directly
        finally:
            logging.info("Telegram bot thread cleanup.")
            # If the thread stops for any reason, update GUI state (thread-safely)
            # Example: QMetaObject.invokeMethod(main_win.stop_bot_button, "setEnabled", Qt.QueuedConnection, Q_ARG(bool, False))
            # For now, we rely on the user clicking "Stop Bot" or app exit to handle MT5 shutdown.


    def on_stop_bot():
        global mt5_initialized_by_bot, bot_thread
        logging.info("Stop Bot button clicked.")
        stop_bot_event.set() # Signal the bot thread to stop (if it were checking)

        # The primary way to stop python-telegram-bot's run_polling is typically via an internal mechanism
        # or by stopping the script/process. Since it's in a daemon thread, it will exit with the main app.
        # For a cleaner stop, start_bot would need to be refactored or use a different PTB method.
        
        if mt5_initialized_by_bot:
            shutdown_mt5()
            logging.info("MT5 connection shut down.")
            mt5_initialized_by_bot = False
        else:
            logging.info("MT5 was not initialized by 'Start Bot', not shutting it down via 'Stop Bot'.")

        main_win.add_log_message("Bot stop process initiated. MT5 shut down if started by bot. Telegram thread will exit with application.")
        main_win.start_bot_button.setEnabled(True)
        main_win.stop_bot_button.setEnabled(False)
        
        if bot_thread and bot_thread.is_alive():
             logging.info("Telegram bot thread is still alive. It's a daemon and will exit with the app.")
        bot_thread = None


    # Connect GUI buttons to these actions
    main_win.save_config_button.clicked.connect(on_save_config)
    main_win.start_bot_button.clicked.connect(on_start_bot)
    main_win.stop_bot_button.clicked.connect(on_stop_bot)
    
    # Load initial config values into GUI fields (if config exists)
    initial_cfg = load_config_values()
    if initial_cfg:
        main_win.telegram_token_input.setText(initial_cfg.get('telegram_token',''))
        main_win.chat_ids_input.setText(initial_cfg.get('chat_ids_str',''))
        main_win.mt5_login_input.setText(str(initial_cfg.get('mt5_login','')))
        main_win.mt5_password_input.setText(initial_cfg.get('mt5_password',''))
        main_win.mt5_server_input.setText(initial_cfg.get('mt5_server',''))
        logging.info("Populated GUI configuration fields from loaded config.")
    else:
        logging.warning("Could not load initial configuration to populate GUI fields.")


    main_win.show()
    exit_code = app.exec_()
    
    logging.info("Application shutting down...")
    if mt5_initialized_by_bot: # If bot was running (or attempted to run and initialized MT5)
        shutdown_mt5()
        logging.info("MT5 connection shut down during application exit.")
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
