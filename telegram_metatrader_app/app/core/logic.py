import logging
from typing import Dict, Any, Optional

from app.db import SessionLocal, add_order, update_order_status, get_order_by_telegram_id, Order
from app.mt5 import place_order # Assuming mt5 connector is initialized elsewhere
# from app.telegram_bot.bot import parse_message # For type hinting if needed, not for direct use here

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def process_telegram_signal(parsed_data: Dict[str, Any]):
    """
    Processes a parsed Telegram signal, stores it, and attempts to execute it via MT5.

    Args:
        parsed_data: The dictionary received from app.telegram_bot.bot.parse_message.
                     Expected format: {"telegram_message_id": "...", "instrument": "...", 
                                       "action": "...", "entry_range": "...", 
                                       "tps": ["...", "..."], "sl": "..."}
    """
    logger.info(f"Processing signal for telegram_message_id: {parsed_data.get('telegram_message_id')}, Data: {parsed_data}")

    telegram_message_id = parsed_data.get("telegram_message_id")
    if not telegram_message_id:
        logger.error("Telegram message ID is missing in parsed_data. Cannot process signal.")
        return

    db = SessionLocal()
    new_order_id: Optional[int] = None # To store the ID of the newly created order

    try:
        # Check for duplicate signal
        existing_order = get_order_by_telegram_id(db, telegram_message_id=str(telegram_message_id))
        if existing_order:
            logger.warning(f"Duplicate signal received for telegram_message_id: {telegram_message_id}. Order ID: {existing_order.id}. Skipping.")
            return

        # Add order to database as "pending"
        new_order_obj: Optional[Order] = None # Define new_order_obj here for broader scope
        try:
            # Ensure volume is present, else use default from model (which is 0.01)
            if "volume" not in parsed_data or parsed_data["volume"] is None:
                 logger.info(f"Volume not in parsed_data for msg_id {telegram_message_id}, will use DB default.")
            
            new_order_obj = add_order(db, order_data=parsed_data)
            new_order_id = new_order_obj.id # Store the ID for later updates
            logger.info(f"Order {new_order_id} for msg_id {telegram_message_id} added to DB as 'pending'.")
        except Exception as e:
            logger.exception(f"Failed to add order for msg_id {telegram_message_id} to database.")
            db.rollback() # Ensure rollback on error during add_order
            return # Stop processing if DB add fails

        # Prepare for MT5 Execution
        # Check if new_order_obj is None which might happen if add_order raised an error before assigning (though current logic re-raises)
        if not new_order_obj:
            logger.error(f"Order object not created for msg_id {telegram_message_id}, cannot proceed with MT5 execution.")
            return

        instrument = new_order_obj.instrument
        order_type = new_order_obj.action.upper() # Ensure "BUY" or "SELL"
        volume = new_order_obj.volume # Using the value from DB (which could be default or from parsed_data)
        
        sl_price: Optional[float] = None
        if new_order_obj.sl:
            try:
                sl_price = float(new_order_obj.sl)
            except ValueError:
                logger.warning(f"Order {new_order_id}: Invalid SL value '{new_order_obj.sl}'. Cannot convert to float.")
                update_order_status(db, order_id=new_order_id, status="failed", status_message=f"Invalid SL value: {new_order_obj.sl}")
                return
        
        tp_price: Optional[float] = None
        if new_order_obj.tps and isinstance(new_order_obj.tps, list) and len(new_order_obj.tps) > 0:
            # Attempt to use the first TP. Ensure it's a valid number.
            first_tp_val = new_order_obj.tps[0]
            try:
                tp_price = float(first_tp_val)
            except (ValueError, TypeError) as e: # Catch TypeError if first_tp_val is not string/number
                logger.warning(f"Order {new_order_id}: Invalid TP value '{first_tp_val}' in tps list {new_order_obj.tps}. Error: {e}. Cannot convert to float.")
                update_order_status(db, order_id=new_order_id, status="failed", status_message=f"Invalid TP value: {first_tp_val}")
                return
        
        # entry_price = new_order_obj.parsed_entry_price # Available if needed for limit orders (e.g. pending orders)

        logger.info(f"Order {new_order_id}: Attempting to place MT5 market order: Instrument={instrument}, Type={order_type}, Vol={volume}, SL={sl_price}, TP={tp_price}")

        # Execute Order via MT5
        # Assumes mt5.initialize() has been called successfully elsewhere
        mt5_result = place_order(
            instrument=instrument, 
            order_type=order_type, 
            volume=volume, 
            sl=sl_price, 
            tp=tp_price
        )

        # Update Order Status in Database
        if mt5_result and mt5_result.get("order_id"):
            update_order_status(
                db_session=db, 
                order_id=new_order_id, 
                mt5_order_id=mt5_result["order_id"], 
                status="executed", 
                executed_price=mt5_result["price"], 
                status_message="Order executed successfully."
            )
            logger.info(f"Order {new_order_id} (MT5 ID: {mt5_result['order_id']}) executed successfully for msg_id {telegram_message_id}. Details: {mt5_result}")
        else:
            # place_order returns None or a dict without 'order_id' on failure
            # The place_order function itself should log detailed errors from MT5
            error_message = "MT5 order execution failed. Check MT5 connector logs."
            if mt5_result and mt5_result.get("comment"): # Use comment from MT5 if available
                error_message = f"MT5 order failed: {mt5_result.get('comment')}"

            logger.error(f"Order {new_order_id}: MT5 order execution failed for msg_id {telegram_message_id}. MT5 Response: {mt5_result}")
            update_order_status(
                db_session=db, 
                order_id=new_order_id, 
                status="failed", 
                status_message=error_message
            )

    except Exception as e:
        logger.exception(f"An unexpected error occurred in process_telegram_signal for msg_id {telegram_message_id}.")
        if new_order_id and new_order_obj: # Check if order was added to DB
            try:
                # Check current status before overwriting, to avoid clobbering a more specific "failed" status
                current_status = db.query(Order.status).filter(Order.id == new_order_id).scalar()
                if current_status not in ["executed", "failed"]: # Avoid overwriting a more specific failure
                    update_order_status(db, order_id=new_order_id, status="error", status_message=f"Core logic processing error: {str(e)[:250]}") # Limit message length
            except Exception as db_update_err:
                logger.error(f"Order {new_order_id}: Failed to update status to 'error' after an exception: {db_update_err}")
        # db.rollback() # Rollback is good, but commit might be needed for status updates on existing orders
    finally:
        db.close()
        logger.debug(f"Database session closed for msg_id {telegram_message_id}.")

if __name__ == '__main__':
    # This is for conceptual testing. 
    # It requires the database to be set up (models.py) and MT5 to be initialized (main.py or direct call).
    # Also, logging needs to be configured (e.g., by main.py or a simple setup_logging here for testing).
    
    # If running this file directly for tests, ensure logging is configured:
    # from app.utils.logger import setup_logging
    # setup_logging(level=logging.DEBUG) # Setup basic console logging for testing

    logger.info("Starting core logic test (conceptual)...")

    # 1. Database: Ensure 'telegram_metatrader_app/trading_app.db' exists and 'orders' table is created.
    #    Run app/db/models.py once if needed: `python -m app.db.models`
    
    # 2. MT5 Connection: For live testing, MT5 terminal must be running and initialized.
    #    Example (uncomment and fill details if testing MT5 interaction directly):
    #    from app.mt5.connector import initialize_mt5, shutdown_mt5
    #    TEST_MT5_LOGIN = 12345678 
    #    TEST_MT5_PASSWORD = "YOUR_PASSWORD"
    #    TEST_MT5_SERVER = "YOUR_SERVER"
    #    if initialize_mt5(TEST_MT5_LOGIN, TEST_MT5_PASSWORD, TEST_MT5_SERVER):
    #        logger.info("MT5 initialized for core logic test.")
    #    else:
    #        logger.error("MT5 initialization failed. MT5 dependent tests will fail.")
    #        # exit() # Or proceed without MT5 for non-MT5 specific logic parts

    # Example parsed_data (as would come from telegram_bot.py's parse_message)
    example_signal_data_1 = {
        "telegram_message_id": "test_msg_001", # Unique ID
        "instrument": "EURUSD", # Ensure this symbol is available in your MT5
        "action": "Buy",
        "entry_range": "1.0850-1.0855",
        "tps": ["1.0870", "1.0890"],
        "sl": "1.0830",
        "volume": 0.01 # Explicitly set volume for testing
    }

    example_signal_data_2 = {
        "telegram_message_id": "test_msg_002", # Unique ID
        "instrument": "GOLD", # Ensure this symbol (e.g., XAUUSD) is available
        "action": "Sell",
        "entry_range": "2030.0-2030.5",
        "tps": ["2025.0"],
        "sl": "2035.0",
        # Volume will use default
    }
    
    example_signal_data_duplicate = { # To test duplicate handling
        "telegram_message_id": "test_msg_001", 
        "instrument": "EURUSD", 
        "action": "Sell", # Different action but same ID
        "entry_range": "1.0850-1.0855",
        "tps": ["1.0870"], "sl": "1.0830"
    }

    example_signal_invalid_sl = {
        "telegram_message_id": "test_msg_003",
        "instrument": "GBPUSD",
        "action": "Buy",
        "entry_range": "1.2650-1.2655",
        "tps": ["1.2670"],
        "sl": "invalid_sl_value" # Invalid SL
    }

    logger.info("\n--- Simulating processing Test Signal 1 (EURUSD Buy) ---")
    # To actually run: process_telegram_signal(example_signal_data_1)
    # Ensure MT5 is initialized if you uncomment the call above.
    
    logger.info("\n--- Simulating processing Test Signal 2 (GOLD Sell, default volume) ---")
    # process_telegram_signal(example_signal_data_2)

    logger.info("\n--- Simulating processing Test Signal 1 Again (Duplicate) ---")
    # process_telegram_signal(example_signal_data_duplicate)

    logger.info("\n--- Simulating processing Test Signal with Invalid SL ---")
    # process_telegram_signal(example_signal_invalid_sl)

    # Example of querying DB post-test (if signals were actually processed):
    # logger.info("\n--- Querying DB for orders after test ---")
    # db_test_session = SessionLocal()
    # try:
    #     orders = get_all_orders(db_test_session, limit=10)
    #     if orders:
    #         for order in orders:
    #             logger.info(f"DB Order: ID={order.id}, MsgID={order.telegram_message_id}, Status={order.status}, MT5ID={order.mt5_order_id}, Message='{order.status_message}'")
    #     else:
    #         logger.info("No orders found in DB.")
    # except Exception as e:
    #     logger.error(f"Error querying DB in test: {e}")
    # finally:
    #     db_test_session.close()

    # (Conceptual) Shutdown MT5 if initialized in this test block
    # if 'mt5_initialized' in locals() and mt5_initialized: # Check if var exists and true
    #    shutdown_mt5()
    #    logger.info("MT5 shut down after core logic test.")
    
    logger.info("Core logic test finished (simulated runs). Uncomment 'process_telegram_signal' calls and MT5 init/shutdown for live testing.")
    logger.info("Ensure MT5 terminal is running for live tests and DB is set up.")
