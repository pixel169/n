import MetaTrader5 as mt5
from datetime import datetime
import logging

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def initialize_mt5(login, password, server) -> bool:
    """
    Initializes the MetaTrader 5 connection and logs in.

    Args:
        login: The MT5 account login.
        password: The MT5 account password.
        server: The MT5 server name.

    Returns:
        True if initialization and login are successful, False otherwise.
    """
    logger.info("Initializing MetaTrader 5...")
    if not mt5.initialize():
        logger.error(f"mt5.initialize() failed, error code: {mt5.last_error()}")
        return False
    logger.info("MetaTrader 5 initialized successfully.")

    logger.info(f"Logging into MetaTrader 5 account {login} on server {server}...")
    if not mt5.login(login, password, server):
        logger.error(f"mt5.login() failed for account {login}, error code: {mt5.last_error()}")
        mt5.shutdown() # Attempt to clean up
        return False
    
    account_info = mt5.account_info()
    if account_info:
        logger.info(f"Login successful. Account: {account_info.name}, Balance: {account_info.balance} {account_info.currency}, Server: {account_info.server}")
    else:
        # This case should ideally not be reached if mt5.login() succeeded without returning False
        logger.warning(f"Login for account {login} reported success, but could not retrieve account info. Error: {mt5.last_error()}")
        # mt5.shutdown() # Decide if this is a critical failure that warrants shutdown
        # return False # Depending on strictness
    return True

def shutdown_mt5():
    """
    Closes the connection to the MetaTrader 5 terminal.
    """
    logger.info("Shutting down MetaTrader 5 connection...")
    mt5.shutdown()
    logger.info("MetaTrader 5 connection shut down.")

def place_order(instrument: str, order_type: str, volume: float, price: float = None, sl: float = None, tp: float = None) -> dict | None:
    """
    Places a market order on MetaTrader 5.

    Args:
        instrument: The trading symbol (e.g., "GOLD", "EURUSD").
        order_type: "BUY" or "SELL".
        volume: The lot size for the order.
        price: The price at which to execute. For market orders, MT5 uses current market price.
               This is mainly for compatibility; current implementation fetches market price.
        sl: Stop loss price.
        tp: Take profit price.

    Returns:
        A dictionary with order details if successful, None otherwise.
    """
    logger.info(f"Attempting to place {order_type} order for {instrument}, Vol: {volume}, SL: {sl}, TP: {tp}")

    symbol_info = mt5.symbol_info(instrument)
    if symbol_info is None:
        logger.error(f"Failed to get symbol_info for {instrument}, error code {mt5.last_error()}")
        return {"error": f"Failed to get symbol_info for {instrument}", "retcode": -1, "comment": f"MT5 error: {mt5.last_error()}"}


    if not symbol_info.visible:
        logger.warning(f"{instrument} is not visible in MarketWatch. Attempting to select it.")
        if not mt5.symbol_select(instrument, True):
            logger.error(f"Failed to select {instrument} in MarketWatch, error code {mt5.last_error()}")
            return {"error": f"Failed to select {instrument} in MarketWatch", "retcode": -1, "comment": f"MT5 error: {mt5.last_error()}"}
        logger.info(f"{instrument} selected in MarketWatch.")
        # Re-fetch symbol info after selecting
        symbol_info = mt5.symbol_info(instrument) # Re-fetch
        if symbol_info is None: # Check again
            logger.error(f"Failed to get symbol_info for {instrument} even after select, error code {mt5.last_error()}")
            return {"error": f"Failed to get symbol_info for {instrument} post-select", "retcode": -1, "comment": f"MT5 error: {mt5.last_error()}"}


    mt5_order_type_val = None
    current_tick = mt5.symbol_info_tick(instrument)
    if not current_tick:
        logger.error(f"Could not fetch market price tick for {instrument}. Error: {mt5.last_error()}")
        return {"error": f"Could not fetch tick for {instrument}", "retcode": -1, "comment": f"MT5 error: {mt5.last_error()}"}

    if order_type.upper() == "BUY":
        mt5_order_type_val = mt5.ORDER_TYPE_BUY
        execution_price = current_tick.ask
    elif order_type.upper() == "SELL":
        mt5_order_type_val = mt5.ORDER_TYPE_SELL
        execution_price = current_tick.bid
    else:
        logger.error(f"Invalid order type: {order_type}. Must be 'BUY' or 'SELL'.")
        return {"error": f"Invalid order type: {order_type}", "retcode": -1, "comment": "Application error: Invalid order type"}

    if execution_price is None or execution_price == 0.0: # Check for valid price
         logger.error(f"Could not fetch valid market price for {instrument}. Ask: {current_tick.ask}, Bid: {current_tick.bid}. Tick info: {current_tick}")
         return {"error": f"Invalid market price for {instrument}", "retcode": -1, "comment": "MT5 error: Could not get valid price"}

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": instrument,
        "volume": float(volume),
        "type": mt5_order_type_val,
        "price": execution_price,
        "deviation": 20,  # Allowable deviation in points
        "magic": 234000,  # A magic number for the order (should be configurable or unique per order)
        "comment": "TG_BOT_ORDER", # Keep comments concise
        "type_time": mt5.ORDER_TIME_GTC,  # Good till cancelled
        "type_filling": mt5.ORDER_FILLING_IOC, # Immediate or Cancel. Consider ORDER_FILLING_FOK for some strategies.
    }

    # Ensure SL/TP are floats if provided and valid
    if sl is not None:
        try:
            sl_val = float(sl)
            if sl_val > 0: request["sl"] = sl_val
            else: logger.warning(f"Invalid SL value {sl_val} for {instrument}, SL not set.")
        except ValueError:
            logger.warning(f"SL value {sl} for {instrument} is not a valid float, SL not set.")
            
    if tp is not None:
        try:
            tp_val = float(tp)
            if tp_val > 0: request["tp"] = tp_val
            else: logger.warning(f"Invalid TP value {tp_val} for {instrument}, TP not set.")
        except ValueError:
            logger.warning(f"TP value {tp} for {instrument} is not a valid float, TP not set.")

    logger.debug(f"Sending order request for {instrument}: {request}")
    result = mt5.order_send(request)

    if result is None:
        # This case indicates a failure at the network level or very early stage in MT5 processing
        last_error = mt5.last_error()
        logger.error(f"order_send failed for {instrument}, error code: {last_error[0]}, description: {last_error[1]}")
        return {"error": "order_send call failed", "retcode": last_error[0], "comment": last_error[1]}

    if result.retcode != mt5.TRADE_RETCODE_DONE and result.retcode != mt5.TRADE_RETCODE_PLACED: # DONE for market, PLACED for pending
        logger.error(f"Order for {instrument} failed. Retcode: {result.retcode} - Comment: {result.comment} - (MT5 Raw Error: {mt5.last_error()})")
        logger.debug(f"Failed order details: Order={result.order}, Price={result.price}, Volume={result.volume}, Deal={result.deal}, Request ID={result.request_id}, Request={result.request}")
        return {
            "error": "Order execution failed by MT5",
            "order_id": result.order,
            "retcode": result.retcode,
            "comment": result.comment,
            "price": result.price,
            "volume": result.volume,
            "deal_id": result.deal,
            "request_id": result.request_id,
            "raw_mt5_error": mt5.last_error()
        }

    logger.info(f"Order for {instrument} placed successfully! Order ID: {result.order}, Price: {result.price}, Volume: {result.volume}")
    order_details = {
        "order_id": result.order,
        "price": result.price, # Execution price
        "volume": result.volume, # Executed volume
        "deal_id": result.deal,
        "instrument": instrument, # From input
        "order_type": order_type, # From input
        "comment": result.comment, # From MT5 result
        "retcode": result.retcode, # From MT5 result
        "request_id": result.request_id, # From MT5 result
        "sl": request.get("sl"), # SL from the original request
        "tp": request.get("tp")  # TP from the original request
    }
    logger.debug(f"Successful order details for {instrument}: {order_details}")
    return order_details

def get_symbol_info(instrument: str) -> dict | None:
    """
    Fetches basic information for a given trading symbol.

    Args:
        instrument: The trading symbol (e.g., "EURUSD", "GOLD").

    Returns:
        A dictionary with symbol information if successful, None otherwise.
    """
    logger.debug(f"Fetching symbol info for {instrument}...")
    info = mt5.symbol_info(instrument)
    if info is None:
        logger.error(f"Failed to get symbol_info for {instrument}, error code: {mt5.last_error()}")
        return None
    
    # Convert SymbolInfo object to a dictionary for easier use and logging
    # Using vars(info) can get all attributes, but be careful with large objects or methods
    # info_dict = vars(info) # This gets all attributes, including private ones if not careful
    # Select specific fields to return for clarity and to avoid overly large dicts
    info_dict = {
        "name": info.name,
        "description": info.description,
        "ask": info.ask,
        "bid": info.bid,
        "last": info.last,
        "time": info.time, # Last quote time
        "spread": info.spread,
        "digits": info.digits,
        "point": info.point,
        "trade_contract_size": info.trade_contract_size,
        "trade_tick_size": info.trade_tick_size,
        "trade_tick_value": info.trade_tick_value,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "visible": info.visible,
        # Add more fields as needed, e.g., info.session_deals, info.price_change, etc.
    }
    logger.debug(f"Symbol info for {instrument}: Ask={info.ask}, Bid={info.bid}, Spread={info.spread}, Digits={info.digits}")
    return info_dict

if __name__ == '__main__':
    # For direct testing of this module, ensure logging is configured.
    # This is usually handled by main.py in the full application.
    if not logging.getLogger().hasHandlers(): # Check if root logger is configured
        logging.basicConfig(level=logging.DEBUG, 
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[logging.StreamHandler()])
        logger.info("Basic logging configured for mt5.connector direct test.")

    # Example Usage (requires MetaTrader 5 terminal running and credentials)
    # Replace with your actual login, password, and server
    TEST_LOGIN = 12345678  # Replace with your MT5 demo account login (integer)
    TEST_PASSWORD = "YOUR_PASSWORD_HERE"  # Replace with your MT5 demo account password
    TEST_SERVER = "YOUR_SERVER_NAME_HERE"  # Replace with your MT5 demo server name

    logger.info("Starting MT5 connector test...")
    if initialize_mt5(TEST_LOGIN, TEST_PASSWORD, TEST_SERVER):
        logger.info("\n--- Testing get_symbol_info ---")
        eurusd_info = get_symbol_info("EURUSD")
        if eurusd_info:
            logger.info(f"EURUSD Info: Ask={eurusd_info.get('ask')}, Bid={eurusd_info.get('bid')}, Spread={eurusd_info.get('spread')}, Digits={eurusd_info.get('digits')}")
        
        gold_info = get_symbol_info("XAUUSD") # Common symbol for Gold, check your broker
        if gold_info:
            logger.info(f"GOLD (XAUUSD) Info: Ask={gold_info.get('ask')}, Bid={gold_info.get('bid')}, Spread={gold_info.get('spread')}")
        else:
            logger.warning("Could not get info for XAUUSD. Ensure it's a valid symbol for your broker.")


        logger.info("\n--- Testing place_order (BUY EURUSD) ---")
        # Ensure EURUSD is available and visible in your Market Watch
        # Adjust SL/TP based on current market prices if testing actual execution
        
        eurusd_tick = mt5.symbol_info_tick("EURUSD")
        if eurusd_tick:
            current_ask = eurusd_tick.ask
            current_bid = eurusd_tick.bid
            logger.info(f"Current EURUSD prices for test: Ask={current_ask}, Bid={current_bid}")

            # Example: Buy EURUSD
            # For a buy order, SL should be below market price, TP above.
            # Pip value for EURUSD is typically 0.0001 (for 5-digit brokers)
            pip_value = eurusd_info.get("point", 0.00001) * (10 if eurusd_info.get("digits", 5) % 2 != 0 else 1) # Heuristic for point vs pip

            # sl_buy = round(current_ask - (50 * pip_value), eurusd_info.get("digits",5)) # 50 pips SL
            # tp_buy = round(current_ask + (100 * pip_value), eurusd_info.get("digits",5)) # 100 pips TP
            
            # For testing, place an order without SL/TP first to ensure basic execution works.
            # Then test with SL/TP. Ensure they are valid prices.
            # order_result_buy = place_order("EURUSD", "BUY", 0.01, sl=sl_buy, tp=tp_buy)
            order_result_buy = place_order("EURUSD", "BUY", 0.01, sl=None, tp=None) 
            if order_result_buy and order_result_buy.get("retcode") == mt5.TRADE_RETCODE_DONE:
                logger.info(f"BUY Order placed successfully: {order_result_buy}")
            else:
                logger.error(f"Failed to place BUY EURUSD order. Result: {order_result_buy}")

            # Example: Sell XAUUSD (illustrative, ensure XAUUSD is available)
            # if gold_info:
            #    gold_tick = mt5.symbol_info_tick("XAUUSD")
            #    if gold_tick:
            #        sl_sell_gold = round(gold_tick.bid + (500 * gold_info.get("point", 0.01)), gold_info.get("digits",2)) # 500 points SL for Gold
            #        tp_sell_gold = round(gold_tick.bid - (1000 * gold_info.get("point", 0.01)), gold_info.get("digits",2)) # 1000 points TP for Gold
            #        order_result_sell_gold = place_order("XAUUSD", "SELL", 0.01, sl=sl_sell_gold, tp=tp_sell_gold)
            #        if order_result_sell_gold and order_result_sell_gold.get("retcode") == mt5.TRADE_RETCODE_DONE:
            #            logger.info(f"SELL Order (XAUUSD) placed successfully: {order_result_sell_gold}")
            #        else:
            #            logger.error(f"Failed to place SELL XAUUSD order. Result: {order_result_sell_gold}")
        else:
            logger.error("Could not get EURUSD tick for SL/TP calculation in test. Skipping market order test.")

        logger.info("\n--- Testing place_order (invalid instrument) ---")
        order_result_invalid = place_order("INVALIDINSTXYZ", "BUY", 0.1)
        if order_result_invalid and order_result_invalid.get("retcode") != mt5.TRADE_RETCODE_DONE:
            logger.info(f"Correctly failed to place order for INVALIDINSTXYZ. Result: {order_result_invalid}")
        else:
            logger.error(f"Order placement for INVALIDINSTXYZ did not fail as expected or succeeded. Result: {order_result_invalid}")

        shutdown_mt5()
    else:
        logger.error("MT5 connection failed. Ensure MetaTrader 5 terminal is running and credentials are correct.")
    
    logger.info("\nMT5 connector test finished.")
