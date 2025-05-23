# Telegram to MetaTrader 5 Bot

## Overview

This application connects to specified Telegram channels, listens for trading signals, parses them, and automatically executes corresponding market orders on a MetaTrader 5 (MT5) account. It provides a Graphical User Interface (GUI) for configuration, logging, and monitoring order history.

**Key Technologies:** Python 3, PyQt5 (for GUI), python-telegram-bot (Telegram API), MetaTrader5 (MT5 Integration), SQLAlchemy (Database).

## Features

*   Monitors specified Telegram channels/groups for trading signals.
*   Parses signals based on a defined format (see "Signal Format Example" below).
*   Executes market orders (Buy/Sell) on the connected MetaTrader 5 account.
*   Supports Stop Loss (SL) and Take Profit (TP) levels. (Currently uses the first TP level if multiple are provided).
*   Stores order details, execution status, and MT5 order IDs in a local SQLite database (`trading_app.db`).
*   GUI for:
    *   Configuring Telegram API token, Chat IDs, and MT5 credentials.
    *   Starting and stopping the bot.
    *   Viewing real-time application logs.
    *   Displaying a table of all processed orders and their current status.
*   Handles duplicate signals by checking the Telegram message ID to prevent re-processing.

## Prerequisites

*   Python 3.x (Python 3.8 or newer recommended).
*   MetaTrader 5 Terminal installed and running on your system.
*   An active MetaTrader 5 trading account (demo or live).
*   A Telegram Bot Token obtained from BotFather.
*   The Chat ID(s) of the Telegram channels or groups you want the bot to monitor.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/telegram-metatrader-app.git # Replace with actual URL
    cd telegram_metatrader_app
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    ```
    Activate the environment:
    *   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        venv\Scripts\activate
        ```

3.  **Install dependencies:**
    Ensure your virtual environment is activated, then run:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure the application:**
    *   Make a copy of `config.ini.template` and rename it to `config.ini`.
    *   Edit `config.ini` with your specific details:
        *   `API_TOKEN` (under `[TELEGRAM]`): Your Telegram Bot Token.
        *   `CHAT_IDS` (under `[TELEGRAM]`): A comma-separated list of Telegram Chat IDs (e.g., `-1001234567890, -1009876543210`). The bot must be a member of these chats.
        *   `LOGIN` (under `[METATRADER5]`): Your MT5 account login ID.
        *   `PASSWORD` (under `[METATRADER5]`): Your MT5 account password.
        *   `SERVER` (under `[METATRADER5]`): Your MT5 account server name.
    *   **Alternatively**, you can leave `config.ini` with placeholder values (or use the template directly if `config.ini` is missing) and enter these details into the GUI when you first run the application. The GUI will then save them to `config.ini`.

## Running the Application

Ensure your virtual environment is activated and you are in the `telegram_metatrader_app` directory.
```bash
python main.py
```
This will launch the GUI.

## How it Works

1.  **Launch:** The application starts, presenting the GUI.
2.  **Configuration:**
    *   On startup, the application attempts to load credentials from `config.ini`. These are displayed in the GUI's configuration fields.
    *   The user can modify these settings in the GUI and click "Save Configuration" to update `config.ini`.
3.  **Start Bot:**
    *   The user clicks the "Start Bot" button in the GUI.
    *   The application uses the configured credentials to:
        *   Initialize the connection to the MetaTrader 5 terminal.
        *   Start the Telegram bot, which begins listening for new messages in the specified Chat IDs.
4.  **Signal Processing:**
    *   When a new message arrives in a monitored Telegram chat:
        1.  The message text is parsed by the bot.
        2.  If it matches the expected signal format, key information (instrument, action, entry, TPs, SL, Telegram message ID) is extracted.
        3.  The system checks if the `telegram_message_id` has already been processed to prevent duplicate trades.
        4.  The parsed signal is saved to the local SQLite database (`trading_app.db`) with an initial status of "pending".
        5.  An attempt is made to execute a market order on the MT5 terminal using the parsed details (e.g., instrument, action, volume, SL, first TP).
        6.  The corresponding order record in the database is updated:
            *   To "executed" along with the MT5 order ID and execution price if successful.
            *   To "failed" with an error message if the trade execution fails.
5.  **Monitoring:**
    *   All significant actions, errors, and received messages are logged. These logs are displayed in real-time in the "Logs" section of the GUI.
    *   The "Orders" table in the GUI displays a history of all signals processed, including their current status and MT5 details.

## Signal Format Example

The bot expects signals in a specific format. Here's an example:

```
🌟GOLD Sell - 3358-3360

blah blah some other text
🔛TP =3356
whatever here
🔛TP =3354
🔛TP =3348

another line
❎STOP LOSS 3365
```

**Key elements parsed:**
*   **Signal Line:** Starts with `🌟`, followed by the instrument (e.g., `GOLD`), action (`Sell` or `Buy`), and entry price range (e.g., `3358-3360`).
*   **Take Profit (TP):** Lines starting with `🔛TP` or `🔛 TP` (with optional `=`), followed by the TP price. Multiple TP lines are supported, but currently, only the first valid TP is used for order placement.
*   **Stop Loss (SL):** A line starting with `❎STOP LOSS` or `❎SL`, followed by the SL price.

The emojis (🌟, 🔛, ❎) are part of the expected pattern and help identify the relevant lines. Other text in the message is generally ignored.

## Troubleshooting / Notes

*   **MetaTrader 5 Terminal:**
    *   Must be running on the same machine where the Python application is executed.
    *   You must be logged into your trading account within the MT5 terminal.
    *   "Algo Trading" (or "AutoTrading") must be enabled in the MT5 terminal. This button is usually found in the toolbar.
*   **Telegram Bot Token:**
    *   Obtain this token by creating a new bot or revoking an existing token with @BotFather on Telegram.
*   **Telegram Chat IDs:**
    *   **For Groups:** Add your bot to the group. You can get the group's Chat ID by using a raw bot API call or forwarding a message from the group to a bot like `@GetIDsBot`. Group IDs are typically negative numbers (e.g., `-1001234567890`).
    *   **For Channels:** Your bot usually needs to be an administrator in the channel to read messages. If the channel is public, you might be able_to use its username (e.g. `@channel_username`), but numeric IDs are more reliable. Private channel IDs are also negative numbers.
    *   The application's Telegram bot must have permission to read messages in the specified chats.
*   **Dependencies:** Ensure all Python packages from `requirements.txt` are installed in your active Python environment.
*   **Configuration File:** Double-check `config.ini` for correct tokens, IDs, and MT5 credentials. Typos are a common source of issues.

## (Optional) Future Enhancements

*   Support for pending orders (Buy Limit, Sell Limit, etc.) based on entry range.
*   More sophisticated Take Profit strategies (e.g., multiple partial TPs, trailing TP).
*   Allowing configuration of trade volume from the signal or GUI.
*   Packaging the application into a standalone executable (e.g., using PyInstaller).
*   More robust error handling and recovery mechanisms.
*   Web-based interface as an alternative to PyQt5 GUI.

## (Optional) License

This project is licensed under the MIT License.
```
