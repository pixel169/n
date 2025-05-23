import re
import logging
from telegram.ext import Application, MessageHandler, filters
from typing import Callable, Dict, List, Optional, Any

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def parse_message(message_text: str, message_id: int) -> Optional[Dict[str, Any]]:
    """
    Parses a Telegram message to extract trading signal information.

    Args:
        message_text: The raw text of the Telegram message.
        message_id: The Telegram message ID.

    Returns:
        A dictionary containing the parsed data if the message matches the format,
        otherwise None.
    """
    parsed_data: Dict[str, Any] = {"tps": [], "telegram_message_id": message_id}
    
    # Regex for the main signal line (instrument, action, entry range)
    # Handles variations in spacing and capitalization for action
    signal_pattern = re.compile(
        r"🌟\s*(?P<instrument>[A-Z]+)\s+(?P<action>Sell|Buy)\s*-\s*(?P<entry_range>\d+\.?\d*\s*-\s*\d+\.?\d*)", 
        re.IGNORECASE
    )
    
    # Regex for Take Profit (TP) lines
    # Handles optional '=' and spacing
    tp_pattern = re.compile(r"🔛\s*TP\s*=?\s*(\d+\.?\d*)", re.IGNORECASE)
    
    # Regex for Stop Loss (SL) line
    # Handles optional 'STOP LOSS' or 'SL' and spacing
    sl_pattern = re.compile(r"❎\s*(?:STOP\s*LOSS|SL)\s*(\d+\.?\d*)", re.IGNORECASE)

    lines = message_text.split('\n')
    
    signal_match_found = False

    for line in lines:
        line = line.strip()
        if not signal_match_found:
            signal_match = signal_pattern.match(line)
            if signal_match:
                data = signal_match.groupdict()
                parsed_data["instrument"] = data["instrument"].upper()
                parsed_data["action"] = data["action"].capitalize()
                # Normalize entry range spacing
                parsed_data["entry_range"] = re.sub(r'\s*-\s*', '-', data["entry_range"])
                signal_match_found = True
                continue # Move to next line after signal is found

        tp_match = tp_pattern.match(line)
        if tp_match:
            parsed_data["tps"].append(tp_match.group(1))
            continue

        sl_match = sl_pattern.match(line)
        if sl_match:
            parsed_data["sl"] = sl_match.group(1)
            continue # SL is typically the last relevant part

    # Ensure essential parts were found
    if "instrument" in parsed_data and "action" in parsed_data and "entry_range" in parsed_data:
        # If no TPs were found, it's still a valid signal, just with an empty list
        if not parsed_data["tps"]:
            del parsed_data["tps"] # Or keep as empty list as per preference
        return parsed_data
    
    return None

async def message_handler(update, context, message_handler_callback: Callable):
    """
    Handles incoming messages, parses them, and calls the callback.
    """
    message_text = update.message.text
    message_id = update.message.message_id
    logger.info(f"Received message. Chat ID: {update.message.chat_id}, Message ID: {message_id}, Text: '{message_text}'")
    
    parsed_data = parse_message(message_text, message_id)
    
    if parsed_data:
        logger.info(f"Message ID {message_id} parsed successfully: {parsed_data}")
        await message_handler_callback(parsed_data) # This callback is process_telegram_signal
    else:
        logger.warning(f"Message ID {message_id} from chat {update.message.chat_id} did not match expected signal format. Text: '{message_text}'")

def start_bot(telegram_token: str, chat_ids: List[str], callback_for_parsed_data: Callable):
    """
    Initializes and runs the Telegram bot.

    Args:
        telegram_token: The Telegram API token.
        chat_ids: A list of chat IDs (as strings) to listen to.
                  Note: telegram.ext.filters.Chat expects integer chat IDs.
        callback_for_parsed_data: A callback function to be invoked with parsed data.
    """
    application = Application.builder().token(telegram_token).build()

    # Convert string chat IDs to integers for the filter
    numeric_chat_ids = [int(chat_id) for chat_id in chat_ids]

    # Using a lambda to pass the custom callback to the handler
    handler = MessageHandler(
        filters.TEXT & (~filters.COMMAND) & filters.Chat(chat_id=numeric_chat_ids),
        lambda update, context: message_handler(update, context, callback_for_parsed_data)
    )
    
    application.add_handler(handler)
    
    logger.info(f"Telegram bot starting. Listening to chat IDs: {numeric_chat_ids}...")
    application.run_polling()
    logger.info("Telegram bot has stopped polling.") # This line will be reached if polling stops

if __name__ == '__main__':
    # For direct testing of this module, ensure logging is configured.
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, 
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[logging.StreamHandler()])
        logger.info("Basic logging configured for telegram_bot.bot direct test.")

    # Example Usage (for testing purposes)
    # Replace with your actual token and chat ID(s)
    TEST_TOKEN = "YOUR_TELEGRAM_API_TOKEN_HERE" # Replace with a test token
    TEST_CHAT_ID = ["YOUR_CHAT_ID_HERE"] # Replace with a test chat_id (as a list of strings)

    def my_callback_test(data: dict):
        logger.info(f"Test Callback received data: {data}")

    # Test parse_message
    logger.info("\n--- Testing parse_message ---")
    test_message_1 = """
    🌟GOLD Sell - 3358-3360

    blah blah some other text
    🔛TP =3356
    whatever here
    🔛TP =3354
    🔛TP =3348

    another line
    ❎STOP LOSS 3365
    """
    logger.info(f"Test 1 Input:\n{test_message_1}")
    logger.info(f"Test 1 Parsed: {parse_message(test_message_1, 101)}")

    test_message_2 = "🌟EURUSD Buy - 1.1234-1.1236"
    logger.info(f"Test 2 Input: {test_message_2}")
    logger.info(f"Test 2 Parsed: {parse_message(test_message_2, 102)}")

    test_message_3 = "Just some random text without the signal format."
    logger.info(f"Test 3 Input: {test_message_3}")
    logger.info(f"Test 3 Parsed: {parse_message(test_message_3, 103)}")
    
    test_message_4 = """
    🌟GBPUSD buy - 1.2345 - 1.2350
    🔛 TP = 1.2360
    🔛 TP 1.2370
    ❎ SL 1.2330
    """
    logger.info(f"Test 4 Input:\n{test_message_4}")
    logger.info(f"Test 4 Parsed: {parse_message(test_message_4, 104)}")

    # To run the bot for testing (requires a valid token and chat_id):
    # logger.info("\nStarting bot for manual testing (press Ctrl+C to stop)...")
    # logger.info(f"Ensure your bot is a member of the chat ID: {TEST_CHAT_ID[0]} and can read messages.")
    # logger.info(f"To test, send a message in the specified format to the chat.")
    # if TEST_TOKEN != "YOUR_TELEGRAM_API_TOKEN_HERE" and TEST_CHAT_ID[0] != "YOUR_CHAT_ID_HERE":
    #    start_bot(TEST_TOKEN, TEST_CHAT_ID, my_callback_test)
    # else:
    #    logger.warning("Test token/chat ID not set. Skipping live bot test.")
    # logger.info("Bot test finished (if it was started).")
